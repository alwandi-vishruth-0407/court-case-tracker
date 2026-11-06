"""Verify local login against the running FastAPI server and actual MySQL."""
import hashlib
import json
import os
import sys
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import mysql.connector

root = Path(__file__).resolve().parents[1]
base_url = "http://127.0.0.1:5173/api"
checks = []
connection = mysql.connector.connect(host="127.0.0.1", port=3306, user="root",
    password=os.environ["DB_PASSWORD"], database="court_case_tracker")
cursor = connection.cursor(dictionary=True)
jar = CookieJar()
browser = build_opener(HTTPCookieProcessor(jar))
anonymous = build_opener()
issued_hashes = set()


def check(condition, description):
    if not condition:
        raise AssertionError(description)
    checks.append(description)
    print(f"PASS: {description}")


def call(path, method="GET", body=None, *, opener=None, headers=None, safe=True):
    request_headers = {"Content-Type": "application/json"}
    if safe:
        request_headers["X-CaseLedger-Request"] = "1"
    request_headers.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    request = Request(base_url + path, data=data, method=method, headers=request_headers)
    try:
        with (opener or browser).open(request, timeout=10) as response:
            return response.status, json.load(response), response.headers
    except HTTPError as error:
        return error.code, json.load(error), error.headers


def record_session():
    token = next(cookie.value for cookie in jar if cookie.name == "caseledger_session")
    issued_hashes.add(hashlib.sha256(token.encode()).hexdigest())
    return token


try:
    check(call("/health", opener=anonymous)[0] == 200, "Health remains available for the startup script")
    for path in ("/auth/me", "/dashboard", "/cases", "/judges", "/parties", "/reports/pending", "/cases/101"):
        check(call(path, opener=anonymous)[0] == 401, f"Unauthenticated GET {path} is blocked")
    for path in ("/judges", "/parties", "/cases", "/cases/103/parties", "/cases/103/hearings", "/cases/103/judgment"):
        check(call(path, "POST", {}, opener=anonymous)[0] == 401, f"Unauthenticated POST {path} is blocked")
    login_body = {"identifier": "demo", "password": os.environ["AUTH_DEMO_PASSWORD"]}
    check(call("/auth/login", "POST", login_body, safe=False)[0] == 403, "Login rejects requests without the browser request header")
    check(call("/auth/login", "POST", login_body, headers={"Origin": "https://untrusted.example"})[0] == 403,
          "Login rejects an untrusted request origin")
    wrong = call("/auth/login", "POST", {"identifier": "demo", "password": "incorrect-password"})
    absent = call("/auth/login", "POST", {"identifier": "absent-account", "password": "incorrect-password"})
    check(wrong[0] == absent[0] == 401 and wrong[1] == absent[1], "Unknown account and wrong password return the same error")
    check(call("/auth/login", "POST", {**login_body, "password": login_body["password"] + " "})[0] == 401,
          "Passwords are checked exactly, without trimming whitespace")
    status, user, headers = call("/auth/login", "POST", login_body)
    check(status == 200 and user["username"] == "demo", "Username login succeeds")
    cookie = headers.get("Set-Cookie", "")
    check("HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie,
          "Session cookie is HttpOnly, SameSite Strict, and scoped to the API")
    check("Max-Age" not in cookie and "Expires=" not in cookie, "Cookie is a browser session cookie")
    check(headers.get("Cache-Control") == "no-store", "Authentication responses are not cached")
    token = record_session()
    cursor.execute("SELECT token_hash FROM auth_sessions WHERE token_hash=%s", (hashlib.sha256(token.encode()).hexdigest(),))
    check(cursor.fetchone() is not None, "MySQL stores a hash of the session token")
    connection.rollback()
    check(call("/auth/me")[1]["email"] == "demo@caseledger.local", "Session survives subsequent requests")
    check(call("/dashboard")[1] == {"total_cases": 5, "pending_cases": 3, "disposed_cases": 2, "old_pending": 1},
          "Authenticated dashboard returns the original case counts")
    check(call("/judges", "POST", {}, safe=False)[0] == 403, "Authenticated writes require the browser request header")
    check(call("/judges", "POST", {}, headers={"Origin": "https://untrusted.example"})[0] == 403,
          "Authenticated writes reject an untrusted origin")
    check(call("/auth/logout", "POST")[0] == 200, "Sign out succeeds")
    check(call("/auth/me")[0] == 401, "Signed-out browser loses access")
    check(call("/dashboard", opener=anonymous, headers={"Cookie": f"caseledger_session={token}"})[0] == 401,
          "Sign out invalidates a replayed session token on the server")
    check(call("/auth/login", "POST", {**login_body, "identifier": "DEMO@CASELEDGER.LOCAL"})[0] == 200,
          "Email login succeeds without case sensitivity")
    email_token = record_session()
    check(call("/auth/login", "POST", login_body)[0] == 200, "Signing in again rotates the browser session")
    replacement = record_session()
    check(replacement != email_token, "Each login produces a different random session token")
    check(call("/dashboard", opener=anonymous, headers={"Cookie": f"caseledger_session={email_token}"})[0] == 401,
          "The replaced session token no longer grants access")
    check(call("/dashboard", opener=anonymous, headers={"Cookie": "caseledger_session=" + "x" * 43})[0] == 401,
          "A forged session token is rejected")
    cursor.execute("UPDATE auth_sessions SET expires_at=UTC_TIMESTAMP()-INTERVAL 1 SECOND WHERE token_hash=%s",
                   (hashlib.sha256(replacement.encode()).hexdigest(),))
    connection.commit()
    check(call("/auth/me")[0] == 401, "Expired sessions are rejected by the backend")
    check(call("/auth/logout", "POST")[0] == 200, "An expired session can still be cleared by sign out")
    cursor.execute("SELECT password_hash FROM auth_users WHERE username='demo'")
    password_hash = cursor.fetchone()["password_hash"]
    check(password_hash.startswith("pbkdf2_sha256$600000$") and password_hash != login_body["password"],
          "Demo password is stored as a salted PBKDF2 hash")
    connection.rollback()
    sys.path.insert(0, str(root / "backend"))
    from auth import check_login_rate, hash_password, verify_password
    from fastapi import HTTPException
    from starlette.requests import Request as ASGIRequest
    rate_request = ASGIRequest({"type": "http", "client": ("isolated-verification", 1), "headers": []})
    for _ in range(10):
        check_login_rate(rate_request)
    try:
        check_login_rate(rate_request)
    except HTTPException as error:
        check(error.status_code == 429, "Rate limiter rejects the eleventh attempt in one minute")
    else:
        raise AssertionError("Rate limiter accepted an excessive attempt")
    first_hash = hash_password("Example only")
    check(first_hash != hash_password("Example only") and verify_password("Example only", first_hash),
          "Password hashing uses fresh salts and verifies the original password")
    check(not verify_password("anything", "invalid-hash"), "Malformed password hashes fail closed")
finally:
    connection.rollback()
    for token_hash in issued_hashes:
        cursor.execute("DELETE FROM auth_sessions WHERE token_hash=%s", (token_hash,))
    connection.commit()
    cursor.close()
    connection.close()

output = f"Login verification passed: {len(checks)} checks.\n\n" + "\n".join(f"PASS: {item}" for item in checks) + "\n"
(root / "docs" / "LOGIN_VERIFICATION.txt").write_text(output, encoding="utf-8")
print(f"Login verification passed: {len(checks)} checks.")
