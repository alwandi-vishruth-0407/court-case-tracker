from datetime import date
import os
from pathlib import Path
from typing import Literal

import mysql.connector
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from db import all_rows, insert_row, one_row, session
from auth import current_user, router as auth_router


app = FastAPI(title="Court Case Tracker", version="1.0")
protected = APIRouter(dependencies=[Depends(current_user)])
app.include_router(auth_router)
if os.getenv("APP_ENV") == "production":
    hosts = os.environ["APP_ALLOWED_HOSTS"].split(",")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in hosts])


@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


class CleanModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class JudgeInput(CleanModel):
    full_name: str = Field(min_length=2, max_length=120)
    designation: str = Field(min_length=2, max_length=100)
    court_name: str = Field(min_length=2, max_length=120)


class PartyInput(CleanModel):
    party_name: str = Field(min_length=2, max_length=150)
    party_type: Literal["Person", "Organization"]


class CaseInput(CleanModel):
    case_number: str = Field(min_length=3, max_length=40)
    title: str = Field(min_length=3, max_length=200)
    court_name: str = Field(min_length=2, max_length=120)
    filed_on: date
    assigned_judge_id: int = Field(gt=0)
    parent_case_id: int | None = Field(default=None, gt=0)


class CasePartyInput(CleanModel):
    party_id: int = Field(gt=0)
    party_role: Literal["Petitioner", "Respondent", "Appellant"]


class HearingInput(CleanModel):
    judge_id: int = Field(gt=0)
    hearing_date: date
    purpose: str = Field(min_length=3, max_length=200)
    hearing_status: Literal["Scheduled", "Held", "Adjourned", "Cancelled"]


class JudgmentInput(CleanModel):
    judgment_date: date
    outcome: str = Field(min_length=3, max_length=100)
    summary: str = Field(min_length=5)
    document_url: HttpUrl | None = None


@app.exception_handler(mysql.connector.Error)
async def database_error_handler(_request, exc):
    if exc.errno == 1062:
        return JSONResponse(status_code=409, content={"detail": "This record already exists."})
    if exc.errno == 1452:
        return JSONResponse(status_code=400, content={"detail": "A referenced record does not exist."})
    return JSONResponse(status_code=503, content={"detail": "The database is temporarily unavailable. Please try again shortly."})


@app.get("/api/health")
def health():
    with session() as connection:
        one_row(connection, "SELECT 1 AS ready")
    return {"status": "ready"}


@protected.get("/api/dashboard")
def dashboard():
    with session() as connection:
        counts = one_row(
            connection,
            """SELECT COUNT(*) AS total_cases,
                      COALESCE(SUM(case_status = 'Pending'), 0) AS pending_cases,
                      COALESCE(SUM(case_status = 'Disposed'), 0) AS disposed_cases
               FROM cases""",
        )
        old = one_row(connection, "SELECT COUNT(*) AS old_pending FROM cases_pending_over_six_months")
    return {**counts, **old}


@protected.get("/api/judges")
def list_judges():
    with session() as connection:
        return all_rows(connection, "SELECT * FROM judges ORDER BY full_name")


@protected.post("/api/judges", status_code=201)
def create_judge(item: JudgeInput):
    with session() as connection:
        new_id = insert_row(
            connection,
            "INSERT INTO judges (full_name, designation, court_name) VALUES (%s, %s, %s)",
            (item.full_name, item.designation, item.court_name),
        )
    return {"judge_id": new_id}


@protected.get("/api/parties")
def list_parties():
    with session() as connection:
        return all_rows(connection, "SELECT * FROM parties ORDER BY party_name")


@protected.post("/api/parties", status_code=201)
def create_party(item: PartyInput):
    with session() as connection:
        new_id = insert_row(
            connection,
            "INSERT INTO parties (party_name, party_type) VALUES (%s, %s)",
            (item.party_name, item.party_type),
        )
    return {"party_id": new_id}


@protected.get("/api/cases")
def list_cases(search: str = Query(default="", max_length=100),
               status: Literal["Pending", "Disposed"] | None = None):
    conditions = []
    params = []
    if search.strip():
        conditions.append("(c.case_number LIKE %s OR c.title LIKE %s)")
        term = f"%{search.strip()}%"
        params.extend((term, term))
    if status:
        conditions.append("c.case_status = %s")
        params.append(status)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""SELECT c.case_id, c.case_number, c.title, c.court_name,
                     c.filed_on, c.case_status, c.parent_case_id,
                     j.full_name AS judge_name
              FROM cases AS c
              JOIN judges AS j ON j.judge_id = c.assigned_judge_id
              {where}
              ORDER BY c.filed_on DESC, c.case_id DESC LIMIT 100"""
    with session() as connection:
        return all_rows(connection, sql, tuple(params))


@protected.post("/api/cases", status_code=201)
def create_case(item: CaseInput):
    with session() as connection:
        new_id = insert_row(
            connection,
            """INSERT INTO cases
               (case_number, title, court_name, filed_on, assigned_judge_id, parent_case_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (item.case_number, item.title, item.court_name, item.filed_on,
             item.assigned_judge_id, item.parent_case_id),
        )
    return {"case_id": new_id}


def appeal_chain(connection, selected_id):
    root = one_row(
        connection,
        """WITH RECURSIVE ancestors AS (
             SELECT case_id, parent_case_id FROM cases WHERE case_id = %s
             UNION ALL
             SELECT parent.case_id, parent.parent_case_id
             FROM cases AS parent
             JOIN ancestors AS child ON parent.case_id = child.parent_case_id
           )
           SELECT case_id FROM ancestors WHERE parent_case_id IS NULL LIMIT 1""",
        (selected_id,),
    )
    if not root:
        return []
    return all_rows(
        connection,
        """WITH RECURSIVE chain AS (
             SELECT case_id, parent_case_id, case_number, title, case_status, 0 AS level
             FROM cases WHERE case_id = %s
             UNION ALL
             SELECT child.case_id, child.parent_case_id, child.case_number,
                    child.title, child.case_status, chain.level + 1
             FROM cases AS child JOIN chain ON child.parent_case_id = chain.case_id
           )
           SELECT * FROM chain ORDER BY level, case_id""",
        (root["case_id"],),
    )


@protected.get("/api/cases/{case_id}")
def case_detail(case_id: int):
    with session() as connection:
        case = one_row(
            connection,
            """SELECT c.*, j.full_name AS judge_name
               FROM cases AS c JOIN judges AS j ON j.judge_id = c.assigned_judge_id
               WHERE c.case_id = %s""",
            (case_id,),
        )
        if not case:
            raise HTTPException(status_code=404, detail="Case not found.")
        parties = all_rows(
            connection,
            """SELECT p.party_id, p.party_name, p.party_type, cp.party_role
               FROM case_parties AS cp JOIN parties AS p ON p.party_id = cp.party_id
               WHERE cp.case_id = %s ORDER BY p.party_name""",
            (case_id,),
        )
        hearings = all_rows(
            connection,
            """SELECT h.*, j.full_name AS judge_name
               FROM hearings AS h JOIN judges AS j ON j.judge_id = h.judge_id
               WHERE h.case_id = %s ORDER BY h.hearing_date DESC, h.hearing_id DESC""",
            (case_id,),
        )
        judgment = one_row(connection, "SELECT * FROM judgments WHERE case_id = %s", (case_id,))
        chain = appeal_chain(connection, case_id)
    return {"case": case, "parties": parties, "hearings": hearings,
            "judgment": judgment, "appeal_chain": chain}


@protected.post("/api/cases/{case_id}/parties", status_code=201)
def attach_party(case_id: int, item: CasePartyInput):
    with session() as connection:
        insert_row(
            connection,
            "INSERT INTO case_parties (case_id, party_id, party_role) VALUES (%s, %s, %s)",
            (case_id, item.party_id, item.party_role),
        )
    return {"case_id": case_id, "party_id": item.party_id}


@protected.post("/api/cases/{case_id}/hearings", status_code=201)
def add_hearing(case_id: int, item: HearingInput):
    with session() as connection:
        case = one_row(connection, "SELECT filed_on FROM cases WHERE case_id = %s", (case_id,))
        if not case:
            raise HTTPException(status_code=404, detail="Case not found.")
        if item.hearing_date < case["filed_on"]:
            raise HTTPException(status_code=400, detail="Hearing date cannot precede filing date.")
        new_id = insert_row(
            connection,
            """INSERT INTO hearings (case_id, judge_id, hearing_date, purpose, hearing_status)
               VALUES (%s, %s, %s, %s, %s)""",
            (case_id, item.judge_id, item.hearing_date, item.purpose, item.hearing_status),
        )
    return {"hearing_id": new_id}


@protected.post("/api/cases/{case_id}/judgment", status_code=201)
def add_judgment(case_id: int, item: JudgmentInput):
    with session() as connection:
        case = one_row(connection, "SELECT filed_on FROM cases WHERE case_id = %s", (case_id,))
        if not case:
            raise HTTPException(status_code=404, detail="Case not found.")
        if item.judgment_date < case["filed_on"]:
            raise HTTPException(status_code=400, detail="Judgment date cannot precede filing date.")
        new_id = insert_row(
            connection,
            """INSERT INTO judgments
               (case_id, judgment_date, outcome, summary, document_url)
               VALUES (%s, %s, %s, %s, %s)""",
            (case_id, item.judgment_date, item.outcome, item.summary,
             str(item.document_url) if item.document_url else None),
        )
    return {"judgment_id": new_id}


@protected.get("/api/reports/pending")
def long_pending_cases():
    with session() as connection:
        return all_rows(
            connection,
            "SELECT * FROM cases_pending_over_six_months ORDER BY filed_on, case_id",
        )

app.include_router(protected)

# Keep API routes ahead of the frontend mount so authentication stays enforced.
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api(path: str):
    raise HTTPException(status_code=404, detail="API endpoint not found.")

frontend_dist = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[1] / "frontend" / "dist")))
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
