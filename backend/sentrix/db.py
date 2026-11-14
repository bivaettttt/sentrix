import json
import os

from sqlalchemy import create_engine, text

engine = create_engine(
    os.getenv(
        "DATABASE_URL", "postgresql+psycopg://sentrix:sentrix-local@127.0.0.1/sentrix"
    ),
    pool_pre_ping=True,
)


def query(conn, statement, **args):
    return conn.execute(text(statement), args)


def one(conn, statement, **args):
    row = query(conn, statement, **args).mappings().first()
    return dict(row) if row is not None else None


def many(conn, statement, **args):
    return [dict(row) for row in query(conn, statement, **args).mappings()]


def lock(conn, kind, identity, shared=False):
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    query(
        conn, f"SELECT {function}(hashtextextended(:key, 0))", key=f"{kind}:{identity}"
    )


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def audit(conn, actor, correlation, action, subject, **detail):
    query(
        conn,
        """INSERT INTO audit(actor,correlation,action,subject,detail)
          VALUES (:actor,:correlation,:action,:subject,CAST(:detail AS jsonb))""",
        actor=actor,
        correlation=correlation,
        action=action,
        subject=str(subject),
        detail=packed(detail),
    )
