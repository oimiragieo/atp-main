from typing import Any


class Store:
    def __init__(self):
        self.data: dict[str, dict[str, Any]] = {}  # key -> object
        self.index: dict[str, list[str]] = {}  # subject_id -> [keys]

    def put(self, key: str, obj: dict[str, Any]) -> None:
        self.data[key] = obj
        sid = obj.get("subject_id")
        if sid:
            self.index.setdefault(sid, []).append(key)

    def export_subject(self, subject_id: str) -> list[dict[str, Any]]:
        keys = self.index.get(subject_id, [])
        return [self.data[k] for k in keys if k in self.data]

    def delete_subject(self, subject_id: str) -> int:
        keys = list(self.index.get(subject_id, []))
        deleted = 0
        for k in keys:
            if k in self.data:
                del self.data[k]
                deleted += 1
        self.index.pop(subject_id, None)
        return deleted
