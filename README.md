# Reel Radar

Track Instagram reels — the **actual video** embedded next to its metrics, with trend charts.
Everything runs on **GitHub Actions**; the dashboard is a static page. **No login, no API key, no
cost.**

**Live page:** https://drop.dashverse.ai/reel-radar

## How it works

Instagram serves its `og:`/`description` meta tags — **likes, comments, caption, owner, date,
thumbnail** — to crawler user-agents (Googlebot). The scraper fetches each reel URL with that UA
and parses those tags. No account, no session, standard library only.

```
 links.txt (the reels you track)                    GitHub Actions (every 5 min)
        │  edit on GitHub, commit                          │  ig_scrape.py fetches with a crawler UA
        └──────────── push triggers ─────────────────────►│  commits data.json back to the repo
                                                           ▼
        static page  ◄──── polls raw data.json ──── raw.githubusercontent.com
        + embeds the real video via Instagram's iframe · auto-updates · "last updated" shown
```

## What you get

✅ **likes**, ✅ **comments**, ✅ caption, ✅ owner, ✅ date posted, ✅ thumbnail — tracked over
time so the dashboard charts trends and ranks reels by engagement.

❌ **view/play count** — Instagram does **not** expose it in the crawler payload. Likes + comments
only. (Views would require a logged-in session or a paid API, which this deliberately avoids.)

## Adding reels

Edit [`links.txt`](links.txt) — one Instagram reel/post URL per line — and commit. Committing
triggers the scrape (`on: push` for `links.txt`); the reel appears on the page within a few minutes.

```
https://www.instagram.com/reel/XXXXXXXXXXX/
https://www.instagram.com/p/XXXXXXXXXXX/
```

## Updating

The `scrape` workflow (`.github/workflows/scrape.yml`) runs **every 5 minutes** (`schedule`), plus
on demand (Actions → **Run workflow**) and whenever `links.txt` changes. Each run appends a
timestamped snapshot per reel, so the charts build a trend.

> GitHub's cron floor is 5 minutes and scheduled runs are best-effort — under load they can be
> delayed by several minutes. `raw.githubusercontent.com` also caches for ~5 min. So real-world
> freshness is roughly **5–15 minutes**, not instant. That's as live as a free, hands-off setup gets.

Run it locally too if you want:

```bash
python3 ig_scrape.py --links links.txt --out data.json     # stdlib only, no pip install
```

## Files

| File | What |
|---|---|
| `index.html` | the dashboard (deployed to drop.dashverse) |
| `sample-data.json` | demo data shown before you add real reels |
| `ig_scrape.py` | the scraper (crawler-UA, standard library) |
| `links.txt` | the reels you track — **edit this to add reels** |
| `data.json` | scraper output the page reads (committed by the workflow) |
| `.github/workflows/scrape.yml` | the 5-min schedule + Run-workflow button |

## Legal / ToS

Reading Instagram's public meta tags is far lighter than API scraping, but automated collection
still runs against Instagram's Terms of Service. Use for your own analytics. You accept the risk.
