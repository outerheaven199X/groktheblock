#!/usr/bin/env python3
"""Sanitize X data in example and demo JSON so posts and accounts can't be looked up.

Replaces verbatim post text with short paraphrased pattern summaries, strips links,
handles and IDs, and buckets follower counts. Cluster structure is kept.
Usage: python3 tools/sanitize_examples.py examples/*.json docs/verification/*.json
"""
import json, re, sys

def bucket(n):
    if isinstance(n, str) or n is None: return n
    for hi, lab in [(100, "<100"), (500, "100-500"), (1000, "500-1k"), (5000, "1k-5k"),
                    (10000, "5k-10k"), (50000, "10k-50k")]:
        if n < hi: return lab
    return "50k+"

def age_bucket(d):
    if d is None or isinstance(d, str): return d
    return "<30d" if d < 30 else "30d-1y" if d < 365 else "1-5y" if d < 1825 else "5y+"

RULES = [
    (r"bundle check|scam|rug|risk \d|dev'?s group", "Warning post: claims the launch was bundled or risky"),
    (r"boost", "Automated listing or boost notice"),
    (r"aped on|alpha (tg|group|circle)|dm to join|my tg|telegram", "Paid-group call brag with an invite to join"),
    (r"\d+(\.\d+)?\s*x\b|→|->|\bto \$?\d|went|hit different|called it|highlighted", "Multiplier brag: early market cap versus current"),
    (r"fading|missed|imagine", "FOMO post: missed-entry framing"),
    (r"still at|early|barely anyone|eyes on|don.t sleep", "Early-entry hype at a low market cap"),
    (r"backed by|believe", "Narrative or meme post about the token's theme"),
    (r"cto|wallet activity", "Wallet-activity commentary"),
]

def paraphrase(t):
    if not isinstance(t, str): return t
    low = t.lower()
    s = next((lab for pat, lab in RULES if re.search(pat, low)), "General promo mentioning the ticker")
    extras = []
    if re.search(r"[1-9A-HJ-NP-Za-km-z]{32,44}", t) or "ca" in re.findall(r"\bca\b", low): extras.append("contract address")
    if "#" in t: extras.append("hashtags")
    if "http" in low or "t.co" in low: extras.append("a link (removed)")
    return s + (" (includes " + ", ".join(extras) + ")" if extras else "")

def scrub_str(s):
    s = re.sub(r"https?://\S+", "[link removed]", s)
    s = re.sub(r"@\S*", "", s)
    return s

def sanitize(o, key=None):
    if isinstance(o, dict):
        if o.get("type") == "X_POST" and isinstance(o.get("detail"), str):
            m = re.match(r"@?(\S+) \((\d+) followers\): (.*)", o["detail"], re.S)
            o = dict(o, detail=f"{m.group(1)} ({bucket(int(m.group(2)))} followers): {paraphrase(m.group(3))}" if m else paraphrase(o["detail"]))
            o["_done"] = True
        out = {}
        for k, v in o.items():
            if k in ("created_at", "author_id", "tweet_id", "post_id", "conversation_id", "url", "exampleLinks") and not isinstance(v, (int, float)) or k in ("url", "exampleLinks"):
                if k == "url" and isinstance(v, str) and ("solscan" in v or "rugcheck" in v or "dexscreener" in v):
                    out[k] = v; continue
                if k == "exampleLinks": out[k] = []; continue
                continue
            if k in ("followers", "following", "medianFollowers"): out[k] = bucket(v); continue
            if k == "age_days_at_post": out["ageBucket"] = age_bucket(v); continue
            if k == "sampleTexts": out[k] = [paraphrase(t) for t in v]; continue
            if k == "exactDuplicateTexts": out[k] = [[paraphrase(t), n] for t, n in v]; continue
            out[k] = sanitize(v, k)
        if out.pop("_done", None):
            out["detail"] = o["detail"]
        return out
    if isinstance(o, list): return [sanitize(v, key) for v in o]
    if isinstance(o, str):
        if o.startswith("http") and any(d in o for d in ("solscan", "rugcheck", "dexscreener", "explorer.solana", "raydium", "pump.fun")): return o
        return scrub_str(o)
    return o

if __name__ == "__main__":
    for f in sys.argv[1:]:
        if not f.endswith(".json"): continue
        raw = open(f).read(); d = json.loads(raw)
        ind = None if "\n" not in raw.strip() else (1 if "\n " in raw and "\n  " not in raw else 2)
        out = json.dumps(sanitize(d), ensure_ascii=False, indent=ind)
        if out != json.dumps(d, ensure_ascii=False, indent=ind): open(f, "w").write(out)
        print("sanitized", f)
