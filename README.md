# Wrexham Tracker

Wrexham AFC, EFL Championship 2026/27 — fixtures, table, promotion projection, news and podcasts
on one page. Static site, no API keys, no build step, £0 to run.

**Live:** https://danpune.github.io/wrexham-tracker/

## How it works

A GitHub Action runs `fetch_data.py` every 30 minutes, writes `data.json`, and commits it.
`index.html` is a single self-contained file that fetches that JSON — no framework, no
dependencies, no external fonts.

| Panel | Source | Cost |
|---|---|---|
| Fixtures & results | ESPN `soccer/eng.2` scoreboard, walked month by month | free |
| League table | ESPN `soccer/eng.2` standings | free |
| News | Google News RSS | free |
| Podcasts | Public podcast RSS (#AskWXM, Me the Wife and Wrexham AFC, Rousey's, BBC Sounds) | free |
| Visitors | hits.sh badge | free, no signup |

## Notes

- ESPN's `teams/{id}/schedule` endpoint only returns matches **already played**, so fixtures
  come from the league scoreboard filtered to Wrexham. 11 requests covers the season.
- ESPN rate-limits bursts with a 403; `get()` retries with a short backoff.
- The promotion number is a straight-line points-per-game projection against the historical
  ~72-point playoff cut. It stays hidden until 8 games are played, because extrapolating from
  three is noise. It is not a simulation.
- Kick-off times render in `Europe/London` regardless of where the viewer is.
- League matches only — cup runs aren't included.

## Develop

```
python3 fetch_data.py     # refresh data.json
python3 test_fetch.py     # self-check on the parsing + projection logic
python3 -m http.server 8731
```
