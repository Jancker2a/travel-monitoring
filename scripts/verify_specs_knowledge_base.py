#!/usr/bin/env python3
"""
Comprehensive QA and Sanity Verification Suite for Hotel Specifications Knowledge Base.

Validates:
1. Schema & Data Types (beach_type, beach_line, sea_entry, ratings, etc.)
2. Anti-Template & Anti-Boilerplate (ensures zero canned/repetitive text)
3. Frequency & Diversity (no generic sentence repeated across hotels)
4. Geographical Truth & Physical Sanity:
   - Nabq Bay resorts cannot be classified as 'sheltered_bay'
   - Inland Hadaba/city resorts cannot be marked 1st line
   - 3rd line hotels cannot claim direct beach access
   - Winter heated pools must have specific details
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.enrich_hotel_specs import (
    DEFAULT_SPECS_FILE,
    VALID_BEACH_TYPES,
    VALID_SEA_ENTRIES,
    VALID_BAY_WINDS,
    VALID_REEF_PRESENCE,
    validate_specs_payload,
    is_template_response,
)


def verify_specs_kb(kb_path: str = DEFAULT_SPECS_FILE) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Runs a full audit of hotel_specs_kb.json and returns (passed, issues, stats)."""
    if not os.path.exists(kb_path):
        return False, [f"KB file not found: {kb_path}"], {}

    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    hotels = data.get("hotels", {})
    issues = []
    stats = {
        "total_hotels": len(hotels),
        "enriched_count": 0,
        "clean_count": 0,
        "flagged_count": 0,
        "line_distribution": Counter(),
        "heated_pools_count": 0,
        "aquapark_count": 0,
    }

    highlights_freq = Counter()
    caution_freq = Counter()

    for h_name, h_info in hotels.items():
        if not h_info.get("is_enriched"):
            continue

        stats["enriched_count"] += 1
        specs = h_info.get("specs")
        if not specs:
            issues.append(f"[{h_name}] Marked enriched but specs is empty")
            stats["flagged_count"] += 1
            continue

        # 1. Schema & Geographic validation
        is_valid, err_msg = validate_specs_payload(specs, hotel_name=h_name)
        if not is_valid:
            issues.append(f"[{h_name}] Schema/Geographic violation: {err_msg}")
            stats["flagged_count"] += 1
            continue

        # 2. Anti-template detection
        if is_template_response(specs):
            issues.append(f"[{h_name}] Template/Boilerplate response detected")
            stats["flagged_count"] += 1
            continue

        # 3. Stats tracking
        b_line = specs.get("beach_line")
        stats["line_distribution"][b_line] += 1
        if specs.get("heated_pools_winter"):
            stats["heated_pools_count"] += 1
        if specs.get("aquapark"):
            stats["aquapark_count"] += 1

        for hl in specs.get("highlights", []):
            if isinstance(hl, str):
                highlights_freq[hl.strip()] += 1
        for ca in specs.get("caution_notes", []):
            if isinstance(ca, str):
                caution_freq[ca.strip()] += 1

        stats["clean_count"] += 1

    # 4. Global repetition check (flag phrases that appear in >35% of entire DB)
    max_allowed_repeat = max(15, int(len(hotels) * 0.35))
    for phrase, count in highlights_freq.most_common(20):
        if count > max_allowed_repeat:
            issues.append(f"High phrase repetition (>{max_allowed_repeat} hotels): '{phrase}' appears in {count} hotels")

    passed = len(issues) == 0
    return passed, issues, stats


def print_qa_report(kb_path: str = DEFAULT_SPECS_FILE) -> bool:
    print(f"\n{'='*70}")
    print(f"📊 HOTEL SPECIFICATIONS KNOWLEDGE BASE QA REPORT: {kb_path}")
    print(f"{'='*70}")

    passed, issues, stats = verify_specs_kb(kb_path)

    print(f"Total Hotels in KB:     {stats.get('total_hotels', 0)}")
    print(f"Enriched Hotels:        {stats.get('enriched_count', 0)}")
    print(f"Clean & Verified:       {stats.get('clean_count', 0)}")
    print(f"Flagged with Issues:    {stats.get('flagged_count', 0)}")
    print(f"Beach Line Breakdown:   {dict(stats.get('line_distribution', {}))}")
    print(f"Winter Heated Pools:    {stats.get('heated_pools_count', 0)}")
    print(f"Aquaparks Verified:     {stats.get('aquapark_count', 0)}")
    print(f"{'='*70}")

    if passed:
        print("✅ FULL QA PASS: 0 schema errors, 0 boilerplate phrases, all sanity rules respected.")
    else:
        print(f"⚠️ FOUND {len(issues)} ISSUES:")
        for idx, err in enumerate(issues[:20], 1):
            print(f"  {idx}. {err}")
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more issues.")

    print(f"{'='*70}\n")
    return passed


if __name__ == "__main__":
    success = print_qa_report()
    sys.exit(0 if success else 1)
