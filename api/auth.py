"""Single-administrator authentication for the HTTP API."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import struct
import time
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse


COOKIE_NAME = "inm2_session"
SESSION_SECONDS = 12 * 60 * 60
FAILURE_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_FAILURES = 5
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
_failure_lock = Lock()
_login_failures: dict[str, list[float]] = {}
_totp_lock = Lock()
_last_totp_counter = -1


@dataclass(frozen=True)
class AuthConfig:
    password_salt: bytes
    password_digest: bytes
    signing_secret: bytes
    cookie_secure: bool
    totp_enabled: bool
    totp_secret: bytes


def _decode_password_hash(value: str) -> tuple[bytes, bytes]:
    parts = value.split(":")
    if len(parts) != 6 or parts[:4] != ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)]:
        raise RuntimeError("INM2_ADMIN_PASSWORD_HASH must be a valid scrypt hash; generate it with python -m api.password_hash")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", parts[4]) or not re.fullmatch(r"[A-Za-z0-9_-]+", parts[5]):
        raise RuntimeError("INM2_ADMIN_PASSWORD_HASH has an invalid format")
    try:
        salt = base64.urlsafe_b64decode(parts[4] + "=" * (-len(parts[4]) % 4))
        digest = base64.urlsafe_b64decode(parts[5] + "=" * (-len(parts[5]) % 4))
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("INM2_ADMIN_PASSWORD_HASH has an invalid format") from exc
    if len(salt) != 16 or len(digest) != 32:
        raise RuntimeError("INM2_ADMIN_PASSWORD_HASH has an invalid salt or digest length")
    return salt, digest


def get_auth_config() -> AuthConfig:
    password_hash = os.environ.get("INM2_ADMIN_PASSWORD_HASH", "")
    signing_secret = os.environ.get("INM2_AUTH_SECRET", "").encode("utf-8")
    secure_value = os.environ.get("INM2_COOKIE_SECURE", "true").strip().lower()
    totp_enabled_value = os.environ.get("INM2_TOTP_ENABLED", "false").strip().lower()
    if not password_hash:
        raise RuntimeError("INM2_ADMIN_PASSWORD_HASH is required")
    password_salt, password_digest = _decode_password_hash(password_hash)
    if len(signing_secret) < 32:
        raise RuntimeError("INM2_AUTH_SECRET must contain at least 32 bytes")
    if secure_value not in {"true", "false"}:
        raise RuntimeError("INM2_COOKIE_SECURE must be true or false")
    if totp_enabled_value not in {"true", "false"}:
        raise RuntimeError("INM2_TOTP_ENABLED must be true or false")
    totp_secret = b""
    if totp_enabled_value == "true":
        encoded_totp_secret = os.environ.get("INM2_TOTP_SECRET", "").strip().upper()
        try:
            totp_secret = base64.b32decode(encoded_totp_secret, casefold=True)
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError("INM2_TOTP_SECRET must be a valid Base32 secret when TOTP is enabled") from exc
        if len(totp_secret) < 20:
            raise RuntimeError("INM2_TOTP_SECRET must decode to at least 20 bytes")
    return AuthConfig(password_salt, password_digest, signing_secret, secure_value == "true", totp_enabled_value == "true", totp_secret)


def validate_auth_config() -> None:
    """Fail startup when the single-admin credentials are not configured safely."""
    get_auth_config()


def _session_signature(payload: str, secret: bytes) -> str:
    return hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()


def _set_session_cookie(response: Response, config: AuthConfig) -> None:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(18)}"
    token = f"{payload}.{_session_signature(payload, config.signing_secret)}"
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=config.cookie_secure,
        samesite="strict",
        path="/",
    )


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        payload, signature = token.rsplit(".", 1)
        issued_at_text, _nonce = payload.split(".", 1)
        issued_at = int(issued_at_text)
        config = get_auth_config()
        if not hmac.compare_digest(_session_signature(payload, config.signing_secret), signature):
            return False
        now = int(time.time())
        return 0 <= now - issued_at <= SESSION_SECONDS
    except (ValueError, RuntimeError, UnicodeError):
        return False


def _origin_is_same_site(request: Request) -> bool:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin or not host:
        return False
    try:
        parsed = urlsplit(origin)
        origin_host = parsed.netloc.casefold()
        request_host = host.casefold()
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"https", "http"} or origin_host != request_host:
            return False
        if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False
        return True
    except ValueError:
        return False


def _allow_login_attempt(client_key: str) -> bool:
    now = time.monotonic()
    with _failure_lock:
        recent = [stamp for stamp in _login_failures.get(client_key, []) if now - stamp < FAILURE_WINDOW_SECONDS]
        _login_failures[client_key] = recent
        return len(recent) < MAX_LOGIN_FAILURES


def _record_login_failure(client_key: str) -> None:
    now = time.monotonic()
    with _failure_lock:
        recent = [stamp for stamp in _login_failures.get(client_key, []) if now - stamp < FAILURE_WINDOW_SECONDS]
        recent.append(now)
        _login_failures[client_key] = recent


def _clear_login_failures(client_key: str) -> None:
    with _failure_lock:
        _login_failures.pop(client_key, None)


def _client_key(request: Request) -> str:
    """Use the proxy-provided client address for login throttling when valid."""
    candidates = [request.headers.get("x-real-ip", "")]
    forwarded = request.headers.get("x-forwarded-for", "").split(",")
    candidates.extend(reversed(forwarded))
    if request.client:
        candidates.append(request.client.host)
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate.strip()))
        except ValueError:
            continue
    return "unknown"


def auth_middleware_response(request: Request) -> Response | None:
    """Return a rejection response when the request lacks a valid admin session."""
    path = request.url.path
    if path in {"/api/v1/auth/login", "/api/v1/auth/session"}:
        return None
    try:
        authenticated = is_authenticated(request)
    except RuntimeError:
        return JSONResponse({"detail": "Authentication is not configured"}, status_code=503,
                            headers={"Cache-Control": "no-store"})
    if not authenticated:
        return JSONResponse({"detail": "Authentication required"}, status_code=401,
                            headers={"Cache-Control": "no-store"})
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _origin_is_same_site(request):
        return JSONResponse({"detail": "Invalid request origin"}, status_code=403,
                            headers={"Cache-Control": "no-store"})
    return None


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    totp_code: str = Field(default="", max_length=16)


router = APIRouter()


@router.get("/auth/session")
def get_session(request: Request) -> dict[str, bool]:
    return {"authenticated": is_authenticated(request), "totp_required": get_auth_config().totp_enabled}


@router.post("/auth/activity")
def record_activity(request: Request, response: Response) -> dict[str, bool]:
    """Extend the session after explicit browser activity, not background polling."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    _set_session_cookie(response, get_auth_config())
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True}


def _verify_totp(code: str, secret: bytes, now: int | None = None) -> bool:
    """Validate a six-digit RFC 6238 code and reject a previously used time step."""
    global _last_totp_counter
    if not re.fullmatch(r"\d{6}", code):
        return False
    current_counter = int((time.time() if now is None else now) // 30)
    match_counter = -1
    for counter in range(max(0, current_counter - 1), current_counter + 2):
        digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1_000_000
        if hmac.compare_digest(f"{value:06d}", code):
            match_counter = counter
    if match_counter < 0:
        return False
    with _totp_lock:
        if match_counter <= _last_totp_counter:
            return False
        _last_totp_counter = match_counter
        return True


@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, bool]:
    if not _origin_is_same_site(request):
        raise HTTPException(status_code=403, detail="Invalid request origin")
    client_key = _client_key(request)
    if not _allow_login_attempt(client_key):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    config = get_auth_config()
    supplied = hashlib.scrypt(
        body.password.encode("utf-8"),
        salt=config.password_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=len(config.password_digest),
        maxmem=64 * 1024 * 1024,
    )
    expected = config.password_digest
    if not hmac.compare_digest(supplied, expected):
        _record_login_failure(client_key)
        raise HTTPException(status_code=401, detail="Incorrect password")
    if config.totp_enabled and not _verify_totp(body.totp_code, config.totp_secret):
        _record_login_failure(client_key)
        raise HTTPException(status_code=401, detail="Incorrect password or authenticator code")
    _clear_login_failures(client_key)
    _set_session_cookie(response, config)
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True}


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    config = get_auth_config()
    response.delete_cookie(COOKIE_NAME, path="/", secure=config.cookie_secure, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}
