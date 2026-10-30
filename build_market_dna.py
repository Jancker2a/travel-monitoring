#!/usr/bin/env python3
"""
Market DNA Profiler: Historical Baseline & Behavioral Archetype Synthesizer.

Performs deep analysis over accumulated historical scrapes:
1. Hotel-level profiling: quantiles, price decay by days-to-departure (D-Minus), volatility.
2. Behavioral Archetype classification:
   - LATE_DUMPER: Significant price drop (>8%) during charter clearance (D <= 14).
   - ROCK_SOLID: Extremely stable pricing (<4% volatility), high sold-out risk.
   - VOLATILE: High frequency swings (>12% volatility).
   - BALANCED: Standard seasonal yield pricing.
3. Destination-level macro yield curves and operator strategy profiling.
4. Outputs `market_dna_profile.json` as permanent long-term memory for daily AI runs.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import math
import os
import re
import functools
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("market_dna")

DEFAULT_OUTPUT_FILE = "market_dna_profile.json"


@functools.lru_cache(maxsize=50000)
def parse_departure_date(
    dates_str: Any,
    offer_url: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> Optional[date]:
    """
    Extracts first departure date from:
    - offer_url parameter 'departureDate=YYYY-MM-DD'
    - ISO '2026-06-01'
    - '28.12.2026 - 06.01.2027' or '28-12-2026' or '28/12/2026'
    - '28.12 - 06.01.2027' (year only at the end)
    - '28.12 - 06.01' or '28.12' (inferred year based on reference_date or date.today())
    - strings with duration parentheses like '28.12 - 06.01 (8 dni)'
    """
    # 1. From offer_url departureDate query param
    if offer_url and isinstance(offer_url, str):
        m_url = re.search(r"[?&]departureDate=(\d{4}-\d{2}-\d{2})", offer_url)
        if m_url:
            try:
                y, mon, d = m_url.group(1).split("-")
                return date(int(y), int(mon), int(d))
            except (ValueError, TypeError):
                pass

    if not dates_str or not isinstance(dates_str, str):
        return None

    text = re.sub(r"\s*\([^)]*\)", "", str(dates_str)).strip()

    # 2. ISO 'YYYY-MM-DD'
    m_iso = re.search(r"(\d{4})[./-](\d{2})[./-](\d{2})", text)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass

    # 3. Full dates 'DD.MM.YYYY' (or 'DD.MM.YYYY - ...')
    m_full = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if m_full:
        try:
            return date(int(m_full.group(3)), int(m_full.group(2)), int(m_full.group(1)))
        except ValueError:
            pass

    # 4. Short start with year at the end 'DD.MM - DD.MM.YYYY'
    m_tail = re.search(r"(\d{1,2})[./-](\d{1,2})\s*-\s*\d{1,2}[./-]\d{1,2}[./-](\d{4})", text)
    if m_tail:
        try:
            return date(int(m_tail.group(3)), int(m_tail.group(2)), int(m_tail.group(1)))
        except ValueError:
            pass

    # 5. Short dates 'DD.MM - DD.MM' or 'DD.MM' (no year)
    m_short = re.search(r"(\d{1,2})[./-](\d{1,2})", text)
    if m_short:
        try:
            d_val = int(m_short.group(1))
            m_val = int(m_short.group(2))
            ref = reference_date or date.today()
            year = ref.year
            # If departure month is earlier than reference month by > 1, it's next year
            if m_val < ref.month - 1:
                year += 1
            return date(year, m_val, d_val)
        except ValueError:
            pass

    return None


@functools.lru_cache(maxsize=50000)
def parse_scraped_date(scraped_at_val: Any) -> Optional[date]:
    """Parses scraped_at timestamp to date."""
    if not scraped_at_val:
        return None
    s = str(scraped_at_val).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


@functools.lru_cache(maxsize=50000)
def extract_operator_from_url(url: Any) -> Optional[str]:
    """Extracts operator code from offer_url (e.g. operator=OREX, operator=CORAL)."""
    if not url or not isinstance(url, str):
        return None
    m = re.search(r"operator=([^&]+)", url, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


@functools.lru_cache(maxsize=500)
def get_d_bucket(days: Optional[int]) -> str:
    """Classifies days-to-departure into yield management phases."""
    if days is None:
        return "unknown"
    if days <= 3:
        return "last_minute"
    if days <= 7:
        return "panic_dump"
    if days <= 14:
        return "first_markdown"
    if days <= 30:
        return "mid_term"
    return "early_bird"


@dataclass
class HotelDNA:
    hotel_name: str
    sample_count: int
    min_price: float
    p10_price: float
    median_price: float
    p90_price: float
    max_price: float
    volatility_pct: float
    d_bucket_medians: Dict[str, float]
    d_dump_drop_pct: float
    archetype: str  # 'LATE_DUMPER', 'ROCK_SOLID', 'VOLATILE', 'BALANCED'
    primary_operator: Optional[str]
    known_operators: List[str]


def analyze_hotel_group(name: str, group: pd.DataFrame) -> Optional[HotelDNA]:
    prices = group["price"].dropna().astype(float).values
    if len(prices) < 2:
        return None

    min_p = float(np.min(prices))
    max_p = float(np.max(prices))
    med_p = float(np.median(prices))
    p10_p = float(np.percentile(prices, 10))
    p90_p = float(np.percentile(prices, 90))

    std_p = float(np.std(prices))
    volatility_pct = round((std_p / max(1.0, med_p)) * 100.0, 1)

    # D-Minus analysis
    bucket_medians: Dict[str, float] = {}
    for b_name, b_df in group.groupby("d_bucket"):
        if b_name != "unknown" and len(b_df) > 0:
            bucket_medians[str(b_name)] = round(float(b_df["price"].median()), 1)

    # Calculate dump drop percentage (early_bird/mid_term vs panic_dump/last_minute)
    early_p = bucket_medians.get("early_bird") or bucket_medians.get("mid_term") or med_p
    late_p = bucket_medians.get("panic_dump") or bucket_medians.get("first_markdown") or med_p
    d_dump_drop_pct = round(((early_p - late_p) / max(1.0, early_p)) * 100.0, 1)

    # Archetype classification
    if d_dump_drop_pct >= 8.0:
        archetype = "LATE_DUMPER"
    elif volatility_pct < 4.5 and d_dump_drop_pct <= 2.0:
        archetype = "ROCK_SOLID"
    elif volatility_pct >= 12.0:
        archetype = "VOLATILE"
    else:
        archetype = "BALANCED"

    # Operators
    operators = [o for o in group["operator"].dropna().tolist() if o]
    known_ops = sorted(list(set(operators)))
    primary_op = pd.Series(operators).mode().iloc[0] if operators else None

    return HotelDNA(
        hotel_name=name,
        sample_count=len(prices),
        min_price=min_p,
        p10_price=p10_p,
        median_price=med_p,
        p90_price=p90_p,
        max_price=max_p,
        volatility_pct=volatility_pct,
        d_bucket_medians=bucket_medians,
        d_dump_drop_pct=d_dump_drop_pct,
        archetype=archetype,
        primary_operator=primary_op,
        known_operators=known_ops,
    )


def build_market_dna(data_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Scans historical CSV files and compiles Market DNA."""
    if not data_dirs:
        # Prioritize cumulative filter files (data/filters) to avoid scanning hundreds of raw run snapshots in data_runs
        if os.path.exists("data/filters") and glob.glob("data/filters/**/*.csv", recursive=True):
            data_dirs = ["data/filters"]
        else:
            data_dirs = ["data_runs", "data/filters"]

    csv_files: List[str] = []
    for d in data_dirs:
        if os.path.exists(d):
            csv_files.extend(glob.glob(f"{d}/**/*.csv", recursive=True))

    # Exclude cohorts or metadata csvs, only keep raw price files
    valid_csvs = [
        f for f in csv_files
        if not f.endswith("_cohorts.csv")
        and not f.endswith("departure_cohorts.csv")
        and not "check24" in f.lower()
        and not "germany" in f.lower()
    ]

    logger.info(f"Found {len(valid_csvs)} raw price CSV files across historical runs.")

    all_dfs: List[pd.DataFrame] = []
    for f in valid_csvs:
        try:
            df = pd.read_csv(f)
            if "hotel_name" in df.columns and "price" in df.columns:
                all_dfs.append(df)
        except Exception as e:
            logger.warning(f"Error reading {f}: {e}")

    if not all_dfs:
        logger.error("No valid hotel price data found to build Market DNA.")
        return {}

    combined = pd.concat(all_dfs, ignore_index=True).drop_duplicates()
    logger.info(f"Combined historical database has {len(combined)} records.")

    # Clean prices
    combined["price"] = pd.to_numeric(combined["price"], errors="coerce")
    combined = combined.dropna(subset=["price", "hotel_name"])
    combined = combined[combined["price"] >= 1000.0]

    # Calculate D-Minus (high-performance batch parsing with lru_cache)
    dates_arr = combined["dates"].fillna("").astype(str).values
    scraped_arr = combined["scraped_at"].fillna("").astype(str).values
    url_arr = (combined.get("offer_url", pd.Series("", index=combined.index)).fillna("").astype(str) + "&" +
               combined.get("url", pd.Series("", index=combined.index)).fillna("").astype(str)).values

    dep_dates = [parse_departure_date(d) for d in dates_arr]
    today = date.today()
    scr_dates = [parse_scraped_date(s) or today for s in scraped_arr]

    d_days: List[Optional[int]] = []
    d_buckets: List[str] = []
    for dep_d, scr_d in zip(dep_dates, scr_dates):
        if dep_d and scr_d:
            delta = (dep_d - scr_d).days
            d_days.append(delta)
            d_buckets.append(get_d_bucket(delta))
        else:
            d_days.append(None)
            d_buckets.append("unknown")

    operators = [extract_operator_from_url(u) for u in url_arr]

    combined["d_minus"] = d_days
    combined["d_bucket"] = d_buckets
    combined["operator"] = operators

    # Hotel level profiling
    hotel_profiles: Dict[str, Dict[str, Any]] = {}
    archetype_counts: Dict[str, int] = {
        "LATE_DUMPER": 0,
        "ROCK_SOLID": 0,
        "VOLATILE": 0,
        "BALANCED": 0,
    }

    for hotel_name, group in combined.groupby("hotel_name"):
        dna = analyze_hotel_group(str(hotel_name), group)
        if dna:
            hotel_profiles[dna.hotel_name] = asdict(dna)
            archetype_counts[dna.archetype] = archetype_counts.get(dna.archetype, 0) + 1

    logger.info(f"Analyzed {len(hotel_profiles)} distinct hotels. Archetype distribution: {archetype_counts}")

    # Destination & Macro level metrics
    overall_prices = combined["price"].values
    macro_profile = {
        "total_records_analyzed": len(combined),
        "total_unique_hotels": len(hotel_profiles),
        "archetype_distribution": archetype_counts,
        "market_price_quantiles": {
            "p10": float(np.percentile(overall_prices, 10)),
            "p25": float(np.percentile(overall_prices, 25)),
            "median": float(np.median(overall_prices)),
            "p75": float(np.percentile(overall_prices, 75)),
            "p90": float(np.percentile(overall_prices, 90)),
        },
        "d_minus_yield_curve": {},
        "active_operators": sorted(list(set(combined["operator"].dropna().tolist()))),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    for b_name, b_df in combined.groupby("d_bucket"):
        if b_name != "unknown":
            macro_profile["d_minus_yield_curve"][str(b_name)] = {
                "median_price": float(b_df["price"].median()),
                "sample_count": len(b_df),
            }

    full_dna = {
        "macro_profile": macro_profile,
        "hotel_profiles": hotel_profiles,
    }

    return full_dna


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Market DNA Profile from historical scrapes.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Target JSON profile path")
    args = parser.parse_args()

    dna = build_market_dna()
    if dna:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(dna, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Market DNA successfully generated and saved to {args.output}")
    else:
        logger.error("Failed to build Market DNA.")


if __name__ == "__main__":
    main()
