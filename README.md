# Reel Radar

Track Instagram reels/posts — the **actual video** embedded next to its metrics (views, likes,
comments, engagement) with trend charts. Everything runs on **GitHub Actions**; the dashboard is a
static page. No local machine, no server to run.

**Live page:** https://drop.dashverse.ai/reel-radar

## How it works

```
 links.txt (the reels you track)                      GitHub Actions (schedule + button)
        │  edit on GitHub, commit                             │  runs ig_scrape.py (instaloader)
        └──────────────── push triggers ────────────────────►│  commits data.json back to the repo
                                                              ▼
              static page  ◄──── polls raw data.json ──── raw.githubusercontent.com
              + embeds the real video via Instagram's iframe
```

You only ever do two things:

- **Add reels** → edit `links.txt` (one URL per line) and commit. The scrape runs automatically.
- **Refresh metrics** → the page's Refresh button re-pulls the latest data; to force a *new* scrape,
  run the workflow (Actions → **scrape** → **Run workflow**).

## Adding reels

Edit [`links.txt`](links.txt) — one Instagram reel/post URL per line:

```
https://www.instagram.com/reel/XXXXXXXXXXX/
https://www.instagram.com/p/XXXXXXXXXXX/
```

Committing it triggers the `scrape` workflow (it runs `on: push` for `links.txt`). Give it a
minute, then hit Refresh on the page.

## Refreshing / scheduling

The `scrape` workflow (`.github/workflows/scrape.yml`) runs:

- **every 6 hours** (`schedule`) — keeps numbers current on their own,
- **on demand** (`workflow_dispatch`) — the **Run workflow** button = your manual refresh,
- **on push to `links.txt`** — so adding a reel scrapes it right away.

Each run appends a timestamped snapshot per reel, so the charts build a trend over time.

## ⚠️ Reliability: Instagram blocks datacenter IPs

GitHub's runners use datacenter IPs, which Instagram rate-limits/blocks hard — **anonymous runs
often come back empty.** To make it reliable, give the workflow a logged-in session:

1. On any machine (once): `pip install instaloader && instaloader --login YOUR_IG_USER`
   (creates `~/.config/instaloader/session-YOUR_IG_USER`).
2. Base64 it: `base64 -i ~/.config/instaloader/session-YOUR_IG_USER | pbcopy` (macOS).
3. In the repo → **Settings → Secrets and variables → Actions**, add:
   - `IG_USERNAME` = your IG username
   - `IG_SESSION`  = the base64 blob
4. The workflow auto-detects the secret and logs in.

Use a burner/secondary Instagram account — a flagged session can get the account challenged.
Even logged in, keep the cadence slow (the 6-hour default is fine).

If it still gets blocked, the reliable-but-paid path is a 3rd-party scraper API (Apify / RapidAPI):
swap the `Scrape` step to call that API with a key stored as a secret.

## What data you get

- **Views/plays, comments, caption, owner, timestamp** — usually available.
- **Likes** — Instagram often hides these; shows `—` when unavailable.
- Full official insights (reach, saves, plays) exist only for **your own** business/creator media
  via the Instagram Graph API — not this tool, which targets arbitrary public reels via instaloader.

## Files

| File | What |
|---|---|
| `index.html` | the dashboard (deployed to drop.dashverse) |
| `sample-data.json` | demo data shown before you add real reels |
| `ig_scrape.py` | the scraper (instaloader) |
| `links.txt` | the reels you track — **edit this to add reels** |
| `data.json` | scraper output the page reads (committed by the workflow) |
| `.github/workflows/scrape.yml` | the schedule + Run-workflow button |

## Legal / ToS

Scraping Instagram violates their Terms of Service. Use for your own analytics, keep the cadence
slow, and prefer a secondary account for the session. You accept the risk.
