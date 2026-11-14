import csv
import os
from io import StringIO
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from sentrix import cases
from sentrix import contracts as c
from sentrix.auth import OPERATIONS, Actor, passwords, require, signin
from sentrix.db import audit, engine, lock, many, one, query
from sentrix.detection import RULES, score
from sentrix.lab import Scenario, run
from sentrix.service import (
    active_versions,
    create_draft,
    ingest,
    reassess,
    receipt,
    rule_parameters,
    rule_transition,
)

app = FastAPI(
    title="Sentrix",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
API = "/api"
Offset = Annotated[int, Query(ge=0)]
Key = Annotated[
    str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9._-]{1,100}$")
]
MANAGERS = ("FRAUD_MANAGER", "ADMIN")


@app.middleware("http")
async def correlation(request: Request, call_next):
    request.state.id = uuid4()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request.state.id)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def error(request: Request, exc: HTTPException):
    return JSONResponse(
        {"detail": exc.detail, "request_id": str(request.state.id)},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation(request: Request, exc: RequestValidationError):
    fields = [
        {"path": list(issue["loc"]), "type": issue["type"]} for issue in exc.errors()
    ]
    return JSONResponse(
        {
            "detail": "VALIDATION_ERROR",
            "fields": fields,
            "request_id": str(request.state.id),
        },
        status_code=422,
    )


@app.get("/health")
def health():
    with engine.connect() as conn:
        query(conn, "SELECT 1")
    return {"status": "ok"}


@app.post(API + "/auth/login")
def login(payload: c.Login, request: Request):
    return signin(payload.login, payload.password, request.state.id)


@app.post(API + "/auth/logout", status_code=204)
def logout(actor: Actor):
    with engine.begin() as conn:
        query(
            conn, "DELETE FROM sessions WHERE digest=:digest", digest=actor["session"]
        )


@app.get(API + "/users")
def users(actor: Actor):
    require(actor, *MANAGERS)
    with engine.connect() as conn:
        return many(conn, "SELECT login,name,role FROM users ORDER BY name")


@app.post(API + "/users", status_code=201)
def add_user(payload: c.User, actor: Actor, request: Request):
    require(actor, "ADMIN")
    with engine.begin() as conn:
        row = one(
            conn,
            """INSERT INTO users VALUES (:login,:name,:password,:role)
                  ON CONFLICT DO NOTHING RETURNING login,name,role""",
            **(payload.model_dump() | {"password": passwords.hash(payload.password)}),
        )
        if row is None:
            raise HTTPException(409, "LOGIN_EXISTS")
        audit(
            conn,
            actor["login"],
            request.state.id,
            "USER_CREATED",
            row["login"],
            role=row["role"],
        )
        return row


@app.get(API + "/accounts")
def accounts(actor: Actor):
    require(actor, *OPERATIONS)
    with engine.connect() as conn:
        return many(
            conn,
            """SELECT a.id,c.id AS customer,c.name,c.category FROM accounts a
                    JOIN customers c ON c.id=a.customer ORDER BY a.id""",
        )


@app.post(API + "/transactions", status_code=201)
def accept(payload: c.Event, actor: Actor, request: Request):
    require(actor, *OPERATIONS)
    with engine.begin() as conn:
        result = ingest(conn, [payload], actor["login"], request.state.id)[0]
        if os.getenv("LAB_MODE") == "1" and one(
            conn,
            "SELECT source FROM lab_faults WHERE source=:source",
            source=payload.source,
        ):
            raise HTTPException(503, "LAB_TRANSIENT_FAILURE")
        return result


@app.post(API + "/transactions/batch", status_code=201)
def batch(payload: c.Batch, actor: Actor, request: Request):
    require(actor, *OPERATIONS)
    with engine.begin() as conn:
        return ingest(conn, payload.events, actor["login"], request.state.id)


@app.post(API + "/transactions/import", status_code=201)
def import_csv(payload: c.Csv, actor: Actor, request: Request):
    require(actor, *OPERATIONS)
    reader = csv.DictReader(StringIO(payload.text), strict=True)
    allowed = set(c.Event.model_fields)
    events = []
    try:
        fields = reader.fieldnames or []
        if not allowed - {"currency"} <= set(fields) <= allowed or len(
            set(fields)
        ) != len(fields):
            raise HTTPException(422, "INVALID_CSV_HEADER")
        for number, row in enumerate(reader, 2):
            if number > 101 or None in row or any(v is None for v in row.values()):
                raise HTTPException(422, "INVALID_CSV_ROW")
            row["amount"] = int(row["amount"])
            events.append(c.Event.model_validate(row))
    except (ValueError, ValidationError, csv.Error) as exc:
        raise HTTPException(422, "INVALID_CSV_ROW") from exc
    if not events:
        raise HTTPException(422, "EMPTY_CSV")
    with engine.begin() as conn:
        return ingest(conn, events, actor["login"], request.state.id)


@app.get(API + "/transactions")
def transactions(
    actor: Actor,
    offset: Offset = 0,
    q: str = "",
    sort: Literal["recent", "amount"] = "recent",
):
    require(actor, *OPERATIONS)
    ordering = "t.amount DESC,t.id" if sort == "amount" else "t.received_at DESC,t.id"
    with engine.connect() as conn:
        return many(
            conn,
            f"""SELECT t.id,t.external_id,t.amount,t.category,t.occurred_at,t.late,c.name AS customer,
           s.score,s.risk FROM transactions t JOIN accounts a ON a.id=t.account JOIN customers c ON c.id=a.customer
           JOIN LATERAL (SELECT score,risk FROM assessments WHERE transaction=t.id ORDER BY created_at DESC,id LIMIT 1) s ON true
           WHERE t.external_id ILIKE :q OR c.name ILIKE :q
           ORDER BY {ordering} LIMIT 50 OFFSET :offset""",
            q=f"%{q[:100]}%",
            offset=offset,
        )


@app.get(API + "/transactions/{id}")
def transaction(id: UUID, actor: Actor):
    require(actor, *OPERATIONS)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        row = one(
            conn,
            """SELECT t.*,a.customer,c.name AS customer_name FROM transactions t
                  JOIN accounts a ON a.id=t.account JOIN customers c ON c.id=a.customer WHERE t.id=:id""",
            id=id,
        )
        if row is None:
            raise HTTPException(404, "TRANSACTION_NOT_FOUND")
        row["assessments"] = many(
            conn,
            "SELECT * FROM assessments WHERE transaction=:id ORDER BY created_at DESC,id",
            id=id,
        )
        row["history"] = many(
            conn,
            """SELECT t.id,t.amount,t.category,t.occurred_at FROM transactions t
            JOIN accounts a ON a.id=t.account WHERE a.customer=:customer AND t.occurred_at<:instant
            ORDER BY t.occurred_at DESC,t.id LIMIT 20""",
            customer=row["customer"],
            instant=row["occurred_at"],
        )
        return row


@app.post(API + "/transactions/{id}/evaluations")
def evaluate(id: UUID, actor: Actor, request: Request):
    require(actor, *MANAGERS)
    with engine.begin() as conn:
        return reassess(conn, id, actor["login"], request.state.id)


@app.get(API + "/rules")
def rules(actor: Actor):
    with engine.connect() as conn:
        items = many(conn, "SELECT * FROM rules ORDER BY code")
        versions = many(
            conn,
            """SELECT * FROM rule_versions WHERE status='PUBLISHED' OR :editor
                    ORDER BY version DESC""",
            editor=actor["role"] in (*MANAGERS, "RULES_ADMIN"),
        )
        for item in items:
            item["versions"] = [v for v in versions if v["code"] == item["code"]]
            item["parameters"] = {
                key: {"min": lo, "max": hi, "default": value}
                for key, (lo, hi, value) in RULES[item["code"]][1].items()
            }
        return items


@app.post(API + "/rules/{code}/versions", status_code=201)
def draft(code: str, payload: c.RuleDraft, actor: Actor, request: Request):
    require(actor, "RULES_ADMIN")
    with engine.begin() as conn:
        return create_draft(conn, code, payload, actor["login"], request.state.id)


@app.post(API + "/rules/versions/{id}/{action}")
def edit_rule(
    id: UUID, action: Literal["submit", "publish"], actor: Actor, request: Request
):
    require(actor, "RULES_ADMIN" if action == "submit" else "FRAUD_MANAGER")
    with engine.begin() as conn:
        return rule_transition(conn, id, action, actor["login"], request.state.id)


@app.put(API + "/rules/{code}/status")
def switch_rule(code: str, payload: c.RuleSwitch, actor: Actor, request: Request):
    require(actor, "FRAUD_MANAGER")
    with engine.begin() as conn:
        lock(conn, "rules", "global")
        row = one(
            conn,
            "UPDATE rules SET enabled=:enabled WHERE code=:code RETURNING *",
            code=code,
            enabled=payload.enabled,
        )
        if row is None:
            raise HTTPException(404, "RULE_NOT_FOUND")
        audit(
            conn,
            actor["login"],
            request.state.id,
            "RULE_SWITCH",
            code,
            **payload.model_dump(),
        )
        return row


@app.post(API + "/rules/{code}/preview")
def preview(code: str, payload: c.RuleDraft, actor: Actor, request: Request):
    require(actor, "RULES_ADMIN", "FRAUD_MANAGER")
    parameters = rule_parameters(code, payload.parameters)
    with engine.begin() as conn:
        lock(conn, "rules", "global", shared=True)
        active = active_versions(conn)
        candidate = [v for v in active if v["code"] != code] + [
            {"code": code, "version": 0, "id": "preview", "parameters": parameters}
        ]
        sample = many(
            conn,
            "SELECT id,features FROM transactions WHERE source='seed' ORDER BY external_id",
        )
        result = [
            {
                "id": row["id"],
                "before": score(row["features"], active),
                "after": score(row["features"], candidate),
            }
            for row in sample
        ]
        audit(
            conn,
            actor["login"],
            request.state.id,
            "RULE_PREVIEW",
            code,
            sample=len(sample),
        )
        return result


@app.get(API + "/cases")
def list_cases(actor: Actor, offset: Offset = 0, state: str = "", q: str = ""):
    require(actor, *OPERATIONS)
    with engine.connect() as conn:
        return many(
            conn,
            """SELECT c.*,p.name AS customer_name,u.name AS assignee_name,
            (c.closed_at IS NULL AND now()>c.due_at) AS overdue
            FROM cases c JOIN customers p ON p.id=c.customer LEFT JOIN users u ON u.login=c.assignee
            WHERE (:staff OR c.assignee=:user) AND (:state='' OR c.status=:state)
            AND (p.name ILIKE :q OR CAST(c.number AS text) ILIKE :q) ORDER BY c.priority DESC,c.due_at,c.number
            LIMIT 50 OFFSET :offset""",
            staff=actor["role"] != "FRAUD_ANALYST",
            user=actor["login"],
            state=state,
            q=f"%{q[:100]}%",
            offset=offset,
        )


@app.get(API + "/cases/{id}")
def case(id: UUID, actor: Actor):
    require(actor, *OPERATIONS)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        return cases.detail(conn, id, actor)


@app.post(API + "/cases/{id}/commands")
def case_command(
    id: UUID, payload: c.CaseCommand, key: Key, actor: Actor, request: Request
):
    require(actor, *OPERATIONS)
    with engine.begin() as conn:
        return receipt(
            conn,
            actor["login"],
            key,
            [str(id), payload.model_dump()],
            lambda: cases.perform(conn, id, payload, actor, request.state.id),
        )


@app.get(API + "/alerts")
def alerts(
    actor: Actor,
    offset: Offset = 0,
    severity: Literal["HIGH", "CRITICAL"] | None = None,
):
    require(actor, *OPERATIONS)
    with engine.connect() as conn:
        return many(
            conn,
            """SELECT a.*,s.score,s.transaction,c.number,c.status,p.name AS customer_name
            FROM alerts a JOIN assessments s ON s.id=a.assessment JOIN cases c ON c.id=a.case_id
            JOIN customers p ON p.id=c.customer WHERE (:staff OR c.assignee=:user)
            AND (CAST(:severity AS text) IS NULL OR a.severity=:severity)
            ORDER BY a.created_at DESC,a.id LIMIT 50 OFFSET :offset""",
            staff=actor["role"] != "FRAUD_ANALYST",
            user=actor["login"],
            severity=severity,
            offset=offset,
        )


@app.get(API + "/analytics")
def analytics(actor: Actor):
    require(actor, *OPERATIONS)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        summary = one(
            conn,
            """SELECT (SELECT count(*) FROM transactions) AS transactions,
            (SELECT count(DISTINCT transaction) FROM assessments) AS processed,
            (SELECT count(*) FROM alerts) AS alerts,count(*) AS cases,
            count(*) FILTER (WHERE priority=2 AND closed_at IS NULL) AS critical_open,
            count(*) FILTER (WHERE closed_at IS NULL AND due_at<now()) AS overdue,
            count(*) FILTER (WHERE first_review IS NULL AND closed_at IS NULL
                AND created_at+interval '2 hours'<now()) AS untriaged_overdue,
            round(avg(extract(epoch FROM first_review-created_at))) AS mean_review_seconds,
            round(avg(extract(epoch FROM closed_at-created_at))) AS mean_closure_seconds,
            round(100.0*count(*) FILTER (WHERE status='CLOSED_FALSE_POSITIVE')/
                nullif(count(*) FILTER (WHERE closed_at IS NOT NULL),0),1) AS false_positive_percent
            FROM cases""",
        )
        return {
            "summary": summary,
            "outcomes": many(
                conn,
                "SELECT status,count(*) AS total FROM cases GROUP BY status ORDER BY status",
            ),
            "severity": many(
                conn,
                "SELECT severity,count(*) AS total FROM alerts GROUP BY severity ORDER BY severity",
            ),
            "workload": many(
                conn,
                """SELECT COALESCE(u.name,'Без назначения') AS analyst,count(*) AS total
                FROM cases c LEFT JOIN users u ON u.login=c.assignee WHERE closed_at IS NULL
                GROUP BY u.name ORDER BY total DESC""",
            ),
            "hits": many(
                conn,
                """SELECT e->>'code' AS code,e->>'version' AS version,count(*) AS total
                FROM assessments CROSS JOIN LATERAL jsonb_array_elements(evaluations) e
                WHERE e->>'hit'='true' GROUP BY 1,2 ORDER BY 1,2""",
            ),
        }


@app.get(API + "/audit")
def history(actor: Actor, offset: Offset = 0):
    require(actor, *MANAGERS)
    with engine.connect() as conn:
        return many(
            conn,
            """SELECT * FROM audit ORDER BY id DESC LIMIT 100 OFFSET :offset""",
            offset=offset,
        )


@app.get(API + "/lab")
def lab_status(actor: Actor):
    require(actor, "ADMIN")
    return {"enabled": os.getenv("LAB_MODE") == "1"}


@app.post(API + "/lab/{scenario}")
def lab_run(scenario: Scenario, actor: Actor):
    require(actor, "ADMIN")
    if os.getenv("LAB_MODE") != "1":
        raise HTTPException(404, "LAB_DISABLED")
    with engine.begin() as conn:
        if not query(conn, "SELECT pg_try_advisory_xact_lock(882443)").scalar_one():
            raise HTTPException(409, "LAB_BUSY")
        try:
            return run(scenario)
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error


@app.exception_handler(OperationalError)
async def database_unavailable(request: Request, error: OperationalError):
    return JSONResponse(
        {"detail": "DATABASE_UNAVAILABLE", "request_id": str(request.state.id)},
        status_code=503,
    )
