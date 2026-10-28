"""R7-01: the frozen r7 decision table (docs/review/adjudication-r7.json) as code. Three orthogonal axes:
anomaly (independent reference distribution), integrity (evidence/timing), context (explanation). The context axis
never changes the primary label: an unexplained valid anomaly is ANOMALY_CONFIRMED, an integrity error is FALSE
whatever the news. This module labels nothing by itself; it only maps a reviewer's axis answers to labels."""
import json
from pathlib import Path

TABLE = json.loads((Path(__file__).resolve().parents[3] / "docs/review/adjudication-r7.json").read_text())


def _match(pat, v):
    return pat == "*" or v in pat.split("|")


def decide(axes: dict) -> dict:
    for k in ("anomaly", "integrity", "context"):
        if axes.get(k) not in TABLE["axes"][k]["values"]:
            raise ValueError(f"{k}={axes.get(k)!r} not in the frozen table")
    for row in TABLE["decisionTable"]:
        if _match(row["integrity"], axes["integrity"]) and _match(row["anomaly"], axes["anomaly"]):
            return {"primary": row["primary"], "context": axes["context"], "tableVersion": TABLE["version"]}
    raise ValueError("decision table is not exhaustive")
