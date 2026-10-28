"""Synthetic checks that the Python port matches classify.ts rules. Run: python3 tests/test_classify.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from cryptosint import classify as C

M, DEP = "MINT", "DEPLOYER"


def tx(slot, ts, transfers, native=(), accts=()):
    return {"slot": slot, "timestamp": ts, "feePayer": DEP, "signature": f"s{slot}{ts}",
            "tokenTransfers": [{"mint": M, "tokenAmount": a, "fromUserAccount": f, "toUserAccount": t} for f, t, a in transfers],
            "nativeTransfers": [{"fromUserAccount": f, "toUserAccount": t, "amount": 1} for f, t in native],
            "accountData": [{"account": a, "nativeBalanceChange": 0} for a in accts]}


txs = [tx(100, 1000, [(None, "INS", 500)], native=[(DEP, "INS")]),          # block 0, deployer funded -> INSIDER
       tx(101, 1002, [(None, "SNP", 1)]),                                    # block 1, 1 tx -> SNIPER
       tx(102, 1010, [(None, "CPY", 1)])] + \
      [tx(103 + i, 1011 + i, [(None, "CPY", 1)]) for i in range(3)] + \
      [tx(200 + i, 2000 + i, [(None, "BOT", 1)]) for i in range(12)] + \
      [tx(300, 3000, [(None, "ORG", 1)]),
       tx(301, 3001, [(None, "MEV", 1)], accts=["T1pyyaTNZsKv2WcRAB8oVnk93mLJw2XzjtVYqCsaHqt"])]
txs += [tx(302 + i, 3002 + i * 7, [(None, "MEV", 1)], accts=["T1pyyaTNZsKv2WcRAB8oVnk93mLJw2XzjtVYqCsaHqt"]) for i in range(6)]
p = C.build_wallet_profiles(txs, M, DEP)
ws = {w["address"]: w for w in C.classify_all_wallets(p, sum(max(0, x.currentHolding) for x in p))}
exp = {"INS": "INSIDER", "SNP": "SNIPER", "CPY": "COPY", "BOT": "AGENT", "ORG": "ORGANIC", "MEV": "AGENT"}
for k, v in exp.items():
    assert ws[k]["type"] == v, (k, ws[k])
assert ws["INS"]["tag"] == "FUNDED BY DEPLOYER"
assert ws["BOT"]["tag"].startswith("BOT PATTERN — 0.0s STDDEV")
assert ws["MEV"]["tag"] == "MEV BOT — 7 TXS"
rels = C.detect_copy_relationships(p, list(ws.values()))
assert any(r["follower"] == "CPY" and r["leader"] == "INS" and r["avgDelaySeconds"] == 10 for r in rels), rels
assert C.compute_organic_score(list(ws.values())) == 17
assert C.generate_verdict(17, C.count_types(list(ws.values())))["severity"] == "CRITICAL"
rep = C.compute_reputation([{"classification": "INSIDER", "entryBlock": 0}, {"classification": "SNIPER", "entryBlock": 1}], "3h", 5)
assert rep == {"score": 90, "grade": "EXTREME", "factors": ["INSIDER on 1 token", "SNIPER on 1 token", "Avg entry block 0.5", "Wallet age: 3h", "Funds 5 wallets"]}, rep
print("classify port: all checks passed", {k: ws[k]["type"] for k in exp}, "copy:", rels)
