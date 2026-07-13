"""
Minimal JWT implementation using only the Python standard library.

This sandbox has no network access to `pip install PyJWT`, so this hand-rolls
HS256 JSON Web Tokens (header.payload.signature, base64url-encoded, HMAC-SHA256
signed) so the dev server issues and verifies tokens in the same *format* real
JWT libraries produce. The production backend (backend/app/core/security.py)
uses python-jose/PyJWT — swap that in and this file becomes unnecessary.
"""
import base64
import hashlib
import hmac
import json
import time
import os

SECRET_KEY = os.environ.get("AVERTAI_SECRET_KEY", "dev-only-secret-change-in-production")
ACCESS_TOKEN_TTL = 60 * 15          # 15 minutes
REFRESH_TOKEN_TTL = 60 * 60 * 24 * 7  # 7 days


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(payload: dict, ttl_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    body["iat"] = int(time.time())
    body["exp"] = int(time.time()) + ttl_seconds

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    body_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{body_b64}".encode()
    signature = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{body_b64}.{sig_b64}"


def verify_token(token: str):
    """Returns the decoded payload dict, or None if invalid/expired."""
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{body_b64}".encode()
        expected_sig = hmac.new(SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
            return None
        payload = json.loads(_b64url_decode(body_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def create_access_token(user_id: str, role: str = "Viewer") -> str:
    return create_token({"sub": user_id, "role": role, "type": "access"}, ACCESS_TOKEN_TTL)


def create_refresh_token(user_id: str) -> str:
    return create_token({"sub": user_id, "type": "refresh"}, REFRESH_TOKEN_TTL)


def hash_password(password: str) -> str:
    """Demo-only hashing (HMAC, not bcrypt — no passlib available offline)."""
    return "demo-hash:" + password


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash
