import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "memory-gateway")))
import pii as PII  # noqa: N812 (external module camel-cased for clarity)


def main():
    sample = {
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "+1 (415) 555-1234",
        "credit_card": "4111 1111 1111 1111",
        "ssn": "123-45-6789",
        "notes": "Contact at jane.doe@example.com about acct 4111 1111 1111 1111 and 123-45-6789",
        "password": "supersecret",
    }

    red = PII.redact_object(sample)
    print(json.dumps(red, indent=2))

    assert red["email"] == "[redacted-email]"
    assert "[redacted-phone]" in red["phone"]
    assert red["ssn"] == "[redacted]"
    assert red["password"] == "[redacted]"  # noqa: S105 test fixture placeholder
    assert red["credit_card"] == "[redacted]"
    assert "[redacted-email]" in red["notes"]
    assert "1111" in red["notes"] and "[redacted" in red["notes"]
    print("OK: PII redaction passed")


if __name__ == "__main__":
    main()
