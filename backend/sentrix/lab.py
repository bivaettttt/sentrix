import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from sentrix.db import engine, one, query


class Scenario(StrEnum):
    normal = "normal"
    large = "large"
    burst = "burst"
    outlier = "outlier"
    recipient = "recipient"
    combination = "combination"
    duplicate = "duplicate"
    invalid = "invalid"
    late = "late"
    version = "version"
    reassessment = "reassessment"
    multiple_alerts = "multiple_alerts"
    grouping = "grouping"
    assignment = "assignment"
    escalation = "escalation"
    false_positive = "false_positive"
    confirmed = "confirmed"
    concurrency = "concurrency"
    close_replay = "close_replay"
    compare = "compare"
    sla = "sla"
    recovery = "recovery"


def run(scenario):
    code = "L-" + uuid4().hex[:10]
    with engine.begin() as conn:
        query(
            conn,
            "INSERT INTO customers VALUES (:c,:name,'GROCERY')",
            c=code,
            name="Профиль лаборатории " + code,
        )
        query(conn, "INSERT INTO accounts VALUES (:c,:c)", c=code)
    traffic, checks, tokens = [], {}, {}
    endpoint = "http://127.0.0.1:8000/api"
    point = (datetime.now(UTC) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    state = None

    def request(actor, method, path, data=None, key=None):
        headers = {"Content-Type": "application/json"}
        if actor not in tokens and actor:
            _, session = request(
                None,
                "POST",
                "/auth/login",
                {"login": actor, "password": os.environ["DEMO_PASSWORD"]},
            )
            tokens[actor] = session["token"]
        if actor:
            headers["Authorization"] = "Bearer " + tokens[actor]
        if key:
            headers["Idempotency-Key"] = key
        message = Request(
            endpoint + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        try:
            reply = urlopen(message, timeout=8)
        except HTTPError as error:
            reply = error
        with reply:
            raw = reply.read()
            body = json.loads(raw) if raw else None
            if actor:
                traffic.append(
                    {
                        "actor": actor,
                        "method": method,
                        "path": path,
                        "input": data,
                        "status": reply.status,
                        "request_id": reply.headers["X-Request-ID"],
                        "response": body,
                    }
                )
            return reply.status, body

    def send(actor, method, path, data=None, expected=200, key=None):
        status, body = request(actor, method, path, data, key)
        if status != expected:
            raise RuntimeError(
                f"{method} {path} returned {status}, expected {expected}"
            )
        return body

    def event(
        i,
        amount=19_000_000,
        instant=point,
        recipient="laboratory-shop",
        category="GROCERY",
    ):
        return {
            "source": code,
            "external_id": str(i),
            "account": code,
            "amount": amount,
            "category": category,
            "channel": "CARD",
            "recipient": recipient,
            "occurred_at": instant.isoformat(),
        }

    def accept(data):
        return send("analyst", "POST", "/transactions", data, 201)

    def hit(item, rule):
        return next(
            e["hit"] for e in item["assessment"]["evaluations"] if e["code"] == rule
        )

    def change(threshold):
        v = send(
            "rules",
            "POST",
            "/rules/R-01/versions",
            {
                "parameters": {"threshold": threshold},
                "reason": "Изолированная проверка",
            },
            201,
        )
        path = f"/rules/versions/{v['id']}"
        send("rules", "POST", path + "/submit")
        return send("manager", "POST", path + "/publish")

    if scenario in {Scenario.outlier, Scenario.recipient, Scenario.combination}:
        for i in range(6, 0, -1):
            accept(event(f"base-{i}", 100_000, point - timedelta(days=i)))
        result = accept(
            event(
                1,
                2_000_000
                if scenario == Scenario.outlier
                else 19_000_000
                if scenario == Scenario.combination
                else 100_000,
                recipient="laboratory-new",
                category="TRANSFER" if scenario == Scenario.combination else "GROCERY",
            )
        )
        checks["expected_factor"] = hit(
            result,
            {
                Scenario.outlier: "R-03",
                Scenario.recipient: "R-05",
                Scenario.combination: "R-08",
            }[scenario],
        )
    elif scenario == Scenario.invalid:
        send("analyst", "POST", "/transactions", event(1, -1), 422)
        checks["no_transaction"] = not send("analyst", "GET", "/transactions?q=" + code)
        with engine.connect() as conn:
            checks["no_stored_event"] = (
                one(
                    conn,
                    "SELECT count(*) AS n FROM transactions WHERE source=:c",
                    c=code,
                )["n"]
                == 0
            )
    elif scenario == Scenario.recovery:
        with engine.begin() as conn:
            query(conn, "INSERT INTO lab_faults VALUES (:c)", c=code)
        try:
            send("analyst", "POST", "/transactions", event(1), 503)
            with engine.connect() as conn:
                checks["rollback"] = (
                    one(
                        conn,
                        "SELECT count(*) AS n FROM transactions WHERE source=:c",
                        c=code,
                    )["n"]
                    == 0
                )
        finally:
            with engine.begin() as conn:
                query(conn, "DELETE FROM lab_faults WHERE source=:c", c=code)
        checks["retry_accepted"] = not accept(event(1))["duplicate"]
    elif scenario == Scenario.burst:
        for i in range(5):
            result = accept(event(i, 100_000, point + timedelta(minutes=i)))
        checks["velocity_rule"] = hit(result, "R-02")
    elif scenario in {Scenario.version, Scenario.reassessment, Scenario.compare}:
        rule = next(r for r in send("rules", "GET", "/rules") if r["code"] == "R-01")
        original = next(v for v in rule["versions"] if v["status"] == "PUBLISHED")
        if scenario == Scenario.compare:
            compared = send(
                "rules",
                "POST",
                "/rules/R-01/preview",
                {
                    "parameters": {"threshold": 100_000_000_000},
                    "reason": "Фиксированный набор",
                },
            )
            checks["same_sample_has_changed_results"] = len(compared) > 0 and any(
                x["before"]["score"] != x["after"]["score"] for x in compared
            )
        else:
            first = accept(event(1))
            try:
                published = change(100_000_000_000)
                checks["new_rule_version"] = published["version"] > original["version"]
                evaluated = send(
                    "manager",
                    "POST",
                    f"/transactions/{first['transaction']}/evaluations",
                )
                checks["separate_assessment"] = (
                    evaluated["id"] != first["assessment"]["id"]
                )
                checks["old_assessment_preserved"] = (
                    accept(event(1))["assessment"] == first["assessment"]
                )
                checks["reassessment_idempotent"] = (
                    send(
                        "manager",
                        "POST",
                        f"/transactions/{first['transaction']}/evaluations",
                    )["id"]
                    == evaluated["id"]
                )
            finally:
                change(original["parameters"]["threshold"])
    elif scenario in {
        Scenario.normal,
        Scenario.large,
        Scenario.duplicate,
        Scenario.late,
    }:
        item = accept(
            event(
                1,
                100_000
                if scenario in {Scenario.normal, Scenario.late}
                else 100_000_000_000,
                point - timedelta(days=40) if scenario == Scenario.late else point,
            )
        )
        state = send("analyst", "GET", f"/transactions/{item['transaction']}")
        if scenario == Scenario.duplicate:
            copy = accept(event(1, 100_000_000_000))
            checks["same_result"] = (
                copy["duplicate"] and copy["assessment"] == item["assessment"]
            )
        elif scenario == Scenario.late:
            checks["flagged_late"] = state["late"]
        elif scenario == Scenario.large:
            checks["large_amount_hit"] = hit(item, "R-01")
        else:
            checks["low_risk"] = item["assessment"]["risk"] == "LOW"
            checks["no_alert"] = not send("manager", "GET", "/cases?q=" + code)
    else:
        first = accept(event(1, 100_000_000_000))
        case = send("manager", "GET", "/cases?q=" + code)[0]
        path = f"/cases/{case['id']}"
        if scenario in {Scenario.grouping, Scenario.multiple_alerts}:
            second = accept(event(2, 100_000_000_000, point + timedelta(minutes=1)))
            cases = send("manager", "GET", "/cases?q=" + code)
            checks["one_case"] = len(cases) == 1
            checks["both_alerts"] = {
                a["transaction"] for a in send("manager", "GET", path)["alerts"]
            } == {first["transaction"], second["transaction"]}
        elif scenario == Scenario.sla:
            with engine.begin() as conn:
                query(
                    conn,
                    "UPDATE cases SET created_at=now()-interval '25 hours',due_at=now()-interval '1 hour' WHERE id=:id",
                    id=case["id"],
                )
            state = send("manager", "GET", path)
            checks["overdue"] = state["overdue"] and state["triage_overdue"]
        else:

            def command(actor, action, **data):
                return send(
                    actor,
                    "POST",
                    path + "/commands",
                    {
                        "revision": case["revision"],
                        "action": action,
                        "reason": "Демонстрация расследования",
                        **data,
                    },
                    key=uuid4().hex,
                )

            case = command("manager", "assign", assignee="analyst")
            checks["assigned"] = case["assignee"] == "analyst"
            if scenario != Scenario.assignment:
                for action in ["triage", "investigate", "evidence", "submit"]:
                    case = command("analyst", action)
                checks["submitted"] = case["status"] == "REVIEW_REQUIRED"
                if scenario != Scenario.escalation:
                    key = uuid4().hex
                    data = {
                        "revision": case["revision"],
                        "action": "close",
                        "reason": "Независимое учебное решение",
                        "outcome": "CONFIRMED"
                        if scenario == Scenario.confirmed
                        else "FALSE_POSITIVE",
                    }
                    if scenario == Scenario.concurrency:

                        def decide(index):
                            selected = (
                                data if index == 0 else data | {"outcome": "CONFIRMED"}
                            )
                            return request(
                                "reviewer",
                                "POST",
                                path + "/commands",
                                selected,
                                key=str(index) + key,
                            )

                        send("reviewer", "GET", path)
                        with ThreadPoolExecutor(2) as pool:
                            attempts = list(pool.map(decide, [0, 1]))
                        checks["single_winner"] = sorted(
                            status for status, _ in attempts
                        ) == [200, 409]
                    else:
                        final = send(
                            "reviewer", "POST", path + "/commands", data, key=key
                        )
                        checks["closed"] = (
                            final["status"] == "CLOSED_" + data["outcome"]
                        )
                        if scenario == Scenario.close_replay:
                            checks["same_response"] = (
                                send(
                                    "reviewer",
                                    "POST",
                                    path + "/commands",
                                    data,
                                    key=key,
                                )
                                == final
                            )
                    checks["one_decision"] = (
                        sum(
                            e["kind"] == "DECISION"
                            for e in send("reviewer", "GET", path)["entries"]
                        )
                        == 1
                    )
        state = send("manager", "GET", path)
    if state is None:
        with engine.connect() as conn:
            state = one(
                conn,
                "SELECT count(*) AS transactions FROM transactions WHERE source=:c",
                c=code,
            )
    for actor in tokens:
        request(actor, "POST", "/auth/logout")
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "state": state,
        "traffic": traffic,
    }
