#!/usr/bin/env python3
"""
Scores the lead judge (and optionally the old regex gates) against labeled posts.

  .venv/bin/python eval/run_eval.py                # judge vs dataset/seed_labeled.jsonl + dataset/labels.jsonl
  .venv/bin/python eval/run_eval.py --regex        # also score the legacy regex gates
Each labeled line: {"category": "BUYER|SELLER|...", "buyer": bool, "author", "headline", "content"}
"""
import os
import sys
import json
import argparse
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.judge import LeadJudge  # noqa: E402


def load_labeled():
    rows = []
    for name in ("seed_labeled.jsonl", "labels.jsonl"):
        path = os.path.join(ROOT, "dataset", name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows += [json.loads(l) for l in f if l.strip()]
    return rows


def report(title, results):
    tp = sum(1 for r in results if r["pred"] and r["buyer"])
    fp = sum(1 for r in results if r["pred"] and not r["buyer"])
    fn = sum(1 for r in results if not r["pred"] and r["buyer"])
    tn = sum(1 for r in results if not r["pred"] and not r["buyer"])
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    acc = (tp + tn) / len(results) if results else 0.0
    print(f"\n== {title} ==  n={len(results)}  precision={prec:.0%}  recall={rec:.0%}  accuracy={acc:.0%}  (TP={tp} FP={fp} FN={fn} TN={tn})")
    for r in results:
        if r["pred"] != r["buyer"]:
            kind = "FALSE POSITIVE" if r["pred"] else "MISSED BUYER"
            print(f"  {kind}: [{r['category']}] {r['author']} — {r['why'][:140]}")
    return prec, rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regex", action="store_true", help="also score the legacy regex gates")
    ap.add_argument("--min-conf", type=float, default=0.7)
    args = ap.parse_args()

    rows = load_labeled()
    if not rows:
        sys.exit("No labeled data found in dataset/.")
    print(f"Loaded {len(rows)} labeled posts ({sum(r['buyer'] for r in rows)} buyers). "
          f"{sum(1 for r in rows if r.get('source') == 'synthetic')} are synthetic seed examples.")

    judge = LeadJudge()
    j_res, cat_hits = [], Counter()
    for r in rows:
        v = judge.judge(r["author"], r["headline"], r["content"])
        pred = LeadJudge.is_qualified(v, args.min_conf)
        cat_hits[(r["category"], v["category"])] += 1
        j_res.append({**r, "pred": pred, "why": f"judged {v['category']} ({v['confidence']:.2f}): {v['reasoning']}"})
    report(f"LLM judge (model={judge.model}, min_conf={args.min_conf})", j_res)
    print(f"  API calls: {judge.calls}, cache hits: {judge.cache_hits}")

    if args.regex:
        from src.verification import verify_bde_lead_authenticity, verify_sales_buying_intent
        g_res = []
        for r in rows:
            a, _ = verify_bde_lead_authenticity(r["author"], r["headline"], "", "", r["content"])
            i, _ = verify_sales_buying_intent(r["content"], r["headline"])
            g_res.append({**r, "pred": bool(a and i), "why": "regex gates"})
        report("Legacy regex gates", g_res)


if __name__ == "__main__":
    main()
