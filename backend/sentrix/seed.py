import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sentrix.auth import passwords
from sentrix.contracts import Event
from sentrix.db import engine, lock, one, packed, query
from sentrix.detection import RULES
from sentrix.service import ingest

USERS = {
    "analyst": ("Мария Лебедева", "FRAUD_ANALYST"),
    "analyst2": ("Алексей Волков", "FRAUD_ANALYST"),
    "reviewer": ("Елена Соколова", "SENIOR_ANALYST"),
    "manager": ("Анна Орлова", "FRAUD_MANAGER"),
    "rules": ("Максим Морозов", "RULES_ADMIN"),
    "admin": ("Ольга Петрова", "ADMIN"),
}


def seed():
    password = os.getenv("DEMO_PASSWORD", "Sentrix-local-demo")
    if len(password) < 12:
        raise ValueError("DEMO_PASSWORD requires 12 characters")
    with engine.begin() as conn:
        lock(conn, "seed", "once")
        if one(conn, "SELECT login FROM users WHERE login='admin'"):
            return
        for login, (name, role) in USERS.items():
            query(
                conn,
                "INSERT INTO users VALUES (:login,:name,:password,:role)",
                login=login,
                name=name,
                password=passwords.hash(password),
                role=role,
            )
        for n in range(1, 9):
            category = "GROCERY" if n % 2 else "SERVICES"
            query(
                conn,
                "INSERT INTO customers VALUES (:id,:name,:category)",
                id=f"C-{n:03}",
                name=f"Учебный профиль {n:02}",
                category=category,
            )
            query(
                conn,
                "INSERT INTO accounts VALUES (:id,:customer)",
                id=f"A-{n:03}",
                customer=f"C-{n:03}",
            )
        for code, (name, params, _) in RULES.items():
            query(
                conn,
                "INSERT INTO rules(code,name) VALUES (:code,:name)",
                code=code,
                name=name,
            )
            query(
                conn,
                """INSERT INTO rule_versions(code,version,status,parameters,reason,author,publisher,published_at)
              VALUES (:code,1,'PUBLISHED',CAST(:params AS jsonb),'Исходная учебная конфигурация','rules','manager',now())""",
                code=code,
                params=packed({k: default for k, (_, _, default) in params.items()}),
            )
        noon = (datetime.now(UTC) - timedelta(days=1)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        events = []
        for n in range(1, 6):
            for i in range(6, 0, -1):
                events.append(
                    Event(
                        source="seed",
                        external_id=f"baseline-{n}-{i}",
                        account=f"A-{n:03}",
                        amount=90_000 + 2300 * i,
                        category="GROCERY" if n % 2 else "SERVICES",
                        channel="CARD",
                        recipient="synthetic-shop",
                        occurred_at=noon - timedelta(days=i),
                    )
                )
        for n in range(1, 5):
            events.append(
                Event(
                    source="seed",
                    external_id=f"review-{n}",
                    account=f"A-{n:03}",
                    amount=17_000_000 + n * 1_350_000,
                    category="TRANSFER" if n % 2 else "SERVICES",
                    channel="MOBILE",
                    recipient="synthetic-new",
                    occurred_at=noon + timedelta(minutes=n),
                )
            )
        ingest(conn, events, "admin", uuid4())
        query(conn, "UPDATE cases SET assignee='analyst' WHERE customer='C-001'")


if __name__ == "__main__":
    seed()
