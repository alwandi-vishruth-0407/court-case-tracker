"""Production configuration checks; optional disposable MySQL integration checks."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(APP_ENV="production", APP_ALLOWED_HOSTS="caseledger.example,testserver",
                  AUTH_TRUSTED_ORIGINS="https://caseledger.example", AUTH_COOKIE_SECURE="true")

from fastapi.testclient import TestClient
from main import app


class ProductionChecks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="https://caseledger.example")

    def test_built_frontend_and_asset(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)
        import re
        asset = re.search(r'src="([^"]+\.js)"', response.text).group(1)
        self.assertEqual(self.client.get(asset).status_code, 200)

    def test_api_does_not_fall_through_to_html(self):
        response = self.client.get("/api/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json(), {"detail": "API endpoint not found."})

    def test_protected_reads(self):
        for path in ("/auth/me", "/cases", "/judges", "/parties", "/reports/pending", "/dashboard"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get("/api" + path).status_code, 401)

    def test_rejects_untrusted_origin_and_missing_header(self):
        body = {"identifier": "demo", "password": "test-only-password"}
        self.assertEqual(self.client.post("/api/auth/login", json=body).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/login", json=body,
            headers={"X-CaseLedger-Request": "1", "Origin": "https://untrusted.example"}).status_code, 403)

    def test_rejects_unknown_host(self):
        self.assertEqual(self.client.get("/", headers={"Host": "untrusted.example"}).status_code, 400)

    def test_insecure_cookie_configuration_fails(self):
        result = subprocess.run([sys.executable, "-c", "import auth"], cwd=ROOT / "backend",
            env={**os.environ, "AUTH_COOKIE_SECURE": "false"}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production requires secure session cookies", result.stderr)

    def test_sql_parser_preserves_trigger_bodies(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from bootstrap_cloud import statements
        sql = list(statements((ROOT / "sql/schema.sql").read_text()))
        self.assertEqual(sum(s.startswith("CREATE TRIGGER") for s in sql), 3)
        self.assertTrue(any("END IF;" in s and s.endswith("END") for s in sql))
        self.assertFalse(any(s.startswith(("USE ", "CREATE DATABASE")) for s in sql))


@unittest.skipUnless(os.getenv("RUN_MYSQL_INTEGRATION") == "true", "Requires a disposable MySQL database")
class MySQLChecks(unittest.TestCase):
    def test_bootstrap_login_refresh_logout_and_restart(self):
        # CI uses its own disposable database; never point it at live user records.
        os.environ.pop("APP_ENV", None)
        sys.path.insert(0, str(ROOT / "scripts"))
        from bootstrap_cloud import main
        from db import one_row, session
        main()
        with session() as connection:
            before = one_row(connection, "SELECT COUNT(*) AS total FROM cases")["total"]
        client = TestClient(app, base_url="https://caseledger.example")
        headers = {"Origin": "https://caseledger.example", "X-CaseLedger-Request": "1"}
        self.assertEqual(client.post("/api/auth/login", headers=headers,
            json={"identifier": "demo", "password": "wrong-password"}).status_code, 401)
        response = client.post("/api/auth/login", headers=headers,
            json={"identifier": "demo", "password": os.environ["AUTH_DEMO_PASSWORD"]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Secure", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        token = client.cookies.get("caseledger_session")
        self.assertEqual(client.get("/api/auth/me").status_code, 200)
        self.assertEqual(client.get("/api/dashboard").json()["total_cases"], before)
        self.assertEqual(len(client.get("/api/cases/101").json()["appeal_chain"]), 3)
        main()
        self.assertEqual(client.get("/api/auth/me").status_code, 200)
        self.assertEqual(client.get("/api/dashboard").json()["total_cases"], before)
        self.assertEqual(client.post("/api/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(client.get("/api/cases", headers={"Cookie": f"caseledger_session={token}"}).status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
