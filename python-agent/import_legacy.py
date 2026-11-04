#!/usr/bin/env python3
"""
import_legacy.py - dump everything the earlier agent runs left behind into the collector database (dataset/posts.db).

Nothing is cleaned or merged. Every record becomes one row in `posts` (intent = 'legacy:<source>'), with all of its
original fields plus the same computed features in the `data` JSON column. Query-run records go to `queries`.

  .venv/bin/python import_legacy.py                # into dataset/posts.db
  .venv/bin/python import_legacy.py --db other.db
  .venv/bin/python import_legacy.py --force        # import again even if legacy rows already exist
"""
import os
import re
import csv
import sys
import json
import glob
import argparse

from src.config import BASE_DIR
import collect_posts as cp


def first(d, *names):
    """First non-empty value among several possible key names (case-insensitive)."""
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return ""


def insert_post(db, source, record, scraped_at, query="", freshness="", content="", author_url="", post_url="", raw_time="", extra=None):
    """One row in `posts`. `data` keeps the original record untouched plus the computed features."""
    card = {"author_url": author_url, "direct_post_url": post_url, "content": content, "author": first(record, "author", "author name")}
    features = {"age_days": cp.age_days(raw_time), "content_len": len(content), "word_count": len(content.split()),
                "hashtag_count": len(re.findall(r"#\w+", content)),
                "has_url": bool(re.search(r"https?://|lnkd\.in|www\.", content)), "has_question": "?" in content}
    data = {"source": source, **(extra or {}), "original": record, **features}
    db.execute("INSERT INTO posts (scraped_at,intent,query,freshness,rank,post_key,post_url,author_url,data) VALUES (?,?,?,?,?,?,?,?,?)",
               (scraped_at or "", f"legacy:{source}", query, freshness, None, cp.post_key_of(card), post_url, author_url,
                json.dumps(data, ensure_ascii=False)))


def import_cards(db, root):
    n = 0
    for line in open(os.path.join(root, "dataset", "cards.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            insert_post(db, "cards.jsonl", r, r.get("seen_at"), query=r.get("query", ""), content=r.get("content", ""),
                        author_url=r.get("author_url", ""))
            n += 1
    return n


def import_seeds(db, root):
    n = 0
    for line in open(os.path.join(root, "dataset", "seed_labeled.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            insert_post(db, "seed_labeled", r, "", content=r.get("content", ""))
            n += 1
    return n


LOG_RE = re.compile(r"^\[(?P<ts>[\d\-]+ [\d:]+),\d+\] \[\w+\] SKIPPED POST TEXT \[(?P<kind>[^\]]*)\] (?P<author>.*?) \| headline='(?P<headline>.*?)' \| (?:(?P<check>intent_check=.*?) \| )?(?P<post>post=.*)$")


def import_logs(db, root):
    n = bad = 0
    for f in sorted(glob.glob(os.path.join(root, "logs", "*.log")) + glob.glob(os.path.join(root, "logs", "*.txt"))):
        for line in open(f, encoding="utf-8", errors="ignore"):
            if "SKIPPED POST TEXT" not in line:
                continue
            m = LOG_RE.match(line.rstrip("\n"))
            if not m:
                bad += 1
                continue
            text = m["post"][len("post='"):].rstrip()
            text = text[:-1] if text.endswith("'") else text
            rec = {"author": m["author"], "headline": m["headline"], "skip_kind": m["kind"], "intent_check": (m["check"] or "")[len("intent_check="):], "post_excerpt": text,
                   "log_file": os.path.basename(f), "raw_line": line.rstrip("\n")}
            insert_post(db, "skipped_log", rec, m["ts"].replace(" ", "T"), content=text)
            n += 1
    return n, bad


def import_leads(db, root):
    n = 0
    exp = os.path.join(root, "exports")
    for f in sorted(glob.glob(os.path.join(exp, "*.json"))):
        base = os.path.basename(f)
        if base.startswith(("metrics_", "intents_report")):
            continue
        data = json.load(open(f, encoding="utf-8"))
        for r in data if isinstance(data, list) else []:
            insert_post(db, "lead_exports", r, first(r, "timestamp", "saved_at", "found_at"),
                        content=str(first(r, "post excerpt", "post_excerpt", "post_content", "content", "buying intent signal")),
                        author_url=first(r, "profile url", "profile_url", "author_url"), post_url=first(r, "post url", "post_url"),
                        raw_time=first(r, "post age"), extra={"source_file": base})
            n += 1
    for f in sorted(glob.glob(os.path.join(exp, "*.csv"))):      # CSVs whose JSON twin exists are the same leads
        if os.path.exists(f[:-4] + ".json"):
            continue
        base = os.path.basename(f)
        for r in csv.DictReader(open(f, encoding="utf-8")):
            insert_post(db, "lead_exports", dict(r), first(r, "timestamp"),
                        content=str(first(r, "post excerpt", "buying intent signal")),
                        author_url=first(r, "profile url"), post_url=first(r, "post url"), extra={"source_file": base})
            n += 1
    return n


def import_memory(db, root):
    m = json.load(open(os.path.join(root, "agent_memory.json"), encoding="utf-8"))
    leads = 0
    for r in m.get("qualified_leads", []):
        insert_post(db, "memory_qualified_leads", r, r.get("timestamp"), author_url=r.get("profile_url", ""), post_url=r.get("post_url", ""))
        leads += 1
    runs = 0
    for r in m.get("execution_history", []):                       # the process log: every query the agent ran
        db.execute("INSERT INTO queries (intent,query,freshness,posts_found,scrolls,status,started_at,seconds) VALUES (?,?,?,?,?,?,?,?)",
                   ("legacy:agent_memory", r.get("query", ""), r.get("freshness", ""), r.get("cards_found"), None,
                    f"qualified={r.get('qualified_count')}; {r.get('outcome', '')}", r.get("timestamp", ""), None))
        runs += 1
    return leads, runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=cp.DEFAULT_DB)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    db = cp.open_db(args.db)
    if not args.force and db.execute("SELECT 1 FROM posts WHERE intent LIKE 'legacy:%' LIMIT 1").fetchone():
        sys.exit("Legacy rows are already in this database (use --force to import again).")
    counts = {"cards.jsonl": import_cards(db, BASE_DIR), "seed_labeled": import_seeds(db, BASE_DIR)}
    counts["skipped_log"], unparsed = import_logs(db, BASE_DIR)
    counts["lead_exports"] = import_leads(db, BASE_DIR)
    counts["memory_qualified_leads"], query_runs = import_memory(db, BASE_DIR)
    db.commit()
    print("Imported into", args.db)
    for k, v in counts.items():
        print(f"  posts   legacy:{k:<24} {v}")
    print(f"  queries legacy:agent_memory          {query_runs}")
    if unparsed:
        print(f"  ({unparsed} skipped-log lines had an unexpected format and were not imported)")
    cp.print_stats(db)


if __name__ == "__main__":
    main()
