#!/usr/bin/env python3
"""Reel Radar scraper — pull public Instagram reel/post metrics with instaloader and append
a timestamped snapshot to data.json so the dashboard can chart trends over time.

    pip install instaloader
    python ig_scrape.py --links links.txt --out data.json

links.txt: one Instagram reel/post URL per line (blank lines / # comments ignored).

Reliability notes:
  - Instagram blocks datacenter IPs and unauthenticated bursts. Run this on your own machine
    (residential IP), space runs out (cron every few hours, NOT every minute), and log in for
    anything beyond a handful of URLs:
        instaloader --login YOUR_USER            # once, creates a saved session
        python ig_scrape.py --links links.txt --login YOUR_USER
  - Like counts are often hidden by Instagram; the field will be null when unavailable.
  - Scraping violates Instagram's ToS. Use for your own analytics; you accept the risk.

Auto-update: schedule this (cron/launchd) and publish data.json somewhere the static page can
fetch it (GitHub gist raw, S3 public object, your own host). The page polls that URL.
Use --gist GIST_ID (with env GITHUB_TOKEN) to push data.json to a gist automatically.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

try:
    import instaloader
except ImportError:
    sys.exit("instaloader not installed. Run: pip install instaloader")

SHORTCODE_RE = re.compile(r"instagram\.com/(reel|reels|p|tv)/([A-Za-z0-9_-]+)")
MAX_HISTORY = 500  # cap per-post snapshots so data.json can't grow unbounded


def parse_links(path: str) -> list[dict]:
    out, seen = [], set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = SHORTCODE_RE.search(line)
            if not m:
                print(f"  ! skipping unrecognized line: {line[:60]}")
                continue
            kind, code = m.group(1), m.group(2)
            kind = "reel" if kind == "reels" else kind
            typ = "post" if kind == "p" else ("igtv" if kind == "tv" else "reel")
            if code in seen:
                continue
            seen.add(code)
            out.append({"url": f"https://www.instagram.com/{kind}/{code}/", "code": code, "type": typ})
    return out


def _safe(fn, default=None):
    try:
        v = fn()
        return v
    except Exception:
        return default


def scrape_one(L: "instaloader.Instaloader", code: str) -> dict:
    post = instaloader.Post.from_shortcode(L.context, code)
    likes = _safe(lambda: int(post.likes))
    if likes is not None and likes < 0:
        likes = None  # hidden
    return {
        "owner": _safe(lambda: post.owner_username, "unknown"),
        "caption": _safe(lambda: (post.caption or "")[:400], ""),
        "taken_at": _safe(lambda: post.date_utc.replace(tzinfo=timezone.utc).isoformat()),
        "is_video": _safe(lambda: bool(post.is_video), False),
        "thumbnail": _safe(lambda: post.url),
        "snapshot": {
            "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "views": _safe(lambda: post.video_view_count),
            "likes": likes,
            "comments": _safe(lambda: int(post.comments)),
        },
    }


def load_existing(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            print("  ! existing data.json unreadable, starting fresh")
    return {"posts": {}}


def push_gist(gist_id: str, path: str) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  ! --gist given but GITHUB_TOKEN not set; skipping push")
        return
    import urllib.request
    with open(path) as f:
        content = f.read()
    body = json.dumps({"files": {os.path.basename(path): {"content": content}}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}", data=body, method="PATCH",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "reel-radar"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = json.load(r)
        url = raw.get("files", {}).get(os.path.basename(path), {}).get("raw_url")
        print(f"  ↑ pushed to gist. Raw URL (put this in Settings):\n    {url}")
    except Exception as e:
        print(f"  ! gist push failed: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape Instagram reel/post metrics into data.json")
    ap.add_argument("--links", default="links.txt", help="file of Instagram URLs (default links.txt)")
    ap.add_argument("--out", default="data.json", help="output JSON (default data.json)")
    ap.add_argument("--login", help="Instagram username to load a saved instaloader session for")
    ap.add_argument("--sleep", type=float, default=4.0, help="seconds between requests (default 4)")
    ap.add_argument("--gist", help="GitHub gist id to PATCH with the result (needs GITHUB_TOKEN)")
    args = ap.parse_args()

    links = parse_links(args.links)
    if not links:
        sys.exit(f"No valid Instagram URLs in {args.links}")

    L = instaloader.Instaloader(download_pictures=False, download_videos=False,
                                download_comments=False, save_metadata=False, quiet=True)
    if args.login:
        try:
            L.load_session_from_file(args.login)
            print(f"  session loaded for @{args.login}")
        except FileNotFoundError:
            sys.exit(f"No saved session for @{args.login}. Run: instaloader --login {args.login}")

    data = load_existing(args.out)
    data.setdefault("posts", {})

    ok = 0
    for i, l in enumerate(links, 1):
        print(f"[{i}/{len(links)}] {l['type']}/{l['code']} …")
        try:
            r = scrape_one(L, l["code"])
        except Exception as e:
            print(f"  ! failed: {e}")
            continue
        entry = data["posts"].get(l["code"], {})
        entry.update({"url": l["url"], "shortcode": l["code"], "type": l["type"],
                      "owner": r["owner"], "caption": r["caption"], "taken_at": r["taken_at"],
                      "is_video": r["is_video"], "thumbnail": r["thumbnail"]})
        hist = entry.get("history", [])
        hist.append(r["snapshot"])
        entry["history"] = hist[-MAX_HISTORY:]
        data["posts"][l["code"]] = entry
        s = r["snapshot"]
        print(f"    views={s['views']} likes={s['likes']} comments={s['comments']}")
        ok += 1
        if i < len(links):
            time.sleep(args.sleep)

    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n✓ wrote {args.out} ({ok}/{len(links)} scraped, {len(data['posts'])} tracked)")

    if args.gist:
        push_gist(args.gist, args.out)


if __name__ == "__main__":
    main()
