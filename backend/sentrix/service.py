from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from sentrix.db import audit, lock, many, one, packed, query
from sentrix.detection import METHODOLOGY, RULES, features, score, validated


def fingerprint(data):
    return sha256(packed(data).encode()).hexdigest()


def active_versions(conn):
    return many(
        conn,
        """SELECT DISTINCT ON (v.code) v.id,v.code,v.version,v.parameters
       FROM rule_versions v JOIN rules r ON r.code=v.code
       WHERE r.enabled AND v.status='PUBLISHED' ORDER BY v.code,v.version DESC""",
    )


def assessment(conn, tx, versions, actor, request):
    basis = fingerprint([METHODOLOGY, [str(v["id"]) for v in versions]])
    item = one(
        conn,
        "SELECT * FROM assessments WHERE transaction=:tx AND basis=:basis",
        tx=tx["id"],
        basis=basis,
    )
    if item:
        return item
    result = score(tx["features"], versions)
    item = one(
        conn,
        """INSERT INTO assessments(transaction,basis,methodology,score,risk,evaluations,anomaly)
       VALUES (:tx,:basis,:methodology,:score,:risk,CAST(:evaluations AS jsonb),CAST(:anomaly AS jsonb)) RETURNING *""",
        tx=tx["id"],
        basis=basis,
        **(
            result
            | {
                "evaluations": packed(result["evaluations"]),
                "anomaly": packed(result["anomaly"]),
            }
        ),
    )
    if item["risk"] in ("HIGH", "CRITICAL"):
        register_alert(conn, tx, item, actor, request)
    audit(
        conn,
        actor,
        request,
        "ASSESSED",
        item["id"],
        risk=item["risk"],
        transaction=tx["id"],
    )
    return item


def register_alert(conn, tx, item, actor, request):
    instant = one(conn, "SELECT clock_timestamp() AS instant")["instant"]
    window = instant.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    priority = 2 if item["risk"] == "CRITICAL" else 1
    case = one(
        conn,
        """SELECT id,priority,due_at FROM cases WHERE customer=:customer AND window_start=:window
       AND status IN ('NEW','TRIAGED','INVESTIGATING','NEEDS_INFORMATION') ORDER BY number DESC LIMIT 1 FOR UPDATE""",
        customer=tx["customer"],
        window=window,
    )
    if case is None:
        case = one(
            conn,
            """INSERT INTO cases(customer,window_start,priority,due_at)
           VALUES (:customer,:window,:priority,:due) RETURNING id""",
            customer=tx["customer"],
            window=window,
            priority=priority,
            due=instant + timedelta(hours=4 if priority == 2 else 24),
        )
        audit(conn, actor, request, "CASE_OPENED", case["id"])
    else:
        query(
            conn,
            """UPDATE cases SET revision=revision+1,priority=greatest(priority,:priority),
          due_at=CASE WHEN :priority=2 THEN least(due_at,created_at+interval '4 hours') ELSE due_at END WHERE id=:id""",
            id=case["id"],
            priority=priority,
        )
    alert = one(
        conn,
        """INSERT INTO alerts(assessment,case_id,severity) VALUES (:a,:c,:s) RETURNING id""",
        a=item["id"],
        c=case["id"],
        s=item["risk"],
    )
    audit(conn, actor, request, "ALERT_CREATED", alert["id"], case=case["id"])


def ingest(conn, events, actor, request):
    data = [
        e.model_dump() | {"occurred_at": e.occurred_at.astimezone(UTC)} for e in events
    ]
    lock(conn, "rules", "global", shared=True)
    # Acquire batch locks in one order before reading mutable customer histories.
    for source, external in sorted({(e["source"], e["external_id"]) for e in data}):
        lock(conn, "event", f"{source}:{external}")
    accounts = {
        row["id"]: row
        for row in many(
            conn,
            """SELECT a.id,a.customer,c.category FROM accounts a
              JOIN customers c ON c.id=a.customer WHERE a.id=ANY(:ids)""",
            ids=list({e["account"] for e in data}),
        )
    }
    if set(accounts) != {e["account"] for e in data}:
        raise HTTPException(422, "UNKNOWN_ACCOUNT")
    for customer in sorted({a["customer"] for a in accounts.values()}):
        lock(conn, "customer", customer)
    versions = active_versions(conn)
    instant = datetime.now(UTC)
    result = []
    for event in data:
        hashed = fingerprint(event)
        existing = one(
            conn,
            "SELECT * FROM transactions WHERE source=:source AND external_id=:external_id",
            source=event["source"],
            external_id=event["external_id"],
        )
        if existing:
            if existing["fingerprint"] != hashed:
                raise HTTPException(409, "EVENT_CONFLICT")
            first = one(
                conn,
                "SELECT * FROM assessments WHERE transaction=:id ORDER BY created_at,id LIMIT 1",
                id=existing["id"],
            )
            result.append(
                {"transaction": existing["id"], "duplicate": True, "assessment": first}
            )
            continue
        end = event["occurred_at"]
        if end > instant + timedelta(minutes=5):
            raise HTTPException(422, "EVENT_IN_FUTURE")
        account = accounts[event["account"]]
        history = many(
            conn,
            """SELECT t.amount,t.recipient,t.occurred_at FROM transactions t JOIN accounts a ON a.id=t.account
             WHERE a.customer=:customer AND t.occurred_at>=:start AND t.occurred_at<:end
             ORDER BY t.occurred_at DESC,t.id LIMIT 1000""",
            customer=account["customer"],
            start=end - timedelta(days=30),
            end=end,
        )
        snapshot = features(event, history, account["category"])
        tx = one(
            conn,
            """INSERT INTO transactions(source,external_id,account,amount,currency,category,channel,recipient,occurred_at,
           fingerprint,late,features) VALUES (:source,:external_id,:account,:amount,:currency,:category,:channel,:recipient,:occurred_at,
           :fingerprint,:late,CAST(:features AS jsonb)) RETURNING *""",
            **event,
            fingerprint=hashed,
            late=end < instant - timedelta(days=30),
            features=packed(snapshot),
        )
        computed = assessment(
            conn, tx | {"customer": account["customer"]}, versions, actor, request
        )
        audit(conn, actor, request, "INGESTED", tx["id"], late=tx["late"])
        result.append(
            {"transaction": tx["id"], "duplicate": False, "assessment": computed}
        )
    return result


def reassess(conn, id, actor, request):
    lock(conn, "rules", "global", shared=True)
    tx = one(
        conn,
        """SELECT t.*,a.customer FROM transactions t JOIN accounts a ON a.id=t.account WHERE t.id=:id""",
        id=id,
    )
    if tx is None:
        raise HTTPException(404, "TRANSACTION_NOT_FOUND")
    lock(conn, "customer", tx["customer"])
    return assessment(conn, tx, active_versions(conn), actor, request)


def receipt(conn, actor, key, payload, operation):
    if not key:
        raise HTTPException(422, "IDEMPOTENCY_KEY_REQUIRED")
    lock(conn, "receipt", f"{actor}:{key}")
    hashed = fingerprint(payload)
    existing = one(
        conn,
        "SELECT * FROM receipts WHERE actor=:actor AND key=:key",
        actor=actor,
        key=key,
    )
    if existing:
        if existing["fingerprint"] != hashed:
            raise HTTPException(409, "COMMAND_CONFLICT")
        return existing["result"]
    result = jsonable_encoder(operation())
    query(
        conn,
        "INSERT INTO receipts VALUES (:actor,:key,:fingerprint,CAST(:result AS jsonb))",
        actor=actor,
        key=key,
        fingerprint=hashed,
        result=packed(result),
    )
    return result


def rule_parameters(code, parameters):
    if code not in RULES:
        raise HTTPException(404, "RULE_NOT_FOUND")
    try:
        return validated(code, parameters)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def create_draft(conn, code, payload, actor, request):
    params = rule_parameters(code, payload.parameters)
    lock(conn, "rule", code)
    v = one(
        conn,
        """INSERT INTO rule_versions(code,version,status,parameters,reason,author)
          SELECT :code,COALESCE(max(version),0)+1,'DRAFT',CAST(:parameters AS jsonb),:reason,:actor
          FROM rule_versions WHERE code=:code RETURNING *""",
        code=code,
        parameters=packed(params),
        reason=payload.reason,
        actor=actor,
    )
    audit(conn, actor, request, "RULE_DRAFTED", v["id"], code=code)
    return v


def rule_transition(conn, id, action, actor, request):
    lock(conn, "rules", "global")
    v = one(conn, "SELECT * FROM rule_versions WHERE id=:id FOR UPDATE", id=id)
    if v is None:
        raise HTTPException(404, "VERSION_NOT_FOUND")
    rule_parameters(v["code"], v["parameters"])
    if action == "submit":
        if v["status"] != "DRAFT" or v["author"] != actor:
            raise HTTPException(409, "SUBMISSION_CONFLICT")
        sql = "UPDATE rule_versions SET status='SUBMITTED' WHERE id=:id RETURNING *"
    else:
        if v["status"] != "SUBMITTED" or v["author"] == actor:
            raise HTTPException(409, "PUBLICATION_CONFLICT")
        if one(
            conn,
            "SELECT id FROM rule_versions WHERE code=:code AND status='PUBLISHED' AND version>=:version",
            code=v["code"],
            version=v["version"],
        ):
            raise HTTPException(409, "STALE_VERSION")
        sql = """UPDATE rule_versions SET status='PUBLISHED',published_at=now(),publisher=:actor WHERE id=:id RETURNING *"""
    result = one(conn, sql, id=id, actor=actor)
    audit(conn, actor, request, "RULE_" + action.upper(), id, code=v["code"])
    return result
