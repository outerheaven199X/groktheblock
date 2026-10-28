"""Shared Solana data helper.

Free, keyless sources by default:
  - Public Solana RPC (SOLANA_RPC_URL, default api.mainnet-beta.solana.com)
  - DexScreener API (pairs, liquidity, price)
  - RugCheck.xyz API (mint/freeze authority, LP lock, top holders)
Optional: HELIUS_API_KEY switches RPC to Helius (faster, higher limits).

Everything is cached as JSON under ./cache (override with CRYPTOSINT_CACHE).
Read-only: no signing, no keys, no transactions sent.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

LAMPORTS_PER_SOL = 1_000_000_000
SOL_MINT = "So11111111111111111111111111111111111111112"
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(os.environ.get("CRYPTOSINT_CACHE", REPO_ROOT / "cache"))
UA = {"User-Agent": "cryptosint-grokbot/0.1 (read-only research)"}


PUBLIC_RPCS = [u for u in os.environ.get("SOLANA_RPC_URL", "").split(",") if u] or [
    "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
]
_rpc_idx = [0]


def rpc_url() -> str:
    key = os.environ.get("HELIUS_API_KEY")
    if key:
        return f"https://mainnet.helius-rpc.com/?api-key={key}"
    return PUBLIC_RPCS[_rpc_idx[0] % len(PUBLIC_RPCS)]


def _failover() -> None:
    """Rotate to the next free public RPC (on rate limit / data allowance errors)."""
    _rpc_idx[0] += 1


# ---------------- cache ----------------

def _cache_path(ns: str, key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:20]
    p = CACHE_DIR / ns
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{h}.json"


def cache_get(ns: str, key: str, max_age: float | None = None) -> Any:
    p = _cache_path(ns, key)
    if not p.exists():
        return None
    if max_age is not None and time.time() - p.stat().st_mtime > max_age:
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def cache_put(ns: str, key: str, value: Any) -> None:
    _cache_path(ns, key).write_text(json.dumps(value))


# ---------------- HTTP / RPC ----------------

_last_call = [0.0]


def _throttle() -> None:
    # Public RPC allows ~10 req/s per IP; stay well under it.
    min_gap = 0.02 if os.environ.get("HELIUS_API_KEY") else 0.15
    dt = time.time() - _last_call[0]
    if dt < min_gap:
        time.sleep(min_gap - dt)
    _last_call[0] = time.time()


# Provider health for this process, reported in each result's coverage block.
PROVIDERS: dict[str, dict] = {}


def _fail_sim(name: str) -> bool:
    """CRYPTOSINT_SIMULATE_FAIL=dexscreener,rugcheck,rpc simulates a provider outage (testing only)."""
    return name in {x.strip() for x in os.environ.get("CRYPTOSINT_SIMULATE_FAIL", "").split(",") if x.strip()}


def mark(name: str, ok: bool, detail: str = "") -> None:
    cur = PROVIDERS.get(name)
    if cur and not cur["ok"] and ok:
        return  # once failed in this run, keep it visible
    PROVIDERS[name] = {"ok": ok, "detail": detail}


def provider_report() -> dict:
    return {k: dict(v) for k, v in PROVIDERS.items()}


def rpc(method: str, params: list, retries: int = 8) -> Any:
    if _fail_sim("rpc"):
        mark("solana-rpc", False, "simulated outage")
        raise RuntimeError(f"RPC {method} failed: simulated outage")
    try:
        res = _rpc(method, params, retries)
        mark("solana-rpc", True)
        return res
    except RuntimeError as e:
        if "error:" not in str(e):
            mark("solana-rpc", False, str(e)[:120])
        raise


def _rpc(method: str, params: list, retries: int = 8) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    delay = 1.0
    for attempt in range(retries):
        _throttle()
        try:
            r = requests.post(rpc_url(), json=body, headers=UA, timeout=40)
            if r.status_code in (403, 413, 429) or r.status_code >= 500:
                _failover(); time.sleep(delay); delay = min(delay * 2, 20); continue
            j = r.json()
            if "error" in j:
                msg = str(j["error"])
                if "429" in msg or "413" in msg or "rate" in msg.lower() or "allowance" in msg.lower():
                    _failover(); time.sleep(delay); delay = min(delay * 2, 20); continue
                raise RuntimeError(f"RPC {method} error: {msg}")
            return j.get("result")
        except (requests.RequestException, ValueError):
            _failover(); time.sleep(delay); delay = min(delay * 2, 20)
    raise RuntimeError(f"RPC {method} failed after {retries} retries")


def http_json(url: str, ns: str, max_age: float = 300) -> Any:
    if _fail_sim(ns):
        mark(ns, False, "simulated outage"); return None
    hit = cache_get(ns, url, max_age)
    if hit is not None:
        mark(ns, True, "cached"); return hit
    res = _http_json(url, ns)
    mark(ns, res is not None, "" if res is not None else "no response / non-200")
    return res


def _http_json(url: str, ns: str) -> Any:
    delay = 1.0
    for _ in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2; continue
            if r.status_code != 200:
                return None
            j = r.json()
            cache_put(ns, url, j)
            return j
        except (requests.RequestException, ValueError):
            time.sleep(delay); delay *= 2
    return None


# ---------------- DexScreener / RugCheck ----------------

def dexscreener_pairs(mint: str) -> list[dict]:
    j = http_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", "dexscreener")
    return [p for p in (j or {}).get("pairs") or [] if p.get("chainId") == "solana"]


def dexscreener_search(q: str) -> list[dict]:
    from urllib.parse import quote
    j = http_json(f"https://api.dexscreener.com/latest/dex/search?q={quote(q)}", "dexscreener")
    return [p for p in (j or {}).get("pairs") or [] if p.get("chainId") == "solana"]


def rugcheck_report(mint: str) -> dict | None:
    return http_json(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", "rugcheck", 600)


def token_metadata(mint: str) -> dict:
    """Name/symbol/supply from DexScreener + RugCheck + RPC (best effort)."""
    meta = {"mint": mint, "name": "Unknown", "symbol": "???", "supply": None, "decimals": None}
    pairs = dexscreener_pairs(mint)
    for p in pairs:
        bt = p.get("baseToken") or {}
        if bt.get("address") == mint:
            meta["name"], meta["symbol"] = bt.get("name", meta["name"]).strip(), bt.get("symbol", meta["symbol"]).strip()
            break
    rc = rugcheck_report(mint) or {}
    tm = rc.get("tokenMeta") or {}
    if meta["symbol"] == "???" and tm:
        meta["name"], meta["symbol"] = tm.get("name", "Unknown"), tm.get("symbol", "???")
    if meta["symbol"] == "???" and has_helius():
        try:  # Helius DAS getAsset, as in the original
            a = rpc("getAsset", {"id": mint}, retries=2) or {}
            md = (a.get("content") or {}).get("metadata") or {}
            meta["name"], meta["symbol"] = md.get("name", "Unknown"), md.get("symbol", "???")
        except Exception:
            pass
    try:
        s = rpc("getTokenSupply", [mint])["value"]
        meta["supply"] = float(s["uiAmountString"])
        meta["decimals"] = s["decimals"]
    except Exception:
        pass
    return meta


# ---------------- signatures & transactions ----------------

def get_signatures(address: str, max_pages: int = 20, page_size: int = 1000,
                   newest_only: bool = False) -> tuple[list[dict], bool]:
    """Return (signatures oldest->newest, reached_genesis).

    Public RPC only pages newest->oldest, so to find a token's launch window we
    walk back up to max_pages*page_size signatures. If we hit the cap before the
    first signature, reached_genesis is False and the "launch window" is really
    just the oldest slice we could reach.
    """
    key = f"{address}:{max_pages}:{page_size}:{newest_only}"
    hit = None if newest_only else cache_get("sigs", key, max_age=120)
    if hit:
        return hit["sigs"], hit["genesis"]
    out, before, genesis = [], None, False
    for _ in range(max_pages):
        opts: dict = {"limit": page_size}
        if before:
            opts["before"] = before
        page = rpc("getSignaturesForAddress", [address, opts]) or []
        out.extend(page)
        if len(page) < page_size:
            genesis = True
            break
        before = page[-1]["signature"]
        if newest_only:
            break
    out.reverse()
    cache_put("sigs", key, {"sigs": out, "genesis": genesis})
    return out, genesis


def get_transaction(sig: str) -> dict | None:
    hit = cache_get("tx", sig)
    if hit is not None:
        return hit or None
    tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    cache_put("tx", sig, tx or {})  # finalized txs never change
    return tx


def _key_str(k: Any) -> str:
    return k["pubkey"] if isinstance(k, dict) else k


def normalize_tx(raw: dict, sig: str) -> dict | None:
    """Convert jsonParsed RPC tx into the Helius-like shape classify.ts expects:
    {signature, slot, timestamp, feePayer, tokenTransfers[], nativeTransfers[], accountData[]}.

    tokenTransfers are derived from per-owner token balance deltas (pre/post),
    one entry per owner with only fromUserAccount or toUserAccount set. This
    matches Helius semantics closely enough for the classifier (which only
    looks at per-wallet in/out amounts).
    """
    if not raw or not raw.get("meta") or raw["meta"].get("err") is not None:
        return None
    meta, msg = raw["meta"], raw["transaction"]["message"]
    keys = [_key_str(k) for k in msg["accountKeys"]]
    loaded = meta.get("loadedAddresses") or {}
    keys += loaded.get("writable", []) + loaded.get("readonly", [])
    pre, post = meta.get("preBalances", []), meta.get("postBalances", [])
    account_data = [{"account": k, "nativeBalanceChange": (post[i] - pre[i]) if i < len(pre) and i < len(post) else 0}
                    for i, k in enumerate(keys)]
    # token deltas per (owner, mint)
    deltas: dict[tuple[str, str], float] = {}
    for sign, arr in ((-1, meta.get("preTokenBalances") or []), (1, meta.get("postTokenBalances") or [])):
        for b in arr:
            owner = b.get("owner") or keys[b["accountIndex"]]
            amt = float(b["uiTokenAmount"].get("uiAmountString") or 0)
            deltas[(owner, b["mint"])] = deltas.get((owner, b["mint"]), 0.0) + sign * amt
    token_transfers = []
    for (owner, mint), d in deltas.items():
        if abs(d) < 1e-12:
            continue
        token_transfers.append({"mint": mint, "tokenAmount": abs(d),
                                "fromUserAccount": owner if d < 0 else None,
                                "toUserAccount": owner if d > 0 else None})
    native = []
    ixs = list(msg.get("instructions", []))
    for inner in meta.get("innerInstructions") or []:
        ixs.extend(inner.get("instructions", []))
    for ix in ixs:
        p = ix.get("parsed")
        if ix.get("program") == "system" and isinstance(p, dict) and p.get("type") in ("transfer", "transferWithSeed"):
            inf = p["info"]
            native.append({"fromUserAccount": inf.get("source"), "toUserAccount": inf.get("destination"),
                           "amount": int(inf.get("lamports", 0))})
    return {"signature": sig, "slot": raw["slot"], "timestamp": raw.get("blockTime") or 0,
            "feePayer": keys[0], "tokenTransfers": token_transfers, "nativeTransfers": native,
            "accountData": account_data, "programIds": sorted({ix.get("programId", "") for ix in ixs})}


def fetch_transactions(sigs: list[dict], limit: int, progress: bool = True) -> list[dict]:
    out = []
    todo = [s for s in sigs if s.get("err") is None][:limit]
    for i, s in enumerate(todo):
        raw = get_transaction(s["signature"])
        n = normalize_tx(raw, s["signature"]) if raw else None
        if n:
            out.append(n)
        if progress and (i + 1) % 50 == 0:
            print(f"  fetched {i + 1}/{len(todo)} txs", flush=True)
    return out


# ---------------- Helius fast path ----------------

_gtfa_ok = [None]  # None unknown, True works, False not on this plan


def has_helius() -> bool:
    return bool(os.environ.get("HELIUS_API_KEY"))


def data_source() -> str:
    if not has_helius():
        return "public-rpc"
    return "helius-gtfa" if _gtfa_ok[0] else "helius-rpc"


def helius_gtfa(address: str, max_tx: int, sort: str = "asc") -> list[dict] | None:
    """Helius getTransactionsForAddress (sortOrder asc = straight to launch, 100 full
    txs per call). Returns None if the key's plan doesn't allow the method."""
    if not has_helius() or _gtfa_ok[0] is False:
        return None
    key = f"gtfa:{address}:{max_tx}:{sort}"
    hit = cache_get("gtfa", key, max_age=None if sort == "asc" else 30)
    if hit is not None:
        _gtfa_ok[0] = True
        return hit
    out, token = [], None
    while len(out) < max_tx:
        params = {"limit": min(100, max_tx - len(out)), "sortOrder": sort, "commitment": "confirmed",
                  "encoding": "jsonParsed", "transactionDetails": "full", "maxSupportedTransactionVersion": 1}
        if token:
            params["paginationToken"] = token
        try:
            page = rpc("getTransactionsForAddress", [address, params], retries=3)
        except RuntimeError as e:
            msg = str(e).lower()
            if any(x in msg for x in ("method", "plan", "not available", "upgrade", "-32601", "forbidden", "403")):
                _gtfa_ok[0] = False
                print("  Helius getTransactionsForAddress not available on this plan; falling back to signature walk", file=sys.stderr)
                return None
            raise
        _gtfa_ok[0] = True
        data = (page or {}).get("data") or []
        for raw in data:
            sig = raw["transaction"]["signatures"][0]
            n = normalize_tx(raw, sig)
            if n:
                out.append(n)
        token = (page or {}).get("paginationToken")
        if not data or not token:
            break
    cache_put("gtfa", key, out)
    return out


def get_token_transactions(mint: str, max_tx: int = 300, max_sig_pages: int = 20) -> dict:
    """Launch-window transactions for a token mint (oldest first).

    Order of preference: Helius getTransactionsForAddress (asc, true launch on any
    size coin) -> signature walk on Helius RPC (deep: 10x pages) -> public RPC walk."""
    g = helius_gtfa(mint, max_tx, "asc")
    if g:
        return {"transactions": g, "reached_genesis": True, "signatures_seen": len(g), "source": "helius-gtfa"}
    pages = max_sig_pages * 10 if has_helius() else max_sig_pages
    sigs, genesis = get_signatures(mint, max_pages=pages)
    txs = fetch_transactions(sigs, max_tx)
    return {"transactions": txs, "reached_genesis": genesis, "signatures_seen": len(sigs), "source": data_source()}


def wallet_first_tx(addr: str, max_pages: int = 3) -> tuple[dict | None, bool]:
    """(first normalized tx, complete?) via Helius asc if possible, else sig walk."""
    g = helius_gtfa(addr, 1, "asc")
    if g:
        return g[0], True
    sigs, genesis = get_signatures(addr, max_pages=max_pages * (10 if has_helius() else 1))
    if not sigs or not genesis:
        return None, genesis
    return normalize_tx(get_transaction(sigs[0]["signature"]), sigs[0]["signature"]), True


def get_wallet_transactions(wallet: str, max_tx: int = 200) -> list[dict]:
    """Most recent wallet transactions (newest page only), oldest first."""
    g = helius_gtfa(wallet, max_tx, "desc")
    if g:
        return sorted(g, key=lambda t: t["slot"])
    sigs, _ = get_signatures(wallet, max_pages=1, page_size=max(max_tx, 50), newest_only=True)
    return fetch_transactions(sigs[-max_tx:], max_tx)


def sol_price_usd() -> float | None:
    pairs = dexscreener_pairs(SOL_MINT)
    for p in pairs:
        if (p.get("baseToken") or {}).get("address") == SOL_MINT and p.get("priceUsd"):
            return float(p["priceUsd"])
    return None


def short(addr: str | None) -> str:
    return f"{addr[:4]}...{addr[-4:]}" if addr and len(addr) > 10 else (addr or "")


def write_json(path: str | Path, obj: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, default=str))


SYSTEM_PROGRAM = "11111111111111111111111111111111"


def is_program_account(addr: str) -> bool:
    """True if the address is owned by a program other than System (pool PDA, vault,
    bonding curve) rather than a normal user wallet. Cached forever."""
    hit = cache_get("owner", addr)
    if hit is None:
        try:
            v = (rpc("getAccountInfo", [addr, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}]) or {}).get("value")
            hit = {"owner": v["owner"] if v else None}
        except Exception:
            hit = {"owner": None}
        cache_put("owner", addr, hit)
    return bool(hit["owner"]) and hit["owner"] != SYSTEM_PROGRAM


def sol_flows(txs: list[dict], mint: str) -> dict[str, float]:
    """Approximate SOL PnL per wallet: sum of the wallet's native SOL balance change
    in every tx where its balance of `mint` changed (includes fees; ignores WSOL
    wrapping edge cases and unsold bags)."""
    flows: dict[str, float] = {}
    for tx in txs:
        owners = {tr.get("fromUserAccount") or tr.get("toUserAccount") for tr in tx["tokenTransfers"] if tr["mint"] == mint}
        if not owners:
            continue
        ch = {a["account"]: a["nativeBalanceChange"] for a in tx["accountData"]}
        wsol = {}
        for tr in tx["tokenTransfers"]:
            if tr["mint"] == SOL_MINT:
                o = tr.get("fromUserAccount") or tr.get("toUserAccount")
                wsol[o] = wsol.get(o, 0) + (tr["tokenAmount"] if tr.get("toUserAccount") else -tr["tokenAmount"])
        for o in owners:
            flows[o] = flows.get(o, 0.0) + ch.get(o, 0) / LAMPORTS_PER_SOL + wsol.get(o, 0)
    return flows
