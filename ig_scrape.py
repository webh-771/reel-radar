#!/usr/bin/env python3
"""Reel Radar scraper — read public Instagram reel/post metrics WITHOUT login or an API.

Instagram serves the og:/description meta tags (likes, comments, caption, owner, date, thumbnail)
to crawler user-agents like Googlebot. We fetch each reel URL with that UA and parse those tags.
No account, no session, no API key. Standard-library only.

    python ig_scrape.py --links links.txt --out data.json

Limitation: the crawler payload does NOT include the view/play count — only likes + comments.

Auto-update: run this on GitHub Actions (or any cron). It appends a timestamped snapshot per reel
to data.json; the dashboard polls that file.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

SHORTCODE_RE = re.compile(r"instagram\.com/(?:[^/]+/)?(reel|reels|p|tv)/([A-Za-z0-9_-]+)")
CRAWLER_UA = "Googlebot/2.1 (+http://www.google.com/bot.html)"
MAX_HISTORY = 500

# "<n> likes, <m> comments - <user> on <Month d, yyyy>: "<caption>""
LIKES_RE    = re.compile(r'([\d,]+)\s+likes', re.I)
COMMENTS_RE = re.compile(r'([\d,]+)\s+comments', re.I)
LIKEJSON_RE = re.compile(r'"like_count":\s*(\d+)')
CMTJSON_RE  = re.compile(r'"comment_count":\s*(\d+)')
DESC_RE     = re.compile(r'<meta\s+(?:property="og:description"|name="description")\s+content="([^"]*)"', re.I)
OGURL_RE    = re.compile(r'<meta\s+property="og:url"\s+content="https://www\.instagram\.com/([^/]+)/', re.I)
TWTITLE_RE  = re.compile(r'<meta\s+name="twitter:title"\s+content="[^(]*\(&#064;([^)&]+)', re.I)
OGIMG_RE    = re.compile(r'<meta\s+property="og:image"\s+content="([^"]*)"', re.I)
DATE_RE     = re.compile(r'on\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})')
CAP_RE      = re.compile(r'\d{4}:\s+&quot;(.*)&quot;', re.S)


def parse_links(path):
    out, seen = [], set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = SHORTCODE_RE.search(line)
            if not m:
                print(f"  ! skip unrecognized: {line[:60]}")
                continue
            kind, code = m.group(1), m.group(2)
            kind = "reel" if kind == "reels" else kind
            typ = "post" if kind == "p" else ("igtv" if kind == "tv" else "reel")
            if code in seen:
                continue
            seen.add(code)
            out.append({"url": f"https://www.instagram.com/{kind}/{code}/", "code": code, "type": typ})
    return out


def _int(s):
    try:
        return int(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_iso(datestr):
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(datestr, fmt).replace(tzinfo=timezone.utc).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_one(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": CRAWLER_UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")

    likes = _int(m.group(1)) if (m := LIKEJSON_RE.search(body)) else None
    comments = _int(m.group(1)) if (m := CMTJSON_RE.search(body)) else None

    desc = ""
    md = DESC_RE.search(body)
    if md:
        desc = html.unescape(md.group(1))
        if likes is None and (ml := LIKES_RE.search(desc)):
            likes = _int(ml.group(1))
        if comments is None and (mc := COMMENTS_RE.search(desc)):
            comments = _int(mc.group(1))

    owner = None
    if (mo := OGURL_RE.search(body)):
        owner = mo.group(1)
    elif (mt := TWTITLE_RE.search(body)):
        owner = mt.group(1)

    thumb = html.unescape(mi.group(1)) if (mi := OGIMG_RE.search(body)) else None
    raw_desc = md.group(1) if md else ""
    taken = _to_iso(mdt.group(1)) if (mdt := DATE_RE.search(html.unescape(raw_desc))) else None
    caption = html.unescape(mc2.group(1)).strip() if (mc2 := CAP_RE.search(raw_desc)) else ""

    if likes is None and comments is None and owner is None:
        raise RuntimeError("no data in response (blocked or unsupported)")

    return {
        "owner": owner or "unknown",
        "caption": caption[:400],
        "taken_at": taken,
        "thumbnail": thumb,
        "snapshot": {
            "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "views": None,  # not exposed to crawlers
            "likes": likes,
            "comments": comments,
        },
    }


def load_existing(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            print("  ! existing data.json unreadable, starting fresh")
    return {"posts": {}}


def push_gist(gist_id, path):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  ! --gist given but GITHUB_TOKEN not set; skipping")
        return
    with open(path) as f:
        content = f.read()
    body = json.dumps({"files": {os.path.basename(path): {"content": content}}}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}", data=body, method="PATCH",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "reel-radar"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = json.load(r)
        print("  ↑ pushed to gist:", raw.get("files", {}).get(os.path.basename(path), {}).get("raw_url"))
    except Exception as e:
        print(f"  ! gist push failed: {e}")


def main():
    ap = argparse.ArgumentParser(description="Scrape public Instagram reel metrics (no login/API)")
    ap.add_argument("--links", default="links.txt")
    ap.add_argument("--out", default="data.json")
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--gist")
    args = ap.parse_args()

    links = parse_links(args.links)
    if not links:
        print(f"No valid Instagram URLs in {args.links} — nothing to do.")
        return

    data = load_existing(args.out)
    data.setdefault("posts", {})

    ok = 0
    for i, l in enumerate(links, 1):
        print(f"[{i}/{len(links)}] {l['type']}/{l['code']} …")
        try:
            r = fetch_one(l["url"])
        except Exception as e:
            print(f"  ! failed: {e}")
            continue
        entry = data["posts"].get(l["code"], {})
        entry.update({"url": l["url"], "shortcode": l["code"], "type": l["type"],
                      "owner": r["owner"], "caption": r["caption"], "taken_at": r["taken_at"],
                      "thumbnail": r["thumbnail"]})
        entry.setdefault("history", []).append(r["snapshot"])
        entry["history"] = entry["history"][-MAX_HISTORY:]
        data["posts"][l["code"]] = entry
        s = r["snapshot"]
        print(f"    @{r['owner']} likes={s['likes']} comments={s['comments']}")
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
