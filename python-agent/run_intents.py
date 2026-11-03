#!/usr/bin/env python3
"""
Runs the agent once per intent in intents_rewritten.md (sequentially - one Chrome profile), then writes a combined
performance report: exports/intents_report_<timestamp>.json and .md.

  .venv/bin/python run_intents.py                 # all intents, 3 leads, 8 minutes each
  .venv/bin/python run_intents.py -n 2 -t 5 --only 2,4
  .venv/bin/python run_intents.py --report-only exports/metrics_A.json exports/metrics_B.json ...
"""
import os, re, sys, glob, json, time, argparse, subprocess
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
EXPORTS = os.path.join(ROOT, "exports")


def parse_intents(path):
    text = open(path, encoding="utf-8").read()
    out = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        niche = re.search(r"^Niche:\s*(.+)$", body, re.M)
        intent = re.search(r"^Intent:\s*(.+)$", body, re.M)
        if intent:
            out.append({"title": title.strip(), "niche": niche.group(1).strip() if niche else "", "intent": intent.group(1).strip()})
    return out


def metrics_files():
    return set(glob.glob(os.path.join(EXPORTS, "metrics_*.json")))


def run_one(i, it, leads, minutes):
    before = metrics_files()
    cmd = [os.path.join(ROOT, ".venv/bin/python"), os.path.join(ROOT, "run_autonomous_leads.py"),
           "-n", str(leads), "-t", str(minutes), "--intent", it["intent"]]
    if it["niche"]:
        cmd += ["--niche", it["niche"]]
    log = os.path.join(ROOT, "logs", f"intent_run_{i}_{datetime.now().strftime('%H%M%S')}.txt")
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":0"))
    with open(log, "w", encoding="utf-8") as f:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env).returncode
    new = sorted(metrics_files() - before)
    return (new[-1] if new else None), rc, log


def build_report(rows):
    tot = {"leads": 0, "searches": 0, "judged": 0, "matches": 0, "usd": 0.0, "sec": 0.0}
    for r in rows:
        m = r.get("metrics")
        if not m:
            continue
        tot["leads"] += m["run"]["leads_found"]; tot["searches"] += m["search"]["searches"]
        tot["judged"] += m["funnel"][2]["count"]; tot["matches"] += m["funnel"][3]["count"]
        tot["usd"] += m["cost"]["estimated_usd"]; tot["sec"] += m["run"]["duration_sec"]
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "totals": tot, "intents": rows}


def render_md(rep):
    t = rep["totals"]
    L = ["# Intent comparison", "", f"Generated {rep['generated_at']}", "",
         f"**Totals:** {t['leads']} leads, {t['searches']} searches, {t['judged']} posts judged, {t['matches']} judge matches, "
         f"{t['sec']/60:.0f} min, ~${t['usd']:.3f}", "",
         "| # | Intent | Leads | Stop | Min | Searches | Empty | Posts seen | New | Judged | Matches | Loc ok | Judged/lead | Dup % | $ |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["intents"]:
        m = r.get("metrics")
        if not m:
            L.append(f"| {r['n']} | {r['title']} | - | run failed (exit {r.get('rc')}) | | | | | | | | | | | |")
            continue
        f = m["funnel"]; e = m["efficiency"]
        L.append(f"| {r['n']} | {r['title']} | {m['run']['leads_found']}/{m['run']['target_leads']} | {m['run']['stop_reason']} | "
                 f"{m['run']['duration_sec']/60:.1f} | {m['search']['searches']} | {m['search']['zero_result_searches']} | "
                 f"{f[0]['count']} | {f[1]['count']} | {f[2]['count']} | {f[3]['count']} | {f[4]['count']} | "
                 f"{e['posts_judged_per_lead'] or '-'} | {e['duplicate_post_rate_pct']} | {m['cost']['estimated_usd']:.3f} |")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--leads", type=int, default=3)
    ap.add_argument("-t", "--minutes", type=int, default=8)
    ap.add_argument("--file", default=os.path.join(ROOT, "intents_rewritten.md"))
    ap.add_argument("--only", default="", help="comma-separated intent numbers, e.g. 2,4")
    ap.add_argument("--pause", type=int, default=45, help="seconds between runs")
    ap.add_argument("--report-only", nargs="*", help="skip running; build the report from these metrics files")
    a = ap.parse_args()

    intents = parse_intents(a.file)
    rows = []
    if a.report_only is not None:
        for i, p in enumerate(a.report_only, 1):
            rows.append({"n": i, "title": intents[i-1]["title"] if i <= len(intents) else p, "metrics": json.load(open(p)), "metrics_file": p})
    else:
        only = {int(x) for x in a.only.split(",") if x.strip()}
        for i, it in enumerate(intents, 1):
            if only and i not in only:
                continue
            print(f"[{datetime.now():%H:%M:%S}] Intent {i}: {it['title']}", flush=True)
            mf, rc, log = run_one(i, it, a.leads, a.minutes)
            print(f"   exit={rc} metrics={os.path.basename(mf) if mf else None} log={log}", flush=True)
            rows.append({"n": i, "title": it["title"], "intent": it["intent"], "rc": rc, "log": log,
                         "metrics_file": mf, "metrics": json.load(open(mf)) if mf else None})
            if rows[-1]["metrics"] and rows[-1]["metrics"]["run"]["stop_reason"] == "safety_halt":
                print("   Safety halt - stopping the batch to protect the account.", flush=True)
                break
            time.sleep(a.pause)
    rep = build_report(rows)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    jp, mp = os.path.join(EXPORTS, f"intents_report_{stamp}.json"), os.path.join(EXPORTS, f"intents_report_{stamp}.md")
    json.dump(rep, open(jp, "w"), indent=2, ensure_ascii=False)
    open(mp, "w", encoding="utf-8").write(render_md(rep))
    print(render_md(rep)); print(jp); print(mp)


if __name__ == "__main__":
    main()
