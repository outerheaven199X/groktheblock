# TCG providers and artwork rights (Card Explorer)

Reviewed 2026-10-29 from the providers' public pages. Nothing here is legal advice; a hosted build needs owner/counsel sign-off.

| Game | Provider | Status | Data use | Artwork |
|---|---|---|---|---|
| Magic: The Gathering | Scryfall API | **Active** (local research preview) | Printing metadata via `/cards/search?unique=prints`; bulk `default_cards` for large imports. Prices stay derived-only (existing rule). | Scryfall serves images of Wizards of the Coast cards. Images are cached unaltered (no crop or overlay; artist and copyright line visible) under `ui/cache/tcg` (gitignored) for local use. **Artwork rights: BLOCKED for redistribution**: no licence for re-hosting card images has been verified, so a hosted build must ship the text fallback. |
| Pokémon TCG | TCGdex | **Inactive** | Open-source API (multilingual, REST/GraphQL). | Card images are Pokémon/Nintendo/Creatures/GAME FREAK artwork; TCGdex grants no artwork licence. Rights unreviewed for this use. |
| Pokémon, Lorcana, One Piece and others | Scrydex | **Inactive** | Paid API ($29–99/mo noted in the earlier plan). Terms §4 forbid reselling, redistributing or mirroring the Services without written authorization; §9 leaves third-party card content with its owners. | Needs a paid plan plus written permission before any activation. |

Rules for every adapter (`lib/grok_the_block/tcg/adapters.py`):
- Only `ACTIVE = True` adapters sync or browse. Inactive games appear in the Game filter as disabled "unavailable: rights not cleared".
- No scraping of marketplace images (TCGplayer, Cardmarket, eBay) and no bypassing provider restrictions.
- Identity: provider id + set + collector number + language; observations are also keyed by finish. Prices and observations never move between printings or finishes.

Scryfall operational rules kept by `tools/sync_tcg_art.py`: ≤10 requests/second (≥120 ms between API calls, ≥100 ms between image downloads), a descriptive `User-Agent` and an `Accept` header, bulk data for substantial imports, no API key. Sources: https://scryfall.com/docs/api, https://scryfall.com/docs/api/images, https://tcgdex.dev/, https://scrydex.com/terms.
