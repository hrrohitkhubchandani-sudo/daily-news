"""
Worldwide official-news collector.
Reads sources.json (an allowlist of official sources), keeps only items
published TODAY (India time), and writes news.json. Nothing is written
by AI: each item is the source's own headline plus a link to the original.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser

IST = ZoneInfo("Asia/Kolkata")
MAX_PER_SOURCE = 30          # newest items kept per source per day
MAX_NEW_PAGES_PER_RUN = 60   # polite limit for sources that need page-opening

DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def domain_ok(link, allowed):
    host = (urlparse(link).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def get_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DailyOfficialNews/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def posted_time(html):
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


def make_item(src, title, link, when):
    return {"title": title, "link": link, "source": src["name"], "country": src["country"],
            "category": src["category"], "time": when.strftime("%H:%M"), "ts": when.isoformat()}


def collect(now_ist=None, fetch=get_page, old=None, sources=None):
    now_ist = now_ist or datetime.now(IST)
    today = now_ist.date().isoformat()
    old = old if old is not None else load_json("news.json")
    sources = sources if sources is not None else load_json("sources.json").get("sources", [])
    checked = old.get("checked", {}) if old.get("date") == today else {}

    items, health, pages_fetched = [], [], 0
    for src in sources:
        if src.get("enabled", True) is False:
            continue
        h = {"name": src["name"], "country": src["country"], "ok": False, "entries": 0, "today": 0, "note": ""}
        try:
            feed = feedparser.parse(src["url"], agent="DailyOfficialNews/1.0")
        except Exception as ex:
            h["note"] = f"error: {ex}"
            health.append(h)
            continue
        if not feed.entries:
            h["note"] = "no entries returned (address may be wrong or blocked)"
            health.append(h)
            continue
        h["ok"], h["entries"] = True, len(feed.entries)
        found, undated = [], 0

        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link or not domain_ok(link, src["domains"]):
                continue
            if src.get("date_mode") == "page":
                if link not in checked:
                    if pages_fetched >= MAX_NEW_PAGES_PER_RUN:
                        continue
                    pages_fetched += 1
                    try:
                        when = posted_time(fetch(link))
                    except Exception:
                        continue                       # try again next run
                    if when and when.date().isoformat() == today:
                        checked[link] = make_item(src, title, link, when)
                    else:
                        checked[link] = None
                        if when is None:
                            undated += 1
                if checked.get(link):
                    found.append(checked[link])
            else:
                stamp = e.get("published_parsed") or e.get("updated_parsed")
                if not stamp:
                    undated += 1
                    continue
                when = datetime(*stamp[:6], tzinfo=timezone.utc).astimezone(IST)
                if when.date().isoformat() == today:
                    found.append(make_item(src, title, link, when))

        found.sort(key=lambda i: i["ts"], reverse=True)
        found = found[:MAX_PER_SOURCE]
        h["today"] = len(found)
        if undated:
            h["note"] = f"{undated} items had no readable date and were skipped"
        items.extend(found)
        health.append(h)

    seen, unique = set(), []
    for i in sorted(items, key=lambda i: i["ts"], reverse=True):
        if i["link"] not in seen:
            seen.add(i["link"])
            unique.append(i)
    return {"date": today, "updated": now_ist.strftime("%H:%M"), "items": unique,
            "health": health, "checked": checked}


if __name__ == "__main__":
    data = collect()
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    ok = sum(1 for h in data["health"] if h["ok"])
    print(f"{len(data['items'])} items for {data['date']}; {ok}/{len(data['health'])} sources reachable")
    for h in data["health"]:
        print(("OK  " if h["ok"] else "FAIL"), h["name"], h["today"], h["note"])
