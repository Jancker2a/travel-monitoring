#!/usr/bin/env python3
"""
scripts/sanitize_real_reviews.py — Enforce Zero Synthetic Review Policy.

1. Identifies hotels in hotel_specs_kb.json and hotel_reputation_kb.json with unverified,
   heuristic/round placeholder review counts (e.g., 2100, 1900, 1800, 500, etc.).
2. Preserves all verified, real TripAdvisor review counts (non-round exact counts scraped
   from Fly.pl/TripAdvisor widgets or verified by curators).
3. Sets unverified review counts to 0 so the UI displays truthful badges ("★ 4.2 на TripAdvisor")
   instead of deceptive synthetic numbers.
4. Live scrape filters dynamically provide exact counts via ta_reviews_override.
"""

from __future__ import annotations

import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sanitize_real_reviews")

SPECS_KB_PATH = "hotel_specs_kb.json"
REP_KB_PATH = "hotel_reputation_kb.json"


def sanitize_review_counts():
    if not os.path.exists(SPECS_KB_PATH):
        logger.error(f"{SPECS_KB_PATH} not found.")
        return

    with open(SPECS_KB_PATH, "r", encoding="utf-8") as f:
        specs_data = json.load(f)
    hotels_specs = specs_data.get("hotels", {})

    rep_data = {}
    hotels_rep = {}
    if os.path.exists(REP_KB_PATH):
        with open(REP_KB_PATH, "r", encoding="utf-8") as f:
            rep_data = json.load(f)
            hotels_rep = rep_data.get("hotels", {})

    verified_count = 0
    zeroed_count = 0

    for h_name, h_info in hotels_specs.items():
        specs = h_info.get("specs", {})
        cur_rev = specs.get("tripadvisor_reviews", 0)
        rep_entry = hotels_rep.get(h_name, {})
        rep_rev = rep_entry.get("ta_review_count", 0)

        # Check if verified exact count
        is_verified = False
        exact_val = 0

        # Known verified curators
        if h_name == "Viva Sharm" or cur_rev == 1504 or rep_rev == 1504:
            is_verified = True
            exact_val = 1504
        elif rep_rev > 0 and (rep_rev % 50 != 0 or rep_rev < 100):
            is_verified = True
            exact_val = rep_rev
        elif cur_rev > 0 and (cur_rev % 50 != 0 or cur_rev < 100):
            is_verified = True
            exact_val = cur_rev

        if is_verified:
            specs["tripadvisor_reviews"] = exact_val
            if "passport" in specs and isinstance(specs["passport"], dict):
                specs["passport"]["ta_reviews"] = exact_val
            if rep_entry:
                rep_entry["ta_review_count"] = exact_val
            verified_count += 1
        else:
            # Zero out synthetic placeholder
            specs["tripadvisor_reviews"] = 0
            if "passport" in specs and isinstance(specs["passport"], dict):
                specs["passport"]["ta_reviews"] = 0
            if rep_entry:
                rep_entry["ta_review_count"] = 0
            zeroed_count += 1

    # Save cleaned specs KB
    with open(SPECS_KB_PATH, "w", encoding="utf-8") as f:
        json.dump(specs_data, f, ensure_ascii=False, indent=2)

    # Save cleaned rep KB if present
    if rep_data:
        with open(REP_KB_PATH, "w", encoding="utf-8") as f:
            json.dump(rep_data, f, ensure_ascii=False, indent=2)

    logger.info(
        f"✅ Sanitize complete: {verified_count} verified real review counts preserved, "
        f"{zeroed_count} synthetic counts safely zeroed out."
    )


if __name__ == "__main__":
    sanitize_review_counts()

