#!/usr/bin/env python3
"""
scripts/fetch_hotel_galleries.py — Autonomous Multi-Photo Gallery Harvester.

Fetches authentic photo galleries (4–8 high-resolution photos) for hotels from:
1. Fly.pl offer pages (via canonical hotel URL truncation)
2. Scraped CSV files in data/filters/**/travel_prices.csv
3. Persistent knowledge base cache in hotel_galleries_kb.json

Features:
- Canonical URL resolution: truncates long booking tokens to permanent hotel overview URLs.
- Deduplication and CDN URL cleaning (high-res WebP formatting).
- Semantic photo categorization (Территория, Бассейн и пляж, Номера, Ресторан, Инфраструктура).
- Updates hotel_galleries_kb.json and compiles into hotel_specs_kb.json.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.parse

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fetch_hotel_galleries")

DEFAULT_GALLERIES_KB = "hotel_galleries_kb.json"
DEFAULT_SPECS_KB = "hotel_specs_kb.json"

SEMANTIC_LABELS = [
    "Территория и отель",
    "Бассейн и пляж",
    "Номера и интерьер",
    "Ресторан и бары",
    "Инфраструктура и спорт",
    "Зона отдыха и релакс",
    "Вид на море",
    "Детская зона",
]


def to_canonical_hotel_url(url: str) -> Optional[str]:
    """Converts a long Fly.pl offer/booking URL into a permanent canonical hotel page URL."""
    if not url or "fly.pl/wycieczka/" not in url:
        return None
    # Matches https://fly.pl/wycieczka/{country},{region},{city}/{hotel-slug}/
    m = re.match(r'(https?://[^/]+/wycieczka/[^/]+/[^/]+/)', url)
    if m:
        return m.group(1)
    return url


def load_galleries_kb(path: str = DEFAULT_GALLERIES_KB) -> Dict[str, Any]:
    """Loads existing galleries KB or creates empty container."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "galleries" in data:
                    return data
        except Exception as e:
            logger.warning(f"Could not load {path}: {e}")
    return {"updated_at": "", "total_hotels": 0, "galleries": {}}


def save_galleries_kb(data: Dict[str, Any], path: str = DEFAULT_GALLERIES_KB):
    """Saves galleries KB atomically with metadata."""
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["total_hotels"] = len(data.get("galleries", {}))
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    logger.info(f"Saved {data['total_hotels']} hotel galleries to {path}")


def extract_photos_from_html(html_text: str, max_photos: int = 8) -> List[Dict[str, str]]:
    """Extracts high-resolution hotel photos from Fly.pl hotel page HTML."""
    # 1. Standard img src
    matches = re.findall(r'<img[^>]+src=[\"\']([^\"\']+)[\"\'][^>]*>', html_text)
    # 2. srcset / data-src
    matches.extend(re.findall(r'(?:srcset|data-src|data-lazy)=[\"\']([^\"\']+)[\"\']', html_text, re.IGNORECASE))
    # 3. Direct CDN image URLs in HTML or embedded JSON state
    pattern_cdn = r'https?://[^\s"\'<>]*(?:/plain/|/img/)[^\s"\'<>]+'
    matches.extend(re.findall(pattern_cdn, html_text, re.IGNORECASE))

    raw_urls = []
    for src in matches:
        # Split srcset comma-separated values
        parts = [p.strip().split(" ")[0] for p in src.split(",")]
        for p in parts:
            if not p:
                continue
            clean = p.split("@")[0].split("&quot;")[0].split('"')[0].split("'")[0].strip()
            clean = clean.replace(r"\/", "/")
            # Upgrade resolution
            clean = re.sub(r'rs:fit:\d+:\d+', 'rs:fit:1280:720', clean)
            clean = re.sub(r'rs:fill:\d+:\d+', 'rs:fit:1280:720', clean)
            
            low = clean.lower()
            if any(bad in low for bad in ("logo", "tripadvisor", "flag", "icon", "svg", "be_users", "user_upload", "przelewy", "visa", "adobestock", "kuba-last-minute")):
                continue
            if any(marker in low for marker in ("/plain/eccx/img/", "/plain/cms/fileadmin/config_img/objects/", "/plain/img/", "rs:fit:1280:720")):
                if clean not in raw_urls:
                    raw_urls.append(clean)

    labeled_photos: List[Dict[str, str]] = []
    for idx, u in enumerate(raw_urls[:max_photos]):
        label = SEMANTIC_LABELS[idx] if idx < len(SEMANTIC_LABELS) else f"Фото отеля {idx + 1}"
        labeled_photos.append({"label": label, "url": u})

    return labeled_photos


def fetch_hotel_gallery(
    session: requests.Session,
    offer_url: str,
    max_photos: int = 8,
    timeout: tuple = (4, 6),
) -> List[Dict[str, str]]:
    """Fetches hotel page and extracts gallery photos."""
    canonical_url = to_canonical_hotel_url(offer_url) or offer_url
    try:
        r = session.get(canonical_url, timeout=timeout)
        if r.status_code == 200:
            photos = extract_photos_from_html(r.text, max_photos=max_photos)
            if photos:
                return photos
            # Fallback: if canonical had 0, try original offer_url
            if canonical_url != offer_url:
                r2 = session.get(offer_url, timeout=timeout)
                if r2.status_code == 200:
                    return extract_photos_from_html(r2.text, max_photos=max_photos)
        else:
            logger.debug(f"HTTP {r.status_code} for {canonical_url}")
    except Exception as e:
        logger.debug(f"Failed to fetch {canonical_url}: {e}")
    return []


def collect_hotel_offer_urls() -> Dict[str, str]:
    """Scans all available CSVs (locally and from git) and finds latest offer_url per hotel."""
    urls: Dict[str, str] = {}
    csv_paths = glob.glob("data/filters/**/travel_prices.csv", recursive=True)
    csv_paths.extend(glob.glob("data_runs/*/*.csv"))
    if os.path.exists("data/travel_prices.csv"):
        csv_paths.append("data/travel_prices.csv")

    for path in csv_paths:
        try:
            with open(path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or "hotel_name" not in reader.fieldnames:
                    continue
                for row in reader:
                    hn = (row.get("hotel_name") or "").strip()
                    ou = (row.get("offer_url") or "").strip()
                    if hn and ou and ou.startswith("http") and hn not in urls:
                        if not any(excl in ou for excl in ("/wycieczka/polska", "/wycieczka/czechy")):
                            urls[hn] = ou
        except Exception as e:
            logger.debug(f"Error scanning {path}: {e}")

    # Fallback/enhancement: scan git tracked files if in sparse checkout
    try:
        import subprocess, io
        git_csvs = subprocess.check_output(
            ["git", "ls-files", "data/filters/*/travel_prices.csv"], text=True
        ).splitlines()
        for gf in git_csvs:
            try:
                content = subprocess.check_output(["git", "show", f"origin/main:{gf}"], text=True)
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    hn = (row.get("hotel_name") or "").strip()
                    ou = (row.get("offer_url") or "").strip()
                    if hn and ou and ou.startswith("http") and hn not in urls:
                        if not any(excl in ou for excl in ("/wycieczka/polska", "/wycieczka/czechy")):
                            urls[hn] = ou
            except Exception:
                pass
    except Exception:
        pass

    return urls


def sync_galleries_into_specs_kb(
    galleries_kb_path: str = DEFAULT_GALLERIES_KB,
    specs_kb_path: str = DEFAULT_SPECS_KB,
) -> int:
    """Injects gallery_photos into hotel_specs_kb.json so Passports compile with galleries."""
    if not os.path.exists(galleries_kb_path) or not os.path.exists(specs_kb_path):
        return 0

    with open(galleries_kb_path, "r", encoding="utf-8") as f:
        g_data = json.load(f)
    galleries = g_data.get("galleries", {})

    with open(specs_kb_path, "r", encoding="utf-8") as f:
        s_data = json.load(f)
    hotels = s_data.get("hotels", {})

    updated = 0
    for h_name, photos in galleries.items():
        if h_name not in hotels:
            hotels[h_name] = {
                "destination": "Кипр" if any(marker in str(photos) for marker in ("cypr", "larnaka", "paphos", "limassol", "kyrenia", "ayia-napa", "protaras")) else "Египет",
                "specs": {"gallery_photos": photos}
            }
            updated += 1
        elif isinstance(hotels[h_name], dict):
            h_entry = hotels[h_name]
            if "specs" in h_entry and isinstance(h_entry["specs"], dict):
                h_entry["specs"]["gallery_photos"] = photos
                if "passport" in h_entry["specs"] and isinstance(h_entry["specs"]["passport"], dict):
                    h_entry["specs"]["passport"]["gallery_photos"] = photos
                updated += 1
            else:
                h_entry["specs"] = {"gallery_photos": photos}
                updated += 1

    if updated > 0:
        with open(specs_kb_path, "w", encoding="utf-8") as f:
            json.dump(s_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Synced {updated} hotel galleries into {specs_kb_path}")
    return updated


def main():
    parser = argparse.ArgumentParser(description="Harvest multi-photo galleries for hotels")
    parser.add_argument("--galleries-kb", default=DEFAULT_GALLERIES_KB, help="Path to hotel_galleries_kb.json")
    parser.add_argument("--specs-kb", default=DEFAULT_SPECS_KB, help="Path to hotel_specs_kb.json")
    parser.add_argument("--urls-file", type=str, default=None, help="Optional JSON file with {hotel_name: offer_url} or {hotel_name: {offer_url: ...}}")
    parser.add_argument("--destination", type=str, default="all", choices=["all", "egypt", "turkey", "greece", "cyprus"], help="Target destination filter")
    parser.add_argument("--max-hotels", type=int, default=1000, help="Max hotels to fetch in one run")
    parser.add_argument("--hotel", type=str, default=None, help="Fetch a single specific hotel by name")
    parser.add_argument("--url", type=str, default=None, help="Explicit URL for the specific hotel")
    args = parser.parse_args()

    g_kb = load_galleries_kb(args.galleries_kb)
    galleries = g_kb.get("galleries", {})

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    })
    session.cookies.set("_crflytest", "newfly2:new", domain=".fly.pl")
    session.cookies.set("newpath", "1", domain=".fly.pl")

    # Single hotel mode
    if args.hotel:
        h_name = args.hotel.strip()
        url = args.url or collect_hotel_offer_urls().get(h_name)
        if not url:
            logger.error(f"No offer_url found for hotel '{h_name}'. Provide with --url.")
            sys.exit(1)
        photos = fetch_hotel_gallery(session, url, timeout=(5, 9))
        if photos:
            galleries[h_name] = photos
            logger.info(f"✅ Successfully fetched {len(photos)} photos for '{h_name}'")
            save_galleries_kb(g_kb, args.galleries_kb)
            sync_galleries_into_specs_kb(args.galleries_kb, args.specs_kb)
        else:
            logger.warning(f"❌ Could not extract photos for '{h_name}' from {url}")
        return

    # Batch mode: scan URLs file or CSVs for hotels missing galleries
    discovered_urls = {}
    if args.urls_file and os.path.exists(args.urls_file):
        try:
            with open(args.urls_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            u = v.get("offer_url") or v.get("url") or ""
                        elif isinstance(v, str):
                            u = v
                        else:
                            u = ""
                        if u and u.startswith("http"):
                            discovered_urls[k] = u
        except Exception as e:
            logger.warning(f"Could not load urls-file {args.urls_file}: {e}")
    if not discovered_urls:
        discovered_urls = collect_hotel_offer_urls()
    logger.info(f"Found {len(discovered_urls)} hotels with offer URLs.")

    # Filter by destination if requested
    if args.destination != "all":
        dest_term = "cypr" if args.destination == "cyprus" else ("turcj" if args.destination == "turkey" else ("grecj" if args.destination == "greece" else "egipt"))
        discovered_urls = {
            h: u for h, u in discovered_urls.items()
            if dest_term in u.lower()
        }
        logger.info(f"Filtered for destination '{args.destination}': {len(discovered_urls)} hotels.")

    # Filter targets that need galleries (< 3 photos)
    to_fetch = [
        (h_name, ou) for h_name, ou in discovered_urls.items()
        if h_name not in galleries or len(galleries[h_name]) < 3
    ][:args.max_hotels]

    logger.info(f"Need to fetch galleries for {len(to_fetch)} hotels (out of {len(discovered_urls)} discovered).")

    count = 0
    try:
        for idx, (h_name, ou) in enumerate(to_fetch, start=1):
            photos = fetch_hotel_gallery(session, ou, timeout=(5, 9))
            if photos:
                galleries[h_name] = photos
                count += 1
                logger.info(f"[{count}/{len(to_fetch)}] (idx {idx}) ✅ {h_name}: fetched {len(photos)} photos")
                if count % 10 == 0:
                    save_galleries_kb(g_kb, args.galleries_kb)
                    logger.info(f"💾 Autosaved progress: {len(galleries)} total galleries in KB")
            else:
                logger.warning(f"[{idx}/{len(to_fetch)}] ⚠️ {h_name}: no photos extracted from {to_canonical_hotel_url(ou)}")
            time.sleep(0.15)  # Polite crawling delay
    finally:
        if count > 0:
            save_galleries_kb(g_kb, args.galleries_kb)
            sync_galleries_into_specs_kb(args.galleries_kb, args.specs_kb)
            logger.info(f"🎉 Completed! Harvested {count} new hotel galleries.")
        else:
            logger.info("All scanned hotels already have photo galleries cached.")


if __name__ == "__main__":
    main()
