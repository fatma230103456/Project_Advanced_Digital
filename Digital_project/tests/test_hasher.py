"""Tests for src.core.hasher."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.core.hasher import compute_hashes, hash_bytes, hash_string


def test_compute_hashes_matches_known_digests(tmp_path: Path):
    payload = b"forensic evidence \xff\x00 hash test"
    fp = tmp_path / "sample.bin"
    fp.write_bytes(payload)

    h = compute_hashes(fp)

    assert h.size == len(payload)
    assert h.md5 == hashlib.md5(payload).hexdigest()
    assert h.sha1 == hashlib.sha1(payload).hexdigest()
    assert h.sha256 == hashlib.sha256(payload).hexdigest()


def test_compute_hashes_streaming_matches_oneshot(tmp_path: Path):
    payload = b"x" * (3 * 1024 * 1024 + 17)  # spans multiple chunks
    fp = tmp_path / "big.bin"
    fp.write_bytes(payload)

    h = compute_hashes(fp, chunk_size=1024)

    assert h.sha256 == hashlib.sha256(payload).hexdigest()
    assert h.size == len(payload)


def test_compute_hashes_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        compute_hashes(tmp_path / "missing.bin")


def test_to_dict_round_trip(tmp_path: Path):
    fp = tmp_path / "x.bin"
    fp.write_bytes(b"abc")
    h = compute_hashes(fp)
    d = h.to_dict()
    assert d["size"] == 3
    assert set(d) == {"md5", "sha1", "sha256", "size"}


def test_hash_bytes_and_string():
    assert hash_bytes(b"hello") == hashlib.sha256(b"hello").hexdigest()
    assert hash_string("hello") == hashlib.sha256(b"hello").hexdigest()
