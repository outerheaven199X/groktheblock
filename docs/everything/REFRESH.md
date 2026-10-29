# Refreshing cached market data (opt-in)

Nothing refreshes on its own. Opening the UI never fetches anything; the browser only reads `ui/data/everything.js`.
A refresh is a local command you run, or schedule yourself.

## Commands

| Command | What it does |
|---|---|
| `python3 tools/build_everything.py --fetch` | Fetch every module now (FX, metals, energy, CFTC, MTG, CS2, markets), then regenerate `ui/data/everything.js`. |
| `python3 tools/build_everything.py --fetch --only=markets,mtg` | Fetch only the named modules; the others keep their last good data. |
| `python3 tools/build_everything.py --scheduled` | For schedulers: fetch only modules whose cadence is due (see below). |
| `python3 tools/build_everything.py` | Regenerate from files, no network. |
| `python3 tools/build_everything.py --check` | Exit 1 if generated files are stale. No network. |

Modules and cadences (`CADENCE` in `tools/build_everything.py`): fx, metals, energy, CFTC COT, MTG, CS2 daily; markets
(Polymarket, Kalshi, equities, options, Treasury, crypto, stablecoins, macro, SEC, Solana) every 6 h. CFTC publishes weekly;
the daily check just re-reads the same week until a new report appears. Scryfall prices update about once a day, so MTG writes
one snapshot file per UTC day (`cache/everything/scryfall/YYYY-MM-DD.json`); a second run that day replaces that day's file.
No history is backfilled: a 14-day trend needs 14 real days of runs.

## Safety properties

- **Single run:** `cache/everything/refresh.lock` (pid + time). A second run exits without touching anything. A lock left by a
  killed run is reclaimed when its pid is gone or after 2 h.
- **Atomic writes:** every output is written to a temp file, fsynced and renamed. An interrupted run leaves the previous file.
- **Per-module isolation:** a module that times out, gets 429/5xx after backoff, returns HTML or bad JSON keeps its last good
  signals, probes and assets, marked `STALE` with `errorCategory`; `lastSuccessAt` is preserved. A module that never succeeded
  is `UNAVAILABLE`. A provider failure never clears a finding and never shows as quiet.
- **Backoff:** HTTP retries 3 times with exponential backoff (1 s, 2 s, 4 s) on 429, 5xx, timeouts and network errors, with a
  per-host minimum gap. Each module also has a 15-minute wall-clock budget (Unix; Windows relies on per-request timeouts).
- **Health log:** `cache/everything/refresh-log.jsonl` (gitignored) records every run start, every module result
  (ok, error category, seconds) and run end. `data/everything/live-derived.json` carries `health[]` with `lastAttemptAt`,
  `lastSuccessAt`, `sourceAsOf`, `status`, `errorCategory`, `cadenceS` and `nextExpectedRun`; the UI shows data age from these.
- **Keys:** no key is needed for any default module. SEC EDGAR runs only when you set `GTB_SEC_USER_AGENT="Your Name you@example.org"`
  (SEC fair-access rule); otherwise it is `NOT_CONFIGURED`. Solana alerts need local `watch-token` reports. Secrets stay in the
  environment and are never written to `ui/data/everything.js` or committed JSON.
- **Repository effect:** a refresh rewrites the tracked files `data/everything/live-derived.json`,
  `data/everything/markets-derived.json`, `ui/data/everything.js` and `docs/assets-manifest.json`. Commit them only if you mean to.
  Vendor-sourced values are stored as derived fields only (see `derive_signal` in `tools/build_everything.py`).

## Windows Task Scheduler

Run once in PowerShell from the repo folder (adjust the Python path; `py -3` also works). This creates a task that runs every
6 hours as you, only while you are logged on:

```powershell
$repo = (Get-Location).Path
schtasks /Create /TN "GrokTheBlock Refresh" /SC HOURLY /MO 6 /F `
  /TR "cmd /c cd /d `"$repo`" && python tools\build_everything.py --scheduled >> cache\everything\scheduler.log 2>&1"
schtasks /Run /TN "GrokTheBlock Refresh"      # test it once now
schtasks /Query /TN "GrokTheBlock Refresh" /V /FO LIST
schtasks /Delete /TN "GrokTheBlock Refresh" /F   # turn it off
```

To include SEC filings, set the variable for your user first: `setx GTB_SEC_USER_AGENT "Your Name you@example.org"`.

## cron (macOS / Linux)

```cron
# crontab -e   — every 6 hours at :17, from the repo root
17 */6 * * * cd /path/to/groktheblock && /usr/bin/python3 tools/build_everything.py --scheduled >> cache/everything/scheduler.log 2>&1
```

Remove the line to turn it off. cron has a minimal environment, so put `GTB_SEC_USER_AGENT=...` on the line above if you want SEC.

## Testing failures

`GTB_HTTP_SIMULATE=timeout:fred,429:cftc,5xx:scryfall,schema:nasdaq` makes the named providers fail inside the HTTP layer
(cache bypassed); `GTB_HTTP_BACKOFF_BASE=0.05` shortens backoff for tests. `tests/test_refresh.py` covers the runner offline.
