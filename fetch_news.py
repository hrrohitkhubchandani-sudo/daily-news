"""
Fetches headlines ONLY from an allowlist of official sources and keeps
only items published TODAY (India time). Writes news.json.
Nothing is written by AI: every item is the source's own headline + link.
"""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser

IST = ZoneInfo("Asia/Kolkata")

# Add more official sources here. "domains" = the only websites a link may point to.
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


def domain_ok(link, allowed):
    host = (urlparse(link).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def collect(now_ist=None):
    now_ist = now_ist or datetime.now(IST)
    today = now_ist.date()
    items, errors, seen = [], [], set()

    for src in SOURCES:
        feed = feedparser.parse(src["url"], agent="DailyOfficialNews/1.0")
        if not feed.entries:
            errors.append(f"No entries from {src['name']}")
            continue
        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            stamp = e.get("published_parsed") or e.get("updated_parsed")
            if not title or not link or not stamp:
                continue                      # no title/link/time = never shown
            if not domain_ok(link, src["domains"]):
                continue                      # link not on allowlisted domain
            when = datetime(*stamp[:6], tzinfo=timezone.utc).astimezone(IST)
            if when.date() != today:
                continue                      # not today = never shown
            if link in seen:
                continue
            seen.add(link)
            items.append({
                "title": title,
                "link": link,
                "source": src["name"],
                "time": when.strftime("%H:%M"),
                "ts": when.isoformat(),
            })

    items.sort(key=lambda i: i["ts"], reverse=True)
    return {
        "date": today.isoformat(),
        "updated": now_ist.strftime("%H:%M"),
        "items": items,
        "errors": errors,
    }


if __name__ == "__main__":
    data = collect()
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"{len(data['items'])} items for {data['date']}; errors: {data['errors']}")
