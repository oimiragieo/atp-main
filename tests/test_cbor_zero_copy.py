#!/usr/bin/env python3
"""Tests for CBOR Zero-Copy Implementation.

This test suite verifies the correctness and performance of the zero-copy CBOR
encoder compared to the regular CBOR encoder.
"""

import unittest
from io import BytesIO

from tools.atp_cbor_codec_poc import (
    _encode_cbor,
    _encode_cbor_zero_copy,
    decode_frame,
    encode_frame,
    encode_frame_zero_copy,
)


class TestZeroCopyCBOR(unittest.TestCase):
    """Test cases for zero-copy CBOR encoding."""

    def test_basic_types_zero_copy(self):
        """Test zero-copy encoding of basic CBOR types."""
        test_cases = [
            (None, b"\xf6"),
            (True, b"\xf5"),
            (False, b"\xf4"),
            (0, b"\x00"),
            (1, b"\x01"),
            (23, b"\x17"),
            (24, b"\x18\x18"),
            (255, b"\x18\xff"),
            (256, b"\x19\x01\x00"),
            (65535, b"\x19\xff\xff"),
            (65536, b"\x1a\x00\x01\x00\x00"),
            (-1, b"\x20"),
            (-24, b"\x37"),
            ("", b"\x60"),
            ("a", b"\x61\x61"),
            ("hello", b"\x65hello"),
            (b"", b"\x40"),
            (b"abc", b"\x43abc"),
            ([], b"\x80"),
            ([1, 2, 3], b"\x83\x01\x02\x03"),
            ({}, b"\xa0"),
            ({"a": 1}, b"\xa1\x61a\x01"),
        ]

        for obj, expected in test_cases:
            with self.subTest(obj=obj):
                # Test regular encoding
                regular_result = _encode_cbor(obj)
                self.assertEqual(regular_result, expected)

                # Test zero-copy encoding
                buffer = BytesIO()
                _encode_cbor_zero_copy(obj, buffer)
                zero_copy_result = buffer.getvalue()
                self.assertEqual(zero_copy_result, expected)

    def test_complex_objects_zero_copy(self):
        """Test zero-copy encoding of complex objects."""
        test_obj = {
            "version": 1,
            "session": "test_session_123",
            "data": {
                "numbers": [1, 2, 3, 42],
                "strings": ["hello", "world"],
                "nested": {
                    "deep": {
                        "value": 999
                    }
                }
            },
            "flags": ["sync", "ack"],
            "metadata": None
        }

        # Test regular encoding
        regular_result = _encode_cbor(test_obj)

        # Test zero-copy encoding
        buffer = BytesIO()
        _encode_cbor_zero_copy(test_obj, buffer)
        zero_copy_result = buffer.getvalue()

        # Results should be identical
        self.assertEqual(regular_result, zero_copy_result)

    def test_frame_encoding_zero_copy(self):
        """Test zero-copy frame encoding."""
        frame = {
            "v": 1,
            "session_id": "test_session",
            "stream_id": "test_stream",
            "msg_seq": 42,
            "frag_seq": 0,
            "flags": ["SYN"],
            "qos": "gold",
            "ttl": 30,
            "payload": {
                "type": "test.message",
                "content": "Hello, world!"
            }
        }

        key = b"test_key_32_bytes_long_key_123"

        # Test regular encoding
        regular_result = encode_frame(frame, key)

        # Test zero-copy encoding
        zero_copy_result = encode_frame_zero_copy(frame, key)

        # Results should be identical
        self.assertEqual(regular_result, zero_copy_result)

        # Verify both can be decoded correctly
        header1, decoded1 = decode_frame(regular_result, key)
        header2, decoded2 = decode_frame(zero_copy_result, key)

        self.assertEqual(header1, header2)
        self.assertEqual(decoded1, decoded2)
        self.assertEqual(decoded1, frame)

    def test_large_frame_zero_copy(self):
        """Test zero-copy encoding with large frames."""
        # Create a large frame
        large_data = "x" * 10000
        frame = {
            "v": 1,
            "session_id": "large_test_session",
            "payload": {
                "type": "large.message",
                "content": large_data,
                "metadata": {
                    "size": len(large_data),
                    "checksum": hash(large_data)
                }
            }
        }

        key = b"large_test_key_32_bytes_long_"

        # Test regular encoding
        regular_result = encode_frame(frame, key)

        # Test zero-copy encoding
        zero_copy_result = encode_frame_zero_copy(frame, key)

        # Results should be identical
        self.assertEqual(regular_result, zero_copy_result)

        # Verify decoding
        _, decoded = decode_frame(zero_copy_result, key)
        self.assertEqual(decoded, frame)

    def test_buffer_reuse_zero_copy(self):
        """Test that zero-copy encoding can reuse buffers."""
        frame1 = {"type": "message1", "data": "first"}
        frame2 = {"type": "message2", "data": "second"}

        key = b"reuse_test_key_32_bytes_long_"

        # Use the same buffer for multiple encodings
        buffer = BytesIO()

        # First encoding
        result1 = encode_frame_zero_copy(frame1, key, buffer)
        buffer.seek(0)  # Reset buffer position
        buffer.truncate(0)  # Clear buffer

        # Second encoding (reusing buffer)
        result2 = encode_frame_zero_copy(frame2, key, buffer)

        # Verify both results are correct
        _, decoded1 = decode_frame(result1, key)
        _, decoded2 = decode_frame(result2, key)

        self.assertEqual(decoded1, frame1)
        self.assertEqual(decoded2, frame2)

    def test_edge_cases_zero_copy(self):
        """Test edge cases for zero-copy encoding."""
        # Empty dict
        buffer = BytesIO()
        _encode_cbor_zero_copy({}, buffer)
        result = buffer.getvalue()
        expected = _encode_cbor({})
        self.assertEqual(result, expected)

        # Empty list
        buffer = BytesIO()
        _encode_cbor_zero_copy([], buffer)
        result = buffer.getvalue()
        expected = _encode_cbor([])
        self.assertEqual(result, expected)

        # Very large integer
        large_int = 2**32 - 1
        buffer = BytesIO()
        _encode_cbor_zero_copy(large_int, buffer)
        result = buffer.getvalue()
        expected = _encode_cbor(large_int)
        self.assertEqual(result, expected)

    def test_error_handling_zero_copy(self):
        """Test error handling in zero-copy encoding."""
        buffer = BytesIO()

        # Test unsupported type
        with self.assertRaises(TypeError):
            _encode_cbor_zero_copy({1, 2, 3}, buffer)

        # Test dict with non-string keys
        with self.assertRaises(TypeError):
            _encode_cbor_zero_copy({1: "value"}, buffer)


class TestCBORPerformance(unittest.TestCase):
    """Performance tests for CBOR encoding."""

    def test_performance_comparison(self):
        """Test that zero-copy encoding performs at least as well as regular encoding."""
        import time

        # Create test data
        frame = {
            "v": 1,
            "session_id": "perf_test_session",
            "payload": {
                "type": "performance.test",
                "data": "x" * 1000
            }
        }
        key = b"perf_test_key_32_bytes_long_"

        # Warm up
        for _ in range(10):
            encode_frame(frame, key)
            encode_frame_zero_copy(frame, key)

        # Benchmark regular encoding
        start = time.perf_counter()
        for _ in range(100):
            encode_frame(frame, key)
        regular_time = time.perf_counter() - start

        # Benchmark zero-copy encoding
        start = time.perf_counter()
        for _ in range(100):
            encode_frame_zero_copy(frame, key)
        zero_copy_time = time.perf_counter() - start

        # Zero-copy should be at least as fast (allowing for some variance)
        # In practice, it should be faster due to reduced memory allocations
        self.assertLessEqual(zero_copy_time, regular_time * 1.2,
                           f"Zero-copy encoding should not be more than 20% slower: "
                           f"regular={regular_time:.4f}s, zero_copy={zero_copy_time:.4f}s")


if __name__ == '__main__':
    unittest.main()
