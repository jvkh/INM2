"""Generate a secret for the optional single-admin TOTP second factor."""

from __future__ import annotations

import base64
import secrets
from urllib.parse import quote


def main() -> None:
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    account = quote("INM2 admin", safe="")
    uri = f"otpauth://totp/{account}?secret={secret}&issuer=INM2&algorithm=SHA1&digits=6&period=30"
    print(f"INM2_TOTP_SECRET={secret}")
    print(f"Authenticator setup URI: {uri}")


if __name__ == "__main__":
    main()
