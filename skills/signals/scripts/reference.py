"""R8-04: the frozen anomaly reference, computed in code (reviewers never reproduce it by eye).

YES if |Δ| of the item's session (bp) ≥ the q-quantile (default 0.975) of |Δ| over the 250 most recent VALID prior daily
changes of the same series (a change is valid only when both adjacent official values exist; nulls are skipped, never
filled). Fewer than 250 valid prior changes → UNASSESSABLE (excluded from the estimator's denominator, never FALSE).
Quantile: linear interpolation between order statistics (Hyndman-Fan type 7, numpy's default). A value exactly on the
cutoff is YES (≥). This measures membership in a statistical tail of recent history. It is NOT market relevance, a hit
rate or predictive accuracy."""
N_PRIOR = 250
Q = 0.975


def percentile(xs, q):
    v = sorted(xs)
    if not v:
        raise ValueError("empty")
    h = (len(v) - 1) * q
    lo = int(h)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (h - lo)


def tail_flag(values, idx, q=Q, n=N_PRIOR):
    """values: official series (percent units, None = missing) in session order; idx: the item's session index."""
    if idx < 1 or values[idx] is None or values[idx - 1] is None:
        return {"status": "UNASSESSABLE", "reason": "item change not observable", "priorValidChanges": 0}
    ch = [round(abs(b - a) * 100, 6) for a, b in zip(values[:idx - 1], values[1:idx]) if a is not None and b is not None]
    if len(ch) < n:
        return {"status": "UNASSESSABLE", "reason": f"{len(ch)} valid prior changes < {n}", "priorValidChanges": len(ch)}
    cut = round(percentile(ch[-n:], q), 6)
    x = round(abs(values[idx] - values[idx - 1]) * 100, 6)
    return {"status": "YES" if x >= cut else "NO", "changeBp": x, "cutoffBp": cut, "quantile": q, "priorValidChanges": len(ch)}
