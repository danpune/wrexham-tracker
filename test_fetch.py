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


if __name__ == "__main__":
    test_rfc822(); test_projection(); test_safe_url(); test_strip_html()
    print("ok")


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
