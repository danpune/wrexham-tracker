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
    matches = [{"completed": True, "result": r} for r in "WWDLW"]
    p = f.project(table, matches)
    assert p["played"] == 10 and p["points"] == 20
    assert p["ppg"] == 2.0
    assert p["remaining"] == 36
    assert p["projected"] == 92
    assert p["gapToSixth"] == 4          # 6th has 24, we have 20
    assert p["form"] == ["W", "W", "D", "L", "W"]
    assert p["tooEarly"] is False

    early = f.project([{"rank": 1, "team": "T", "played": 3, "points": 2,
                        "isWrexham": True}], matches)
    assert early["tooEarly"] is True     # don't extrapolate off 3 games

    assert f.project([{"rank": 1, "team": "T", "played": 1, "points": 1,
                       "isWrexham": False}], matches) is None


def test_strip_html():
    assert f.strip_html("<p>Hello  <b>world</b></p>") == "Hello world"
    assert f.strip_html("Caf&eacute; &amp; bar") == "Café & bar"
    assert f.strip_html(None) == ""


if __name__ == "__main__":
    test_rfc822(); test_projection(); test_strip_html()
    print("ok")
