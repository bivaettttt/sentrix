from datetime import timedelta
from fractions import Fraction
from statistics import median

RULES = {
    "R-01": ("Крупная операция", {"threshold": (1, 10**11, 15_000_000)}, 55),
    "R-02": ("Высокая частота", {"count": (2, 1000, 5)}, 55),
    "R-03": ("Отклонение суммы", {"ratio": (2, 100, 6)}, 35),
    "R-04": ("Нетипичная категория", {}, 12),
    "R-05": ("Новый получатель", {}, 18),
    "R-06": ("Нетипичное время", {"start": (0, 23, 6), "end": (1, 24, 23)}, 10),
    "R-07": (
        "Серия около порога",
        {"threshold": (100, 10**11, 15_000_000), "count": (2, 1000, 3)},
        35,
    ),
    "R-08": ("Комбинация факторов", {"count": (2, 7, 3)}, 22),
}
METHODOLOGY = "sentrix-points/1"
HIGH = 50
CRITICAL = 80


def validated(code, parameters):
    limits = RULES[code][1]
    if set(parameters) != set(limits) or any(
        type(parameters[key]) is not int or not lo <= parameters[key] <= hi
        for key, (lo, hi, _) in limits.items()
    ):
        raise ValueError("INVALID_PARAMETERS")
    if code == "R-06" and parameters["start"] >= parameters["end"]:
        raise ValueError("INVALID_TIME_RANGE")
    return parameters


def features(event, history, typical):
    hour = event["occurred_at"]
    recent = [
        r["amount"] for r in history if r["occurred_at"] >= hour - timedelta(minutes=10)
    ]
    base = [
        r["amount"] for r in history if r["occurred_at"] < hour - timedelta(minutes=10)
    ]
    center = int(median(base)) if len(base) >= 5 else None
    mad = int(median([abs(a - center) for a in base])) if center is not None else None
    return {
        "amount": event["amount"],
        "hour": hour.hour,
        "observations": len(history),
        "baseline_count": len(base),
        "recent_amounts": recent,
        "median": center,
        "mad": mad,
        "category": event["category"],
        "typical": typical,
        "recipient_known": any(r["recipient"] == event["recipient"] for r in history),
    }


def score(snapshot, versions):
    f = snapshot
    anomaly = {
        "method": "median-mad/1",
        "status": "COLD_START" if f["median"] is None else "READY",
        "amount_outlier": f["median"] is not None
        and f["amount"] - f["median"] >= 6 * max(f["mad"], f["median"] // 10, 1),
        "unusual_category": f["observations"] >= 5 and f["category"] != f["typical"],
        "burst": len(f["recent_amounts"]) >= 4,
    }
    checks = {
        "R-01": lambda p: f["amount"] >= p["threshold"],
        "R-02": lambda p: len(f["recent_amounts"]) + 1 >= p["count"],
        "R-03": lambda p: (
            f["median"] is not None and f["amount"] >= p["ratio"] * f["median"]
        ),
        "R-04": lambda p: anomaly["unusual_category"],
        "R-05": lambda p: f["observations"] >= 5 and not f["recipient_known"],
        "R-06": lambda p: not p["start"] <= f["hour"] < p["end"],
        "R-07": lambda p: (
            Fraction(8, 10) * p["threshold"] <= f["amount"] < p["threshold"]
            and 1
            + sum(
                Fraction(8, 10) * p["threshold"] <= v < p["threshold"]
                for v in f["recent_amounts"]
            )
            >= p["count"]
        ),
    }
    evaluations = []
    for v in sorted(versions, key=lambda v: v["code"]):
        code = v["code"]
        p = v["parameters"]
        hit = (
            sum(e["hit"] for e in evaluations) >= p["count"]
            if code == "R-08"
            else checks[code](p)
        )
        name, _, points = RULES[code]
        evaluations.append(
            {
                "code": code,
                "name": name,
                "version": v["version"],
                "version_id": str(v["id"]),
                "parameters": p,
                "hit": hit,
                "points": points if hit else 0,
            }
        )
    anomaly["points"] = 15 if anomaly["amount_outlier"] else 0
    value = min(100, sum(e["points"] for e in evaluations) + anomaly["points"])
    risk = (
        "CRITICAL"
        if value >= CRITICAL
        else "HIGH"
        if value >= HIGH
        else "MEDIUM"
        if value >= 25
        else "LOW"
    )
    return {
        "methodology": METHODOLOGY,
        "score": value,
        "risk": risk,
        "evaluations": evaluations,
        "anomaly": anomaly,
    }
