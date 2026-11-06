"""Add the demo login without changing any court domain records."""
import os
import sys
from pathlib import Path

import mysql.connector

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "backend"))
from auth import hash_password, verify_password

connection = mysql.connector.connect(host="127.0.0.1", port=3306, user=os.environ["AUTH_DB_USER"],
    password=os.environ["DB_PASSWORD"], database="court_case_tracker", connection_timeout=5)
cursor = connection.cursor()
try:
    sql = (project_root / "sql" / "auth_schema.sql").read_text(encoding="utf-8")
    for statement in sql.split(";"):
        if statement.strip():
            cursor.execute(statement)
    cursor.execute("SELECT password_hash FROM auth_users WHERE username='demo'")
    existing = cursor.fetchone()
    if existing:
        if not verify_password(os.environ["AUTH_DEMO_PASSWORD"], existing[0]):
            raise RuntimeError("The existing demo account does not match the saved credential. It was not changed.")
        print("Existing demo login verified.")
    else:
        cursor.execute("INSERT INTO auth_users(username,email,display_name,password_hash) VALUES (%s,%s,%s,%s)",
            ("demo", "demo@caseledger.local", "Demo User", hash_password(os.environ["AUTH_DEMO_PASSWORD"])))
        print("Demo login created. Username: demo. Email: demo@caseledger.local.")
    if os.environ.get("APP_DB_USER"):
        cursor.execute("GRANT UPDATE, DELETE ON court_case_tracker.auth_sessions TO %s@'localhost'", (os.environ["APP_DB_USER"],))
    connection.commit()
    print("Authentication tables are ready. Court records were preserved.")
finally:
    cursor.close()
    connection.close()
