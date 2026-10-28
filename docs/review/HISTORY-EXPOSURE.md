# History exposure (R6-04)

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
