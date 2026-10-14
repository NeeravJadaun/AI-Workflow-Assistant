"""Minimal signed-token auth. Demo-grade: see README limitations."""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db

ROLE_PERMISSIONS = {"reviewer": {"submit", "approve"}, "submitter": {"submit"}}
TOKEN_TTL = 8 * 3600
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, _, _ = stored.partition("$")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)


def _sign(payload: str) -> str:
    return hmac.new(config.secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(username: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": time.time() + TOKEN_TTL}).encode()).decode()
    return f"{payload}.{_sign(payload)}"


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if not creds:
        raise HTTPException(401, "Login required")
    payload, _, sig = creds.credentials.partition(".")
    if not hmac.compare_digest(sig, _sign(payload)):
        raise HTTPException(401, "Invalid token")
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        raise HTTPException(401, "Invalid token")
    if data["exp"] < time.time():
        raise HTTPException(401, "Token expired")
    conn = db.connect()
    try:
        row = conn.execute("SELECT username, role FROM users WHERE username=?", (data["u"],)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(401, "Unknown user")
    # Permissions come from the DB role on every request, never from the token or the model.
    return {"username": row["username"], "role": row["role"], "permissions": sorted(ROLE_PERMISSIONS.get(row["role"], set()))}


def require(permission: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if permission not in user["permissions"]:
            raise HTTPException(403, f"Missing permission: {permission}")
        return user
    return dep
