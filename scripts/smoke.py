import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

base = os.getenv("SENTRIX_API", "http://127.0.0.1:8000/api")
users = {}


def call(actor, method, path, data=None, expected=200, key=None):
    headers = {}
    if actor:
        headers["Authorization"] = "Bearer " + users[actor]
    if data is not None:
        headers["Content-Type"] = "application/json"
    if key:
        headers["Idempotency-Key"] = key
    request = Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
        method=method,
    )
    try:
        res = urlopen(request, timeout=10)
    except HTTPError as error:
        res = error
    with res:
        result = res.read()
        assert res.status == expected, (method, path, res.status, result[:500])
        assert res.headers["X-Request-ID"]
    return json.loads(result) if result else None


for user in ("manager", "analyst", "analyst2", "reviewer", "rules", "admin"):
    users[user] = call(
        None,
        "POST",
        "/auth/login",
        {"login": user, "password": os.getenv("DEMO_PASSWORD", "Sentrix-local-demo")},
    )["token"]

source = "check-" + uuid4().hex[:12]
instant = (datetime.now(UTC) - timedelta(days=1)).replace(hour=12)


def event(i, amount=19_000_000, occurred=instant):
    return dict(
        source=source,
        external_id=str(i),
        account="A-008",
        amount=amount,
        channel="CARD",
        category="SERVICES",
        recipient="demo-shop",
        occurred_at=occurred.isoformat(),
    )


call(None, "GET", "/transactions", expected=401)
call("rules", "GET", "/cases", expected=403)
first = call("analyst", "POST", "/transactions", event(1), 201)
duplicate = call("analyst", "POST", "/transactions", event(1), 201)
assert (
    duplicate["duplicate"]
    and first["assessment"]["id"] == duplicate["assessment"]["id"]
)
call("analyst", "POST", "/transactions", event(1, 20_000_000), 409)
call("analyst", "POST", "/transactions", event(2, -10), 422)
call(
    "analyst",
    "POST",
    "/transactions/batch",
    {
        "events": [
            event("rollback"),
            event(2, occurred=datetime.now(UTC) + timedelta(days=1)),
        ]
    },
    422,
)
assert not call("analyst", "GET", "/transactions?q=rollback")

with ThreadPoolExecutor(2) as pool:
    repeated = list(
        pool.map(
            lambda _: call("analyst", "POST", "/transactions", event(3), 201), (0, 1)
        )
    )
assert {x["duplicate"] for x in repeated} == {False, True}
assert len({x["transaction"] for x in repeated}) == 1
item = next(
    x
    for x in call("manager", "GET", "/cases")
    if x["customer"] == "C-008" and x["status"] == "NEW"
)
path = f"/cases/{item['id']}"
read = call("manager", "GET", path)
assert {a["transaction"] for a in read["alerts"]} >= {
    first["transaction"],
    repeated[0]["transaction"],
}
call("analyst2", "GET", path, expected=404)


def command(actor, action, key=None, expected=200, **kwargs):
    return call(
        actor,
        "POST",
        path + "/commands",
        {
            "action": action,
            "revision": item["revision"],
            "reason": "Synthetic verification",
            **kwargs,
        },
        expected,
        key or uuid4().hex,
    )


call(
    "manager",
    "POST",
    path + "/commands",
    {
        "action": "assign",
        "revision": item["revision"],
        "reason": "No key",
        "assignee": "analyst",
    },
    422,
)
item = command("manager", "assign", assignee="analyst")
command("analyst", "submit", expected=409)
item = command("analyst", "triage")
item = command("analyst", "investigate")
command("analyst", "submit", expected=422)
item = command("analyst", "evidence")
item = command("analyst", "submit")
command("analyst", "close", expected=403, outcome="CONFIRMED")
keys = [uuid4().hex, uuid4().hex]


def decide(i):
    data = {
        "action": "close",
        "revision": item["revision"],
        "reason": "Independent synthetic review",
        "outcome": ["FALSE_POSITIVE", "CONFIRMED"][i],
    }
    try:
        outcome = call("reviewer", "POST", path + "/commands", data, 200, keys[i])
        return 200, i, outcome, data
    except AssertionError as error:
        assert error.args[0][2] == 409, error
        return 409, i, None, data


with ThreadPoolExecutor(2) as pool:
    attempts = list(pool.map(decide, (0, 1)))
assert sorted(a[0] for a in attempts) == [200, 409]
_, i, final, body = next(a for a in attempts if a[0] == 200)
again = call("reviewer", "POST", path + "/commands", body, 200, keys[i])
assert final == again
assert (
    len(
        [e for e in call("reviewer", "GET", path)["entries"] if e["kind"] == "DECISION"]
    )
    == 1
)
call(
    "rules",
    "POST",
    "/rules/R-01/versions",
    {"parameters": {"threshold": 0}, "reason": "Invalid threshold"},
    422,
)
draft = call(
    "rules",
    "POST",
    "/rules/R-01/versions",
    {"parameters": {"threshold": 99_000_000}, "reason": "Verification change"},
    201,
)
vp = f"/rules/versions/{draft['id']}"
call("rules", "POST", vp + "/publish", expected=403)
call("rules", "POST", vp + "/submit")
call("manager", "POST", vp + "/publish")
rechecked = call("manager", "POST", f"/transactions/{first['transaction']}/evaluations")
assert rechecked["id"] != first["assessment"]["id"]
assert not next(e for e in rechecked["evaluations"] if e["code"] == "R-01")["hit"]
assert (
    first["assessment"]
    == call("analyst", "POST", "/transactions", event(1), 201)["assessment"]
)
assert (
    call("manager", "POST", f"/transactions/{first['transaction']}/evaluations")["id"]
    == rechecked["id"]
)
old = event(4, 100, instant - timedelta(days=35))
header = ",".join(old)
text = header + "\n" + ",".join(str(old[k]) for k in old)
loaded = call("analyst", "POST", "/transactions/import", {"text": text}, 201)[0]
assert call("analyst", "GET", f"/transactions/{loaded['transaction']}")["late"]
assert call("manager", "GET", "/analytics")["summary"]["processed"] >= 4
print(
    "PostgreSQL HTTP smoke: ingestion, rollback, concurrent replay, case scope, grouping, concurrent decision, rule publication, reassessment, CSV and SLA reporting"
)
