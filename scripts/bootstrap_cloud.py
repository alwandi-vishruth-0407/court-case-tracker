"""Initialize an empty cloud database, without resetting existing records."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from auth import hash_password, verify_password
from db import all_rows, one_row, session


def statements(text):
    delimiter = ";"
    pending = ""
    for line in text.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        if line.strip().upper().startswith("DELIMITER "):
            if pending.strip():
                raise ValueError("Unexpected SQL before delimiter directive")
            delimiter = line.strip().split()[1]
            continue
        pending += line + "\n"
        if pending.rstrip().endswith(delimiter):
            statement = pending.rstrip()[:-len(delimiter)].strip()
            pending = ""
            if not statement.upper().startswith(("CREATE DATABASE", "USE ")):
                yield statement
    if pending.strip():
        raise ValueError("Unterminated SQL statement")


def execute_script(connection, name):
    cursor = connection.cursor()
    try:
        for statement in statements((ROOT / "sql" / name).read_text(encoding="utf-8")):
            cursor.execute(statement)
    finally:
        cursor.close()


def main():
    password = os.environ.get("AUTH_DEMO_PASSWORD", "")
    if len(password) < 12:
        raise RuntimeError("Set AUTH_DEMO_PASSWORD to at least 12 characters in the hosting environment.")
    with session() as connection:
        lock = one_row(connection, "SELECT GET_LOCK('caseledger_bootstrap', 30) AS acquired")
        if lock["acquired"] != 1:
            raise RuntimeError("Another database initialization is still running.")
        try:
            tables = {row["TABLE_NAME"].lower() for row in all_rows(connection,
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'")}
            domain = {"judges", "parties", "cases", "case_parties", "hearings", "judgments"}
            if "caseledger_setup" in tables:
                state = one_row(connection, "SELECT completed FROM caseledger_setup WHERE setup_id=1")
                if not state or not state["completed"]:
                    raise RuntimeError("A previous initialization was interrupted. Inspect the database before retrying; no data was reset.")
            if not tables:
                cursor = connection.cursor()
                try:
                    cursor.execute("CREATE TABLE caseledger_setup (setup_id INT PRIMARY KEY, completed BOOLEAN NOT NULL)")
                    cursor.execute("INSERT INTO caseledger_setup VALUES (1, FALSE)")
                    connection.commit()
                finally:
                    cursor.close()
                execute_script(connection, "schema.sql")
                execute_script(connection, "seed.sql")
                cursor = connection.cursor()
                try:
                    cursor.execute("UPDATE caseledger_setup SET completed=TRUE WHERE setup_id=1")
                    connection.commit()
                finally:
                    cursor.close()
            elif not domain.issubset(tables):
                raise RuntimeError("The database is partially initialized. Inspect it before retrying; no records were reset.")
            # Verify DBMS features even when initialization was interrupted.
            one_row(connection, "SELECT COUNT(*) AS count FROM cases_pending_over_six_months")
            triggers = {row["TRIGGER_NAME"] for row in all_rows(connection,
                "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()")}
            if not {"trg_judgment_disposes_case", "trg_case_not_own_parent_insert", "trg_case_not_own_parent_update"}.issubset(triggers):
                raise RuntimeError("Required MySQL triggers are missing. Inspect the schema before deployment.")
            execute_script(connection, "auth_schema.sql")
            user = one_row(connection, "SELECT password_hash FROM auth_users WHERE username=%s", ("demo",))
            if user:
                if not verify_password(password, user["password_hash"]):
                    raise RuntimeError("The configured password does not match the existing demo account. It was not changed.")
            else:
                cursor = connection.cursor()
                try:
                    cursor.execute("INSERT INTO auth_users(username,email,display_name,password_hash) VALUES (%s,%s,%s,%s)",
                        ("demo", "demo@caseledger.local", "Demo User", hash_password(password)))
                finally:
                    cursor.close()
            connection.commit()
            print("Database schema and demo login are ready. Existing records were preserved.")
        finally:
            one_row(connection, "SELECT RELEASE_LOCK('caseledger_bootstrap') AS released")


if __name__ == "__main__":
    main()
