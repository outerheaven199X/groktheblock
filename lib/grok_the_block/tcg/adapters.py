"""Provider adapters for the Card Explorer.

One adapter per card game. Only adapters with ACTIVE=True are synced or shown as browsable; the others are recorded so the
UI can list them as unavailable with the exact reason, never as supported.

Identity rule: a printing is identified by provider id + set + collector number + language, and a market observation is
further keyed by finish (nonfoil / foil / etched). Prices are never moved between printings or finishes.
"""
from __future__ import annotations

import re

IMG_SIZES = ("small", "normal", "large", "png")
FINISH_PRICE = {"nonfoil": ("usd", "eur"), "foil": ("usd_foil", "eur_foil"), "etched": ("usd_etched", None)}


def printing_key(provider: str, pid: str, set_code: str, cn: str, lang: str) -> str:
    return f"{provider}:{pid}:{(set_code or '').lower()}:{cn}:{(lang or 'en').lower()}"


def finish_key(pkey: str, finish: str) -> str:
    return f"{pkey}:{finish}"


def parse_scryfall_uri(url: str) -> tuple[str, str] | None:
    """https://scryfall.com/card/vma/4/black-lotus -> ('vma', '4'). Used to bind a tracked observation to its exact printing."""
    m = re.match(r"https?://scryfall\.com/card/([^/]+)/([^/]+)/", url or "")
    return (m.group(1).lower(), m.group(2)) if m else None


class Adapter:
    game = ""
    name = ""
    provider = ""
    ACTIVE = False
    reason = ""
    terms_url = ""

    def describe(self) -> dict:
        return {"game": self.game, "name": self.name, "provider": self.provider, "active": self.ACTIVE, "reason": self.reason, "terms": self.terms_url}


class ScryfallAdapter(Adapter):
    game, name, provider, ACTIVE = "mtg", "Magic: The Gathering", "Scryfall", True
    reason = "Active: Scryfall API (free, attribution, no repackaging; images unaltered, artist and copyright line visible)."
    terms_url = "https://scryfall.com/docs/api"

    @staticmethod
    def faces(c: dict) -> list[dict]:
        """Exact image(s) for THIS printing. Single-image layouts (incl. split, flip, adventure) use top-level image_uris;
        double-faced layouts (transform, modal_dfc, ...) have no top-level image_uris and use card_faces[i].image_uris."""
        if isinstance(c.get("image_uris"), dict):
            return [{"face": 0, "name": c.get("name"), "uris": {k: c["image_uris"].get(k) for k in IMG_SIZES if c["image_uris"].get(k)}}]
        out = []
        for i, f in enumerate(c.get("card_faces") or []):
            iu = f.get("image_uris") if isinstance(f, dict) else None
            out.append({"face": i, "name": f.get("name") if isinstance(f, dict) else None, "uris": {k: iu.get(k) for k in IMG_SIZES if iu.get(k)} if isinstance(iu, dict) else {}})
        return out or [{"face": 0, "name": c.get("name"), "uris": {}}]  # no imagery at all: one face, text fallback

    @staticmethod
    def variant_tags(c: dict) -> list[str]:
        t = []
        if c.get("border_color") == "borderless":
            t.append("borderless")
        for fe in c.get("frame_effects") or []:
            if fe in ("showcase", "extendedart", "etched", "inverted", "shatteredglass"):
                t.append(fe)
        if c.get("full_art"):
            t.append("full art")
        if c.get("promo"):
            t.append("promo")
        if c.get("textless"):
            t.append("textless")
        for pt in c.get("promo_types") or []:
            if pt in ("serialized", "galaxyfoil", "surgefoil", "textured", "halofoil", "stepandcompleat", "confettifoil"):
                t.append(pt)
        return t

    def printing(self, c: dict) -> dict | None:
        if not isinstance(c, dict) or c.get("object") != "card" or not c.get("id"):
            return None
        lang = c.get("lang") or "en"
        key = printing_key("scryfall", c["id"], c.get("set", ""), c.get("collector_number", ""), lang)
        faces = self.faces(c)
        tags = self.variant_tags(c)
        return {
            "key": key, "provider": "scryfall", "id": c["id"], "oracle_id": c.get("oracle_id") or ((c.get("card_faces") or [{}])[0].get("oracle_id")),
            "name": c.get("name"), "set": (c.get("set") or "").lower(), "set_name": c.get("set_name"), "cn": c.get("collector_number"),
            "lang": lang, "rarity": c.get("rarity"), "released": c.get("released_at"), "layout": c.get("layout"),
            "finishes": [f for f in (c.get("finishes") or []) if f in FINISH_PRICE], "variant": tags,
            # Alternate art = a different illustration from the oracle card's default; reprint = same illustration, other set.
            "illustration": c.get("illustration_id") or ((c.get("card_faces") or [{}])[0].get("illustration_id")),
            "artist": c.get("artist"), "image_status": c.get("image_status") or "missing", "faces": faces,
            "uri": (c.get("scryfall_uri") or "").split("?")[0], "digital": bool(c.get("digital")),
        }


class TcgdexAdapter(Adapter):
    game, name, provider = "pokemon", "Pokémon TCG", "TCGdex"
    reason = ("Inactive: TCGdex code/data are open source, but card images are Pokémon/Nintendo/Creatures/GAME FREAK artwork with no "
              "licence granted by TCGdex; image and price rights unreviewed for this use.")
    terms_url = "https://tcgdex.dev/"


class ScrydexAdapter(Adapter):
    game, name, provider = "pokemon-scrydex", "Pokémon / Lorcana / One Piece (Scrydex)", "Scrydex"
    reason = ("Inactive: paid API; Terms §4 forbid redistributing or mirroring the Services without written authorization and "
              "§9 leave third-party card content with its owners. Needs a plan and written permission first.")
    terms_url = "https://scrydex.com/terms"


ADAPTERS = [ScryfallAdapter(), TcgdexAdapter(), ScrydexAdapter()]


def adapter(game: str) -> Adapter:
    for a in ADAPTERS:
        if a.game == game:
            return a
    raise KeyError(game)


def group_printings(printings: list[dict], tracked_ids: set[str] | None = None) -> list[dict]:
    """Group printings by oracle card; separate alternate art (other illustration), print variants (same art, special
    treatment) and reprints (same art, other set). Duplicate names with different oracle ids stay separate cards."""
    tracked_ids = tracked_ids or set()
    by: dict[str, list[dict]] = {}
    for p in printings:
        by.setdefault(p["oracle_id"] or p["key"], []).append(p)
    out = []
    for oid, ps in by.items():
        ps.sort(key=lambda p: (p["id"] not in tracked_ids, p.get("released") or "", p["set"], p["cn"]))
        base = ps[0]
        for p in ps:
            if p is base:
                p["kind"] = "tracked" if p["id"] in tracked_ids else "default"
            elif p.get("illustration") and p["illustration"] != base.get("illustration"):
                p["kind"] = "alternate art"
            elif p.get("variant"):
                p["kind"] = "print variant"
            else:
                p["kind"] = "reprint"
        out.append({"oracle_id": oid, "name": base["name"], "printings": ps})
    out.sort(key=lambda g: g["name"] or "")
    return out
