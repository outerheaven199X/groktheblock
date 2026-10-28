---
name: promo-provenance
description: Check a coin's promo images and videos for forensic provenance signals: hashes, perceptual-hash reuse, EXIF, generator and editor metadata, ffprobe, C2PA content credentials, frame sampling, and loops. Reports signals, never verdicts. Use when someone asks whether a promo clip or 'celebrity' image is AI-made or recycled.
---
# Promo Provenance

## Steps
1. Get the original files. Download the media the user shares, or media from a post (X re-encodes uploads, so originals from the project's site or Telegram carry more metadata).
2. Run `.venv/bin/python skills/promo-provenance/scripts/provenance.py <files...> --label <TICKER>`.
   - It needs `ffmpeg`/`ffprobe`.
   - Optional: `c2patool` (install from the c2pa-rs GitHub releases) and `exiftool`.
3. Every file is added to `cache/media_index.jsonl`, so later files are checked for reuse against everything seen before.
4. For reverse search, extract 1 or 2 frames (`ffmpeg -ss 1 -i in.mp4 -frames:v 1 f.png`) and use WebSearch or the browser to look for earlier copies.
5. Report signals and notes as written. Never say "this is AI" or "this is fake". Missing metadata is normal, and present metadata can be forged.

## Present the result as a Page
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the CryptOSINT dashboard (`ui/index.html`), with kit blocks only:
Page style (matches `ui/index.html`): set `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (organic green, insider/sell red, sniper/warn amber; the same tokens as the UI's `--ok`, `--bad`, `--warn`). Class colors are fixed everywhere: ORGANIC green, INSIDER red, SNIPER amber, AGENT blue-violet, COPY cyan. Typography comes from the kit (serif-style headline title, mono for addresses and figures by writing them in backticks); never hardcode fonts or paint your own background. Order sections like the UI tab for this view: a one-line kicker `Text` (data source, tx count, scan time), headline `Metrics` (the UI's gauge cards), the main visual, then tables, then an "Evidence" `LinkCards` section and the disclaimer line. Shorten addresses as `9zd5…QzhD`. Status pills: `danger` for CRITICAL/HIGH, `warning` for MEDIUM, no tone for LOW.
- One `Section` per file: `Properties` (type, size, C2PA present, encoder), a `BulletList` of signals, and the notes in small text.
- A reuse `Table` if any matches were found.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
