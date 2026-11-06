"""Local demo authentication with hashed passwords and revocable MySQL sessions."""
import hashlib
import hmac
import os
import secrets
import time
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from db import one_row, session

COOKIE_NAME = "caseledger_session"
SESSION_SECONDS = 8 * 60 * 60
PASSWORD_ITERATIONS = 600_000
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "true" if os.getenv("APP_ENV") == "production" else "false").lower() == "true"
TRUSTED_ORIGINS = frozenset(os.getenv(
    "AUTH_TRUSTED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000",
).strip().split(","))
TRUSTED_ORIGINS = frozenset(origin.strip().rstrip("/") for origin in TRUSTED_ORIGINS if origin.strip())
if os.getenv("APP_ENV") == "production":
    if not COOKIE_SECURE:
        raise RuntimeError("Production requires secure session cookies.")
    if not os.getenv("AUTH_TRUSTED_ORIGINS") or any(not origin.startswith("https://") for origin in TRUSTED_ORIGINS):
        raise RuntimeError("Set AUTH_TRUSTED_ORIGINS to the public HTTPS origin.")
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != PASSWORD_ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (TypeError, ValueError):
        return False


# Unknown accounts still pay the password hashing cost, avoiding a fast lookup path.
_dummy_hash = hash_password(secrets.token_urlsafe(32))
_attempts = OrderedDict()
_attempt_lock = Lock()


def check_login_rate(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _attempt_lock:
        if client not in _attempts and len(_attempts) >= 1000:
            _attempts.popitem(last=False)
        attempts = _attempts.setdefault(client, deque())
        _attempts.move_to_end(client)
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in one minute.",
                                headers={"Retry-After": "60"})
        attempts.append(now)


def require_safe_request(request: Request) -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        # A custom header prevents ordinary cross-origin forms from submitting writes.
        if request.headers.get("X-CaseLedger-Request") != "1":
            raise HTTPException(status_code=403, detail="The request could not be verified. Refresh the page and try again.")
        origin = request.headers.get("Origin")
        if origin and origin not in TRUSTED_ORIGINS:
            raise HTTPException(status_code=403, detail="This request origin is not allowed.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_user(request: Request) -> dict:
    require_safe_request(request)
    token = request.cookies.get(COOKIE_NAME, "")
    if len(token) != 43:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    with session() as connection:
        user = one_row(connection,
            """SELECT u.user_id, u.username, u.email, u.display_name
               FROM auth_sessions AS s JOIN auth_users AS u ON u.user_id=s.user_id
               WHERE s.token_hash=%s AND s.expires_at > UTC_TIMESTAMP()""",
            (_token_hash(token),))
    if not user:
        raise HTTPException(status_code=401, detail="Your session has ended. Sign in again.")
    return user


class LoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", dependencies=[Depends(require_safe_request)])
def login(item: LoginInput, request: Request, response: Response):
    check_login_rate(request)
    identifier = item.identifier.strip().lower()
    with session() as connection:
        user = one_row(connection,
            "SELECT user_id, username, email, display_name, password_hash FROM auth_users WHERE username=%s OR email=%s LIMIT 1",
            (identifier, identifier))
        matches = verify_password(item.password, user["password_hash"] if user else _dummy_hash)
        if not matches or not user:
            raise HTTPException(status_code=401, detail="Incorrect username/email or password.")
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cursor = connection.cursor()
        try:
            cursor.execute("DELETE FROM auth_sessions WHERE expires_at <= UTC_TIMESTAMP()")
            previous_token = request.cookies.get(COOKIE_NAME, "")
            if len(previous_token) == 43:
                cursor.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (_token_hash(previous_token),))
            cursor.execute(
                "INSERT INTO auth_sessions(token_hash,user_id,created_at,expires_at) VALUES (%s,%s,%s,%s)",
                (_token_hash(token), user["user_id"], now, now + timedelta(seconds=SESSION_SECONDS)))
        finally:
            cursor.close()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=COOKIE_SECURE,
                        samesite="strict", path="/api")
    return {key: user[key] for key in ("user_id", "username", "email", "display_name")}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user


@router.post("/logout", dependencies=[Depends(require_safe_request)])
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME, "")
    if len(token) == 43:
        with session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (_token_hash(token),))
            finally:
                cursor.close()
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, secure=COOKIE_SECURE, samesite="strict")
    return {"status": "signed_out"}
