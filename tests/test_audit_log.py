import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
import audit_log as audit_log  # renamed for lint N812 compliance


def test_tamper_detection_comprehensive():
    """Comprehensive tamper detection tests for audit logs."""
    secret = b"test-secret-comprehensive"

    with tempfile.TemporaryDirectory() as temp_dir:
        log_path = os.path.join(temp_dir, "audit.log")

        # Create a valid audit log with multiple events
        events = [
            {"action": "user_login", "user": "alice", "timestamp": "2024-01-01T10:00:00Z"},
            {"action": "data_access", "user": "alice", "resource": "sensitive_data", "timestamp": "2024-01-01T10:05:00Z"},
            {"action": "user_logout", "user": "alice", "timestamp": "2024-01-01T10:30:00Z"},
            {"action": "admin_action", "user": "admin", "operation": "config_change", "timestamp": "2024-01-01T11:00:00Z"}
        ]

        # Append events to create valid log
        prev_hash = None
        for event in events:
            prev_hash = audit_log.append_event(log_path, event, secret, prev_hash)

        # Verify the original log is valid
        assert audit_log.verify_log(log_path, secret), "Original log should be valid"

        # Test 1: Tamper with event data
        print("Testing event data tampering...")
        with open(log_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            # Tamper with second event
            tampered_record = json.loads(lines[1])
            tampered_record["event"]["user"] = "bob"  # Change alice to bob
            lines[1] = json.dumps(tampered_record) + "\n"
            f.seek(0)
            f.writelines(lines)
            f.truncate()

        assert not audit_log.verify_log(log_path, secret), "Tampered event data should be detected"

        # Reset log for next test
        prev_hash = None
        with open(log_path, "w", encoding="utf-8") as f:
            f.truncate(0)
        for event in events:
            prev_hash = audit_log.append_event(log_path, event, secret, prev_hash)

        # Test 2: Tamper with hash chain
        print("Testing hash chain tampering...")
        with open(log_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            # Tamper with hash in third record
            tampered_record = json.loads(lines[2])
            tampered_record["hash"] = "tampered-hash-12345"
            lines[2] = json.dumps(tampered_record) + "\n"
            f.seek(0)
            f.writelines(lines)
            f.truncate()

        assert not audit_log.verify_log(log_path, secret), "Tampered hash chain should be detected"

        # Reset log for next test
        prev_hash = None
        with open(log_path, "w", encoding="utf-8") as f:
            f.truncate(0)
        for event in events:
            prev_hash = audit_log.append_event(log_path, event, secret, prev_hash)

        # Test 3: Delete an event (truncate log)
        print("Testing event deletion...")
        with open(log_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            # Remove the second event
            del lines[1]
            f.seek(0)
            f.writelines(lines)
            f.truncate()

        assert not audit_log.verify_log(log_path, secret), "Event deletion should be detected"

        # Reset log for next test
        prev_hash = None
        with open(log_path, "w", encoding="utf-8") as f:
            f.truncate(0)
        for event in events:
            prev_hash = audit_log.append_event(log_path, event, secret, prev_hash)

        # Test 4: Insert fake event
        print("Testing event insertion...")
        with open(log_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            # Insert a fake event between first and second
            first_record = json.loads(lines[0])
            fake_event = {
                "event": {"action": "fake_action", "user": "hacker", "timestamp": "2024-01-01T10:02:00Z"},
                "hash": "fake-hash",
                "prev": first_record.get("hash"),  # Use the hash from the first record
                "hmac": "fake-hmac"
            }
            lines.insert(1, json.dumps(fake_event) + "\n")
            f.seek(0)
            f.writelines(lines)
            f.truncate()

        assert not audit_log.verify_log(log_path, secret), "Event insertion should be detected"

        # Reset log for next test
        prev_hash = None
        with open(log_path, "w", encoding="utf-8") as f:
            f.truncate(0)
        for event in events:
            prev_hash = audit_log.append_event(log_path, event, secret, prev_hash)

        # Test 5: Tamper with HMAC (if present)
        print("Testing HMAC tampering...")
        # This test assumes HMAC is part of the record structure
        # If HMAC is not present, this test will be skipped
        with open(log_path, "r+", encoding="utf-8") as f:
            lines = f.readlines()
            tampered_record = json.loads(lines[0])
            if "hmac" in tampered_record:
                tampered_record["hmac"] = "tampered-hmac-12345"
                lines[0] = json.dumps(tampered_record) + "\n"
                f.seek(0)
                f.writelines(lines)
                f.truncate()
                assert not audit_log.verify_log(log_path, secret), "HMAC tampering should be detected"
            else:
                print("Skipping HMAC test - no HMAC field in records")

        print("✅ All tamper detection tests passed!")


def main():
    secret = b"test-secret"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "audit.log")
        h = None
        for i in range(3):
            h = audit_log.append_event(p, {"idx": i, "msg": f"event-{i}"}, secret, h)
        assert audit_log.verify_log(p, secret)
        # Tamper with a byte
        with open(p, "r+", encoding="utf-8") as f:
            data = f.read()
            data = data.replace("event-1", "event-X")
            f.seek(0)
            f.write(data)
            f.truncate()
        assert not audit_log.verify_log(p, secret)
    print("OK: audit log chaining passed")

    # Run comprehensive tamper detection tests
    test_tamper_detection_comprehensive()


if __name__ == "__main__":
    main()
