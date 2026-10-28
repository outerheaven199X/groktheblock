#!/usr/bin/env python3
"""Shill-network detector: find coordinated posting patterns around a ticker on X.

Python can't call the bot's X tools, so the bot saves raw X search responses
(the JSON returned by search_posts_all, with expansions=author_id and
user.fields=created_at,public_metrics,...) into a folder, then runs:

  shill_network.py <ticker-label> <file-or-dir> [more ...] [--out-dir out/] [--sim 0.6]

Signals (each is a pattern, not proof):
  - near-identical text  : word-shingle Jaccard >= --sim after stripping links/mentions/numbers
  - account age          : account created < 30 days before posting; creation dates clustered within 72h
  - posting-time bursts  : >= 4 distinct accounts posting within a 5-minute window
  - follower/following   : following/followers >= 10, or < 25 followers
Accounts linked by text similarity (strong) or by shared burst + shared creation
window (medium) form a graph; connected groups of >= 3 accounts are reported as
"coordinated pattern clusters".
"""
import argparse, json, re, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

URL = re.compile(r"https?://\S+")
MENTION = re.compile(r"@\w+")
NUM = re.compile(r"\d+([.,]\d+)?")
WS = re.compile(r"\s+")


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load(paths):
    posts, users = {}, {}
    files = []
    for p in map(Path, paths):
        files += sorted(p.glob("*.json")) + sorted(p.glob("*.txt")) if p.is_dir() else [p]
    for f in files:
        raw = f.read_text()
        # tolerate tool output with trailing notes: grab the first JSON object
        start = raw.find("{")
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[start:])
        except Exception:
            print(f"skip {f}: no JSON", file=sys.stderr); continue
        for d in obj.get("data") or []:
            if d.get("text", "").startswith("RT @"):
                continue  # retweets are copies by design; search with -is:retweet
            posts[d["id"]] = d
        for u in (obj.get("includes") or {}).get("users") or []:
            users[u["id"]] = u
    return list(posts.values()), users


B58 = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def norm(text):
    t = B58.sub(" ", text)  # contract addresses are shared by everyone; don't let them create similarity
    t = URL.sub(" ", t.lower()); t = MENTION.sub(" ", t); t = NUM.sub(" # ", t)
    t = re.sub(r"[^\w$#\s]", " ", t)
    return WS.sub(" ", t).strip()


def shingles(t, k=3):
    w = t.split()
    if len(w) < k:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def analyze(label, posts, users, sim=0.6, burst_s=300, burst_min=4):
    for p in posts:
        p["_t"] = parse_time(p["created_at"]); p["_n"] = norm(p.get("text", "")); p["_sh"] = shingles(p["_n"])
    posts.sort(key=lambda p: p["_t"])
    by_author = defaultdict(list)
    for p in posts:
        by_author[p["author_id"]].append(p)
    acct = {}
    for a, ps in by_author.items():
        u = users.get(a, {})
        pm = u.get("public_metrics") or {}
        fol, fing = pm.get("followers_count", 0), pm.get("following_count", 0)
        created = parse_time(u["created_at"]) if u.get("created_at") else None
        age_days = (ps[0]["_t"] - created).days if created else None
        flags = []
        if age_days is not None and age_days < 30: flags.append(f"account {age_days}d old at first post")
        if fol < 25: flags.append(f"{fol} followers")
        if fol and fing / max(fol, 1) >= 10: flags.append(f"following/followers {fing}/{fol}")
        acct[a] = {"id": a, "username": u.get("username", a), "followers": fol, "following": fing,
                   "created_at": u.get("created_at"), "age_days_at_post": age_days, "posts": len(ps),
                   "verified": u.get("verified"), "flags": flags}
    # --- edges
    edges = defaultdict(lambda: {"text": 0, "burst": 0, "created": 0, "examples": []})
    authors = list(by_author)
    # text similarity (pairwise over posts from different authors)
    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            a, b = posts[i], posts[j]
            if a["author_id"] == b["author_id"]: continue
            s = jaccard(a["_sh"], b["_sh"])
            if s >= sim and len(a["_n"].split()) >= 4:
                k = tuple(sorted((a["author_id"], b["author_id"])))
                edges[k]["text"] += 1
                if len(edges[k]["examples"]) < 2: edges[k]["examples"].append([a.get("url"), b.get("url"), round(s, 2)])
    # bursts
    bursts = []
    i = 0
    while i < len(posts):
        j = i
        while j + 1 < len(posts) and (posts[j + 1]["_t"] - posts[i]["_t"]).total_seconds() <= burst_s: j += 1
        auth = {p["author_id"] for p in posts[i:j + 1]}
        if len(auth) >= burst_min:
            bursts.append({"start": posts[i]["created_at"], "end": posts[j]["created_at"], "accounts": sorted(auth), "posts": j - i + 1})
            i = j + 1
        else:
            i += 1
    burst_of = defaultdict(set)
    for bi, b in enumerate(bursts):
        for a in b["accounts"]: burst_of[a].add(bi)
    # creation-date clusters (72h windows) among accounts younger than 1 year
    cr = sorted([(parse_time(v["created_at"]), k) for k, v in acct.items() if v["created_at"]])
    created_group = {}
    gi = 0
    for idx, (t, a) in enumerate(cr):
        grp = [b for (t2, b) in cr if 0 <= (t2 - t).total_seconds() <= 72 * 3600]
        if len(grp) >= 3 and a not in created_group:
            for b in grp: created_group.setdefault(b, gi)
            gi += 1
    for x in range(len(authors)):
        for y in range(x + 1, len(authors)):
            a, b = authors[x], authors[y]
            k = tuple(sorted((a, b)))
            if burst_of[a] & burst_of[b]: edges[k]["burst"] += len(burst_of[a] & burst_of[b])
            if a in created_group and created_group.get(a) == created_group.get(b): edges[k]["created"] = 1
    strong = {k: e for k, e in edges.items() if e["text"] > 0 or (e["burst"] > 0 and e["created"])}
    # components
    parent = {a: a for a in authors}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in strong: parent[find(a)] = find(b)
    comps = defaultdict(list)
    for a in authors: comps[find(a)].append(a)
    clusters = []
    for members in comps.values():
        if len(members) < 3: continue
        mem = set(members)
        es = {k: e for k, e in strong.items() if k[0] in mem}
        sample_texts = []
        for a in members:
            sample_texts.append(by_author[a][0].get("text", "")[:140])
        clusters.append({
            "size": len(members),
            "accounts": [acct[a]["username"] for a in members],
            "posts": sum(acct[a]["posts"] for a in members),
            "textLinks": sum(1 for e in es.values() if e["text"]), "burstAndCreationLinks": sum(1 for e in es.values() if e["burst"] and e["created"]),
            "medianFollowers": sorted(acct[a]["followers"] for a in members)[len(members) // 2],
            "youngAccounts": sum(1 for a in members if (acct[a]["age_days_at_post"] or 9999) < 30),
            "exampleLinks": [ex for e in es.values() for ex in e["examples"]][:4],
            "sampleTexts": sample_texts[:4],
        })
    clusters.sort(key=lambda c: -c["posts"])
    in_cluster = {a for c in comps.values() if len(c) >= 3 for a in c}
    coord_posts = sum(len(by_author[a]) for a in in_cluster)
    dup_groups = defaultdict(list)
    for p in posts:
        if len(p["_n"].split()) >= 4: dup_groups[p["_n"]].append(p["author_id"])
    exact = sorted(([t, len(set(a))] for t, a in dup_groups.items() if len(set(a)) >= 2), key=lambda x: -x[1])[:10]
    report = {
        "ticker": label, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sample": {"posts": len(posts), "accounts": len(acct),
                   "from": posts[0]["created_at"] if posts else None, "to": posts[-1]["created_at"] if posts else None},
        "coordinationIndex": round(100 * coord_posts / len(posts)) if posts else 0,
        "coordinationIndexMeaning": "% of sampled posts that came from accounts inside a coordinated pattern cluster (>=3 linked accounts). Signal, not a verdict.",
        "clusters": clusters,
        "bursts": bursts[:20],
        "exactDuplicateTexts": exact,
        "accountFlags": {"young(<30d)": sum(1 for v in acct.values() if (v["age_days_at_post"] or 9999) < 30),
                          "lowFollowers(<25)": sum(1 for v in acct.values() if v["followers"] < 25),
                          "highFollowingRatio(>=10x)": sum(1 for v in acct.values() if v["followers"] and v["following"] / max(v["followers"], 1) >= 10)},
        "accounts": sorted(acct.values(), key=lambda v: -v["posts"]),
        "edges": [{"a": acct[k[0]]["username"], "b": acct[k[1]]["username"], **{x: e[x] for x in ("text", "burst", "created")}} for k, e in strong.items()],
        "disclaimer": "These are coordinated-pattern signals from a public sample, not accusations. Similar text can be a meme, a quote, or a giveaway template; check examples before saying anything.",
    }
    return report


def draw(report, path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt, networkx as nx
    G = nx.Graph()
    accts = {a["username"]: a for a in report["accounts"]}
    for e in report["edges"]:
        G.add_edge(e["a"], e["b"], kind="text" if e["text"] else "timing")
    for u in accts:
        if u not in G and len(G) < 400: G.add_node(u)
    fig, ax = plt.subplots(figsize=(12, 9), facecolor="#07080a"); ax.set_facecolor("#07080a")
    pos = nx.spring_layout(G, k=0.35, seed=7)
    linked = {n for e in G.edges for n in e}
    colors = ["#ff3b5c" if n in linked else "#00e87b" for n in G.nodes]
    sizes = [40 + min(400, 10 * accts.get(n, {}).get("posts", 1)) for n in G.nodes]
    te = [e for e in G.edges if G.edges[e]["kind"] == "text"]; ti = [e for e in G.edges if G.edges[e]["kind"] != "text"]
    nx.draw_networkx_edges(G, pos, edgelist=te, edge_color="#ff3b5c", alpha=.6, ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=ti, edge_color="#ffb020", style="dashed", alpha=.5, ax=ax)
    nx.draw_networkx_nodes(G, pos, node_color=colors, node_size=sizes, ax=ax, linewidths=0)
    if len(linked) <= 60:
        nx.draw_networkx_labels(G, pos, labels={n: "@" + n for n in linked}, font_size=7, font_color="#e8e8e8", ax=ax)
    s = report["sample"]
    ax.set_title(f"{report['ticker']} on X: coordination index {report['coordinationIndex']}%  |  {s['posts']} posts, {s['accounts']} accounts\n"
                 "red = linked by near-identical text (solid) or shared burst + creation window (dashed); green = no link. Signals, not verdicts.",
                 color="#e8e8e8", fontsize=10)
    ax.axis("off"); fig.tight_layout(); fig.savefig(path, dpi=140, facecolor=fig.get_facecolor()); plt.close(fig)


def markdown(r):
    L = [f"# Shill-network report: {r['ticker']}", "",
         f"Sample: {r['sample']['posts']} posts from {r['sample']['accounts']} accounts ({r['sample']['from']} to {r['sample']['to']}).",
         f"**Coordination index: {r['coordinationIndex']}%** ({r['coordinationIndexMeaning']})", "",
         f"Account flags: {r['accountFlags']}", "", "## Coordinated pattern clusters"]
    if not r["clusters"]: L.append("None found in this sample.")
    for i, c in enumerate(r["clusters"][:10], 1):
        L += [f"### Cluster {i}: {c['size']} accounts, {c['posts']} posts, median followers {c['medianFollowers']}, {c['youngAccounts']} young accounts",
              "Accounts: " + ", ".join("@" + a for a in c["accounts"][:25]),
              *[f"> {t}" for t in c["sampleTexts"][:3]],
              *[f"- similar pair: {a} / {b} (similarity {s})" for a, b, s in c["exampleLinks"][:3]], ""]
    if r["exactDuplicateTexts"]:
        L += ["## Identical text posted by multiple accounts", *[f"- {n} accounts: \"{t[:120]}\"" for t, n in r["exactDuplicateTexts"]], ""]
    if r["bursts"]:
        L += ["## Posting bursts (>=4 accounts in 5 min)", *[f"- {b['start']}: {len(b['accounts'])} accounts, {b['posts']} posts" for b in r["bursts"][:10]], ""]
    L += ["---", r["disclaimer"]]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker"); ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[3] / "out"))
    ap.add_argument("--sim", type=float, default=0.6)
    a = ap.parse_args()
    posts, users = load(a.inputs)
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "", a.ticker) or "ticker"
    if not posts:
        empty = {"ticker": a.ticker, "generatedAt": None, "sample": {"posts": 0, "accounts": 0, "from": None, "to": None},
                 "coordinationIndex": 0, "coordinationIndexMeaning": "No posts to assess.", "clusters": [], "bursts": [],
                 "exactDuplicateTexts": [], "accountFlags": {"young(<30d)": 0}, "accounts": [], "edges": [],
                 "emptyReason": "X search returned no posts for this query. That is not evidence of organic promotion; the search window is short and sampled.",
                 "disclaimer": "Signals, not accusations."}
        (out / f"shill-{slug}.json").write_text(json.dumps(empty, indent=2))
        print(f"No posts found in inputs. Wrote an empty result (not a clean bill of health): {out}/shill-{slug}.json"); return
    r = analyze(a.ticker, posts, users, a.sim)
    (out / f"shill-{slug}.json").write_text(json.dumps(r, indent=2))
    (out / f"shill-{slug}.md").write_text(markdown(r))
    draw(r, out / f"shill-{slug}.png")
    print(markdown(r)[:3000]); print(f"\nFiles: {out}/shill-{slug}.json .md .png")


if __name__ == "__main__":
    main()
