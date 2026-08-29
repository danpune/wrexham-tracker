#!/usr/bin/env python3
"""Build data.json for the Wrexham tracker from free public feeds (no API keys)."""

import json, os, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

UA = "wrexham-tracker/1.0 (github.com/danpune/wrexham-tracker)"

TEAM_ID = "352"          # Wrexham, ESPN
LEAGUE = "eng.2"         # EFL Championship — table and projection are league-only
# Cups run on their own calendars: the Carabao Cup starts in August, and
# Championship clubs enter the FA Cup at the third round in January.
COMPETITIONS = [(LEAGUE, "League"), ("eng.league_cup", "EFL Cup"), ("eng.fa", "FA Cup")]
LOGO = "https://a.espncdn.com/i/teamlogos/soccer/500/%s.png"
SEASON_MONTHS = [(2026, m) for m in (8, 9, 10, 11, 12)] + [(2027, m) for m in range(1, 7)]
PLAYOFF_CUTOFF = 72      # historical 6th-place points, Championship. Used for the projection.
MIN_GAMES_TO_PROJECT = 8
TOTAL_GAMES = 46

NEWS_FEED = ("https://news.google.com/rss/search?"
             "q=%22Wrexham+AFC%22+OR+%22Wrexham%22+football&hl=en-GB&gl=GB&ceid=GB:en")

# (show, feed, max episodes to take)
PODCASTS = [
    ("#AskWXM", "https://feeds.soundcloud.com/users/soundcloud:users:35366634/sounds.rss", 4),
    ("Me, the Wife and Wrexham AFC", "https://rss.buzzsprout.com/2028049.rss", 4),
    ("Rousey's Wrexham Round Up", "https://feeds.megaphone.fm/COMG1954100977", 3),
    ("BBC Sounds: Wrexham AFC", "https://feeds.bbci.co.uk/sport/football/teams/wrexham/rss.xml", 1),
]


def get(url, as_json=False, tries=3):
    """ESPN rate-limits bursts with a 403; a short backoff clears it."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            raw = urllib.request.urlopen(req, timeout=30).read()
            return json.loads(raw) if as_json else raw
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def iso(dt_str):
    """ESPN gives 2026-08-28T19:00Z; normalise to a full ISO instant."""
    return dt_str.replace("Z", "+00:00")


def rfc822(s):
    """RSS pubDate -> ISO UTC. Returns None if unparseable rather than guessing.

    strptime's %Z matches "GMT" but yields a *naive* datetime, which astimezone()
    then reads as machine-local time — silently shifting every feed timestamp by
    the runner's UTC offset. parsedate_to_datetime handles the real grammar.
    """
    try:
        dt = parsedate_to_datetime(s.strip())
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:                     # no zone given: RFC 822 says assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# --- fixtures & results -------------------------------------------------------
# ESPN's team/schedule endpoint only returns matches already played, so walk the
# league scoreboard month by month and filter. 11 requests, cheap, complete.
def fetch_matches():
    out = []
    for league, comp_name in COMPETITIONS:
      for year, month in SEASON_MONTHS:
        last = 31 if month in (1, 3, 5, 7, 8, 10, 12) else 30 if month != 2 else 28
        url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
               f"?dates={year}{month:02d}01-{year}{month:02d}{last}")
        try:
            data = get(url, as_json=True)
        except Exception:
            continue
        time.sleep(0.3)          # 33 requests a run: don't burst ESPN into a 403
        for ev in data.get("events", []):
            comp = ev["competitions"][0]
            teams = comp["competitors"]
            if not any(t["team"]["id"] == TEAM_ID for t in teams):
                continue
            us = next(t for t in teams if t["team"]["id"] == TEAM_ID)
            them = next(t for t in teams if t["team"]["id"] != TEAM_ID)
            status = comp.get("status", {}).get("type", {})
            done = status.get("completed", False)
            us_score = int(us.get("score") or 0) if done else None
            them_score = int(them.get("score") or 0) if done else None
            result = None
            if done:
                result = "W" if us_score > them_score else "L" if us_score < them_score else "D"
            out.append({
                "id": ev["id"],
                "league": league,
                "comp": comp_name,
                "date": iso(ev["date"]),
                "opponent": them["team"]["displayName"],
                "logo": LOGO % them["team"]["id"],
                "opponentAbbr": them["team"].get("abbreviation", ""),
                "home": us.get("homeAway") == "home",
                "venue": comp.get("venue", {}).get("fullName", ""),
                "completed": done,
                "us": us_score,
                "them": them_score,
                "result": result,
                "state": status.get("detail", ""),
            })
    out.sort(key=lambda m: m["date"])
    return out


# --- league table -------------------------------------------------------------
def fetch_table():
    data = get(f"https://site.api.espn.com/apis/v2/sports/soccer/{LEAGUE}/standings", as_json=True)
    entries = (data["children"][0]["standings"]["entries"] if "children" in data
               else data["standings"]["entries"])
    rows = []
    for e in entries:
        s = {x["name"]: x for x in e["stats"]}
        val = lambda k: int(float(s[k]["value"])) if k in s else 0
        rows.append({
            "rank": val("rank"),
            "team": e["team"]["displayName"],
            "abbr": e["team"].get("abbreviation", ""),
            "played": val("gamesPlayed"),
            "won": val("wins"),
            "drawn": val("ties"),
            "lost": val("losses"),
            "gf": val("pointsFor"),
            "ga": val("pointsAgainst"),
            "gd": val("pointDifferential"),
            "points": val("points"),
            "logo": LOGO % e["team"]["id"],
            "isWrexham": e["team"]["id"] == TEAM_ID,
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


# --- news ---------------------------------------------------------------------
def fetch_news(limit=40):
    root = ET.fromstring(get(NEWS_FEED))
    items = []
    for it in root.iter("item"):
        title = unescape(it.findtext("title") or "")
        source = ""
        # Google News appends " - Publisher" to every headline.
        if " - " in title:
            title, source = title.rsplit(" - ", 1)
        items.append({
            "title": title.strip(),
            "url": safe_url(it.findtext("link")),
            "source": source.strip() or (it.findtext("source") or "").strip(),
            "published": rfc822(it.findtext("pubDate") or ""),
        })
    items = [i for i in items if i["published"] and i["url"]]
    items.sort(key=lambda i: i["published"], reverse=True)
    return items[:limit]


# --- podcasts -----------------------------------------------------------------
def safe_url(u):
    """Only http(s) survives. Feed items are third-party: a javascript: or data:
    URL here would land in an href or a media src, and HTML-escaping does not
    neutralise a scheme. Rejecting at the source covers every consumer."""
    u = (u or "").strip()
    if u[:7].lower() == "http://":
        # The site is served over HTTPS, so plain-http media is blocked as mixed
        # content regardless of CSP. Several podcast CDNs still publish http
        # enclosures and serve the same file fine over TLS.
        u = "https://" + u[7:]
    return u if u[:8].lower() == "https://" else ""


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(s or ""))).strip()


def fetch_podcasts(limit=20):
    episodes = []
    for show, url, take in PODCASTS:
        try:
            root = ET.fromstring(get(url))
        except Exception:
            continue
        for it in list(root.iter("item"))[:take]:
            enc = it.find("enclosure")
            published = rfc822(it.findtext("pubDate") or "")
            if not published:
                continue
            title = strip_html(it.findtext("title"))
            summary = strip_html(it.findtext("description"))
            if title.lower() in show.lower():   # BBC titles every episode "Wrexham AFC"
                title = summary or title
            episodes.append({
                "show": show,
                "title": title[:160],
                "summary": summary[:220],
                "audio": safe_url(enc.get("url")) if enc is not None else None,
                "url": safe_url(it.findtext("link")),
                "published": published,
            })
    episodes.sort(key=lambda e: e["published"], reverse=True)
    return episodes[:limit]


# --- prediction market odds -------------------------------------------------
# Polymarket lists a 3-way market per Championship fixture, slugged
# elc-<home>-<away>-YYYY-MM-DD. Kalshi lists the same fixtures
# (KXEFLCHAMPIONSHIPGAME) but every one is quoteless -- no bid, ask, last price
# or open interest -- so there is nothing to show from it yet.
def fetch_odds(matches, lookahead=5):
    """Polymarket lists a 3-way market per fixture, slugged elc-<h>-<a>-YYYY-MM-DD.
    A generic "Wrexham" search only ranks up resolved past events, so query per
    fixture and match on the date in the slug.

    Kalshi lists the same fixtures (KXEFLCHAMPIONSHIPGAME) but every contract is
    quoteless -- no bid, ask, last price or open interest -- so there is nothing
    to read from it. Add it here if that changes.
    """
    odds = {}
    upcoming = [m for m in matches if not m["completed"]][:lookahead]
    for m in upcoming:
        day = m["date"][:10]
        term = urllib.parse.quote(m["opponent"].split()[0] + " Wrexham")
        try:
            data = get(f"https://gamma-api.polymarket.com/public-search"
                       f"?q={term}&limit_per_type=10", as_json=True)
        except Exception:
            continue
        for ev in data.get("events", []):
            if not (ev.get("slug") or "").endswith(day) or ev.get("closed"):
                continue
            book = {}
            for mk in ev.get("markets", []):
                try:
                    price = float(json.loads(mk.get("outcomePrices") or "[]")[0])
                except (ValueError, IndexError, TypeError):
                    continue
                if float(mk.get("liquidity") or 0) <= 0:
                    continue      # listed but untraded: a 0/1 placeholder, not a price
                name = (mk.get("groupItemTitle") or mk.get("question") or "").lower()
                key = "draw" if "draw" in name else "wrexham" if "wrexham" in name else "opponent"
                book[key] = price
            if len(book) == 3:
                odds[day] = {"book": {k: round(v, 3) for k, v in book.items()},
                             "url": "https://polymarket.com/event/" + ev["slug"]}
            break
        time.sleep(1)             # be polite: this runs every 30 minutes
    return odds


# --- match centre ------------------------------------------------------------
# ESPN's summary endpoint carries team stats, the goal/card timeline and both
# XIs. Pulled for the latest finished match only -- older games would bloat
# data.json for something nobody scrolls back to.
KEEP_STATS = ["possessionPct", "totalShots", "shotsOnTarget", "wonCorners",
              "foulsCommitted", "yellowCards", "redCards", "saves"]


def fetch_summary(matches):
    done = [m for m in matches if m["completed"]]
    if not done:
        return None
    m = done[-1]
    try:
        d = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{m['league']}"
                f"/summary?event={m['id']}", as_json=True)
    except Exception:
        return None

    stats = {}
    for t in d.get("boxscore", {}).get("teams", []):
        side = "us" if t["team"]["id"] == TEAM_ID else "them"
        stats[side] = {x["name"]: x.get("displayValue")
                       for x in t.get("statistics", []) if x["name"] in KEEP_STATS}

    goals = []
    for k in d.get("keyEvents", []):
        kind = (k.get("type") or {}).get("text", "")
        if not k.get("scoringPlay") and "Card" not in kind:
            continue
        who = (k.get("participants") or [{}])[0].get("athlete", {}).get("displayName", "")
        goals.append({
            "clock": (k.get("clock") or {}).get("displayValue", ""),
            "kind": "goal" if k.get("scoringPlay") else
                    "red" if "Red" in kind else "yellow",
            "who": who,
            "us": (k.get("team") or {}).get("id") == TEAM_ID,
        })

    lineups = {}
    for r in d.get("rosters", []):
        side = "us" if r.get("team", {}).get("id") == TEAM_ID else "them"
        lineups[side] = [
            {"name": p.get("athlete", {}).get("displayName", ""),
             "pos": (p.get("position") or {}).get("abbreviation", "")}
            for p in r.get("roster", []) if p.get("starter")]

    hl = {}
    try:                                  # optional, curated, merge-only
        with open("highlights.json") as f:
            hl = json.load(f).get("highlights", {})
    except (OSError, ValueError):
        pass

    return {"yt": (hl.get(m["id"]) or {}).get("yt"),
            "search": "https://www.youtube.com/results?search_query=" + urllib.parse.quote(
                f"Wrexham {m['opponent']} highlights"),
            "match": {"opponent": m["opponent"], "logo": m["logo"], "home": m["home"],
                      "us": m["us"], "them": m["them"], "date": m["date"],
                      "comp": m["comp"], "result": m["result"]},
            "stats": stats, "events": goals, "lineups": lineups}


# WMO weather codes -> a short label. Open-Meteo is free and needs no key.
WMO = {0: ("Clear", "\u2600\ufe0f"), 1: ("Mostly clear", "\U0001f324\ufe0f"),
       2: ("Partly cloudy", "\u26c5"), 3: ("Overcast", "\u2601\ufe0f"),
       45: ("Fog", "\U0001f32b\ufe0f"), 48: ("Fog", "\U0001f32b\ufe0f"),
       51: ("Drizzle", "\U0001f327\ufe0f"), 53: ("Drizzle", "\U0001f327\ufe0f"),
       55: ("Drizzle", "\U0001f327\ufe0f"), 61: ("Rain", "\U0001f327\ufe0f"),
       63: ("Rain", "\U0001f327\ufe0f"), 65: ("Heavy rain", "\U0001f327\ufe0f"),
       71: ("Snow", "\U0001f328\ufe0f"), 73: ("Snow", "\U0001f328\ufe0f"),
       75: ("Heavy snow", "\U0001f328\ufe0f"), 80: ("Showers", "\U0001f326\ufe0f"),
       81: ("Showers", "\U0001f326\ufe0f"), 82: ("Heavy showers", "\U0001f327\ufe0f"),
       95: ("Storm", "\u26c8\ufe0f"), 96: ("Storm", "\u26c8\ufe0f"), 99: ("Storm", "\u26c8\ufe0f")}


def fetch_weather(city, when):
    """Kickoff forecast for the venue city. Baked in here rather than fetched in
    the browser: one call every 30 minutes instead of one per visitor, and the
    page needs no extra CSP origin. Open-Meteo only forecasts ~16 days out."""
    if not city:
        return None
    try:
        g = get("https://geocoding-api.open-meteo.com/v1/search?count=1&language=en"
                "&name=" + urllib.parse.quote(city), as_json=True)
        hit = (g.get("results") or [None])[0]
        if not hit:
            return None
        w = get(f"https://api.open-meteo.com/v1/forecast?latitude={hit['latitude']}"
                f"&longitude={hit['longitude']}&hourly=temperature_2m,weather_code"
                f"&start_date={when[:10]}&end_date={when[:10]}&timezone=GMT", as_json=True)
        hourly = w.get("hourly") or {}
        times = hourly.get("time") or []
        i = next((n for n, t in enumerate(times) if t[:13] >= when[:13]), None)
        if i is None:
            return None
        label, icon = WMO.get(hourly["weather_code"][i], ("", "\U0001f321\ufe0f"))
        return {"temp": round(hourly["temperature_2m"][i]), "label": label, "icon": icon}
    except Exception:
        return None


def fetch_next_info(matches):
    """Broadcast + head-to-head for the next fixture. Where-to-watch matters a
    lot here: much of Wrexham's audience found the club through the series and
    is watching from outside the UK."""
    nxt = next((m for m in matches if not m["completed"]), None)
    if not nxt:
        return None
    try:
        d = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{nxt['league']}"
                f"/summary?event={nxt['id']}", as_json=True)
    except Exception:
        return None
    tv = []
    for b in d.get("broadcasts", []):
        name = (b.get("media") or {}).get("shortName") or ""
        if name and name not in tv:
            tv.append(name)
    h2h = next((x.get("summary") for x in (d.get("seasonseries") or [])
                if x.get("type") == "head-to-head"), None)
    city = ((d.get("gameInfo") or {}).get("venue") or {}).get("address", {}).get("city")
    return {"tv": tv[:4], "h2h": h2h, "venue": nxt.get("venue"), "city": city,
            "weather": fetch_weather(city, nxt["date"])}


def fetch_squad():
    try:
        d = get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{LEAGUE}"
                f"/teams/{TEAM_ID}/roster", as_json=True)
    except Exception:
        return []
    out = []
    for a in d.get("athletes", []):
        it = a if "displayName" in a else (a.get("items") or [{}])[0]
        if not it.get("displayName"):
            continue
        out.append({"no": it.get("jersey") or "",
                    "name": it["displayName"],
                    "pos": (it.get("position") or {}).get("abbreviation", ""),
                    "age": it.get("age")})
    order = {"G": 0, "D": 1, "M": 2, "F": 3}
    out.sort(key=lambda p: (order.get(p["pos"], 4), p["name"]))
    return out


# --- promotion projection -----------------------------------------------------
def project(table, matches):
    us = next((r for r in table if r["isWrexham"]), None)
    if not us:
        return None
    played, points = us["played"], us["points"]
    ppg = points / played if played else 0
    remaining = TOTAL_GAMES - played
    sixth = next((r for r in table if r["rank"] == 6), None)
    return {
        # A points-per-game projection off a handful of games is noise, so the UI
        # hides the number until there is enough season to extrapolate from.
        "tooEarly": played < MIN_GAMES_TO_PROJECT,
        "played": played,
        "points": points,
        "rank": us["rank"],
        "ppg": round(ppg, 2),
        "remaining": remaining,
        "projected": round(points + ppg * remaining),
        "cutoff": PLAYOFF_CUTOFF,
        "neededPpg": round(max(0, PLAYOFF_CUTOFF - points) / remaining, 2) if remaining else 0,
        "gapToSixth": (sixth["points"] - points) if sixth else None,
        "form": [m["result"] for m in matches
                 if m["completed"] and m["comp"] == "League"][-5:],
    }


DIR = os.path.dirname(os.path.abspath(__file__))


def vevent(m):
    """One VEVENT. Commas are separators in ICS, so they're stripped, not escaped."""
    dt = datetime.fromisoformat(m["date"])
    start = dt.strftime("%Y%m%dT%H%M00Z")
    end = (dt + timedelta(hours=2)).strftime("%Y%m%dT%H%M00Z")
    vs = f"Wrexham v {m['opponent']}" if m["home"] else f"{m['opponent']} v Wrexham"
    tag = "" if m["comp"] == "League" else f" ({m['comp']})"
    return ["BEGIN:VEVENT", f"UID:{m['id']}@wrexham-tracker",
            f"DTSTART:{start}", f"DTEND:{end}",
            f"SUMMARY:{vs} \u26bd{tag}".replace(",", ""),
            "LOCATION:" + (m.get("venue") or "").replace(",", " "),
            f"DESCRIPTION:{m['comp']} 2026/27".replace(",", ""), "END:VEVENT"]


def write_ics(matches):
    """Real .ics files -- iOS Safari cannot download a data: URI -- plus one
    subscribable all-fixtures feed, so a fan subscribes once instead of adding
    46 matches by hand."""
    icsdir = os.path.join(DIR, "ics")
    os.makedirs(icsdir, exist_ok=True)
    keep, feed = set(), []
    for m in matches:
        if m["completed"]:
            continue
        try:
            ev = vevent(m)
        except Exception:
            continue
        feed += ev
        fn = f"{m['id']}.ics"
        keep.add(fn)
        with open(os.path.join(icsdir, fn), "w", newline="") as f:
            f.write("\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0",
                                  "PRODID:wrexham-tracker"] + ev + ["END:VCALENDAR"]))
    keep.add("wrexham.ics")
    with open(os.path.join(icsdir, "wrexham.ics"), "w", newline="") as f:
        f.write("\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:wrexham-tracker",
                              "X-WR-CALNAME:Wrexham AFC fixtures", "X-PUBLISHED-TTL:PT12H"]
                             + feed + ["END:VCALENDAR"]))
    for f in os.listdir(icsdir):          # prune fixtures already played
        if f.endswith(".ics") and f not in keep:
            os.remove(os.path.join(icsdir, f))


def main():
    matches = fetch_matches()
    table = fetch_table()
    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": "2026/27",
        "competition": "EFL Championship",
        "matches": matches,
        "table": table,
        "news": fetch_news(),
        "podcasts": fetch_podcasts(),
        "projection": project(table, matches),
        "odds": fetch_odds(matches),
        "lastMatch": fetch_summary(matches),
        "nextInfo": fetch_next_info(matches),
        "squad": fetch_squad(),
    }
    write_ics(matches)
    with open(os.path.join(DIR, "data.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"matches={len(matches)} (league={sum(1 for m in matches if m['comp']=='League')}) table={len(table)} news={len(data['news'])} "
          f"pods={len(data['podcasts'])} odds={len(data['odds'])} squad={len(data['squad'])}")


if __name__ == "__main__":
    main()
