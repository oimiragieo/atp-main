"""Tests for per-prefix billing record signing (GAP-109)."""

import pytest

from router_service.billing_records import BillingRecord, BillingRecordSigner, SignedBillingRecord
from router_service.key_manager import KeyManager


@pytest.fixture
def key_manager():
    km = KeyManager()
    km.add_key("test-key-1", b"secret1234567890123456", make_current=True)
    return km


@pytest.fixture
def signer(key_manager):
    return BillingRecordSigner(key_manager)


def test_billing_record_creation():
    """Test basic billing record creation."""
    record = BillingRecord(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
        timestamp=1234567890000000,
        sequence=1,
    )

    assert record.tenant == "tenant1"
    assert record.adapter == "adapter1"
    assert record.prefix == "192.168.1.0/24"
    assert record.in_tokens == 100
    assert record.out_tokens == 50
    assert record.usd_micros == 1000
    assert record.timestamp == 1234567890000000
    assert record.sequence == 1


def test_signed_billing_record_creation(signer):
    """Test signed billing record creation."""
    signed = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
    )

    assert signed.record.tenant == "tenant1"
    assert signed.record.adapter == "adapter1"
    assert signed.record.prefix == "192.168.1.0/24"
    assert signed.record.in_tokens == 100
    assert signed.record.out_tokens == 50
    assert signed.record.usd_micros == 1000
    assert signed.record.sequence == 1
    assert signed.signature is not None
    assert signed.kid == "test-key-1"


def test_signature_verification(signer):
    """Test signature verification."""
    signed = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
    )

    assert signer.verify_record(signed) is True


def test_signature_chain_sequence(signer):
    """Test signature chain with multiple records."""
    # Create multiple records for same tenant
    records = []
    for i in range(3):
        signed = signer.sign_record(
            tenant="tenant1",
            adapter="adapter1",
            prefix=f"192.168.{i}.0/24",
            in_tokens=100 + i * 10,
            out_tokens=50 + i * 5,
            usd_micros=1000 + i * 100,
        )
        records.append(signed)

    # Verify all signatures
    for record in records:
        assert signer.verify_record(record) is True

    # Check sequence numbers are incrementing
    assert records[0].record.sequence == 1
    assert records[1].record.sequence == 2
    assert records[2].record.sequence == 3


def test_signature_chain_different_tenants(signer):
    """Test signature chain with different tenants."""
    # Create records for different tenants
    signed1 = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
    )

    signed2 = signer.sign_record(
        tenant="tenant2",
        adapter="adapter1",
        prefix="192.168.2.0/24",
        in_tokens=200,
        out_tokens=100,
        usd_micros=2000,
    )

    # Verify both signatures
    assert signer.verify_record(signed1) is True
    assert signer.verify_record(signed2) is True

    # Check sequences are independent per tenant
    assert signed1.record.sequence == 1
    assert signed2.record.sequence == 1


def test_tampered_record_detection(signer):
    """Test detection of tampered records."""
    signed = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
    )

    # Tamper with the record
    signed.record.usd_micros = 9999  # Change amount

    assert signer.verify_record(signed) is False


def test_serialization_roundtrip(signer):
    """Test serialization and deserialization."""
    original = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
    )

    # Serialize to dict
    data = original.to_dict()

    # Deserialize from dict
    reconstructed = SignedBillingRecord.from_dict(data)

    # Verify reconstructed record
    assert reconstructed.record.tenant == original.record.tenant
    assert reconstructed.record.adapter == original.record.adapter
    assert reconstructed.record.prefix == original.record.prefix
    assert reconstructed.record.in_tokens == original.record.in_tokens
    assert reconstructed.record.out_tokens == original.record.out_tokens
    assert reconstructed.record.usd_micros == original.record.usd_micros
    assert reconstructed.record.sequence == original.record.sequence
    assert reconstructed.signature == original.signature
    assert reconstructed.kid == original.kid

    # Verify signature still works
    assert signer.verify_record(reconstructed) is True


def test_key_rotation(key_manager, signer):
    """Test signature verification with key rotation."""
    # Add a second key
    key_manager.add_key("test-key-2", b"newsecret123456789012", make_current=False)

    # Create record with first key
    signed1 = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.1.0/24",
        in_tokens=100,
        out_tokens=50,
        usd_micros=1000,
    )

    # Rotate to second key
    key_manager.rotate("test-key-2")

    # Create record with second key
    signed2 = signer.sign_record(
        tenant="tenant1",
        adapter="adapter1",
        prefix="192.168.2.0/24",
        in_tokens=200,
        out_tokens=100,
        usd_micros=2000,
    )

    # Both should verify (key manager can access both keys)
    assert signer.verify_record(signed1) is True
    assert signer.verify_record(signed2) is True

    # Check key IDs
    assert signed1.kid == "test-key-1"
    assert signed2.kid == "test-key-2"
