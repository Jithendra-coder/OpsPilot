"""Password and username checks for locally managed team accounts."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import re

ROUNDS = 600_000
USERNAME = re.compile(r"[a-z0-9][a-z0-9._@+-]{2,63}\Z")


def normalize_username(value):
    if not isinstance(value, str):
        raise ValueError("Username must be text.")
    value = value.strip().casefold()
    if not USERNAME.fullmatch(value):
        raise ValueError("Use 3–64 letters, numbers, or . _ @ + - characters for a username.")
    return value


def hash_password(password):
    if not isinstance(password, str) or not 16 <= len(password) <= 256:
        raise ValueError("Password must be between 16 and 256 characters.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ROUNDS).hex()
    return salt, digest


def verify_password(password, salt, expected):
    try:
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ROUNDS).hex()
    except (TypeError, ValueError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(candidate, expected)
