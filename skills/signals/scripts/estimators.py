"""R8-03: design-based estimators for the r8 Treasury study. Only PROBABILITY_SAMPLE items enter population estimates,
weighted by 1/inclusionProbability (Hájek ratio estimator); EPISODE, QUIET_CONTROL and BOUNDARY_CHALLENGE items are
excluded unless the same item was also drawn by the probability design. The interval is a stratified bootstrap (items are
resampled with replacement within each stratum, keeping the stratum sample sizes), not a Wilson interval, which would
ignore unequal inclusion probabilities. A pooled, unweighted share over all items is refused."""
import random


class EstimatorError(Exception):
    pass


def _hajek(items, label):
    num = sum(w for w, y in items if y == label)
    den = sum(w for w, _ in items)
    return num / den if den else None


def population_share(labels: dict, sealed: dict, design: dict, label: str, reps: int = 2000, seed: int = 0) -> dict:
    pi = {s["stratumKey"]: s["inclusionProbability"] for s in design["strata"]}
    excluded, by = {}, {}
    for iid, y in labels.items():
        k = sealed[iid]
        if "PROBABILITY_SAMPLE" not in k["components"]:
            for c in k["components"]:
                excluded[c] = excluded.get(c, 0) + 1
            continue
        if y == "UNASSESSABLE":
            continue
        if abs(k["inclusionProbability"] - pi[k["stratumKey"]]) > 1e-12:
            raise EstimatorError(f"{iid}: inclusion probability disagrees with the frozen design")
        by.setdefault(k["stratumKey"], []).append((1 / k["inclusionProbability"], y))
    items = [x for v in by.values() for x in v]
    est = _hajek(items, label)
    rng = random.Random(seed)
    boots = []
    for _ in range(reps):
        res = [rng.choice(v) for v in by.values() for _ in v]
        b = _hajek(res, label)
        if b is not None:
            boots.append(b)
    boots.sort()
    lo = boots[int(0.025 * (len(boots) - 1))] if boots else None
    hi = boots[int(round(0.975 * (len(boots) - 1)))] if boots else None
    return {"label": label, "estimate": est, "itemsUsed": len(items), "excluded": excluded,
            "interval": {"method": f"stratified bootstrap percentile 95%, {reps} reps, seed {seed}", "low": lo, "high": hi}}


def pooled_share(labels, label):
    raise EstimatorError("pooled unweighted share across EPISODE/QUIET_CONTROL/PROBABILITY_SAMPLE/BOUNDARY_CHALLENGE is not an estimator of anything; refused")
