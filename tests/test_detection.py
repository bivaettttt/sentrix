from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sentrix.contracts import Event
from sentrix.detection import RULES, features, score, validated

POINT = datetime(2025, 3, 1, 12, tzinfo=UTC)
VERSIONS = [
    {
        "code": code,
        "id": code,
        "version": 1,
        "parameters": {k: entry[2] for k, entry in params.items()},
    }
    for code, (_, params, _) in RULES.items()
]


def test_cold_start():
    input = {
        "amount": 100,
        "occurred_at": POINT,
        "category": "GROCERY",
        "recipient": "shop",
    }
    computed = score(features(input, [], "GROCERY"), VERSIONS)
    assert computed["anomaly"]["status"] == "COLD_START"
    assert computed["risk"] == "LOW"


def test_explanation_and_snapshot():
    input = {
        "amount": 20_000_000,
        "occurred_at": POINT,
        "category": "TRANSFER",
        "recipient": "new",
    }
    history = [
        {
            "amount": 100_000,
            "occurred_at": POINT - timedelta(days=i + 1),
            "recipient": "shop",
        }
        for i in range(6)
    ]
    snapshot = features(input, history, "GROCERY")
    result = score(snapshot, VERSIONS)
    assert result == score(snapshot, reversed(VERSIONS))
    assert result["risk"] == "CRITICAL"
    assert result["anomaly"]["amount_outlier"]
    assert {row["code"] for row in result["evaluations"] if row["hit"]} == {
        "R-01",
        "R-03",
        "R-04",
        "R-05",
        "R-08",
    }


@pytest.mark.parametrize(
    "invalid", [{"threshold": True}, {"threshold": 0}, {"threshold": 1, "code": 2}, {}]
)
def test_reject_invalid_rule(invalid):
    with pytest.raises(ValueError):
        validated("R-01", invalid)


def test_reject_float_and_naive_timestamp():
    request = dict(
        source="unit",
        external_id="1",
        account="A-001",
        currency="RUB",
        category="GROCERY",
        channel="CARD",
        recipient="synthetic",
        occurred_at=POINT,
    )
    with pytest.raises(ValidationError):
        Event(amount=1.2, **request)
    with pytest.raises(ValidationError):
        Event(amount=12, **(request | {"occurred_at": "2025-01-01T12:00:00"}))
