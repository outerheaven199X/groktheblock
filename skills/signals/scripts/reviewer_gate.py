"""R9-05: validator for the EXISTING reviewer gate (docs/review/eval-treasury/reviewer-gate-r8.json). No new gate.
A gate may only say PASS when: two independent reviewers are assigned and each has an independently completed record of
all 12 r8 vignettes; a third adjudicator is assigned; the 25-item calibration pilot is complete by both reviewers; and
disagreements are recorded. Identities stay private (records carry opaque refs). Returns a list of problems ([] = valid)."""
VIGNETTES, PILOT = 12, 25


def validate(g: dict) -> list:
    if g.get("status") != "PASS":
        return [] if g.get("status") == "BLOCKED" else [f"unknown status {g.get('status')!r}"]
    errs = []
    rec = g.get("records") or {}
    revs = rec.get("reviewers") or []
    if not g.get("reviewersAssigned") or len(revs) < 2:
        errs.append("two independent reviewer records are required")
    for r in revs:
        if not r.get("independent"):
            errs.append(f"reviewer {r.get('ref')} not recorded as independent")
        if r.get("vignettes") != VIGNETTES:
            errs.append(f"reviewer {r.get('ref')} must have all {VIGNETTES} vignettes recorded")
    if not g.get("adjudicatorAssigned") or not rec.get("adjudicator"):
        errs.append("adjudicator slot is unfilled")
    p = rec.get("pilot") or {}
    if p.get("items") != PILOT or len(set(p.get("completedBy") or [])) < 2:
        errs.append(f"calibration pilot of {PILOT} items not completed by both reviewers")
    if "disagreements" not in rec:
        errs.append("disagreement record missing (record an empty list if none)")
    return errs
