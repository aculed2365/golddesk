"""Fast watcher: Trump's Truth Social posts + breaking headlines, checked every ~90 seconds.

Reading the feeds is free. Claude only looks at items that are NEW, in one small batch,
and you only get a text when something can move gold.
"""
import email.utils
import hashlib
import json
import logging
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import config
import db
import tg
from llm import ask

log = logging.getLogger("desk")

WATCH_EVERY_SEC = max(30, int(float(os.getenv("WATCH_EVERY_SEC", "90"))))
WATCH_MODEL = os.getenv("WATCH_MODEL", "claude-haiku-5-5")

FEEDS = {
    "TRUMP": os.getenv("TRUMP_FEED", "https://www.trumpstruth.org/feed?limit=20"),
    "NEWS": os.getenv(
        "NEWS_FEED",
        "https://news.google.com/rss/search?q=(gold+OR+Fed+OR+Powell+OR+tariff+OR+tariffs+OR+sanctions"
        "+OR+missile+OR+attack+OR+ceasefire+OR+%22rate+cut%22)+when:1h&hl=en-US&gl=US&ceid=US:en",
    ),
}

SYSTEM = """You judge breaking items for a gold (XAUUSD) day trader. For each item decide if it can move gold in the next few hours.
High = likely to move gold sharply now (new tariffs or trade threats, attacks/wars/ceasefires, Fed/Powell surprises, Trump attacking the Fed or talking rates/dollar/gold, sanctions on big economies, US data shocks).
Medium = worth knowing, smaller effect. Low = not relevant (sports, celebrities, domestic politics with no market angle, old news).
Gold usually goes UP on fear, war, tariffs, a weaker dollar, rate cuts; DOWN on calm, a stronger dollar, higher yields/rate hikes.
Never invent facts beyond the item text.
Reply JSON only: {"items": [{"id": "", "impact": "high|medium|low", "gold": "up|down|unclear", "line": "max 15 words, plain English"}]}"""


def _fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 GoldDesk/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        desc = (it.findtext("description") or "").strip()
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link or title).strip()
        pub = it.findtext("pubDate") or ""
        items.append({"guid": guid, "title": title, "text": desc[:600], "link": link, "pub": pub})
    return items


def _age_minutes(pub: str):
    try:
        dt = email.utils.parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except (TypeError, ValueError):
        return None


def _key(source: str, guid: str) -> str:
    return "w:" + source + ":" + hashlib.sha1(guid.encode()).hexdigest()[:16]


def check_once(market_open: bool, first_run: bool = False) -> int:
    fresh = []
    for source, url in FEEDS.items():
        if not url:
            continue
        try:
            items = _fetch(url)
        except Exception as e:  # noqa: BLE001
            log.warning("feed %s failed: %s", source, e)
            continue
        for it in items:
            if db.seen_before(_key(source, it["guid"])):
                continue
            age = _age_minutes(it["pub"])
            if first_run or (age is not None and age > 90):
                continue  # don't flood you with old stuff
            fresh.append(dict(it, source=source, id=str(len(fresh))))

    if not fresh or not market_open:
        return 0

    batch = [{"id": f["id"], "source": f["source"], "title": f["title"], "text": f["text"]}
             for f in fresh[:25]]
    verdict = ask(WATCH_MODEL, SYSTEM, json.dumps(batch), max_tokens=1200)
    sent = 0
    for v in verdict.get("items", []) if isinstance(verdict, dict) else []:
        f = next((x for x in fresh if x["id"] == str(v.get("id"))), None)
        if not f:
            continue
        impact = v.get("impact")
        if impact == "high" or (impact == "medium" and f["source"] == "TRUMP"):
            arrow = {"up": "⬆️ gold up", "down": "⬇️ gold down"}.get(v.get("gold"), "↕️ unclear")
            head = "🇺🇸 TRUMP POST" if f["source"] == "TRUMP" else "🚨 BREAKING"
            t = datetime.now(config.DUBAI).strftime("%H:%M")
            tg.send(f"{head} ({t} Dubai) — {impact.upper()} — {arrow}\n{v.get('line', '')}\n"
                    f"“{f['title'][:200]}”\n{f['link']}")
            sent += 1
    return sent


def watch_loop(market_open_fn, paused_fn) -> None:
    first = True
    while True:
        try:
            check_once(market_open_fn() and not paused_fn(), first_run=first)
            first = False
        except Exception:  # noqa: BLE001
            log.exception("watcher error")
        time.sleep(WATCH_EVERY_SEC)
