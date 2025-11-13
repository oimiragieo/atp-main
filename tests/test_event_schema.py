import json
import os

schema_path = os.path.join(os.path.dirname(__file__), "..", "tools", "event_schema.json")


def load_schema():
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


def validate(event: dict, schema: dict) -> bool:
    # Minimal validator for required fields and enums (no external libs)
    for req in schema.get("required", []):
        if req not in event:
            return False
    props = schema.get("properties", {})
    for k, spec in props.items():
        if k in event:
            if spec.get("type") == "string" and not isinstance(event[k], str):
                return False
            if "enum" in spec and event[k] not in spec["enum"]:
                return False
    return True


def main():
    schema = load_schema()
    ok_event = {
        "ts": "2025-08-30T12:00:00Z",
        "tenant": "acme",
        "actor": "user:u1",
        "action": "route.dispatch",
        "resource": "stream:st1",
        "result": "allow",
        "details": {"qos": "gold"},
    }
    bad_event = dict(ok_event)
    bad_event["result"] = "unknown"
    assert validate(ok_event, schema)
    assert not validate(bad_event, schema)
    print("OK: event schema POC passed")


if __name__ == "__main__":
    main()
