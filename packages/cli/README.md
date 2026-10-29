# grok-the-block

Local research preview of Grok The Block. One command starts a read-only server on `127.0.0.1` and opens the bundled browser UI.

```
npx grok-the-block            # OS-assigned port, opens your browser
npx grok-the-block --no-open  # print the URL only
npx grok-the-block --port 8000
```

- No wallet, sign-in, telemetry, install hooks or runtime dependencies. Node >= 22.14.0.
- Serves only the files in `dist/ui/` (GET/HEAD), plus a small same-origin JSON API under `/api/` (POST only, loopback Host and same-origin Origin required, per-run token, 64 KB bodies). No CORS, cannot be framed.
- The browser UI talks only to that local API (CSP `connect-src 'self'`). Data is a cached snapshot plus labelled synthetic examples; the package is snapshot-only and does not refresh in the background.
- Investigate any loaded observation: an evidence-only dossier works offline (export HTML or JSON, or print to PDF), and "Copy to Grok" copies a bounded prompt.
- Optional Connected Grok: `XAI_API_KEY=... npx grok-the-block`, or paste a key for the session only. The key stays in the launcher process, is never written to disk and never reaches the page. Each question shows the exact evidence packet and asks for consent; xAI bills your account for tokens and search calls. The live xAI path is implemented against the documented Responses API but is UNVERIFIED (tested only against a local mock).
- Optional local watchlist: stored in a per-user state directory (`GTB_STATE_DIR`, or the OS default such as `~/.local/state/grok-the-block`), never inside the package. Clear it from the Watchlist view.
- Card Explorer shows text cards: card artwork is not included in the npm package. Images only appear when you run the app from a clone of the GitHub repo and run its optional `python3 tools/sync_tcg_art.py` there.
- Ctrl+C stops it. Not financial advice.
