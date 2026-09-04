#!/usr/bin/env python3
"""Fill highlights.json: completed matches -> official YouTube highlight video ids.

Scrapes the official channels' /videos pages (newest first), matches titles against
completed matches in data.json by opponent name + the word "highlights", then verifies
EVERY candidate via YouTube's oEmbed endpoint: author_url must be an official channel.
Checking author_url and not author_name is deliberate -- a spam channel can rename
itself to spoof the name (learned on the sibling World Cup project).

Merge-only and fail-safe: never removes entries, exits 0 on any fetch failure.
Runs in CI after fetch_data.py. Standard library only, no API key.
"""
import json, os, re, sys, urllib.parse, urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
# Official rights-holding channels. The club's handle is @WxmAFCofficial -- NOT
# @WrexhamAFC, which does not exist.
CHANNELS = ["@WxmAFCofficial", "@theEFL", "@cbssportsgolazo"]

# Each Championship club's own channel. @theEFL only uploads a subset of
# fixtures -- the rest are on the clubs' channels, and unofficial reuploaders
# ("DicapOr Football" and friends) crowd the same search results, which is why
# nothing is trusted unless its oEmbed author_url is in this list.
# Discovered via YouTube search and matched against the club name, Sept 2026.
CLUB_CHANNELS = {
    "Birmingham City": "@BCFC",                "Blackburn Rovers": "@BlackburnRovers",
    "Bolton Wanderers": "@OfficialBWFC",       "Bristol City": "@BristolCityFootballClub",
    "Burnley": "@burnleyofficial",             "Cardiff City": "@CardiffCityFC",
    "Charlton Athletic": "@CAFCOfficial",      "Derby County": "@dcfcofficial",
    "Lincoln City": "@lincolncityfc1685",      "Middlesbrough": "@MiddlesbroughFC",
    "Millwall": "@MillwallFC",                 "Norwich City": "@CanariesTV",
    "Portsmouth": "@OfficialPompey",           "Preston North End": "@pnefcofficial",
    "Queens Park Rangers": "@QPR",             "Sheffield United": "@sheffieldunited",
    "Southampton": "@SouthamptonFC",           "Stoke City": "@StokeCity",
    "Swansea City": "@SwanseaCity",            "Watford": "@watfordfcofficial",
    "West Bromwich Albion": "@OfficialAlbion", "West Ham United": "@westhamunited",
    "Wolverhampton Wanderers": "@OfficialWolvesVideo", "Wrexham": "@WxmAFCofficial",
}
OFFICIAL = {"https://www.youtube.com/" + c.lower()
            for c in CHANNELS + list(CLUB_CHANNELS.values())}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "en"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def channel_videos(handle):
    """(videoId, title) for the channel's latest uploads, newest first."""
    html = fetch(f"https://www.youtube.com/{handle}/videos")
    m = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not m:
        return []
    vids = []

    def walk(o):
        if isinstance(o, dict):
            lv = o.get("lockupViewModel")
            if lv and lv.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                title = (((lv.get("metadata") or {}).get("lockupMetadataViewModel") or {})
                         .get("title") or {}).get("content", "")
                if lv.get("contentId") and title:
                    vids.append((lv["contentId"], title))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(m.group(1)))
    return vids


UNITS = {"second": 0, "minute": 0, "hour": 0, "day": 1,
         "week": 7, "month": 30, "year": 365}


def age_days(published):
    """'2 weeks ago' -> 14. None when YouTube gave us nothing to read."""
    m = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", published or "")
    return int(m.group(1)) * UNITS[m.group(2)] if m else None


def channel_search(handle, query):
    """(videoId, title, publishedText) from a channel's own search page.

    The /videos page only exposes the latest 30 uploads, and @theEFL covers all
    three EFL divisions -- barely two days of fixtures. Searching the channel
    reaches the whole back catalogue, which is the only way to fill in a match
    played more than a couple of days ago.
    """
    html = fetch(f"https://www.youtube.com/{handle}/search?query="
                 + urllib.parse.quote(query))
    m = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not m:
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            vr = o.get("videoRenderer")
            if vr and vr.get("videoId"):
                title = "".join(r.get("text", "") for r in (vr.get("title") or {}).get("runs", []))
                if title:
                    out.append((vr["videoId"], title,
                                (vr.get("publishedTimeText") or {}).get("simpleText", "")))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(m.group(1)))
    return out


def official(video_id):
    """True only if the upload really is on one of the official channels."""
    try:
        u = f"https://www.youtube.com/oembed?url=https://youtu.be/{video_id}&format=json"
        d = json.loads(fetch(u))
    except Exception:
        return False
    return (d.get("author_url") or "").lower().rstrip("/") in OFFICIAL


# What these channels actually call clubs in titles. Without these, requiring
# every token rejects "West Brom", "Wolves", "QPR", "Preston".
ALIASES = {
    "queens park rangers": "qpr",
    "west bromwich albion": "west brom",
    "wolverhampton wanderers": "wolves",
    "preston north end": "preston",
    "sheffield united": "sheff utd",
    "sheffield wednesday": "sheff wed",
    # clubs title their own uploads with the nickname: "Highlights | Pompey v QPR"
    "portsmouth": "pompey",
    "middlesbrough": "boro",
}


def matches_title(a, b, title):
    """True when the title is a highlights upload naming BOTH of these clubs.

    Requiring both names is what kills the West Ham / West Bromwich collision --
    they are both in this division and @theEFL uploads highlights for every
    fixture, so a one-sided match would attach the wrong video.
    """
    t = title.lower()
    if "highlight" not in t:
        return False
    # Clubs also post behind-the-scenes and alternate-angle reels with
    # "highlights" in the title. They are not the match.
    if re.search(r"\bbts\b|\balt(ernate)? highlights\b|roving cam|behind the scenes"
                 r"|\bcam:|fan cam|tunnel cam", t):
        return False
    return _names(a, t) and _names(b, t)


def _names(club, t):
    alias = ALIASES.get(club.lower())
    if alias and re.search(rf"\b{re.escape(alias)}\b", t):
        return True
    return all(re.search(rf"\b{re.escape(w)}\b", t) for w in key_words(club))


def key_words(opponent):
    """'Birmingham City' -> {'birmingham'}: the distinctive word to match on."""
    drop = {"city", "town", "united", "athletic", "rovers", "wanderers", "county",
            "albion", "forest", "fc", "afc"}
    words = [w.lower() for w in re.sub(r"[^\w\s]", " ", opponent).split()]
    # Sheffield United and Sheffield Wednesday differ only in a word `drop`
    # removes, which would make either match the other's highlights.
    if words and words[0] == "sheffield":
        return set(words)
    keep = [w for w in words if w not in drop and len(w) >= 5]
    return set(keep or [w for w in words if w not in drop] or words)


MAX_SEARCHES = 10         # per run, and each searches up to 4 channels; the
                          # cron catches a cold start up over a few hours


def age_days_since(iso_date):
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - d).days


def main():
    data = json.load(open(os.path.join(DIR, "data.json")))
    path = os.path.join(DIR, "highlights.json")
    doc = json.load(open(path))
    hl = doc.setdefault("highlights", {})

    def pair(v):
        # entries written before the league-wide scan stored only the opponent
        return v.get("teams") or ["Wrexham", v.get("opponent", "")]

    dropped = [mid for mid, v in hl.items()
               if v.get("title") and not matches_title(*pair(v), v["title"])]
    for mid in dropped:
        print(f"  dropping stale/mismatched entry {mid}: {hl[mid].get('title','')[:60]}")
        del hl[mid]

    videos = []
    for handle in CHANNELS:
        try:
            videos += channel_videos(handle)
        except Exception as e:
            print(f"  {handle}: {type(e).__name__}", file=sys.stderr)
    if not videos:
        print("no channel uploads readable; leaving highlights.json untouched")
        return

    # Every completed league fixture, not just Wrexham's -- @theEFL uploads
    # highlights for the whole division, so the same scrape covers all 24 clubs.
    # Newest first, so a fixture maps to the newest matching upload.
    fixtures = []
    for m in data["matches"]:
        if m["completed"]:
            fixtures.append((m["id"], "Wrexham", m["opponent"], m["date"]))
    try:
        lg = json.load(open(os.path.join(DIR, "league.json")))
        names = {k: v["n"] for k, v in lg["teams"].items()}
        for m in lg["matches"]:
            if m["c"] and m["i"] not in {f[0] for f in fixtures}:
                fixtures.append((m["i"], names.get(m["h"], ""), names.get(m["a"], ""), m["d"]))
    except (OSError, ValueError, KeyError):
        pass
    fixtures.sort(key=lambda f: f[3], reverse=True)

    used = set()
    added = 0
    for mid, ha, ab, when in fixtures:
        if mid in hl or not (ha and ab):
            continue
        for vid, title in videos:
            if vid in used or not matches_title(ha, ab, title) or not official(vid):
                continue
            hl[mid] = {"yt": vid, "title": title, "teams": [ha, ab]}
            used.add(vid)
            added += 1
            print(f"  {when[:10]} {ha} v {ab}: {vid}  {title[:52]}")
            break

    # Anything the bulk scan could not see -- i.e. played more than a couple of
    # days ago -- gets one targeted search. Capped per run so a cold start
    # spreads over several crons, and misses are remembered so a fixture with no
    # upload is not searched for forever.
    misses = doc.setdefault("misses", {})
    todo = [f for f in fixtures
            if f[0] not in hl and f[1] and f[2] and misses.get(f[0], 0) < 3]
    for mid, ha, ab, when in todo[:MAX_SEARCHES]:
        played = age_days_since(when)
        found = None
        where = ["@theEFL", "@cbssportsgolazo",
                 CLUB_CHANNELS.get(ha), CLUB_CHANNELS.get(ab)]
        for vid, title, pub in [v for ch in where if ch
                                for v in channel_search(ch, f"{ha} {ab} highlights")]:
            if vid in used or not matches_title(ha, ab, title):
                continue
            age = age_days(pub)
            # A fixture's highlights go up within a day of it. Anything from a
            # different season -- or the reverse fixture months away -- is not
            # this match, however well the two club names line up.
            if age is None or played is None or abs(age - played) > 35:
                continue
            if not official(vid):
                continue
            found = (vid, title)
            break
        if found:
            hl[mid] = {"yt": found[0], "title": found[1], "teams": [ha, ab]}
            used.add(found[0])
            misses.pop(mid, None)
            added += 1
            print(f"  [search] {when[:10]} {ha} v {ab}: {found[0]}  {found[1][:46]}")
        else:
            misses[mid] = misses.get(mid, 0) + 1

    if added or dropped or todo:
        json.dump(doc, open(path, "w"), indent=1)
        # This runs after fetch_data.py, so league.json was written before these
        # videos were known. Patch it here rather than leave the Match tab a
        # cron behind on every new highlight.
        lp = os.path.join(DIR, "league.json")
        try:
            lg = json.load(open(lp))
            for m in lg["matches"]:
                yt = hl.get(m["i"], {}).get("yt")
                if yt:
                    m["y"] = yt
                else:
                    m.pop("y", None)
            json.dump(lg, open(lp, "w"), separators=(",", ":"))
        except (OSError, ValueError, KeyError):
            pass
    print(f"added {added}, total {len(hl)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:            # never break the pipeline over highlights
        print("highlights skipped:", type(e).__name__, e, file=sys.stderr)
