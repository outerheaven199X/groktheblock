"""R8-03 / R9-02: design-based estimators for the Treasury study. Only PROBABILITY_SAMPLE items enter population estimates;
EPISODE, QUIET_CONTROL and BOUNDARY_CHALLENGE items are excluded unless the same item was also drawn by the probability design.

Point estimate: stratified ratio (Hájek) estimate, Σ_h N_h·p̂_h / Σ_h N_h, where p̂_h is the share among ASSESSABLE labelled items
of stratum h (UNASSESSABLE is treated as within-stratum non-response and reported, never as a negative).
Variance (R9-02): stratified simple random sampling WITHOUT replacement, Σ_h N_h²·(1 − n_h/N_h)·s²_h / m_h, divided by the
squared covered population. The finite-population correction makes a fully enumerated stratum (n_h = N_h) contribute zero.
Normal 95% interval, clipped to [0, 1]. Coverage is reported per stratum; a stratum with no assessable item is listed in
missingStrata and the estimate then describes only the covered population (fullPopulation = False, publishable = False).
Strata with one assessable item have no variance estimate (also not publishable). A pooled unweighted share is refused."""
import math


class EstimatorError(Exception):
    pass


def population_share(labels: dict, sealed: dict, design: dict, label: str, reps=None, seed=None) -> dict:
    strata = {s["stratumKey"]: s for s in design["strata"]}
    excluded, lab = {}, {k: [] for k in strata}
    for iid, y in labels.items():
        k = sealed[iid]
        if "PROBABILITY_SAMPLE" not in k["components"]:
            for c in k["components"]:
                excluded[c] = excluded.get(c, 0) + 1
            continue
        s = strata.get(k["stratumKey"])
        if s is None or abs(k["inclusionProbability"] - s["inclusionProbability"]) > 1e-12:
            raise EstimatorError(f"{iid}: stratum / inclusion probability disagrees with the frozen design")
        lab[k["stratumKey"]].append(y)
    by, num, cov, var, problems = {}, 0.0, 0, 0.0, []
    for h, s in strata.items():
        ys = [1.0 if y == label else 0.0 for y in lab[h] if y != "UNASSESSABLE"]
        m, N, n = len(ys), s["N"], s["n"]
        fpc = 1 - n / N
        p = sum(ys) / m if m else None
        vc = None
        if m >= 2:
            s2 = sum((y - p) ** 2 for y in ys) / (m - 1)
            vc = N * N * fpc * s2 / m
        elif m == 1 and fpc == 0:
            vc = 0.0
        elif m == 1:
            problems.append(h)
        by[h] = {"N": N, "n": n, "labelled": len(lab[h]), "assessable": m, "share": p, "fpc": fpc, "varianceContribution": vc}
        if m:
            num += N * p; cov += N
            var += vc or 0.0
    total = sum(s["N"] for s in strata.values())
    missing = sorted(h for h, b in by.items() if b["assessable"] == 0)
    est = num / cov if cov else None
    se = math.sqrt(var) / cov if cov else None
    for h in by:
        if by[h]["varianceContribution"] is not None and cov:
            by[h]["varianceContribution"] = by[h]["varianceContribution"] / (cov * cov)
    complete = all(b["labelled"] == b["n"] and b["assessable"] == b["n"] for b in by.values())
    publishable = bool(cov) and not missing and not problems
    warn = []
    if missing:
        warn.append(f"no assessable item in strata {', '.join(missing)}: the estimate covers only {cov}/{total} windows")
    if problems:
        warn.append(f"one assessable item in strata {', '.join(problems)}: no variance estimate")
    lo = hi = None
    if est is not None and se is not None:
        lo, hi = max(0.0, est - 1.96 * se), min(1.0, est + 1.96 * se)
        if se == 0:
            lo = hi = est
    return {"label": label, "estimate": est, "standardError": se, "itemsUsed": sum(b["assessable"] for b in by.values()), "excluded": excluded,
            "interval": {"method": "stratified SRSWOR linearization with finite-population correction, normal 95%", "low": lo, "high": hi},
            "byStratum": by, "coverage": {"missingStrata": missing, "fullPopulation": not missing, "complete": complete,
                                          "populationCoveredShare": cov / total if total else None},
            "publishable": publishable, "warning": "; ".join(warn) or None}


def pooled_share(labels, label):
    raise EstimatorError("pooled unweighted share across EPISODE/QUIET_CONTROL/PROBABILITY_SAMPLE/BOUNDARY_CHALLENGE is not an estimator of anything; refused")
