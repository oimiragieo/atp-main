import binascii
import hashlib
import hmac
import json
from io import BytesIO
from typing import Any


def _encode_uint(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([major << 5 | n])
    elif n < 256:
        return bytes([major << 5 | 24, n])
    elif n < 65536:
        return bytes([major << 5 | 25]) + n.to_bytes(2, "big")
    elif n < 4294967296:
        return bytes([major << 5 | 26]) + n.to_bytes(4, "big")
    else:
        return bytes([major << 5 | 27]) + n.to_bytes(8, "big")


def _encode_cbor(obj: Any) -> bytes:
    # Minimal deterministic CBOR encoder for ints/str/bool/None/list/dict[str,Any]
    if obj is None:
        return b"\xf6"  # null
    if obj is True:
        return b"\xf5"
    if obj is False:
        return b"\xf4"
    if isinstance(obj, int):
        if obj >= 0:
            return _encode_uint(0, obj)
        else:
            # Negative: value is -1 - n encoded in major type 1
            return _encode_uint(1, -1 - obj)
    if isinstance(obj, float):
        # Encode float as IEEE 754 double precision
        import struct
        return b"\xfb" + struct.pack(">d", obj)
    if isinstance(obj, str):
        b = obj.encode("utf-8")
        return _encode_uint(3, len(b)) + b
    if isinstance(obj, bytes):
        return _encode_uint(2, len(obj)) + obj
    if isinstance(obj, list):
        enc_items = b"".join(_encode_cbor(x) for x in obj)
        return _encode_uint(4, len(obj)) + enc_items
    if isinstance(obj, dict):
        # Canonical: sort by key as UTF-8 bytes
        items = []
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError("Only string keys supported in this POC")
            items.append((k, v))
        items.sort(key=lambda kv: kv[0].encode("utf-8"))
        enc = b"".join(_encode_cbor(k) + _encode_cbor(v) for k, v in items)
        return _encode_uint(5, len(items)) + enc
    raise TypeError(f"Unsupported type for CBOR POC: {type(obj)!r}")


def _encode_cbor_zero_copy(obj: Any, buffer: BytesIO) -> None:
    """Zero-copy CBOR encoder that writes directly to a buffer."""
    if obj is None:
        buffer.write(b"\xf6")  # null
    elif obj is True:
        buffer.write(b"\xf5")
    elif obj is False:
        buffer.write(b"\xf4")
    elif isinstance(obj, int):
        if obj >= 0:
            buffer.write(_encode_uint(0, obj))
        else:
            # Negative: value is -1 - n encoded in major type 1
            buffer.write(_encode_uint(1, -1 - obj))
    elif isinstance(obj, float):
        # Encode float as IEEE 754 double precision
        import struct
        buffer.write(b"\xfb")
        buffer.write(struct.pack(">d", obj))
    elif isinstance(obj, str):
        b = obj.encode("utf-8")
        buffer.write(_encode_uint(3, len(b)))
        buffer.write(b)
    elif isinstance(obj, bytes):
        buffer.write(_encode_uint(2, len(obj)))
        buffer.write(obj)
    elif isinstance(obj, list):
        buffer.write(_encode_uint(4, len(obj)))
        for x in obj:
            _encode_cbor_zero_copy(x, buffer)
    elif isinstance(obj, dict):
        # Canonical: sort by key as UTF-8 bytes
        items = []
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError("Only string keys supported in this POC")
            items.append((k, v))
        items.sort(key=lambda kv: kv[0].encode("utf-8"))

        buffer.write(_encode_uint(5, len(items)))
        for k, v in items:
            _encode_cbor_zero_copy(k, buffer)
            _encode_cbor_zero_copy(v, buffer)
    else:
        raise TypeError(f"Unsupported type for zero-copy CBOR: {type(obj)!r}")


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def encode_frame(frame: dict[str, Any], key: bytes) -> bytes:
    """Encode a frame into a simple envelope with CBOR body, CRC32, and HMAC-SHA256.

    Format: b'ATPC' | hlen(2) | header_json | blen(4) | body | crc32(4) | hmac(32)
    HMAC is computed over: header_json || body || crc32
    """
    header = {"alg": "HS256", "fmt": "cbor", "chk": "crc32"}
    h = canonical_json(header)
    body = _encode_cbor(frame)
    crc = binascii.crc32(body) & 0xFFFFFFFF
    crc_bytes = crc.to_bytes(4, "big")
    mac = hmac.new(key, h + body + crc_bytes, hashlib.sha256).digest()
    out = [b"ATPC", len(h).to_bytes(2, "big"), h, len(body).to_bytes(4, "big"), body, crc_bytes, mac]
    return b"".join(out)


def encode_frame_zero_copy(frame: dict[str, Any], key: bytes, buffer: BytesIO = None) -> bytes:
    """Zero-copy version of encode_frame that minimizes memory allocations.

    Uses a pre-allocated buffer to avoid intermediate byte object creation.
    """
    if buffer is None:
        buffer = BytesIO()

    header = {"alg": "HS256", "fmt": "cbor", "chk": "crc32"}
    h = canonical_json(header)

    # Write header to buffer
    buffer.write(b"ATPC")
    buffer.write(len(h).to_bytes(2, "big"))
    buffer.write(h)

    # Remember position for body length
    body_start_pos = buffer.tell()
    buffer.write(b"\x00\x00\x00\x00")  # Placeholder for body length

    # Encode body directly to buffer
    body_start = buffer.tell()
    _encode_cbor_zero_copy(frame, buffer)
    body_end = buffer.tell()
    body_length = body_end - body_start

    # Go back and write actual body length
    buffer.seek(body_start_pos)
    buffer.write(body_length.to_bytes(4, "big"))
    buffer.seek(body_end)

    # Get the body bytes for CRC and HMAC computation
    buffer.seek(body_start)
    body = buffer.read(body_length)
    buffer.seek(body_end)

    # Compute CRC and HMAC
    crc = binascii.crc32(body) & 0xFFFFFFFF
    crc_bytes = crc.to_bytes(4, "big")
    mac = hmac.new(key, h + body + crc_bytes, hashlib.sha256).digest()

    # Write trailer
    buffer.write(crc_bytes)
    buffer.write(mac)

    return buffer.getvalue()


def decode_frame(payload: bytes, key: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decode and verify envelope; returns (header, frame) dicts.
    Raises ValueError on checksum/signature mismatch or malformed input.
    """
    if not payload.startswith(b"ATPC"):
        raise ValueError("Invalid magic")
    i = 4
    if i + 2 > len(payload):
        raise ValueError("Truncated header length")
    hlen = int.from_bytes(payload[i : i + 2], "big")
    i += 2
    if i + hlen > len(payload):
        raise ValueError("Truncated header")
    h = payload[i : i + hlen]
    i += hlen
    try:
        header = json.loads(h.decode("utf-8"))
    except Exception as e:
        raise ValueError("Invalid header JSON") from e
    if i + 4 > len(payload):
        raise ValueError("Truncated body length")
    blen = int.from_bytes(payload[i : i + 4], "big")
    i += 4
    if i + blen + 4 + 32 > len(payload):
        raise ValueError("Truncated body or trailer")
    body = payload[i : i + blen]
    i += blen
    crc_bytes = payload[i : i + 4]
    i += 4
    mac = payload[i : i + 32]
    # Verify
    exp_crc = binascii.crc32(body) & 0xFFFFFFFF
    got_crc = int.from_bytes(crc_bytes, "big")
    if got_crc != exp_crc:
        raise ValueError("Checksum mismatch")
    exp_mac = hmac.new(key, h + body + crc_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(exp_mac, mac):
        raise ValueError("Signature mismatch")
    # Decode CBOR body to Python
    frame = _decode_cbor(body)
    return header, frame


def _decode_cbor(data: bytes) -> Any:
    # Minimal decoder matching the encoder above
    def read(n: int) -> bytes:
        nonlocal i
        if i + n > len(data):
            raise ValueError("Truncated CBOR")
        b = data[i : i + n]
        i += n
        return b

    def read_uint(add: int) -> int:
        if add < 24:
            return add
        if add == 24:
            return int.from_bytes(read(1), "big")
        if add == 25:
            return int.from_bytes(read(2), "big")
        if add == 26:
            return int.from_bytes(read(4), "big")
        if add == 27:
            return int.from_bytes(read(8), "big")
        raise ValueError("Indefinite lengths not supported in POC")

    def decode_one() -> Any:
        nonlocal i
        ib = read(1)[0]
        major = ib >> 5
        add = ib & 0x1F
        if major == 0:  # unsigned
            return read_uint(add)
        if major == 1:  # negative
            n = read_uint(add)
            return -1 - n
        if major == 2:  # bytes
            ln = read_uint(add)
            return read(ln)
        if major == 3:  # text
            ln = read_uint(add)
            return read(ln).decode("utf-8")
        if major == 4:  # array
            ln = read_uint(add)
            return [decode_one() for _ in range(ln)]
        if major == 5:  # map
            ln = read_uint(add)
            d: dict[str, Any] = {}
            for _ in range(ln):
                k = decode_one()
                v = decode_one()
                d[k] = v
            return d
        if major == 7:  # simple
            if add == 20:
                return False
            if add == 21:
                return True
            if add == 22:
                return None
            raise ValueError("Unsupported simple value")
        raise ValueError("Unsupported major type")

    i = 0
    result = decode_one()
    if i != len(data):
        raise ValueError("Trailing bytes in CBOR POC")
    return result
