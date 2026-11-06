"""Verify the actual MySQL database and the running frontend API proxy."""
import json
import os
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

import mysql.connector

project_root = Path(__file__).resolve().parents[1]
checks = []


def check(condition, description):
    if not condition:
        raise AssertionError(description)
    checks.append(description)
    print(f"PASS: {description}")


connection = mysql.connector.connect(
    host="127.0.0.1", port=3306, user="root",
    password=os.environ["DB_PASSWORD"], database="court_case_tracker",
    connection_timeout=5,
)
cursor = connection.cursor(dictionary=True)
try:
    cursor.execute("SELECT COUNT(*) AS total, SUM(case_status='Pending') AS pending, SUM(case_status='Disposed') AS disposed FROM cases")
    baseline = cursor.fetchone()
    check(baseline == {"total": 5, "pending": 3, "disposed": 2}, "Live MySQL contains five cases, three pending and two disposed")
    cursor.execute("SELECT case_id FROM cases_pending_over_six_months")
    check([row["case_id"] for row in cursor.fetchall()] == [102], "Pending view selects only the old contract dispute")
    connection.rollback()

    def expect_rejection(sql, params, errno, description):
        try:
            cursor.execute(sql, params)
        except mysql.connector.Error as error:
            check(error.errno == errno, description)
        else:
            raise AssertionError(f"Database accepted invalid data: {description}")
        finally:
            connection.rollback()

    expect_rejection("UPDATE cases SET parent_case_id=case_id WHERE case_id=103", (), 1644,
                     "Update trigger rejects a case as its own parent")
    cursor.execute("SELECT MAX(case_id)+1000 AS unused_id FROM cases")
    unused_id = cursor.fetchone()["unused_id"]
    connection.rollback()
    expect_rejection(
        "INSERT INTO cases (case_id,case_number,title,court_name,filed_on,assigned_judge_id,parent_case_id) VALUES (%s,%s,'Verification','Demo Court',CURRENT_DATE,1,%s)",
        (unused_id, "VERIFY/" + uuid4().hex[:12], unused_id), 1644,
        "Insert trigger rejects a case as its own parent")
    expect_rejection("INSERT INTO parties(party_name,party_type) VALUES ('Verification','Invalid')", (), 3819,
                     "CHECK constraint rejects invalid party types")
    expect_rejection("UPDATE cases SET case_status='Invalid' WHERE case_id=103", (), 3819,
                     "CHECK constraint rejects invalid case statuses")
    expect_rejection("INSERT INTO case_parties(case_id,party_id,party_role) VALUES (103,3,'Invalid')", (), 3819,
                     "CHECK constraint rejects invalid case party roles")
    expect_rejection("UPDATE hearings SET hearing_status='Invalid' WHERE case_id=102", (), 3819,
                     "CHECK constraint rejects invalid hearing statuses")
    expect_rejection("UPDATE cases SET assigned_judge_id=2147483647 WHERE case_id=103", (), 1452,
                     "Foreign key rejects an absent judge")
    expect_rejection("INSERT INTO judgments(case_id,judgment_date,outcome,summary) VALUES (101,CURRENT_DATE,'Verification','Verification only')", (), 1062,
                     "Unique constraint rejects a second judgment for the same case")
    cursor.execute("INSERT INTO judgments(case_id,judgment_date,outcome,summary) VALUES (102,CURRENT_DATE,'Verification','Verification only')")
    cursor.execute("SELECT case_status FROM cases WHERE case_id=102")
    check(cursor.fetchone()["case_status"] == "Disposed", "Judgment insert trigger changes a pending case to Disposed")
    connection.rollback()
    cursor.execute("SELECT case_status FROM cases WHERE case_id=102")
    check(cursor.fetchone()["case_status"] == "Pending", "Rollback restores the sample case after trigger verification")
    cursor.execute("SELECT COUNT(*) AS total FROM judgments")
    check(cursor.fetchone()["total"] == 2, "Rollback leaves the two original judgments unchanged")
finally:
    connection.rollback()
    cursor.close()
    connection.close()


browser = build_opener(HTTPCookieProcessor(CookieJar()))
login_request = Request("http://127.0.0.1:5173/api/auth/login", method="POST",
    data=json.dumps({"identifier": "demo", "password": os.environ["AUTH_DEMO_PASSWORD"]}).encode(),
    headers={"Content-Type": "application/json", "X-CaseLedger-Request": "1"})
with browser.open(login_request, timeout=5) as response:
    response.read()


def api(path):
    with browser.open("http://127.0.0.1:5173" + path, timeout=5) as response:
        return json.load(response)


check(api("/api/health") == {"status": "ready"}, "Frontend proxy reaches the actual MySQL backend")
check(api("/api/dashboard") == {"total_cases": 5, "pending_cases": 3, "disposed_cases": 2, "old_pending": 1}, "Dashboard reads correct live database counts")
check(len(api("/api/judges")) == 2, "Judge API returns both sample judges")
check(len(api("/api/parties")) == 4, "Party API returns all four sample parties")
check(len(api("/api/cases")) == 5, "Case API returns all five sample cases")
check(len(api("/api/cases?status=Pending")) == 3, "Case status filtering returns the three pending cases")
check([row["case_id"] for row in api("/api/cases?search=Contract")] == [102], "Case search executes its parameterized SQL correctly")
for case_id in (101, 201, 301):
    detail = api(f"/api/cases/{case_id}")
    check([row["case_id"] for row in detail["appeal_chain"]] == [101, 201, 301],
          f"Case {case_id} returns its complete appeal chain")
    check(len(detail["parties"]) == 2, f"Case {case_id} joins the correct two parties")
detail = api("/api/cases/101")
check(len(detail["hearings"]) == 2 and detail["judgment"] is not None,
      "Case detail reads hearings, judges, and judgment from MySQL")
check([row["case_id"] for row in api("/api/reports/pending")] == [102], "Pending report API queries the MySQL view")
output = f"Live verification passed: {len(checks)} checks.\n\n" + "\n".join(f"PASS: {item}" for item in checks) + "\n"
(project_root / "docs" / "LIVE_VERIFICATION.txt").write_text(output, encoding="utf-8")
print(f"Live verification passed: {len(checks)} checks.")
with browser.open(Request("http://127.0.0.1:5173/api/auth/logout", method="POST",
                         headers={"X-CaseLedger-Request": "1"}), timeout=5) as response:
    response.read()
