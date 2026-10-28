---
name: promo-provenance
description: Grok The Block (understand what actually happened on-chain, in plain English). Check a coin's promo images and videos for forensic provenance signals: hashes, perceptual-hash reuse, EXIF, generator and editor metadata, ffprobe, C2PA content credentials, frame sampling, and loops. Reports signals, never verdicts. Use when someone asks whether a promo clip or 'celebrity' image is AI-made or recycled.
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
End every run by rendering the report as a Grok Bot Page (canvas), not a wall of chat text. Read your `canvas` skill before the first `WriteCanvas`. Use the same layout as the Grok The Block dashboard (`ui/index.html`), with kit blocks only.
Page structure (requirement: a Page must reach the same conclusions, evidence and next steps as the dashboard). Use `palette={["#00e87b", "#ff3b5c", "#ffb020"]}` on `Page` (the UI's `--org`, `--ins`, `--snip`); class colors are ORGANIC green, INSIDER red, SNIPER amber, AGENT violet, COPY cyan. Typography comes from the kit; never hardcode fonts. Build it from the result's `assessment` block when present (token scan, wallet scan, rug replay), in this order:
1. Title `Grok The Block: <subject>`; `summary` = `assessment.lead.text`. If the data is a bundled example, say "Example data, recorded <date>, not live" in the summary.
2. A `Callout` with the lead finding (tone `danger` for CRITICAL/HIGH, `warning` for MEDIUM) and `lead.why` when present. Name the basis: observed, heuristic or inferred.
3. Section "Coverage & limits", before any numbers: `Rows` with one row per `coverage.limits` item (kind as `meta`) and one per failed provider (`status` danger). An unreached launch, sampled X data, local-only reputation and approximate SOL figures must appear here. Missing provider data is "unknown", never "clean".
4. `Metrics` for the key numbers, then the main visual.
5. Section "Findings & evidence": a `Table` with Finding, Severity, Basis and Evidence columns, plus `LinkCards` for the Solscan or provider links in `evidence`.
6. Section "Next steps": `Rows`, one per `assessment.nextActions` item (title = `label`, meta = `why` followed by "Ask Grok Bot: “<ask>”"). Never say a step ran unless you ran it in this turn.
Shorten addresses as `9zd5…QzhD`.
- One `Section` per file: `Properties` (type, size, C2PA present, encoder), a `BulletList` of signals, and the notes in small text.
- A reuse `Table` if any matches were found.
- Keep the disclaimer line at the bottom: signals from public data, not accusations.
- If you already made a Page for this token, wallet, or ticker, update it with `EditCanvas` instead of making a new one.
- In chat, give one or two lines and the Page link. Never post the report anywhere yourself. If the user wants to post it, draft the text for them to post.

## Rules
- Read-only. Never sign transactions, connect wallets, trade, or ask for a seed phrase or private key.
- Say "coordinated pattern", "flagged wallet", or "signal". Do not say "bot", "scammer", or "fraud" about a named account or wallet.
- The tool never whitelists or skips any coin, including any coin tied to the author.
