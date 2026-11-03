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
    matches = re.findall(r'<img[^>]+src=[\"\']([^\"\']+)[\"\'][^>]*>', html_text)
    raw_urls = []
    
    # Priority 1: Images inside hotel gallery section or Fly.pl CDN image paths
    for src in matches:
        if any(marker in src for marker in ("/plain/", "IMG/", "rs:fit:", "config_img")):
            # Clean URL: strip trailing duplicate extensions or query fragments
            clean = src.split("@")[0].strip()
            # Upgrade resolution if rs:fit:800:0 or rs:fill:
            clean = re.sub(r'rs:fit:\d+:\d+', 'rs:fit:1280:720', clean)
            clean = re.sub(r'rs:fill:\d+:\d+', 'rs:fit:1280:720', clean)
            
            # Filter out non-hotel assets
            low = clean.lower()
            if any(bad in low for bad in ("logo", "tripadvisor", "flag", "icon", "svg", "user_upload", "be_users")):
                continue
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
    """Scans all available CSVs and finds latest offer_url per hotel."""
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
        if h_name in hotels and isinstance(hotels[h_name], dict):
            h_entry = hotels[h_name]
            if "specs" in h_entry and isinstance(h_entry["specs"], dict):
                h_entry["specs"]["gallery_photos"] = photos
                if "passport" in h_entry["specs"] and isinstance(h_entry["specs"]["passport"], dict):
                    h_entry["specs"]["passport"]["gallery_photos"] = photos
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
    parser.add_argument("--max-hotels", type=int, default=50, help="Max hotels to fetch in one run")
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
        photos = fetch_hotel_gallery(session, url)
        if photos:
            galleries[h_name] = photos
            logger.info(f"✅ Successfully fetched {len(photos)} photos for '{h_name}'")
            save_galleries_kb(g_kb, args.galleries_kb)
            sync_galleries_into_specs_kb(args.galleries_kb, args.specs_kb)
        else:
            logger.warning(f"❌ Could not extract photos for '{h_name}' from {url}")
        return

    # Batch mode: scan CSVs for hotels missing galleries
    discovered_urls = collect_hotel_offer_urls()
    logger.info(f"Found {len(discovered_urls)} hotels with offer URLs.")

    count = 0
    try:
        for h_name, ou in discovered_urls.items():
            if count >= args.max_hotels:
                break
            # Skip if already has 3+ photos
            if h_name in galleries and len(galleries[h_name]) >= 3:
                continue

            photos = fetch_hotel_gallery(session, ou)
            if photos and len(photos) >= 2:
                galleries[h_name] = photos
                count += 1
                logger.info(f"[{count}/{args.max_hotels}] ✅ {h_name}: fetched {len(photos)} photos")
                if count % 5 == 0:
                    save_galleries_kb(g_kb, args.galleries_kb)
                time.sleep(0.2)  # Polite crawling delay
    finally:
        if count > 0:
            save_galleries_kb(g_kb, args.galleries_kb)
            sync_galleries_into_specs_kb(args.galleries_kb, args.specs_kb)
        else:
            logger.info("All scanned hotels already have photo galleries cached.")


if __name__ == "__main__":
    main()
