"""Create a password hash for INM2_ADMIN_PASSWORD_HASH without echoing input."""

from __future__ import annotations

import base64
import getpass
import hashlib
import secrets
import sys

from api.auth import SCRYPT_N, SCRYPT_P, SCRYPT_R


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def main() -> int:
    password = getpass.getpass("Admin password (at least 12 characters): ")
    confirmation = getpass.getpass("Repeat admin password: ")
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if len(password) < 12:
        print("Password must contain at least 12 characters.", file=sys.stderr)
        return 1
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    print(f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{_encode(salt)}:{_encode(digest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
