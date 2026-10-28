# History exposure (R6-04)

## Update 2026-10-28 15:19 ET: coordinated purge done (owner-approved force-push)
With the owner's explicit approval, published history was rewritten using the rehearsed git-filter-repo plan. It removes the listed paths and strips every blob that `tools/verify_history.py` flagged. That covers the scope of the earlier sanitize purge, so old example X data and account/connection data are gone from history. A full mirror and bundle backup was taken first and kept privately; it was not published.

| Ref | Before | After |
|---|---|---|
| main | fd858c0 | aa4de42 |
| ui/investigation-workbench-20261028 | d82465e | 305c51a |
| ui/reference-dark-preserved-20261028 | 8ae120e | b9ec827 |

- **Current files unchanged:** main's tree is byte-identical before and after (`d0f6639…`).
- **Draft branches:** both lost their older screenshots and example files, nothing else. Nothing was merged.
- **Kept:** `examples/provenance-sample.json` (blob `82d5a4f`) is part of the current tree, so it was kept.
- **PR #1:** GitHub moved `refs/pull/1/head` to b9ec827.
- **Verification on a fresh clone from GitHub:** `verify_history` found **0** issues over 28 commits and 567 blobs. A mirror that includes the pull refs also found 0. The leak test reported 144 files clean, and `run_all.py` passed 219/219 counted tests.

**Still exposed:** the purge cannot revoke anything that was **already cloned** before it: forks, local copies, CI caches and third-party mirrors or archives. GitHub may also keep the old commits reachable by SHA, and in cached views or PR history, until GitHub Support expires them on request. If any secrets were in the old commits, they should be treated as public and rotated.

(The text below is the pre-purge record.)


**Status: not resolved in published history.** The current tree (`HEAD`) contains only synthetic or project-generated public samples (see `docs/assets-manifest.json`). Earlier commits on GitHub still contain real on-chain examples and screenshots, raw vendor payloads (`tests/fixtures/providers/`, removed in round 5), and verification screenshots. No history was rewritten and nothing was force-pushed in this round.

## What is exposed
`python tools/verify_history.py` scans every blob reachable from any ref. On the repository at fe02ee3: 21 commits, **177 findings** (145 earlier sample versions, 86 removed paths, 36 blobs with real on-chain identifiers matched by SHA-256 against `tests/fixtures/onchain-denylist.json`, 28 vendor payload shapes; one blob can have several reasons). The commits involved are 918c2ff, 12f9dc1, 6eddfa7, 39e619e, 36c94d1, dcd946e, 9f8515b, 6309ebc, 607c32d, e396a91, 5a431ea, 77707ea, 5db4c29 and c894915. fe02ee3 is the commit that removes them from the tree.

## Purge rehearsal (disposable clone only)
On a disposable `--mirror` clone, git-filter-repo removed the paths and stripped the flagged blob ids. After that, `verify_history` reported **0 findings** over 21 commits, and the HEAD tree hash was unchanged (`75ded00…`). The exact commands and counts are in `history-purge-verification.json`. This was **not run on the real repository**, and nothing was pushed: filter-repo deletes the clone's `origin` remote.

## Options (the owner decides; none is taken here)
1. **Coordinated purge.** (A coordinated purge:) Run the rehearsed filter-repo commands on a fresh mirror, force-push all refs, and have collaborators re-clone. Then ask GitHub Support to expire cached views and dangling objects for PRs and old SHAs. This needs explicit owner approval because it is a force-push. A separate, older a separate local purge checkout force-push is also still pending the owner's decision.
2. **Clean-root repo.** (A clean-root repository:) Publish a new repository whose single root commit is the current synthetic tree. Then archive or make private the old repository. This avoids a force-push, but the old repository has to be retired.
3. **Risk acceptance.** (Documented risk acceptance:) Keep the history as it is and record the decision. This rests on the facts that the identifiers are public on-chain data and the vendor payloads are small samples. The provider-rights review in `PROVIDER-RIGHTS.md` should confirm that this is acceptable.

## Caveat that applies to every option
A rewrite or a new root cannot revoke copies that are **already cloned**, **forks**, GitHub caches or mirrors, or anything archived by third parties. Purging reduces future exposure. It does not undo past distribution.
