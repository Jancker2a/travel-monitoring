#!/usr/bin/env python3
"""
auto_enrich_delta.py — Autonomous Delta Detector and Incremental KB Enricher.

Designed to run on CI before dashboard generation:
1. Scans all active travel_prices.csv files for hotels.
2. Identifies unindexed hotels (delta between CSVs and hotel_specs_kb.json).
3. If delta is 0, terminates instantly (0.1s).
4. If new hotels are found:
   - Enriches them via LLM (Gemini / OpenAI) using hotel_specs enricher.
   - Automatically validates schema, cleanses boilerplate, and compiles complete Passports.
   - Saves hotel_specs_kb.json for immediate use by dashboards and subsequent CI commit.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import logging
import os
import sys
from typing import Dict, List, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("auto_enrich_delta")

DEFAULT_SPECS_KB = "hotel_specs_kb.json"
DEFAULT_DATA_PATTERN = "data/filters/**/travel_prices.csv"


def discover_hotels_from_csvs() -> Dict[str, Dict[str, Any]]:
    """Scans all CSV files and extracts unique hotel names with inferred metadata."""
    discovered: Dict[str, Dict[str, Any]] = {}
    csv_paths = glob.glob(DEFAULT_DATA_PATTERN, recursive=True)
    if os.path.exists("data/travel_prices.csv"):
        csv_paths.append("data/travel_prices.csv")

    for path in csv_paths:
        try:
            with open(path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("hotel_name", "").strip()
                    if not name or len(name) < 3:
                        continue

                    if name not in discovered:
                        # Determine destination/country
                        country = row.get("country", "").strip()
                        region = row.get("region", "").strip()
                        dest = country or ("Египет" if "ш-э-ш" in region.lower() or "хургада" in region.lower() else "Турция")
                        
                        stars = 4
                        try:
                            s_val = row.get("stars", "")
                            if s_val and s_val.isdigit():
                                stars = int(s_val)
                        except Exception:
                            pass

                        discovered[name] = {
                            "hotel_name": name,
                            "destination": dest,
                            "stars": stars,
                            "sample_price": row.get("price", "0"),
                        }
        except Exception as e:
            logger.debug(f"Could not read {path}: {e}")

    return discovered


def main():
    parser = argparse.ArgumentParser(description="Auto-enrich new hotels into Knowledge Base")
    parser.add_argument("--specs-kb", default=DEFAULT_SPECS_KB, help="Path to hotel_specs_kb.json")
    parser.add_argument("--dry-run", action="store_true", help="Report delta without making API calls")
    parser.add_argument("--max-batch", type=int, default=25, help="Maximum new hotels to enrich per CI run")
    args = parser.parse_args()

    if not os.path.exists(args.specs_kb):
        logger.warning(f"KB file {args.specs_kb} not found. Exiting.")
        sys.exit(0)

    try:
        with open(args.specs_kb, "r", encoding="utf-8") as f:
            kb = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {args.specs_kb}: {e}")
        sys.exit(0)

    hotels_in_kb = kb.get("hotels", kb)
    discovered = discover_hotels_from_csvs()
    logger.info(f"Discovered {len(discovered)} unique hotels across active CSV files. KB contains {len(hotels_in_kb)} hotels.")

    # Find delta (hotels in CSV that are not enriched in KB)
    unindexed = []
    for name, item in discovered.items():
        if name not in hotels_in_kb or not hotels_in_kb[name].get("is_enriched"):
            unindexed.append(item)

    if not unindexed:
        logger.info("✅ All hotels from scrape data are already 100% enriched in Knowledge Base. Nothing to do.")
        sys.exit(0)

    logger.info(f"🔍 Discovered {len(unindexed)} unindexed/new hotels needing enrichment: {[u['hotel_name'] for u in unindexed[:10]]}")

    if args.dry_run:
        logger.info("Dry-run mode: skipping enrichment.")
        sys.exit(0)

    # Check for API keys
    has_api = bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if not has_api:
        logger.warning("No GEMINI_API_KEY or OPENAI_API_KEY found in environment. Relying on fallback drawer generation.")
        sys.exit(0)

    # Invoke enrichment pipeline for the delta batch
    try:
        from scripts.enrich_hotel_specs import enrich_hotel_specs_kb
    except ImportError:
        try:
            from enrich_hotel_specs import enrich_hotel_specs_kb
        except ImportError:
            logger.error("Could not import enrich_hotel_specs_kb.")
            sys.exit(0)

    batch_to_enrich = unindexed[:args.max_batch]
    logger.info(f"🚀 Enriching {len(batch_to_enrich)} new hotels via LLM pipeline...")
    try:
        enrich_hotel_specs_kb(
            hotel_list=batch_to_enrich,
            specs_path=args.specs_kb,
            max_hotels=len(batch_to_enrich),
            force=False,
            dry_run=False
        )
        logger.info(f"✅ Auto-enrichment successful. Updated {len(batch_to_enrich)} hotel passports in {args.specs_kb}.")
    except Exception as e:
        logger.warning(f"Auto-enrichment step encountered an error: {e}. Non-critical, proceeding.")

    # Synchronize photo galleries into specs KB if available
    try:
        from scripts.fetch_hotel_galleries import sync_galleries_into_specs_kb
        sync_galleries_into_specs_kb(specs_kb_path=args.specs_kb)
    except Exception as e:
        logger.debug(f"Gallery sync skipped: {e}")


if __name__ == "__main__":
    main()

