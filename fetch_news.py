"""
Fetches headlines ONLY from an allowlist of official sources.
PIB's feed has no dates, so for every new item we open the official
release page and read its "Posted On" date. Only items confirmed as
posted TODAY (India time) are kept. Nothing is written by AI.
"""
import json
import os
import re
import urllib.request
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser

IST = ZoneInfo("Asia/Kolkata")
MAX_NEW_PAGES_PER_RUN = 60

SOURCES = [
    {
        "name": "PIB (Govt. of India) - English",
        "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        "domains": ["pib.gov.in"],
    },
    {
        "name": "PIB (Govt. of India) - Hindi",
        "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=2&Regid=3",
        "domains": ["pib.gov.in"],
    },
]

# Matches e.g. "02 NOV 2026 10:45AM" or "2 Nov 2026 10:45 AM"
DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])")


def domain_ok(link, allowed):
    host = (urlparse(link).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def get_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DailyOfficialNews/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def posted_time(html):
    """Return the first 'DD MON YYYY HH:MMAM' found on the page, as an IST datetime."""
    m = DATE_RE.search(html)
    if not m:
        return None
    d, mon, y, hh, mm, ap = m.groups()
    try:
        dt = datetime.strptime(f"{int(d):02d} {mon.title()} {y} {int(hh):02d}:{mm} {ap.upper()}",
                               "%d %b %Y %I:%M %p")
    except ValueError:
        return None
    return dt.replace(tzinfo=IST)


def load_old(path="news.json"):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def collect(now_ist=None, fetch=get_page, old=None):
    now_ist = now_ist or datetime.now(IST)
    today = now_ist.date().isoformat()
    old = old if old is not None else load_old()
    # Remember pages already checked today (link -> item dict, or None if not today)
    checked = old.get("checked", {}) if old.get("date") == today else {}

    errors, entries = [], []
    for src in SOURCES:
        feed = feedparser.parse(src["url"], agent="DailyOfficialNews/1.0")
        if not feed.entries:
            errors.append(f"No entries from {src['name']}")
            continue
        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if title and link and domain_ok(link, src["domains"]):
                entries.append((src["name"], title, link))

    fetched, no_date = 0, 0
    for name, title, link in entries:
        if link in checked:
            continue
        if fetched >= MAX_NEW_PAGES_PER_RUN:
            break
        fetched += 1
        try:
            when = posted_time(fetch(link))
        except Exception as ex:
            errors.append(f"Could not open {link}: {ex}")
            continue                          # try again next run
        if when is None:
            no_date += 1
            checked[link] = None              # date not found = never shown
        elif when.date().isoformat() == today:
            checked[link] = {"title": title, "link": link, "source": name,
                             "time": when.strftime("%H:%M"), "ts": when.isoformat()}
        else:
            checked[link] = None              # older than today = never shown

    if no_date:
        errors.append(f"{no_date} pages had no readable date and were skipped")

    items = sorted([v for v in checked.values() if v], key=lambda i: i["ts"], reverse=True)
    return {"date": today, "updated": now_ist.strftime("%H:%M"),
            "items": items, "errors": errors, "checked": checked}


if __name__ == "__main__":
    data = collect()
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"{len(data['items'])} items for {data['date']}; errors: {data['errors']}")
