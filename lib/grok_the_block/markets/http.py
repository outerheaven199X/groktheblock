"""Small HTTP layer for the market fetchers: per-host throttle, retries, cache, provider health."""
from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlparse

import requests

from .. import data as D

# Some public finance endpoints refuse non-browser user agents; this is a plain read, nothing else.
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
              "Accept": "application/json, text/csv, */*"}
MIN_GAP = {"api.elections.kalshi.com": 0.25, "data-api.polymarket.com": 0.2, "gamma-api.polymarket.com": 0.2,
           "query1.finance.yahoo.com": 0.4, "query2.finance.yahoo.com": 0.4, "api.nasdaq.com": 0.6, "cdn.cboe.com": 0.4}
_last: dict[str, float] = {}


def _throttle(host: str) -> None:
    gap = MIN_GAP.get(host, 0.3)
    dt = time.time() - _last.get(host, 0)
    if dt < gap:
        time.sleep(gap - dt)
    _last[host] = time.time()


# Last failure category per provider for the refresh runner's health metadata (timeout, rate_limited, http_5xx, http_4xx,
# tls, network, schema, html_challenge). Cleared on success.
LAST_ERR: dict[str, str] = {}


def _sim(provider: str) -> str | None:
    """GTB_HTTP_SIMULATE=timeout:fred,429:cftc,5xx:scryfall,schema:nasdaq simulates provider failures (testing only)."""
    for part in (os.environ.get("GTB_HTTP_SIMULATE") or "").split(","):
        if ":" in part:
            mode, prov = part.split(":", 1)
            if prov.strip() in (provider, "*"):
                return mode.strip()
    return None


def get(url: str, provider: str, *, as_text: bool = False, max_age: float = 120, timeout: float = 30, headers: dict | None = None) -> Any:
    """GET with retries (exponential backoff on 429/5xx/timeouts). Returns parsed JSON (or text) or None. Records provider health either way."""
    ns = "mk-" + provider
    sim = _sim(provider)
    hit = D.cache_get(ns, url, max_age) if max_age and not sim else None
    if hit is not None:
        LAST_ERR.pop(provider, None)
        return hit
    host = urlparse(url).netloc
    delay = float(os.environ.get("GTB_HTTP_BACKOFF_BASE", "1.0"))
    for _ in range(3):
        _throttle(host)
        try:
            if sim == "timeout":
                raise requests.Timeout("simulated timeout")
            if sim == "schema":
                LAST_ERR[provider] = "schema"; return None
            r = None if sim in ("429", "5xx") else requests.get(url, headers=headers or BROWSER_UA, timeout=timeout, allow_redirects=True)
            code = 429 if sim == "429" else 503 if sim == "5xx" else r.status_code
            if code == 429 or code >= 500:
                LAST_ERR[provider] = "rate_limited" if code == 429 else "http_5xx"
                time.sleep(delay); delay *= 2; continue
            if code != 200:
                LAST_ERR[provider] = f"http_{code}"; return None
            out = r.text if as_text else r.json()
            if as_text and out.lstrip()[:15].lower().startswith(("<!doctype html", "<html")):
                LAST_ERR[provider] = "html_challenge"; return None  # an HTML challenge page is not data
            if max_age:
                D.cache_put(ns, url, out)
            LAST_ERR.pop(provider, None)
            return out
        except requests.exceptions.SSLError:
            LAST_ERR[provider] = "tls"; time.sleep(delay); delay *= 2
        except requests.Timeout:
            LAST_ERR[provider] = "timeout"; time.sleep(delay); delay *= 2
        except requests.RequestException:
            LAST_ERR[provider] = "network"; time.sleep(delay); delay *= 2
        except ValueError:
            LAST_ERR[provider] = "schema"; time.sleep(delay); delay *= 2
    return None


def first(provider_label: str, attempts: list[tuple[str, Any]]) -> tuple[Any, str | None]:
    """Try (name, thunk) pairs in order; mark the provider ok with the one that worked, or failed."""
    if D._fail_sim(provider_label):
        D.mark(provider_label, False, "simulated outage"); return None, None
    tried = []
    for name, fn in attempts:
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001 - a parse error is a provider failure, not a crash
            res = None; tried.append(f"{name}: {type(e).__name__}")
        if res:
            D.mark(provider_label, True, f"via {name}" + (f" (after {', '.join(tried)} failed)" if tried else ""))
            return res, name
        if not tried or not tried[-1].startswith(name):
            tried.append(f"{name}: no data")
    D.mark(provider_label, False, "; ".join(tried)[:200])
    return None, None
