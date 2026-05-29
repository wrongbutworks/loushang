from __future__ import annotations

import hashlib
import string

_BASE36_ALPHABET = string.digits + string.ascii_lowercase


def _to_base36(n: int) -> str:
    """
    Convert a non-negative integer to base36 string.
    """
    if n == 0:
        return "0"
    chars: list[str] = []
    while n > 0:
        n, r = divmod(n, 36)
        chars.append(_BASE36_ALPHABET[r])
    return "".join(reversed(chars))


def short_hash(text: str) -> str:
    """
    Fast deterministic short hash for identifiers/logging (non-cryptographic).
    - Based on SHA-1 for portability, then encoded as two base36 chunks for compactness
    - NOT suitable for security-sensitive use-cases
    """
    d = hashlib.sha1(text.encode("utf-8")).digest()  # 20 bytes
    # Take first 8 and next 8 bytes to form two 64-bit ints, improving avalanche
    h1 = int.from_bytes(d[0:8], byteorder="big", signed=False)
    h2 = int.from_bytes(d[8:16], byteorder="big", signed=False)
    return _to_base36(h2) + _to_base36(h1)
