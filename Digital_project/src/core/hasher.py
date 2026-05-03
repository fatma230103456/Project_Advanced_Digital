"""Cryptographic hashing for chain-of-custody integrity verification."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileHashes:
    md5: str
    sha1: str
    sha256: str
    size: int

    def to_dict(self) -> dict:
        return {"md5": self.md5, "sha1": self.sha1, "sha256": self.sha256, "size": self.size}


def compute_hashes(path: str | os.PathLike, chunk_size: int = 1024 * 1024) -> FileHashes:
    """Compute MD5, SHA-1, and SHA-256 hashes of a file in a single pass."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    size = 0
    with open(p, "rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return FileHashes(
        md5=md5.hexdigest(),
        sha1=sha1.hexdigest(),
        sha256=sha256.hexdigest(),
        size=size,
    )


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of arbitrary bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_string(s: str) -> str:
    """Return the SHA-256 hex digest of a string (UTF-8)."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
