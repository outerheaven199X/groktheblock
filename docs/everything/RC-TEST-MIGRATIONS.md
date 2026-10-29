# Everything RC: intentional test migrations

Existing assertions changed only where the release candidate intentionally changed behaviour. Each changed line carries a `# MIGRATED (RC)` comment.

| Suite | Old assertion | New assertion | Why |
|---|---|---|---|
| `tests/ui/ui_everything.py` | `#views [data-view=universe]` exists and is clicked | Universe is reached via More Markets > All Markets directory (`#nm-more [data-feat=more.all]`); Anomalies is a top-level `#views > [data-view=anomalies]` | Asset-first navigation: Universe is a directory, not the main workflow |
| `tests/ui/ui_everything.py` | `[data-ustat=shipped]` status filter narrows tiles | Covered classes are grouped first (count = shipped count); uncovered sit in one collapsed group | Status filter replaced by grouping so licence-gated classes are not a prominent roadmap |
| `tests/ui/ui_everything.py` | `.tile .nm` inner texts | `.tile .nm` textContent | Uncovered tiles are in a collapsed `<details>`; innerText of hidden nodes is empty |
| `tests/ui/ui_everything.py` | click `[data-uni=pokemon]` | open the "Not covered yet" group, then click | Same grouping change |
| `tests/ui/ui_everything.py` | `[data-uni=fx-majors] svg.spark` | `.tile:has([data-uni=fx-majors]) svg.spark` | Tile split into a tool button and a Details button |
| `tests/ui/ui_everything.py` | Anomalies shows "Live" and synthetic sections together; `[data-aset]` filters | Default mode is Real cached with no synthetic rows; Examples mode holds every synthetic item; `[data-af=aMode]` switches | Synthetic findings belong in an explicit Examples mode |
| `tests/ui/ui_everything.py` | first synthetic row opens the SNES example | the SNES example row is selected by key | Examples now include cross-market example reports, so "first" changed |
| `tests/ui/ui_everything.py` | detail above `.tile` (first) | detail above the grid column | Mobile families start collapsed |
| `tests/ui/ui_v6_sweep.py` | click `[data-uni=mtg]` | open families, then click | Mobile families start collapsed |
| `tests/test_ui_v6_static.py` | network scan over index.html, app.js, stage.js | also scans registry.js | New UI source file |
| `tests/run_all.py` | — | adds `test_registry.py` | New suite |
| `tests/ui/ui_rc.py` (RC-M10, TCG Card Explorer) | every route view in {token … universe} | same list plus `tcg` | New Card Explorer renderer; nothing removed |
| `tests/test_ui_v6_static.py` (TCG) | network scan over index.html, app.js, stage.js, registry.js | also scans tcg.js | New UI source file |
| `tests/run_all.py` (TCG) | — | adds `test_tcg.py` | New suite |

No threshold, detector or fixture was changed.
