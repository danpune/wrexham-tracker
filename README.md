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
| Highlights | Official YouTube channels (@WxmAFCofficial, @theEFL, @cbssportsgolazo), verified via oEmbed | free |
| Podcasts | Public podcast RSS (#AskWXM, Me the Wife and Wrexham AFC, Rousey's, BBC Sounds) | free |
| Odds | Polymarket per-fixture 3-way markets | free |
| Visitors | hits.sh badge | free, no signup |
| Weather | Open-Meteo (geocode + forecast) | free |

## Notes

- ESPN's `teams/{id}/schedule` endpoint only returns matches **already played**, so fixtures
  come from the league scoreboard filtered to Wrexham. 11 requests covers the season.
- ESPN rate-limits bursts with a 403; `get()` retries with a short backoff.
- The promotion number is a straight-line points-per-game projection against the historical
  ~72-point playoff cut. It stays hidden until 8 games are played, because extrapolating from
  three is noise. It is not a simulation.
- Kick-off times render in `Europe/London` regardless of where the viewer is.
- League matches only — cup runs aren't included.
- Odds come from Polymarket, matched per fixture (a generic "Wrexham" search only ranks up
  *resolved* past events). Kalshi lists the same fixtures under `KXEFLCHAMPIONSHIPGAME` but every
  contract is quoteless — no bid, ask or open interest — so it is deliberately not wired in.
- Display only: there is no trading integration and nothing on the site is betting advice.
- Feed URLs are filtered to http(s) at fetch time. HTML-escaping does not neutralise a
  `javascript:` scheme, and news/podcast links are third-party.
- No preload hint on `data.json`: `as="fetch"` mode-mismatches `fetch()` and doubles the download.

## Refresh trigger

The repo's own `schedule` has never fired (GitHub does not always start crons on a
brand-new repo). Until it does, `update.yml` also accepts a `repository_dispatch` of
type `refresh`, and the tennis tracker's proven 30-minute cron pings it. That needs a
fine-grained PAT with **Contents: read and write** on this repo, stored as the
`WXM_DISPATCH` secret in `danpune/tennis-slams-tracker`. With no secret set the ping
step skips and neither project is affected.

Kick a refresh by hand any time:

```
gh workflow run "Update Wrexham data" --repo danpune/wrexham-tracker
```

## Develop

```
python3 fetch_data.py     # refresh data.json
python3 test_fetch.py     # self-check on the parsing + projection logic
python3 -m http.server 8731
```
