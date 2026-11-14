from fastapi import HTTPException

from sentrix.db import audit, many, one, packed, query

TRANSITIONS = {
    "triage": (("NEW",), "TRIAGED"),
    "investigate": (("TRIAGED",), "INVESTIGATING"),
    "request_information": (("INVESTIGATING",), "NEEDS_INFORMATION"),
    "resume": (("NEEDS_INFORMATION",), "INVESTIGATING"),
    "submit": (("INVESTIGATING",), "REVIEW_REQUIRED"),
    "return": (("REVIEW_REQUIRED",), "INVESTIGATING"),
    "close": (("REVIEW_REQUIRED",), None),
}


def visible(case, actor):
    role = actor["role"]
    if (
        case is None
        or (role == "FRAUD_ANALYST" and case["assignee"] != actor["login"])
        or role == "RULES_ADMIN"
    ):
        raise HTTPException(404, "CASE_NOT_FOUND")
    return case


def detail(conn, id, actor):
    case = visible(
        one(
            conn,
            """SELECT c.*,u.name AS assignee_name,p.name AS customer_name,
       (c.first_review IS NULL AND now()>c.created_at+interval '2 hours') AS triage_overdue,
       (now()>c.due_at AND c.closed_at IS NULL) AS overdue FROM cases c JOIN customers p ON p.id=c.customer
       LEFT JOIN users u ON u.login=c.assignee WHERE c.id=:id""",
            id=id,
        ),
        actor,
    )
    case["entries"] = many(
        conn, "SELECT * FROM case_entries WHERE case_id=:id ORDER BY id", id=id
    )
    case["alerts"] = many(
        conn,
        """SELECT a.id,a.severity,t.id AS transaction,t.amount,t.category,t.occurred_at,
       s.score,s.evaluations,s.anomaly FROM alerts a JOIN assessments s ON s.id=a.assessment
       JOIN transactions t ON t.id=s.transaction WHERE a.case_id=:id ORDER BY a.created_at,a.id""",
        id=id,
    )
    return case


def perform(conn, id, payload, actor, request):
    row = visible(
        one(conn, "SELECT * FROM cases WHERE id=:id FOR UPDATE", id=id), actor
    )
    role = actor["role"]
    who = actor["login"]
    action = payload.action
    status = row["status"]
    if row["revision"] != payload.revision:
        raise HTTPException(409, "STALE_CASE")
    if status.startswith("CLOSED_"):
        raise HTTPException(409, "CASE_CLOSED")

    assignment = row["assignee"]
    submitter = row["submitter"]
    kind = "TRANSITION"
    data = {"old_status": status, "old_assignee": assignment}
    if action == "assign":
        if role != "FRAUD_MANAGER":
            raise HTTPException(403, "ASSIGNMENT_FORBIDDEN")
        if status == "REVIEW_REQUIRED":
            raise HTTPException(409, "REVIEW_LOCKED")
        if not one(
            conn,
            "SELECT login FROM users WHERE login=:u AND role='FRAUD_ANALYST'",
            u=payload.assignee,
        ):
            raise HTTPException(422, "INVALID_ASSIGNEE")
        assignment = payload.assignee
        kind = "ASSIGNMENT"
    elif action in ("close", "return"):
        if role != "SENIOR_ANALYST" or submitter == who:
            raise HTTPException(403, "INDEPENDENT_REVIEW_REQUIRED")
        if status != "REVIEW_REQUIRED":
            raise HTTPException(409, "INVALID_TRANSITION")
        if action == "close":
            if payload.outcome is None:
                raise HTTPException(422, "OUTCOME_REQUIRED")
            status = "CLOSED_" + payload.outcome
            kind = "DECISION"
            data["outcome"] = payload.outcome
            data["evidence"] = [
                e["id"]
                for e in many(
                    conn,
                    "SELECT id FROM case_entries WHERE case_id=:id AND kind='EVIDENCE' ORDER BY id",
                    id=id,
                )
            ]
            data["alerts"] = [
                str(e["id"])
                for e in many(
                    conn, "SELECT id FROM alerts WHERE case_id=:id ORDER BY id", id=id
                )
            ]
        else:
            status, submitter = "INVESTIGATING", None
    else:
        if role != "FRAUD_ANALYST" or assignment != who:
            raise HTTPException(403, "ASSIGNEE_REQUIRED")
        if action in ("comment", "evidence"):
            if status == "REVIEW_REQUIRED":
                raise HTTPException(409, "REVIEW_LOCKED")
            kind = action.upper()
        else:
            allowed, target = TRANSITIONS[action]
            if status not in allowed:
                raise HTTPException(409, "INVALID_TRANSITION")
            status = target
            if action == "submit":
                if not one(
                    conn,
                    "SELECT id FROM case_entries WHERE case_id=:id AND kind='EVIDENCE' LIMIT 1",
                    id=id,
                ):
                    raise HTTPException(422, "EVIDENCE_REQUIRED")
                submitter = who
    data.update(status=status, assignee=assignment)
    update = one(
        conn,
        """UPDATE cases SET revision=revision+1,status=:status,assignee=:assignee,
       submitter=:submitter, first_review=CASE WHEN :action='triage' THEN now() ELSE first_review END,
       closed_at=CASE WHEN :action='close' THEN now() ELSE NULL END
       WHERE id=:id RETURNING *""",
        id=id,
        status=status,
        assignee=assignment,
        submitter=submitter,
        action=action,
    )
    query(
        conn,
        """INSERT INTO case_entries(case_id,kind,author,body,revision,details)
          VALUES (:id,:kind,:author,:body,:revision,CAST(:details AS jsonb))""",
        id=id,
        kind=kind,
        author=who,
        body=payload.reason,
        revision=payload.revision,
        details=packed(data),
    )
    audit(conn, who, request, "CASE_" + action.upper(), id, **data)
    return update
