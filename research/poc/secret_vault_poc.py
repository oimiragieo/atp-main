import json

from tools.kms_poc import KMS


class SecretVault:
    def __init__(self, path: str, kms: KMS):
        self.path = path
        self.kms = kms
        self._store: dict[str, dict[str, str]] = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self._store = json.load(f)
        except Exception:
            self._store = {}

    def put(self, name: str, plaintext: bytes, aad: bytes = b"") -> None:
        dk, wrapped = self.kms.generate_data_key()
        blob = self.kms.encrypt(wrapped, plaintext, aad=aad)
        self._store[name] = {"wrapped": wrapped.hex(), "blob": json.dumps(blob)}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._store, f)

    def get(self, name: str, aad: bytes = b"") -> bytes:
        rec = self._store.get(name)
        if not rec:
            raise KeyError(name)
        wrapped = bytes.fromhex(rec["wrapped"])
        blob = json.loads(rec["blob"])
        return self.kms.decrypt(wrapped, blob, aad=aad)
