# grok-the-block

Local research preview of Grok The Block. One command starts a read-only server on `127.0.0.1` and opens the bundled browser UI.

```
npx grok-the-block            # OS-assigned port, opens your browser
npx grok-the-block --no-open  # print the URL only
npx grok-the-block --port 8000
```

- No wallet, sign-in, telemetry, install hooks or runtime dependencies. Node >= 22.14.0.
- Serves only the files in `dist/ui/`. GET/HEAD only, Host-checked, no CORS, cannot be framed.
- The browser UI makes no network requests (CSP `connect-src 'none'`). Data is a cached snapshot plus labelled synthetic examples.
- Ctrl+C stops it. Not financial advice.
