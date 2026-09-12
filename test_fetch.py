#!/usr/bin/env python3
"""Self-check for the parsing logic. Run: python test_fetch.py"""
from datetime import datetime, timezone
import fetch_data as f


def test_rfc822():
    # The bug this guards: strptime's %Z matches "GMT" but returns a naive
    # datetime, so astimezone() re-reads it as machine-local and shifts the
    # timestamp by the runner's UTC offset.
    assert f.rfc822("Fri, 28 Aug 2026 21:19:29 GMT") == "2026-08-28T21:19:29+00:00"
    assert f.rfc822("Fri, 28 Aug 2026 21:19:29 +0100") == "2026-08-28T20:19:29+00:00"
    assert f.rfc822("garbage") is None
    assert f.rfc822("") is None


def test_projection():
    table = [{"rank": i, "team": f"T{i}", "played": 10, "points": 30 - i,
              "isWrexham": i == 10} for i in range(1, 25)]
    matches = [{"completed": True, "result": r, "comp": "League"} for r in "WWDLW"]
    p = f.project(table, matches)
    assert p["played"] == 10 and p["points"] == 20
    assert p["ppg"] == 2.0
    assert p["remaining"] == 36
    assert p["projected"] == 92
    assert p["gapToSixth"] == 4          # 6th has 24, we have 20
    assert p["form"] == ["W", "W", "D", "L", "W"]

    # A cup tie must not enter league form -- it is not part of the promotion picture.
    withcup = matches + [{"completed": True, "result": "L", "comp": "EFL Cup"}]
    assert f.project(table, withcup)["form"] == ["W", "W", "D", "L", "W"]
    assert p["tooEarly"] is False

    early = f.project([{"rank": 1, "team": "T", "played": 3, "points": 2,
                        "isWrexham": True}], matches)
    assert early["tooEarly"] is True     # don't extrapolate off 3 games

    assert f.project([{"rank": 1, "team": "T", "played": 1, "points": 1,
                       "isWrexham": False}], matches) is None


def test_safe_url():
    assert f.safe_url("https://a.example/x") == "https://a.example/x"
    # http media is mixed content on an HTTPS page, so it is upgraded, not dropped
    assert f.safe_url("http://a.example/x.mp3") == "https://a.example/x.mp3"
    # esc() does not neutralise a scheme, so these must never reach an href
    assert f.safe_url("javascript:alert(1)") == ""
    assert f.safe_url("data:text/html,<script>") == ""
    assert f.safe_url("  JAVASCRIPT:alert(1)") == ""
    assert f.safe_url(None) == ""


def test_strip_html():
    assert f.strip_html("<p>Hello  <b>world</b></p>") == "Hello world"
    assert f.strip_html("Caf&eacute; &amp; bar") == "Café & bar"
    assert f.strip_html(None) == ""




def test_matches_title():
    """Both clubs must be named. The division has West Ham AND West Bromwich,
    and Sheffield United AND Sheffield Wednesday, so a one-sided match is wrong."""
    import build_highlights as h
    ok = h.matches_title
    assert ok("Wrexham", "Millwall", "HIGHLIGHTS | Wrexham AFC vs Millwall")
    assert ok("Millwall", "Wrexham", "HIGHLIGHTS | Wrexham AFC vs Millwall")
    assert ok("Wrexham", "Queens Park Rangers", "QPR 1-2 Wrexham | Highlights")
    assert ok("Wolverhampton Wanderers", "Stoke City", "Wolves v Stoke City | Highlights")
    assert ok("West Bromwich Albion", "Burnley", "West Brom 2-0 Burnley highlights")
    # not a highlights upload
    assert not ok("Wrexham", "Millwall", "Wrexham AFC vs Millwall | Full match")
    # only one club named
    assert not ok("Wrexham", "Millwall", "HIGHLIGHTS | Wrexham AFC vs Watford")
    # the collisions
    assert not ok("West Ham United", "Burnley", "West Bromwich Albion v Burnley | Highlights")
    assert not ok("West Bromwich Albion", "Burnley", "West Ham United v Burnley | Highlights")
    assert not ok("Sheffield United", "Derby County", "Sheffield Wednesday v Derby | Highlights")
    assert not ok("Sheffield Wednesday", "Derby County", "Sheffield United v Derby | Highlights")
    # 'ham' inside Birmingham must not satisfy West Ham
    assert not ok("West Ham United", "Watford", "Birmingham City v Watford | Highlights")


def test_age_days():
    """YouTube's coarse 'N units ago' text is the only date signal on a search
    result, and it is what separates this season's fixture from the reverse one."""
    import build_highlights as h
    assert h.age_days("2 weeks ago") == 14
    assert h.age_days("10 months ago") == 300
    assert h.age_days("1 year ago") == 365
    assert h.age_days("3 days ago") == 3
    assert h.age_days("Streamed 2 days ago") == 2
    assert h.age_days("") is None
    assert h.age_days(None) is None
    # the guard the search pass applies: posted after kickoff, soon after
    ok = h.posted_after_match
    assert ok("2 weeks ago", 18)          # Cardiff (A), 17 Aug, read on 4 Sep
    assert ok("5 hours ago", 0)           # same-night upload
    assert ok("1 day ago", 1)
    assert not ok("10 months ago", 18)    # last season's
    assert not ok("2 years ago", 18)
    # Blackburn v Sheff Utd: Carabao Cup 25 Aug, league 8 Sep, both 1-2. The
    # cup clip is 2 weeks old against a league game 4 days old -- before kickoff.
    assert not ok("2 weeks ago", 4)
    assert not ok("", 4)
    assert not ok("3 days ago", None)


def test_rejects_bts_reels():
    """Clubs post behind-the-scenes reels titled '... Alt Highlights'. Not the match."""
    import build_highlights as h
    assert not h.matches_title("Blackburn Rovers", "Queens Park Rangers",
                               "ROVING CAM: Blackburn Rovers v QPR BTS & Alt Highlights")
    assert not h.matches_title("Millwall", "Wrexham", "TUNNEL CAM | Millwall v Wrexham highlights")
    assert h.matches_title("Blackburn Rovers", "Queens Park Rangers",
                           "Blackburn Rovers 1-2 QPR | Extended Highlights")


def test_title_traps_from_review():
    """Every title here was attached, or would have been, to the wrong match."""
    import build_highlights as h
    ok = h.matches_title
    # "derby" is a football noun -- this clip went on Charlton v Derby County
    assert not ok("Charlton Athletic", "Derby County",
                  "LONDON DERBY! | West Ham United v Charlton Athletic extended highlights")
    assert not ok("Preston North End", "Derby County",
                  "DERBY DAY! | Preston North End v Blackburn Rovers highlights")
    assert ok("Portsmouth", "Derby County",
              "SZMODICS SCORES AGAIN! | Portsmouth v Derby County Extended Highlights")
    # "sheffield" and "united" from two different clubs
    assert not ok("Sheffield United", "West Ham United",
                  "Sheffield Wednesday v West Ham United | highlights")
    assert ok("Sheffield United", "Bolton Wanderers",
              "WHAT A GAME! | Sheffield United v Bolton Wanderers Extended Highlights")
    assert ok("Sheffield United", "Stoke City", "Sheff Utd 2-0 Stoke | Highlights")
    # not the first team
    assert not ok("Derby County", "Middlesbrough",
                  "HIGHLIGHTS | Derby County Women Vs Middlesbrough (H)")
    assert not ok("Swansea City", "Sheffield United",
                  "Swansea City v Sheffield United | U21 | Highlights")
    assert not ok("Swansea City", "Wrexham", "HIGHLIGHTS | Swansea City Women vs Wrexham AFC Women")
    # a cup tie is not the league game between the same clubs...
    assert not ok("Southampton", "West Ham United",
                  "HIGHLIGHTS: Southampton 1-4 West Ham | Carabao Cup")
    # ...but it is exactly what a cup fixture needs
    assert ok("Southampton", "West Ham United",
              "HIGHLIGHTS: Southampton 1-4 West Ham | Carabao Cup", cup=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
