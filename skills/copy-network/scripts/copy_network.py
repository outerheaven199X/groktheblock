#!/usr/bin/env python3
"""Copy Trade Network: graph of leader (INSIDER/AGENT) -> follower wallets
from a token-scan JSON (detectCopyRelationships port: follower buys 3-30s after
a leader, blocks 2-10, delay stddev < 5s).

usage: copy_network.py <scan.json> [--out graph.png]
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from cryptosint.data import short

COL = {"INSIDER": "#ff3b5c", "AGENT": "#b06bff", "SNIPER": "#ffb020", "COPY": "#4fc3ff", "ORGANIC": "#00e87b"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("scan"); ap.add_argument("--out")
    a = ap.parse_args()
    r = json.loads(Path(a.scan).read_text())
    rels = r.get("copyNetwork") or []
    types = {w["address"]: w["type"] for w in r["wallets"]}
    sym = r["token"]["symbol"]
    out = Path(a.out) if a.out else Path(a.scan).with_name(f"copy-network-{sym}.png")
    leaders = {}
    for x in rels:
        leaders.setdefault(x["leader"], []).append(x)
    print(f"${sym}: {len(rels)} copy relationships, {len(leaders)} leaders")
    for l, fs in sorted(leaders.items(), key=lambda kv: -len(kv[1])):
        print(f"  leader {short(l)} ({types.get(l, '?')}) <- {len(fs)} followers, avg delay {sum(f['avgDelaySeconds'] for f in fs) / len(fs):.0f}s")
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt, networkx as nx
    G = nx.DiGraph()
    for x in rels:
        G.add_edge(x["leader"], x["follower"], d=x["avgDelaySeconds"])
    fig, ax = plt.subplots(figsize=(11, 8), facecolor="#07080a"); ax.set_facecolor("#07080a"); ax.axis("off")
    if G:
        pos = nx.spring_layout(G, seed=3, k=0.6)
        nx.draw_networkx_edges(G, pos, edge_color="#666", arrows=True, ax=ax, alpha=.7)
        nx.draw_networkx_nodes(G, pos, node_color=[COL.get(types.get(n, "COPY"), "#4fc3ff") for n in G], node_size=[600 if n in leaders else 160 for n in G], ax=ax)
        nx.draw_networkx_labels(G, pos, labels={n: short(n) for n in G}, font_size=7, font_color="#e8e8e8", ax=ax)
        nx.draw_networkx_edge_labels(G, pos, edge_labels={(u, v): f"{d['d']}s" for u, v, d in G.edges(data=True)}, font_size=6, font_color="#aaa", bbox=dict(alpha=0), ax=ax)
    else:
        ax.text(.5, .5, "No copy-trade relationships detected in this scan window", color="#e8e8e8", ha="center", transform=ax.transAxes)
    ax.set_title(f"${sym} copy-trade network (leader → follower, avg delay). Timing patterns, not proof of control.", color="#e8e8e8")
    fig.tight_layout(); fig.savefig(out, dpi=130, facecolor=fig.get_facecolor()); plt.close(fig)
    print(f"PNG: {out}")


if __name__ == "__main__":
    main()
