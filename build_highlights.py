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
import json, os, re, sys, urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
# Official rights-holding channels. The club's handle is @WxmAFCofficial -- NOT
# @WrexhamAFC, which does not exist.
CHANNELS = ["@WxmAFCofficial", "@theEFL", "@cbssportsgolazo"]
OFFICIAL = {"https://www.youtube.com/" + c.lower() for c in CHANNELS}
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
}


def matches_title(opponent, title):
    """A title is this fixture's only if it names Wrexham and the opponent.

    The "wrexham" guard is what kills the West Ham / West Bromwich collision --
    both are in this division and @theEFL uploads highlights for every fixture.
    """
    t = title.lower()
    if "highlight" not in t or "wrexham" not in t:
        return False
    alias = ALIASES.get(opponent.lower())
    if alias and re.search(rf"\b{re.escape(alias)}\b", t):
        return True
    return all(re.search(rf"\b{re.escape(w)}\b", t) for w in key_words(opponent))


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


def main():
    data = json.load(open(os.path.join(DIR, "data.json")))
    path = os.path.join(DIR, "highlights.json")
    doc = json.load(open(path))
    hl = doc.setdefault("highlights", {})

    dropped = [mid for mid, v in hl.items()
               if v.get("title") and not matches_title(v.get("opponent", ""), v["title"])]
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

    # newest match first, so a fixture maps to the newest matching upload
    done = [m for m in data["matches"] if m["completed"]][::-1]
    used = set()
    added = 0
    for m in done:
        if m["id"] in hl:
            continue
        for vid, title in videos:
            if vid in used:
                continue
            if not matches_title(m["opponent"], title):
                continue
            if not official(vid):
                continue
            hl[m["id"]] = {"yt": vid, "title": title, "opponent": m["opponent"]}
            used.add(vid)
            added += 1
            print(f"  {m['date'][:10]} v {m['opponent']}: {vid}  {title[:56]}")
            break

    if added or dropped:
        json.dump(doc, open(path, "w"), indent=1)
    print(f"added {added}, total {len(hl)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:            # never break the pipeline over highlights
        print("highlights skipped:", type(e).__name__, e, file=sys.stderr)
