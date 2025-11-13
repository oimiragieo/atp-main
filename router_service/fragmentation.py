"""Frame fragmentation & reassembly (POC: poc_fragment_reassembly).

Assumptions (PoC scope):
  * Only payload.content with {'text': <str>} is fragmented.
  * Flags include 'FRAG'; last fragment also gets 'LAST'.
  * msg_seq constant across fragments.
  * Duplicate fragments ignored (except LAST reprocessing for completion attempts).
  * Missing fragment detection after repeated completion attempts raises ValueError.
"""

from __future__ import annotations

import hashlib
import time
from typing import TypedDict

from metrics.registry import REGISTRY

from .frame import Frame
from .reassembly_store import ExternalReassemblyStore
from .tracing import get_tracer

MAX_FRAGMENT_SIZE = 256  # bytes of text payload per fragment in this PoC


def _compute_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class FragmentationPolicy:
    """Policy-driven fragmentation configuration."""

    def __init__(
        self,
        base_max_size: int = MAX_FRAGMENT_SIZE,
        qos_multipliers: dict[str, float] | None = None,
        binary_max_size: int = 1024,
        enable_merkle: bool = False,
    ):
        self.base_max_size = base_max_size
        self.qos_multipliers = qos_multipliers or {"gold": 2.0, "silver": 1.5, "bronze": 1.0}
        self.binary_max_size = binary_max_size
        self.enable_merkle = enable_merkle

    def get_max_fragment_size(self, frame: Frame) -> int:
        """Determine max fragment size based on frame properties."""
        multiplier = self.qos_multipliers.get(frame.qos, 1.0)

        # Check if payload is binary
        if self._is_binary_payload(frame):
            return int(self.binary_max_size * multiplier)

        return int(self.base_max_size * multiplier)

    def _is_binary_payload(self, frame: Frame) -> bool:
        """Check if frame contains binary payload."""
        if not isinstance(frame.payload.content, dict):
            return True  # Non-dict content is treated as binary
        return "text" not in frame.payload.content


class MerkleTree:
    """Simple Merkle tree for cumulative checksums."""

    def __init__(self):
        self.leaves: list[str] = []
        self.tree: list[str] = []

    def add_leaf(self, data: str):
        """Add a leaf node (fragment data)."""
        leaf_hash = hashlib.sha256(data.encode("utf-8")).hexdigest()
        self.leaves.append(leaf_hash)
        self._rebuild_tree()

    def get_root(self) -> str | None:
        """Get the Merkle root hash."""
        if not self.tree:
            return None
        return self.tree[0]

    def _rebuild_tree(self):
        """Rebuild the Merkle tree."""
        if not self.leaves:
            self.tree = []
            return

        # Start with leaves
        current_level = self.leaves.copy()

        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
                next_level.append(combined)
            current_level = next_level

        self.tree = current_level


def _compute_merkle_checksum(text: str, fragment_size: int) -> str:
    """Compute Merkle tree root for fragmented text."""
    if not text:
        return hashlib.sha256(b"").hexdigest()

    merkle = MerkleTree()
    for i in range(0, len(text), fragment_size):
        chunk = text[i : i + fragment_size]
        merkle.add_leaf(chunk)

    root = merkle.get_root()
    return root or ""  # Return full 64-character hash for merkle


class _ReassemblyState(TypedDict, total=False):
    parts: dict[int, str]
    last_seq: int | None
    attempts: int
    frag_sizes: dict[int, int]
    prev_missing: list[int]
    is_binary: bool
    merkle_root: str | None
    total_size: int


class Reassembler:
    def __init__(self, store: ExternalReassemblyStore | None = None, gap_ttl_s: float = 0.5) -> None:
        self._state: dict[tuple[str, str, int], _ReassemblyState] = {}
        self._store = store
        self._gap_ttl_s = float(gap_ttl_s)
        self._gap_since: dict[tuple[str, str, int], float] = {}
        self._last_access: dict[tuple[str, str, int], float] = {}
        self._ctr_late = REGISTRY.counter("late_fragments_dropped")

    def push(self, frame: Frame) -> Frame | None:
        key = (frame.session_id, frame.stream_id, frame.msg_seq)
        self._last_access[key] = time.time()
        # If external store configured, delegate persistence and completion check
        if self._store is not None:
            is_last = "LAST" in frame.flags
            frag_data = ""
            is_binary = False

            if isinstance(frame.payload.content, dict) and "text" in frame.payload.content:
                frag_data = frame.payload.content["text"]
            elif isinstance(frame.payload.content, (bytes, bytearray)):
                frag_data = frame.payload.content.hex()
                is_binary = True
            else:
                # Handle other payload types as binary
                frag_data = str(frame.payload.content)
                is_binary = True

            complete, full = self._store.push_part(
                frame.session_id, frame.stream_id, frame.msg_seq, frame.frag_seq, frag_data, is_last, is_binary
            )
            if not complete:
                return None
            # Completed via store: build final
            tracer = get_tracer()
            span_cm = tracer.start_as_current_span("fragment.reassemble") if tracer else None
            if span_cm:
                span = span_cm.__enter__()
                try:
                    span.set_attribute("frag.parts", int((len(full) // max(1, len(frag_data))) if frag_data else 0))
                    span.set_attribute("frag.session", frame.session_id)
                    span.set_attribute("frag.stream", frame.stream_id)
                    span.set_attribute("frag.msg_seq", int(frame.msg_seq))
                    span.set_attribute("frag.bytes", int(len(full or "")))
                except Exception:  # noqa: S110 - best-effort span attribute set
                    pass
            final_payload = frame.payload.model_copy(deep=True)
            if is_binary:
                final_payload.content = bytes.fromhex(full or "")
            elif isinstance(final_payload.content, dict):
                final_payload.content["text"] = full or ""
            final_payload.checksum = _compute_checksum(full or "")
            final = Frame(
                v=frame.v,
                session_id=frame.session_id,
                stream_id=frame.stream_id,
                msg_seq=frame.msg_seq,
                frag_seq=0,
                flags=[f for f in frame.flags if f not in ("FRAG", "LAST")] + ["REASSEMBLED"],
                qos=frame.qos,
                ttl=frame.ttl,
                window=frame.window,
                meta=frame.meta,
                payload=final_payload,
                sig=None,
            )
            if span_cm:
                span_cm.__exit__(None, None, None)
            return final
        # Fallback: in-process reassembly state
        st = self._state.setdefault(
            key,
            {
                "parts": {},
                "last_seq": None,
                "attempts": 0,
                "frag_sizes": {},
                "is_binary": False,
                "merkle_root": None,
                "total_size": 0,
            },
        )
        # Gap timer: determine expected next contiguous index
        expected_next = 0
        while expected_next in st["parts"]:
            expected_next += 1
        now = time.time()
        if frame.frag_seq > expected_next:
            # gap observed
            self._gap_since.setdefault(key, now)
        else:
            # if gap is being closed, clear timer
            if key in self._gap_since and frame.frag_seq == expected_next:
                # if arrived too late, drop
                if (now - self._gap_since.get(key, now)) > self._gap_ttl_s:
                    self._ctr_late.inc(1)
                    return None
                # else will proceed and clear below
                self._gap_since.pop(key, None)
        is_last = "LAST" in frame.flags
        if frame.frag_seq in st["parts"] and not (is_last and st["last_seq"] == frame.frag_seq):
            return None
        frag_data = ""
        is_binary = False
        if isinstance(frame.payload.content, dict) and "text" in frame.payload.content:
            frag_data = frame.payload.content["text"]
        elif isinstance(frame.payload.content, (bytes, bytearray)):
            frag_data = frame.payload.content.hex()
            is_binary = True
            st["is_binary"] = True
        else:
            # Handle other payload types as binary
            frag_data = str(frame.payload.content)
            is_binary = True
            st["is_binary"] = True

        st["parts"][frame.frag_seq] = frag_data
        sizes = st["frag_sizes"]  # ensure exists from initializer
        prev_size = sizes.get(frame.frag_seq)
        cur_size = len(frag_data)
        if prev_size is not None and cur_size < prev_size:
            raise ValueError("fragment truncated")
        sizes[frame.frag_seq] = cur_size
        st["total_size"] += cur_size

        # Handle merkle checksum if present
        if frame.payload.checksum and len(frame.payload.checksum) > 16:
            # This is a merkle root (full SHA256 hash)
            if st["merkle_root"] is None:
                st["merkle_root"] = frame.payload.checksum
            elif st["merkle_root"] != frame.payload.checksum:
                raise ValueError("merkle root mismatch")
        elif frame.payload.checksum and st.get("merkle_root") is None:
            # Regular checksum validation (only if not using merkle)
            if frame.payload.checksum != _compute_checksum(frag_data):
                raise ValueError("checksum mismatch fragment")

        if is_last:
            st["last_seq"] = frame.frag_seq
        if st["last_seq"] is None:
            return None
        last = st["last_seq"]
        parts = st["parts"]
        missing = [i for i in range(last + 1) if i not in parts]
        if missing:
            previously_missing = st.get("prev_missing")
            if previously_missing == missing:
                st["attempts"] += 1
            st["prev_missing"] = list(missing)
            if st["attempts"] >= 2:
                raise ValueError(f"missing fragments: {missing}")
            return None
        sizes_map = st["frag_sizes"]
        expected = 0
        for i in range(last):
            sz = sizes_map.get(i)
            if sz is None:
                continue
            expected = max(expected, sz)
        if expected > 0:
            for i in range(last):
                sz = sizes_map.get(i)
                if sz is not None and sz < expected:
                    raise ValueError("fragment truncated (size variance)")
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("fragment.reassemble") if tracer else None
        if span_cm:
            span = span_cm.__enter__()
            try:
                span.set_attribute("frag.parts", int(last + 1))
                span.set_attribute("frag.session", frame.session_id)
                span.set_attribute("frag.stream", frame.stream_id)
                span.set_attribute("frag.msg_seq", int(frame.msg_seq))
            except Exception:  # noqa: S110 - best-effort
                pass
        full_data = "".join(parts[i] for i in range(last + 1))
        if span_cm:
            try:
                span.set_attribute("frag.bytes", int(len(full_data)))
            except Exception:  # noqa: S110 - best-effort span attribute set
                pass
        final_payload = frame.payload.model_copy(deep=True)
        if st["is_binary"]:
            # Binary payload reassembly
            final_payload.content = bytes.fromhex(full_data)
            final_payload.checksum = _compute_checksum(full_data)
        elif isinstance(final_payload.content, dict):
            # Text payload reassembly
            final_payload.content["text"] = full_data
            # Use merkle root if available, otherwise compute regular checksum
            if st["merkle_root"]:
                final_payload.checksum = st["merkle_root"]
            else:
                final_payload.checksum = _compute_checksum(full_data)
        final = Frame(
            v=frame.v,
            session_id=frame.session_id,
            stream_id=frame.stream_id,
            msg_seq=frame.msg_seq,
            frag_seq=0,
            flags=[f for f in frame.flags if f not in ("FRAG", "LAST")] + ["REASSEMBLED"],
            qos=frame.qos,
            ttl=frame.ttl,
            window=frame.window,
            meta=frame.meta,
            payload=final_payload,
            sig=None,
        )
        del self._state[key]
        if span_cm:
            span_cm.__exit__(None, None, None)
        return final

    def gc(self, ttl_s: float = 300.0) -> int:
        """Remove reassembly states older than ttl_s seconds. Returns number removed."""
        now = time.time()
        to_remove = [k for k, t in self._last_access.items() if now - t > ttl_s]
        for k in to_remove:
            self._state.pop(k, None)
            self._gap_since.pop(k, None)
            self._last_access.pop(k, None)
        return len(to_remove)


def fragment_frame(
    frame: Frame, max_fragment_size: int = MAX_FRAGMENT_SIZE, policy: FragmentationPolicy | None = None
) -> list[Frame]:
    if policy is None:
        policy = FragmentationPolicy(base_max_size=max_fragment_size)

    # Determine max fragment size using policy
    max_size = policy.get_max_fragment_size(frame)

    # Handle different payload types
    if isinstance(frame.payload.content, dict) and "text" in frame.payload.content:
        # Text payload
        text = frame.payload.content["text"]
        return _fragment_text_payload(frame, text, max_size, policy)
    elif isinstance(frame.payload.content, (bytes, bytearray)):
        # Binary payload
        return _fragment_binary_payload(frame, frame.payload.content, max_size, policy)
    else:
        # Other payload types treated as binary
        binary_data = str(frame.payload.content).encode("utf-8")
        return _fragment_binary_payload(frame, binary_data, max_size, policy)


def _fragment_text_payload(frame: Frame, text: str, max_size: int, policy: FragmentationPolicy) -> list[Frame]:
    """Fragment a text payload."""
    frags: list[Frame] = []
    seq = 0

    # Compute merkle checksum if enabled
    if policy.enable_merkle:
        merkle_checksum = _compute_merkle_checksum(text, max_size)
    else:
        merkle_checksum = None

    for start in range(0, len(text), max_size):
        chunk = text[start : start + max_size]
        f = frame.model_copy(deep=True)
        f.frag_seq = seq
        f.payload.content["text"] = chunk
        f.flags = list(set(f.flags + ["FRAG"]))

        # Use merkle checksum if enabled, otherwise per-fragment checksum
        if policy.enable_merkle and merkle_checksum:
            f.payload.checksum = merkle_checksum
        else:
            f.payload.checksum = _compute_checksum(chunk)

        frags.append(f)
        seq += 1

    # mark last
    if frags:
        if "LAST" not in frags[-1].flags:
            frags[-1].flags.append("LAST")
    else:
        # empty payload -> single empty fragment
        f = frame.model_copy(deep=True)
        f.frag_seq = 0
        f.payload.content["text"] = ""
        f.flags = list(set(f.flags + ["FRAG", "LAST"]))
        f.payload.checksum = _compute_checksum("")
        frags.append(f)

    try:
        REGISTRY.histogram("fragment_count_per_message", [1, 2, 4, 8, 16, 32]).observe(float(len(frags)))
    except Exception:  # noqa: S110 - metrics observation best-effort
        pass
    return frags


def _fragment_binary_payload(
    frame: Frame, binary_data: bytes, max_size: int, policy: FragmentationPolicy
) -> list[Frame]:
    """Fragment a binary payload."""
    frags: list[Frame] = []
    seq = 0

    # Compute merkle checksum if enabled
    if policy.enable_merkle:
        merkle_checksum = _compute_merkle_checksum(binary_data.hex(), max_size)
    else:
        merkle_checksum = None

    for start in range(0, len(binary_data), max_size):
        chunk = binary_data[start : start + max_size]
        f = frame.model_copy(deep=True)
        f.frag_seq = seq
        f.payload.content = chunk  # Store as bytes
        f.flags = list(set(f.flags + ["FRAG"]))

        # Use merkle checksum if enabled, otherwise per-fragment checksum
        if policy.enable_merkle and merkle_checksum:
            f.payload.checksum = merkle_checksum
        else:
            f.payload.checksum = _compute_checksum(chunk.hex())

        frags.append(f)
        seq += 1

    # mark last
    if frags:
        if "LAST" not in frags[-1].flags:
            frags[-1].flags.append("LAST")
    else:
        # empty payload -> single empty fragment
        f = frame.model_copy(deep=True)
        f.frag_seq = 0
        f.payload.content = b""
        f.flags = list(set(f.flags + ["FRAG", "LAST"]))
        f.payload.checksum = _compute_checksum("")
        frags.append(f)

    try:
        REGISTRY.histogram("fragment_count_per_message", [1, 2, 4, 8, 16, 32]).observe(float(len(frags)))
    except Exception:  # noqa: S110 - metrics observation best-effort
        pass
    return frags


def to_more_flag_semantics(fragments: list[Frame]) -> list[Frame]:
    """Return copies of fragments using MORE-flag semantics.

    Semantics:
    - All non-final fragments include 'MORE'.
    - Final fragment MUST NOT include 'MORE'.
    - Existing 'LAST' flag is removed for final fragment (non-final fragments have no 'LAST').
    - Keeps 'FRAG' for continuity with current PoC while enabling conformance tests that
      expect 'MORE' semantics.
    """
    out: list[Frame] = []
    for i, f in enumerate(fragments):
        nf = f.model_copy(deep=True)
        flags = set(nf.flags)
        if i < len(fragments) - 1:
            flags.discard("LAST")
            flags.add("MORE")
        else:
            flags.discard("LAST")
            flags.discard("MORE")
        # keep FRAG marker
        flags.add("FRAG")
        nf.flags = sorted(flags)
        out.append(nf)
    return out
