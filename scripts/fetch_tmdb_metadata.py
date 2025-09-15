#!/usr/bin/env python3
"""
Populate Serie metadata (real name, synopsis, image) from TVMaze for the series
already present in your database.

Usage:
  python scripts/fetch_tmdb_metadata.py [--only-missing] [--no-rename] [--sleep 0.2]

Notes:
  - Uses TVMaze singlesearch endpoint, no API key required:
      https://api.tvmaze.com/singlesearch/shows?q=<name>
  - Reads shows from the `serie` table and updates fields in place.
  - Only touches rows that are missing metadata when --only-missing is set.
  - By default, also updates the show name to TVMaze's canonical `name`.
"""
import os
import sys
import json
import time
import argparse
import unicodedata
import re
from urllib import request, parse, error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app.app import app  # noqa: E402
from app.models import db, Serie  # noqa: E402


def http_get_json(url: str, params: dict | None = None, headers: dict | None = None):
    if params:
        q = parse.urlencode(params)
        sep = '&' if ('?' in url) else '?'
        url = f"{url}{sep}{q}"
    req = request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url}")
        data = resp.read()
        return json.loads(data.decode('utf-8'))


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').lower()
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def strip_tags(html: str) -> str:
    if not html:
        return ''
    # Remove simple HTML tags from TVMaze summary
    return re.sub(r"<[^>]+>", "", html)


def update_one(serie: Serie, update_name: bool) -> bool:
    # TVMaze singlesearch returns a single best match or 404
    base = "https://api.tvmaze.com/singlesearch/shows"
    try:
        data = http_get_json(base, params={"q": serie.name})
    except Exception as e:
        print(f"[WARN] search failed for '{serie.name}': {e}")
        return False

    vm_name = data.get('name') or serie.name
    summary_html = data.get('summary') or ''
    overview = strip_tags(summary_html).strip()
    image = data.get('image') or {}
    image_url = image.get('original') or image.get('medium') or ''

    changed = False
    if update_name and vm_name and vm_name != serie.name:
        serie.name = vm_name
        changed = True
    if overview and (not serie.synopsis or serie.synopsis.strip() != overview.strip()):
        serie.synopsis = overview
        changed = True
    if image_url and (not serie.image_url or serie.image_url.strip() != image_url.strip()):
        serie.image_url = image_url
        changed = True

    return changed


def main():
    parser = argparse.ArgumentParser(description="Populate series metadata from TVMaze")
    parser.add_argument("--only-missing", action="store_true", help="Update only rows missing synopsis or image")
    parser.add_argument("--no-rename", action="store_true", help="Do not update the series name from TVMaze")
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between API calls")
    args = parser.parse_args()

    updated = 0
    skipped = 0

    with app.app_context():
        # Ensure tables exist (in case script runs before app bootstrap)
        db.create_all()
        q = Serie.query
        if args.only_missing:
            q = q.filter((Serie.synopsis.is_(None)) | (Serie.synopsis == "") | (Serie.image_url.is_(None)) | (Serie.image_url == ""))
        series = q.all()
        total = len(series)
        print(f"Found {total} series to process.")
        for i, s in enumerate(series, 1):
            changed = update_one(s, update_name=(not args.no_rename))
            if changed:
                db.session.add(s)
                db.session.commit()
                updated += 1
                print(f"[{i}/{total}] Updated: {s.name}")
            else:
                skipped += 1
                print(f"[{i}/{total}] No change: {s.name}")
            time.sleep(max(0.0, args.sleep))

    print(f"Done. Updated: {updated}, Unchanged: {skipped}")


if __name__ == "__main__":
    main()
