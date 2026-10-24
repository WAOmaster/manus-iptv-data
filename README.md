# manus-iptv-data

A small public data feed for a family Android TV app (Manus IPTV). Once a day (02:00 Sri Lanka time) a GitHub Actions job checks every channel in the public iptv-org playlist, works out which ones still play, and publishes three small files on GitHub Pages:

| File | What it is |
|---|---|
| `channels.json.gz` | One record per stream: `u` url, `h` first 16 hex chars of sha1(url), `id` tvg-id, `s` status, `p` popularity 0-10, `c` check date (yyyymmdd) |
| `epg.json.gz` | Now/next TV guide: `{channel_id: [[start, stop, title], ...]}`, UTC epoch seconds, titles max 80 chars, about 2 h back to 30 h ahead. Keys are base ids (tvg-id without `@feed`) |
| `meta.json` | When it ran, counts per status, guide coverage, sources used, file sizes, run time |

Status `s`: `a` alive, `d` dead (dead on 2 days in a row), `g` blocked/auth (401/403/451 - the job runs in the US, the TV is in Sri Lanka, so this is NOT dead), `t` timeout or unknown.

Pages URL: https://waomaster.github.io/manus-iptv-data/

## Only public data
Everything here comes from public sources listed below. No tokens, no private playlists, nothing from the TV. Do not add any.

## Sources and licences
- iptv-org playlist and API (channels, feeds, guides, streams): https://github.com/iptv-org/iptv and https://github.com/iptv-org/api - Unlicense (public domain).
- iptv-org EPG grabber (run in CI, outputs reduced to titles/times): https://github.com/iptv-org/epg - Unlicense. The sites it reads have their own terms; only short title/time data is kept.
- i.mjh.nz guides (Pluto, Plex, Roku, Samsung TV Plus XMLTV): https://i.mjh.nz/ by Matt Huisman. No licence file is published; used as a free public download, only titles/times kept. Credit: i.mjh.nz.
- epgshare01 per-country guides (gap fill only): https://epgshare01.online/ - states "free EPG for legal use only"; no explicit grant for automated download, so this is the first source to drop if asked.
- Sri Lankan schedules (`extra_epg/hiru.py`, `extra_epg/rupavahini.py`): public schedule pages of Hiru TV (hirutv.lk) and Rupavahini (tv.rupavahini.lk). One request per page per run, identifying User-Agent, only titles/times kept. Both robots.txt files allow this (no terms-of-use page read). Schedules are weekly templates and may differ from what actually airs.
- Streams are third-party links; this repo hosts no video.

## How the pipeline works
`prepare` (download + build records + popularity) then in parallel `probe` (async HTTP check, 64 at once, 8 s timeout) and `grab` (one job per top-10 site, 400 channels max, chunked, 21 min limit) then `publish` (merge guides, write files) then `deploy` (GitHub Pages). Guide priority: `extra_epg/` > i.mjh.nz > grabber > epgshare01.
Popularity: `ln(1+G)+0.5ln(1+F)+0.3ln(1+S)+0.5[network]+0.3[launched]` (G guide sites, F feeds, S streams from the iptv-org API), scaled 0-10. The app adds its own country boost.
Probe history lives in the Actions cache (`state/history.json`, restored each run) so "dead" needs two dead days in a row.

## Extra schedules
See `extra_epg/README.md` to plug in broadcaster-website schedules (e.g. Sri Lanka).

## Run it
- On GitHub: Actions tab > daily-data > Run workflow (or `gh workflow run daily.yml`).
- Locally (Python 3.12, `pip install aiohttp`): `python pipeline/prepare.py work`, `python pipeline/probe.py work state/history.json`, `python pipeline/publish.py work site`. Tests: `python tests/test_basic.py`.
