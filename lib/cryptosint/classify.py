"""Faithful Python port of CryptOSINT src/lib/classify.ts.

Thresholds, ordering, tags and verdict text are kept identical to the original.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

WALLET_TYPES = ["AGENT", "INSIDER", "COPY", "SNIPER", "ORGANIC"]

# Known Jito/MEV-related program IDs
MEV_PROGRAMS = {
    "T1pyyaTNZsKv2WcRAB8oVnk93mLJw2XzjtVYqCsaHqt",  # Jito tip
    "HFqU5x63VTqvQss8hp11i4bPYoTAYn4jQf4g3HcNBhiL",  # Jito bundle
}


@dataclass
class WalletProfile:
    address: str
    firstBlock: int
    txCount: int = 0
    txTimestamps: list = field(default_factory=list)
    totalBought: float = 0.0
    totalSold: float = 0.0
    currentHolding: float = 0.0
    isFundedByDeployer: bool = False
    interactsWithMev: bool = False


def _touches_mev(tx: dict) -> bool:
    return any(a["account"] in MEV_PROGRAMS for a in tx.get("accountData") or [])


def build_wallet_profiles(transactions: list, token_mint: str, deployer: str) -> list[WalletProfile]:
    profiles: dict[str, WalletProfile] = {}
    sorted_txs = sorted(transactions, key=lambda t: t["slot"])
    first_slot = sorted_txs[0]["slot"] if sorted_txs else 0
    for tx in sorted_txs:
        rel = tx["slot"] - first_slot
        mev = _touches_mev(tx)
        for tr in tx.get("tokenTransfers") or []:
            if tr["mint"] != token_mint:
                continue
            for addr in (tr.get("fromUserAccount"), tr.get("toUserAccount")):
                if not addr or addr == token_mint:
                    continue
                p = profiles.setdefault(addr, WalletProfile(address=addr, firstBlock=rel))
                p.txCount += 1
                p.txTimestamps.append(tx["timestamp"])
                if mev:
                    p.interactsWithMev = True
                if tr.get("toUserAccount") == addr:
                    p.totalBought += tr["tokenAmount"]
                    p.currentHolding += tr["tokenAmount"]
                if tr.get("fromUserAccount") == addr:
                    p.totalSold += tr["tokenAmount"]
                    p.currentHolding -= tr["tokenAmount"]
        for nt in tx.get("nativeTransfers") or []:
            if nt.get("fromUserAccount") == deployer and nt.get("toUserAccount") in profiles:
                profiles[nt["toUserAccount"]].isFundedByDeployer = True
    return list(profiles.values())


def tx_cadence_stddev(timestamps: list) -> float:
    if len(timestamps) < 3:
        return math.inf
    s = sorted(timestamps)
    iv = [s[i] - s[i - 1] for i in range(1, len(s))]
    mean = sum(iv) / len(iv)
    return math.sqrt(sum((x - mean) ** 2 for x in iv) / len(iv))


def _fmt_sd(x: float) -> str:
    return "Infinity" if math.isinf(x) else f"{x:.1f}"


def classify_wallet(p: WalletProfile, total_supply: float, insiders: set) -> tuple[str, str | None]:
    supply_pct = (p.currentHolding / total_supply) * 100 if total_supply > 0 else 0
    # INSIDER: block 0-1, deployer-funded or holds >1% supply
    if p.firstBlock <= 1 and (p.isFundedByDeployer or supply_pct > 1):
        tag = "FUNDED BY DEPLOYER" if p.isFundedByDeployer else f"BLOCK {p.firstBlock} ENTRY — {supply_pct:.1f}% SUPPLY"
        return "INSIDER", tag
    # AGENT: uniform cadence, high tx count, MEV interaction
    sd = tx_cadence_stddev(p.txTimestamps)
    if (sd < 2 and p.txCount > 10) or (p.interactsWithMev and p.txCount > 5) or (p.txCount > 20 and sd < 5):
        tag = f"MEV BOT — {p.txCount} TXS" if p.interactsWithMev else f"BOT PATTERN — {_fmt_sd(sd)}s STDDEV"
        return "AGENT", tag
    # SNIPER: blocks 1-3, low lifetime tx count
    if p.firstBlock <= 3 and p.txCount <= 2:
        return "SNIPER", f"BLOCK {p.firstBlock} SNIPE — {p.txCount} TX{'S' if p.txCount > 1 else ''}"
    # COPY: blocks 2-5 with a small consistent tx pattern
    if 2 <= p.firstBlock <= 5 and 3 <= p.txCount <= 15:
        return "COPY", f"BLOCK {p.firstBlock} ENTRY — FOLLOWS INSIDER PATTERN"
    return "ORGANIC", None


def classify_all_wallets(profiles: list[WalletProfile], total_supply: float) -> list[dict]:
    insiders = {p.address for p in profiles
                if p.firstBlock <= 1 and (p.isFundedByDeployer or (total_supply > 0 and p.currentHolding / total_supply > 0.01))}
    out = []
    for p in profiles:
        t, tag = classify_wallet(p, total_supply, insiders)
        out.append({
            "address": p.address, "type": t,
            # NOTE: original computes this in TOKEN units (sold - bought + holding), not SOL.
            "pnlSol": p.totalSold - p.totalBought + p.currentHolding,
            "pnlUsd": 0,
            "supplyPercent": (p.currentHolding / total_supply) * 100 if total_supply > 0 else 0,
            "entryBlock": p.firstBlock, "txCount": p.txCount, "tag": tag,
        })
    return out


# ── Copy Trade Detection ──
COPY_MIN_DELAY_S, COPY_MAX_DELAY_S, COPY_MAX_STDDEV_S = 3, 30, 5
COPY_MIN_MATCHES, COPY_MAX_FOLLOWER_BLOCK = 2, 10


def _first_ts(p: WalletProfile) -> float:
    return min(p.txTimestamps) if p.txTimestamps else 0


def detect_copy_relationships(profiles: list[WalletProfile], classified: list[dict]) -> list[dict]:
    types = {w["address"]: w["type"] for w in classified}
    leaders = [p for p in profiles if types.get(p.address) in ("INSIDER", "AGENT")]
    if not leaders:
        return []
    leader_times = [{"address": p.address, "timestamp": _first_ts(p)} for p in leaders if _first_ts(p) > 0]
    rels = []
    for f in profiles:
        if not (2 <= f.firstBlock <= COPY_MAX_FOLLOWER_BLOCK):
            continue
        ft = _first_ts(f)
        if ft == 0:
            continue
        m = _best_leader(ft, leader_times, f.address)
        if m:
            rels.append(m)
    return rels


def _best_leader(ft: float, leaders: list, follower: str) -> dict | None:
    best, best_delay, delays = None, math.inf, []
    for l in leaders:
        if l["address"] == follower:
            continue
        d = ft - l["timestamp"]
        if COPY_MIN_DELAY_S <= d <= COPY_MAX_DELAY_S:
            delays.append(d)
            if d < best_delay:
                best_delay, best = d, l["address"]
    if not best or len(delays) < COPY_MIN_MATCHES:
        if best and COPY_MIN_DELAY_S <= best_delay <= COPY_MAX_DELAY_S:
            return {"leader": best, "follower": follower, "avgDelaySeconds": js_round(best_delay), "matchCount": 1}
        return None
    mean = sum(delays) / len(delays)
    sd = math.sqrt(sum((x - mean) ** 2 for x in delays) / len(delays))
    if sd > COPY_MAX_STDDEV_S:
        return None
    return {"leader": best, "follower": follower, "avgDelaySeconds": js_round(mean), "matchCount": len(delays)}


def js_round(x: float) -> int:
    """JavaScript Math.round (half up), unlike Python's banker's rounding."""
    return math.floor(x + 0.5)


def compute_organic_score(wallets: list[dict]) -> int:
    if not wallets:
        return 100
    return js_round(sum(1 for w in wallets if w["type"] == "ORGANIC") / len(wallets) * 100)


def generate_verdict(score: int, c: dict) -> dict:
    if score < 20:
        return {"severity": "CRITICAL", "summary": f"{100 - score}% of wallet activity is non-organic. {c['INSIDER']} insider wallets and {c['AGENT']} agent wallets dominate this token's activity. Price action is substantially manufactured."}
    if score < 40:
        return {"severity": "HIGH", "summary": f"Organic activity is low at {score}%. {c['INSIDER']} insiders and {c['SNIPER']} snipers entered in the first blocks. Exercise caution."}
    if score < 65:
        return {"severity": "MEDIUM", "summary": f"Mixed signals. {score}% organic activity with {c['AGENT']} detected agents and {c['COPY']} copy traders. Moderate coordination detected."}
    return {"severity": "LOW", "summary": f"{score}% organic activity. Wallet distribution appears relatively healthy. Standard sniper and bot presence within normal ranges."}


def count_types(wallets: list[dict]) -> dict:
    c = {t: 0 for t in WALLET_TYPES}
    for w in wallets:
        c[w["type"]] += 1
    return c


# ── Wallet Mode ──

def classify_wallet_for_token(txs: list, wallet: str, mint: str) -> dict:
    rel = [t for t in txs if any(tr["mint"] == mint and wallet in (tr.get("fromUserAccount"), tr.get("toUserAccount"))
                                 for tr in t.get("tokenTransfers") or [])]
    if not rel:
        return {"classification": "ORGANIC", "entryBlock": 0, "pnlSol": 0, "buyAmount": 0, "sellAmount": 0, "holdingAmount": 0, "tag": None}
    rel.sort(key=lambda t: t["slot"])
    p = WalletProfile(address=wallet, firstBlock=0)
    for tx in rel:
        if _touches_mev(tx):
            p.interactsWithMev = True
        for tr in tx["tokenTransfers"]:
            if tr["mint"] != mint:
                continue
            if tr.get("toUserAccount") == wallet:
                p.totalBought += tr["tokenAmount"]; p.currentHolding += tr["tokenAmount"]
                p.txCount += 1; p.txTimestamps.append(tx["timestamp"])
            if tr.get("fromUserAccount") == wallet:
                p.totalSold += tr["tokenAmount"]; p.currentHolding -= tr["tokenAmount"]
                p.txCount += 1; p.txTimestamps.append(tx["timestamp"])
    t, tag = classify_single_profile(p)
    return {"classification": t, "entryBlock": p.firstBlock, "pnlSol": p.totalSold - p.totalBought + p.currentHolding,
            "buyAmount": p.totalBought, "sellAmount": p.totalSold, "holdingAmount": p.currentHolding, "tag": tag}


def classify_single_profile(p: WalletProfile) -> tuple[str, str | None]:
    sd = tx_cadence_stddev(p.txTimestamps)
    if (sd < 2 and p.txCount > 10) or (p.interactsWithMev and p.txCount > 5) or (p.txCount > 20 and sd < 5):
        return "AGENT", (f"MEV BOT — {p.txCount} TXS" if p.interactsWithMev else f"BOT PATTERN — {_fmt_sd(sd)}s STDDEV")
    if p.firstBlock <= 1 and p.txCount >= 2:
        return "INSIDER", f"BLOCK {p.firstBlock} ENTRY"
    if p.firstBlock <= 3 and p.txCount <= 2:
        return "SNIPER", f"BLOCK {p.firstBlock} SNIPE — {p.txCount} TX{'S' if p.txCount > 1 else ''}"
    if 2 <= p.firstBlock <= 5 and 3 <= p.txCount <= 15:
        return "COPY", f"BLOCK {p.firstBlock} ENTRY — FOLLOWS PATTERN"
    return "ORGANIC", None


def generate_wallet_verdict(classes: list[str]) -> dict:
    c = {t: 0 for t in WALLET_TYPES}
    for x in classes:
        c[x] += 1
    total = len(classes)
    if c["INSIDER"] >= 3:
        return {"severity": "CRITICAL", "summary": f"Wallet classified as INSIDER on {c['INSIDER']} of {total} tokens. Consistent early-block entry pattern across multiple launches. High probability of coordinated activity."}
    if c["INSIDER"] >= 1:
        return {"severity": "HIGH", "summary": f"Wallet classified as INSIDER on {c['INSIDER']} token{'s' if c['INSIDER'] > 1 else ''}, SNIPER on {c['SNIPER']}. Early entry patterns detected across {total} tokens."}
    if c["SNIPER"] + c["COPY"] > c["ORGANIC"]:
        return {"severity": "MEDIUM", "summary": f"Wallet shows {c['SNIPER']} sniper entries and {c['COPY']} copy-trade patterns across {total} tokens. Likely automated or semi-automated trading."}
    return {"severity": "LOW", "summary": f"Wallet is primarily organic across {total} tokens. {c['ORGANIC']} organic interactions, {c['SNIPER']} sniper entries. Normal trading behavior."}


# ── Reputation ──
REP_POINTS = {"INSIDER": 25, "AGENT": 10, "SNIPER": 8, "COPY": 3, "ORGANIC": 0}
GRADES = [(81, "EXTREME"), (56, "HIGH"), (31, "MODERATE"), (11, "LOW"), (0, "CLEAN")]


def compute_reputation(history: list[dict], wallet_age: str | None = None, funded_count: int | None = None) -> dict:
    if not history:
        return {"score": 0, "grade": "CLEAN", "factors": []}
    factors, base = [], 0
    tc = {t: 0 for t in WALLET_TYPES}
    for r in history:
        tc[r["classification"]] += 1
        base += REP_POINTS[r["classification"]]
    for t in ("INSIDER", "AGENT", "SNIPER", "COPY"):
        if tc[t]:
            factors.append(f"{t} on {tc[t]} token{'s' if tc[t] > 1 else ''}")
    avg = sum(r["entryBlock"] for r in history) / len(history)
    if avg < 2:
        base = js_round(base * 1.5); factors.append(f"Avg entry block {avg:.1f}")
    if wallet_age and (wallet_age.endswith("m") or wallet_age.endswith("h")):
        base = js_round(base * 1.5); factors.append(f"Wallet age: {wallet_age}")
    if funded_count is not None and funded_count > 3:
        base = js_round(base * 1.2); factors.append(f"Funds {funded_count} wallets")
    score = min(base, 100)
    grade = next(g for th, g in GRADES if score >= th)
    return {"score": score, "grade": grade, "factors": factors}
