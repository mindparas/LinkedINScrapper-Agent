#!/usr/bin/env python3
"""
collect_posts.py - bulk LinkedIn POST collector. Data only: no judging, no cleaning, no daily budget.

  for each intent (intents_rewritten.md), one after the other, each with its own share of the time limit:
      used = []                                   # fresh, empty list for every intent
      repeat until the intent's time is up:
          ask the cheap LLM for queries (free hand: it sees the intent and the list of queries already used)
          for each new query:  search "past 24 hours", then "past week"; scroll; dump every post card into SQLite

  .venv/bin/python collect_posts.py --minutes 60          # all intents, 60 minutes in total
  .venv/bin/python collect_posts.py --minutes 30 --only 1,4
  .venv/bin/python collect_posts.py --dry-run             # one round of queries per intent, no browser
  .venv/bin/python collect_posts.py --stats
"""

import os
import re
import sys
import json
import time
import random
import sqlite3
import hashlib
import argparse
import logging
import urllib.parse
from datetime import datetime

from src.config import BASE_DIR, Style
from src import llm
from src.browser import setup_stealth_driver, verify_or_prompt_login, scan_linkedin_content_cards
from src.safety import detect_checkpoint

DEFAULT_DB = os.path.join(BASE_DIR, "dataset", "posts.db")
DEFAULT_INTENTS = os.path.join(BASE_DIR, "intents_rewritten.md")
WINDOWS = ("past-24h", "past-week")

# ─────────────────────────────────────────────────────────────────────────────
# Database: three plain tables
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (            -- one row every time a search returns a post card (nothing is cleaned or merged)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at TEXT, intent TEXT, query TEXT, freshness TEXT, rank INTEGER,
    post_key TEXT,                            -- activity urn, or a hash of author+text; use it later to find repeats
    post_url TEXT, author_url TEXT,
    data TEXT                                 -- JSON with EVERYTHING about the post: card fields, full text, full HTML, links, images, buttons, attributes, features
);
CREATE TABLE IF NOT EXISTS queries (          -- the process log: every query run, per intent and window
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent TEXT, query TEXT, freshness TEXT, posts_found INTEGER, scrolls INTEGER, status TEXT,
    started_at TEXT, seconds REAL,
    page_url TEXT, page_text TEXT              -- the search page as a person sees it (full text)
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent TEXT, model TEXT, prompt TEXT, response TEXT, tokens_in INTEGER, tokens_out INTEGER, usd REAL,
    error TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT, area TEXT, title TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_intent ON posts(intent, query);
"""


def open_db(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    have = {r[1] for r in db.execute('PRAGMA table_info(queries)')}
    for col in ('page_url', 'page_text'):
        if col not in have:
            db.execute(f'ALTER TABLE queries ADD COLUMN {col} TEXT')
    db.commit()
    return db


def now():
    return datetime.now().isoformat(timespec="seconds")


def parse_intents(path):
    """Blocks shaped like '## Intent 1: title / Niche: ... / Intent: ...' (see intents_rewritten.md)."""
    text = open(path, encoding="utf-8").read()
    out = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        intent = re.search(r"^Intent:\s*(.+)$", body, re.M)
        if intent:
            out.append({"title": title.strip(), "intent": intent.group(1).strip()})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Queries: the cheap LLM, free hand
# ─────────────────────────────────────────────────────────────────────────────
QUERY_SYSTEM = ("You are a business development executive at a custom software development company (web, mobile, AI, healthcare, IoT). "
                "You find new clients by searching LinkedIn posts. You want posts written by people who need software built, in their own words. "
                "Write the short search queries (usually 2 to 5 words) that you would type into LinkedIn post search to find them. "
                "Return JSON: {\"queries\": [\"...\", \"...\"]}")


def situation_of(text):
    """The intent without its 'Typical phrases' and 'Exclude' sentences. The phrases are the label/seller words the model
    used to copy into its searches, and the exclusions are for later judging, not for searching."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(p for p in parts if not re.match(r"(Typical phrases|Exclude)\b", p))


def ask_queries(db, intent, used):
    """One LLM round for this intent. `used` is the list of queries already run for it. Returns a list of strings."""
    prompt = (f"The kind of client you are looking for:\n{situation_of(intent['intent'])}\n\n"
              "Write the search queries you would type into LinkedIn to find posts where these people say they need this. "
              "Think about what the person would literally write in the post. Write as many as you like.")
    if used:
        prompt += "\n\nQueries already used (write different ones):\n" + "\n".join(used)
    model, tin, tout, usd, error, data = llm.model_for("collector"), 0, 0, 0.0, "", None
    try:
        data, usage, model = llm.complete_json(QUERY_SYSTEM, prompt, "collector", max_tokens=3000, timeout=90)
        tin, tout = int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)
        pin, pout = llm.price_for(model)
        usd = (tin * pin + tout * pout) / 1e6
    except Exception as e:
        error = llm.describe_error(e)
    db.execute("INSERT INTO llm_calls (intent,model,prompt,response,tokens_in,tokens_out,usd,error,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (intent["title"], model, prompt, json.dumps(data, ensure_ascii=False) if data else "", tin, tout, usd, error, now()))
    db.commit()
    if error:
        print(f"   {Style.RED}query generation failed: {error}{Style.RESET}")
    out = []
    for q in (data or {}).get("queries", []):
        # The model writes freely. Quote marks are only dropped when searching: inside quotes LinkedIn demands the
        # exact phrase and returned nothing for most of them, without quotes the same words still match.
        q = " ".join(re.sub(r'["\u201c\u201d]', " ", str(q)).split())
        if q:
            out.append(q)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Scraping tools (browser)
# ─────────────────────────────────────────────────────────────────────────────
LAZY_LOAD_SCRIPT = """
    const more = Array.from(document.querySelectorAll('button')).find(b =>
        /show more results|see more results|load more/i.test((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')));
    if (more) { more.click(); return 'clicked_more'; }
    const items = document.querySelectorAll('[data-bde-card-id], div[role="listitem"]');
    let last = items.length ? items[items.length - 1] : null;
    if (!last) {
        const btns = document.querySelectorAll("button[aria-label*='Comment' i]");
        last = btns.length ? btns[btns.length - 1] : null;
    }
    if (last) {
        last.scrollIntoView({block: 'end', behavior: 'instant'});
        let el = last.parentElement;
        while (el) {
            if (el.scrollHeight > el.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(el).overflowY)) {
                el.scrollTop = el.scrollHeight;
            }
            el = el.parentElement;
        }
    }
    window.scrollTo(0, document.body.scrollHeight);
    return 'scrolled';
"""
COMMENT_BTN = "button[aria-label*='Comment' i]"

# Click every "see more" inside post cards so the FULL text is on the page before it is read.
EXPAND_SCRIPT = """
    // EXPAND_SEE_MORE
    let n = 0;
    document.querySelectorAll('div[role="listitem"] button, [data-bde-card-id] button').forEach(b => {
        const own = (b.innerText || '').trim().toLowerCase();
        const all = (own + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
        if ((/^(\\u2026|\\.\\.\\.)?\\s*(see )?more$/.test(own) || /see more/.test(all)) && !/comment|result|people|job/.test(all)) {
            try { b.click(); n++; } catch (_) {}
        }
    });
    return n;
"""

# Everything about each tagged post card: full HTML, full text, attributes, ids, links, images, videos, buttons.
CAPTURE_SCRIPT = """
    return Array.from(document.querySelectorAll('[data-bde-card-id]')).map(el => {
        const attrs = {};
        for (const a of el.attributes) attrs[a.name] = a.value;
        const urns = Array.from(el.querySelectorAll('[data-urn],[data-activity-urn],[data-entity-urn],[data-id]')).map(n => ({
            tag: n.tagName, urn: n.getAttribute('data-urn') || n.getAttribute('data-activity-urn') || n.getAttribute('data-entity-urn') || n.getAttribute('data-id')}));
        const anc = [];
        let p = el.parentElement;
        for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
            for (const a of p.attributes) if (/urn:li:/.test(a.value)) anc.push({name: a.name, value: a.value});
        }
        return {
            card_id: el.getAttribute('data-bde-card-id'),
            outer_html: el.outerHTML,
            inner_text: el.innerText || '',
            text_content: el.textContent || '',
            attributes: attrs, urns: urns, ancestor_urns: anc,
            links: Array.from(el.querySelectorAll('a[href]')).map(a => ({href: a.href, text: (a.innerText || '').trim(), aria: a.getAttribute('aria-label') || ''})),
            images: Array.from(el.querySelectorAll('img')).map(i => ({src: i.currentSrc || i.src, alt: i.alt || ''})),
            videos: Array.from(el.querySelectorAll('video, source')).map(v => ({src: v.currentSrc || v.src || '', poster: v.poster || ''})),
            buttons: Array.from(el.querySelectorAll('button')).map(b => ({text: (b.innerText || '').trim(), aria: b.getAttribute('aria-label') || ''}))
        };
    });
"""
URN_RE = re.compile(r"urn:li:(?:activity|ugcPost|share):\d+")


def expand_see_more(driver):
    try:
        if driver.execute_script(EXPAND_SCRIPT):
            time.sleep(1.2)                                    # let the expanded text render
    except Exception:
        pass


def capture_raw(driver):
    """{card_id: everything about that card}"""
    try:
        return {r["card_id"]: r for r in (driver.execute_script(CAPTURE_SCRIPT) or [])}
    except Exception:
        return {}


def enrich(card, raw):
    """Attach the full capture to the card; derive the post link from the raw HTML when the scanner found none."""
    card["raw"] = raw
    card["derived_post_url"] = ""
    if raw and not card.get("direct_post_url"):
        m = URN_RE.search(raw.get("outer_html", "")) or next(
            (URN_RE.search(str(a.get("value", ""))) for a in raw.get("ancestor_urns", []) if URN_RE.search(str(a.get("value", "")))), None)
        if m:
            card["derived_post_url"] = f"https://www.linkedin.com/feed/update/{m.group(0)}/"
    return card


def search_url(query, freshness, sort):
    url = ("https://www.linkedin.com/search/results/content/?keywords=" + urllib.parse.quote(query)
           + f"&datePosted=%22{freshness}%22&origin=GLOBAL_SEARCH_HEADER")
    return url + ("&sortBy=%5B%22date_posted%22%5D" if sort == "date" else "")


def count_cards(driver):
    from selenium.webdriver.common.by import By
    return len(driver.find_elements(By.CSS_SELECTOR, COMMENT_BTN))


def page_text_flags(driver):
    from selenium.webdriver.common.by import By
    text = driver.find_element(By.TAG_NAME, "body").text
    return ("No results found" in text or "Try removing filters or rephrasing your search" in text,
            "No more results" in text or "You've viewed all" in text)


def scroll_once(driver):
    """Trigger LinkedIn's lazy loading and wait (up to ~6s) for new cards."""
    before = count_cards(driver)
    driver.execute_script(LAZY_LOAD_SCRIPT)
    for _ in range(12):
        time.sleep(0.5)
        if count_cards(driver) > before:
            break
    time.sleep(random.uniform(*SCROLL_PAUSE))


def post_key_of(card):
    m = re.search(r"urn:li:(activity|ugcPost|share):(\d+)", (card.get("direct_post_url", "") or card.get("derived_post_url", "")) or "")
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    basis = (card.get("author_url", "") or card.get("author", "")) + "|" + " ".join((card.get("content", "") or "").split())[:300]
    return "h:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]


def age_days(raw):
    m = re.match(r"\s*(\d+)\s*(s|m|min|h|hr|d|day|w|wk|mo|yr)s?\b", (raw or "").lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {"s": n / 86400, "m": n / 1440, "min": n / 1440, "h": n / 24, "hr": n / 24, "d": n, "day": n,
            "w": n * 7, "wk": n * 7, "mo": n * 30, "yr": n * 365}[unit]


def dump_card(db, intent, query, freshness, rank, card):
    """Store the card as it came: a few columns for searching, and `data` = everything, as JSON."""
    content = (card.get("content") or "")
    features = {"age_days": age_days(card.get("raw_timestamp", "")), "content_len": len(content),
                "word_count": len(content.split()), "hashtag_count": len(re.findall(r"#\w+", content)),
                "has_url": bool(re.search(r"https?://|lnkd\.in|www\.", content)), "has_question": "?" in content}
    db.execute("INSERT INTO posts (scraped_at,intent,query,freshness,rank,post_key,post_url,author_url,data) VALUES (?,?,?,?,?,?,?,?,?)",
               (now(), intent, query, freshness, rank, post_key_of(card), (card.get("direct_post_url") or card.get("derived_post_url") or ""),
                card.get("author_url", ""), json.dumps({**card, **features}, ensure_ascii=False)))


# ─────────────────────────────────────────────────────────────────────────────
# Account safety: slower pacing, a wider warning detector, and a cool-down after any warning
# ─────────────────────────────────────────────────────────────────────────────
PAUSE_BETWEEN_SEARCHES = (8, 15)       # seconds, before every search page
BREAK_EVERY_SEARCHES = 5               # after this many searches, take a longer rest
LONG_BREAK = (60, 120)                 # seconds
SCROLL_PAUSE = (1.5, 3.0)              # seconds after each scroll
COOLDOWN_HOURS = 12
COOLDOWN_FILE = os.path.join(BASE_DIR, "dataset", "collector_cooldown.json")

# Looked for only in LinkedIn's own notice areas (alerts, dialogs, toasts) and the top of the page, never in post text,
# so a post that talks about "unusual activity" cannot stop a run.
WARNING_MARKERS = ("unusual activity", "unusual", "we noticed", "we've noticed", "suspicious", "automated", "robot", "captcha",
                   "restricted", "too many requests", "slow down", "temporarily", "verify", "security check", "not allowed",
                   "limit reached", "try again later", "something went wrong")
WARNING_SCRIPT = """
    // WARNING_SCAN
    const parts = [];
    document.querySelectorAll('[role="alert"], [role="alertdialog"], [role="dialog"], .artdeco-toast-item, .artdeco-modal, .artdeco-global-alert')
        .forEach(e => parts.push((e.innerText || '').trim()));
    return parts.filter(Boolean).join(' | ').slice(0, 1500);
"""


def detect_warning(driver):
    """Returns a reason when LinkedIn shows a challenge, restriction or 'unusual activity' notice, else ''."""
    reason = detect_checkpoint(driver)
    if reason:
        return reason
    try:
        notice = (driver.execute_script(WARNING_SCRIPT) or "").strip()
    except Exception:
        return ""
    low = notice.lower()
    for m in WARNING_MARKERS:
        if m in low:
            return f"LinkedIn showed a notice ('{m}'): {notice[:200]}"
    return ""


def cooldown_left():
    """Hours left of the cool-down that a warning started, or 0."""
    try:
        with open(COOLDOWN_FILE, encoding="utf-8") as f:
            until = json.load(f).get("until", 0)
        return max(0.0, (until - time.time()) / 3600)
    except Exception:
        return 0.0


def start_cooldown(reason):
    try:
        with open(COOLDOWN_FILE, "w", encoding="utf-8") as f:
            json.dump({"until": time.time() + COOLDOWN_HOURS * 3600, "reason": reason, "at": now()}, f)
    except Exception:
        pass


SEARCHES_DONE = [0]


def pace_before_search():
    """Rest between searches, and a longer break every few searches."""
    SEARCHES_DONE[0] += 1
    if SEARCHES_DONE[0] > 1 and (SEARCHES_DONE[0] - 1) % BREAK_EVERY_SEARCHES == 0:
        wait = random.uniform(*LONG_BREAK)
        print(f"   (resting {wait:.0f}s to keep the account calm)")
        time.sleep(wait)
    time.sleep(random.uniform(*PAUSE_BETWEEN_SEARCHES))


def stop_for_warning(db, driver, intent, query, freshness, reason, t0):
    """Print, remember (queries row with the page text, changes row, cool-down file) and tell the caller to stop."""
    print(f"{Style.RED}{Style.BOLD}🛑 {reason}. Stopping to protect the account (cool-down {COOLDOWN_HOURS}h).{Style.RESET}")
    try:
        page_url = driver.current_url
        page_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        page_url = page_text = ""
    db.execute("INSERT INTO queries (intent,query,freshness,posts_found,scrolls,status,started_at,seconds,page_url,page_text) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (intent, query, freshness, 0, 0, "checkpoint: " + reason[:300], now(), round(time.time() - t0, 1), page_url, page_text))
    db.execute("INSERT INTO changes (created_at,area,title,detail) VALUES (?,?,?,?)",
               (now(), "warning", "LinkedIn warning stopped the run", f"intent={intent}; query={query}; window={freshness}; {reason}"))
    db.commit()
    start_cooldown(reason)


def scrape_window(driver, db, intent, query, freshness, args, deadline, logger):
    """One search (one query, one time window): load, scan, scroll, dump. Returns 'done' | 'no_results' | 'checkpoint'."""
    t0 = time.time()
    pace_before_search()
    driver.get(search_url(query, freshness, args.sort))
    time.sleep(random.uniform(3.5, 4.5))
    reason = detect_warning(driver)
    if reason:
        stop_for_warning(db, driver, intent, query, freshness, reason, t0)
        return "checkpoint"
    no_results, _ = page_text_flags(driver)
    seen_ids, seen_keys, found, scrolls, empty_scrolls, status = set(), set(), 0, 0, 0, ""
    while not no_results:
        added = 0
        expand_see_more(driver)
        cards = scan_linkedin_content_cards(driver, logger)
        raw_by_id = capture_raw(driver)
        for card in cards:
            enrich(card, raw_by_id.get(card.get("card_id")))
            key = post_key_of(card)
            if card.get("card_id") in seen_ids or key in seen_keys:   # the same card, seen again after a scroll
                continue
            seen_ids.add(card.get("card_id"))
            seen_keys.add(key)
            found += 1
            added += 1
            dump_card(db, intent, query, freshness, found, card)
        db.commit()
        empty_scrolls = 0 if added else empty_scrolls + 1
        if scrolls >= args.max_scrolls or empty_scrolls >= 2 or time.time() >= deadline or page_text_flags(driver)[1]:
            break
        scrolls += 1
        scroll_once(driver)
        reason = detect_warning(driver)
        if reason:
            stop_for_warning(db, driver, intent, query, freshness, reason, t0)
            return "checkpoint"
    status = status or ("no_results" if found == 0 else "done")
    try:
        page_url = driver.current_url
        page_text = driver.execute_script("return document.body ? document.body.innerText : ''") or ""
    except Exception:
        page_url = page_text = ""
    db.execute("INSERT INTO queries (intent,query,freshness,posts_found,scrolls,status,started_at,seconds,page_url,page_text) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (intent, query, freshness, found, scrolls, status, now(), round(time.time() - t0, 1), page_url, page_text))
    db.commit()
    print(f"   {freshness:<9} → {found} posts, {scrolls} scrolls ({status})")
    return status


def run_intent(driver, db, intent, deadline, args, logger):
    """Keep asking for queries and scraping them until this intent's time is up. Returns 'time_up' | 'no_more_queries' | 'checkpoint'."""
    used = []                                                  # the simple list: queries used for THIS intent only
    empty_rounds = 0
    while time.time() < deadline:
        used_lower = {u.lower() for u in used}
        new = []
        for q in ask_queries(db, intent, used):
            if q.lower() not in used_lower:
                used_lower.add(q.lower())
                new.append(q)
        if not new:
            empty_rounds += 1
            if empty_rounds >= 2:
                return "no_more_queries"
            continue
        empty_rounds = 0
        print(f"   LLM wrote {len(new)} new queries ({len(used)} used so far)")
        for q in new:
            if time.time() >= deadline:
                return "time_up"
            used.append(q)
            print(f"\n🔍 '{q}'   ({int(deadline - time.time())}s left for this intent)")
            for freshness in WINDOWS:
                if time.time() >= deadline:
                    break
                if scrape_window(driver, db, intent["title"], q, freshness, args, deadline, logger) == "checkpoint":
                    return "checkpoint"
    return "time_up"


# ─────────────────────────────────────────────────────────────────────────────
def print_stats(db):
    g = lambda sql: db.execute(sql).fetchone()[0]
    print(f"\n{Style.BOLD}DATASET{Style.RESET}  rows={g('SELECT COUNT(*) FROM posts')}  "
          f"distinct posts={g('SELECT COUNT(DISTINCT post_key) FROM posts')}  queries run={g('SELECT COUNT(DISTINCT intent||query) FROM queries')}  "
          f"llm cost=${g('SELECT COALESCE(SUM(usd),0) FROM llm_calls'):.4f}")
    for r in db.execute("""SELECT intent, COUNT(*) rows_, COUNT(DISTINCT post_key) posts, COUNT(DISTINCT query) queries
                           FROM posts GROUP BY intent ORDER BY MIN(id)"""):
        print(f"  {r['intent'][:52]:<52} queries={r['queries']:<4} rows={r['rows_']:<6} distinct posts={r['posts']}")


def main():
    ap = argparse.ArgumentParser(description="Bulk LinkedIn post collector (data only, time-limited).")
    ap.add_argument("--minutes", type=float, default=60, help="total time limit, shared equally by the intents (default 60)")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--intents-file", default=DEFAULT_INTENTS)
    ap.add_argument("--only", default="", help="comma list of intent numbers from the file, e.g. 1,4")
    ap.add_argument("--intent", default="", help="collect for this free-text intent instead of the file")
    ap.add_argument("--max-scrolls", type=int, default=5, help="scrolls per search page (default 5)")
    ap.add_argument("--ignore-cooldown", action="store_true", help="run even though a LinkedIn warning started a cool-down")
    ap.add_argument("--sort", default=os.environ.get("SEARCH_SORT", "relevance"), choices=["relevance", "date"])
    ap.add_argument("--dry-run", action="store_true", help="one round of queries per intent, printed only; no browser")
    ap.add_argument("--stats", action="store_true", help="print what the database holds and exit")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger = logging.getLogger("collector")
    db = open_db(args.db)
    if args.stats:
        print_stats(db)
        return

    if args.intent:
        intents = [{"title": "Custom intent", "intent": args.intent}]
    else:
        intents = parse_intents(args.intents_file)
        if args.only:
            keep = {int(x) for x in args.only.split(",") if x.strip().isdigit()}
            intents = [it for i, it in enumerate(intents, 1) if i in keep]
    if not intents:
        sys.exit("No intents found.")
    if not llm.api_key_present():
        sys.exit(f"Missing {llm.key_hint()}: the query writer needs it.")
    print(f"{Style.BOLD}Collector{Style.RESET}  db={args.db}  query model={llm.model_for('collector')}  "
          f"intents={len(intents)}  time limit={args.minutes:g} min")

    if args.dry_run:
        for it in intents:
            print(f"\n[{it['title']}]")
            for q in ask_queries(db, it, []):
                print("   ", q)
        return

    left_h = cooldown_left()
    if left_h and not args.ignore_cooldown:
        sys.exit(f"LinkedIn showed a warning recently. Cool-down: {left_h:.1f} h left (details in {COOLDOWN_FILE}). "
                 "Use --ignore-cooldown to run anyway.")

    driver = setup_stealth_driver(os.path.join(BASE_DIR, "linkedin_chrome_profile"))
    end = time.time() + args.minutes * 60
    try:
        verify_or_prompt_login(driver, logger)
        for i, it in enumerate(intents):
            left = end - time.time()
            if left <= 5:
                print("Time limit reached.")
                break
            share = left / (len(intents) - i)                  # unused time of an earlier intent flows to the later ones
            print(f"\n{'=' * 78}\n{Style.BOLD}INTENT {i + 1}/{len(intents)}: {it['title']}{Style.RESET}  ({share / 60:.1f} min)\n{'=' * 78}")
            result = run_intent(driver, db, it, time.time() + share, args, logger)
            print(f"\n→ {it['title']}: {result}")
            if result == "checkpoint":
                break
    except KeyboardInterrupt:
        print("\nInterrupted. Everything scraped so far is saved.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    print_stats(db)


if __name__ == "__main__":
    main()
