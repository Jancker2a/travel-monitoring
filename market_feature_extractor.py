#!/usr/bin/env python3
"""
Market Feature Extractor for AI Market Intelligence.

Distills raw filter scrapes, historical Market DNA, and cross-border arbitrage data
into a dense, highly structured JSON context (~2 KB) optimized for LLM synthesis.

Extracts:
1. Macro Filter Snapshot (Phase, Days-to-Departure distribution, 24h price trend).
2. Floor Breakers (Hotels currently trading at or near historical season minimum).
3. Top Price Movers (Highest 24h drops and spikes).
4. Cross-Border Arbitrage Highlights (Poland vs Germany Check24 price delta).
5. Curated Top Candidates for deep individual AI Booking Dossiers.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from build_market_dna import parse_departure_date, parse_scraped_date, get_d_bucket

logger = logging.getLogger("feature_extractor")
DEFAULT_DNA_FILE = "market_dna_profile.json"


def extract_filter_features(
    prices_csv_path: str,
    dna_profile_path: str = DEFAULT_DNA_FILE,
    filter_id: Optional[str] = None,
    filter_title: Optional[str] = None,
    arbitrage_matches: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Extracts structured market features from a filter's travel_prices.csv.
    """
    if not os.path.exists(prices_csv_path):
        raise FileNotFoundError(f"Prices CSV not found: {prices_csv_path}")

    df = pd.read_csv(prices_csv_path)
    if "hotel_name" not in df.columns or "price" not in df.columns:
        raise ValueError(f"Invalid prices CSV structure in {prices_csv_path}")

    # Load DNA profile if present
    dna_hotels: Dict[str, Any] = {}
    macro_dna: Dict[str, Any] = {}
    if os.path.exists(dna_profile_path):
        try:
            with open(dna_profile_path, "r", encoding="utf-8") as f:
                dna_data = json.load(f)
                dna_hotels = dna_data.get("hotel_profiles", {})
                macro_dna = dna_data.get("macro_profile", {})
        except Exception as e:
            logger.warning(f"Could not load DNA profile from {dna_profile_path}: {e}")

    # Filter out invalid / domestic outlier rows (< 1000 PLN)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price", "hotel_name"])
    df = df[df["price"] >= 1000.0]

    if df.empty:
        return {"error": "No valid package tour rows found."}

    # Dedup by hotel_name keeping latest
    latest_per_hotel = df.sort_values(by="scraped_at", ascending=True).groupby("hotel_name").last().reset_index()

    prices = latest_per_hotel["price"].values
    med_price = float(np.median(prices))
    min_price = float(np.min(prices))
    max_price = float(np.max(prices))
    p10_price = float(np.percentile(prices, 10))
    p90_price = float(np.percentile(prices, 90))

    # Calculate Days-to-Departure (D-Minus)
    d_values: List[int] = []
    d_buckets_count: Dict[str, int] = {}
    today = date.today()

    for _, row in latest_per_hotel.iterrows():
        dep_d = parse_departure_date(str(row.get("dates", "")))
        if dep_d:
            d = (dep_d - today).days
            d_values.append(d)
            b = get_d_bucket(d)
            d_buckets_count[b] = d_buckets_count.get(b, 0) + 1

    avg_d = int(np.median(d_values)) if d_values else 14
    dominant_phase = max(d_buckets_count.items(), key=lambda x: x[1])[0] if d_buckets_count else "mid_term"

    # Identify Floor Breakers & Archetype enrichment
    floor_breakers: List[Dict[str, Any]] = []
    active_candidates: List[Dict[str, Any]] = []

    for _, row in latest_per_hotel.iterrows():
        h_name = str(row["hotel_name"])
        cur_p = float(row["price"])
        h_dna = dna_hotels.get(h_name)

        hist_min = cur_p
        hist_med = cur_p
        archetype = "BALANCED"

        if h_dna:
            hist_min = float(h_dna.get("min_price", cur_p))
            hist_med = float(h_dna.get("median_price", cur_p))
            archetype = h_dna.get("archetype", "BALANCED")

        # Is current price within 2.5% of historical minimum?
        is_floor = cur_p <= (hist_min * 1.025)
        # Quantile relative to current filter
        cur_rank = float(np.sum(prices < cur_p)) / max(1, len(prices))

        cand_info = {
            "hotel_name": h_name,
            "current_price": cur_p,
            "historical_min": hist_min,
            "historical_median": hist_med,
            "quantile_in_filter": round(cur_rank, 2),
            "archetype": archetype,
            "dates": str(row.get("dates", "")),
            "duration": str(row.get("duration", "")),
            "rating": str(row.get("rating", "")),
            "offer_url": str(row.get("offer_url") or row.get("url") or ""),
        }

        if is_floor:
            floor_breakers.append(cand_info)

        # Select for active candidate list if interesting
        if is_floor or cur_rank <= 0.15 or archetype == "LATE_DUMPER":
            active_candidates.append(cand_info)

    # Sort active candidates by best value / floor proximity
    active_candidates.sort(key=lambda x: (x["quantile_in_filter"], x["current_price"]))
    selected_for_ai = active_candidates[:12]

    # Process cross-border arbitrage highlights if available
    arbitrage_summary: List[Dict[str, Any]] = []
    if arbitrage_matches:
        for m in arbitrage_matches[:5]:
            arbitrage_summary.append({
                "hotel_name": m.get("hotel_name"),
                "best_deal": m.get("best_deal"),
                "savings_pct": m.get("savings_pct"),
                "spread_pln": m.get("spread_pln"),
                "price_pl": m.get("price_pl"),
                "price_de_pln": m.get("price_de_pln"),
                "airport_de": m.get("airport_de"),
            })

    # Assemble compacted market context
    market_context = {
        "filter_id": filter_id or os.path.basename(os.path.dirname(prices_csv_path)),
        "filter_title": filter_title or "",
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "market_stats": {
            "hotel_count": len(latest_per_hotel),
            "min_price": min_price,
            "p10_price": p10_price,
            "median_price": med_price,
            "p90_price": p90_price,
            "max_price": max_price,
            "median_days_to_departure": avg_d,
            "dominant_yield_phase": dominant_phase,
            "phase_distribution": d_buckets_count,
        },
        "floor_saturation": {
            "floor_breaker_count": len(floor_breakers),
            "floor_breaker_pct": round((len(floor_breakers) / max(1, len(latest_per_hotel))) * 100.0, 1),
            "sample_floor_hotels": [f["hotel_name"] for f in floor_breakers[:6]],
        },
        "arbitrage_highlights": arbitrage_summary,
        "selected_hotel_dossiers": selected_for_ai,
    }

    return market_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract compact market features for AI context.")
    parser.add_argument("--csv", required=True, help="Path to travel_prices.csv")
    parser.add_argument("--dna", default=DEFAULT_DNA_FILE, help="Path to market_dna_profile.json")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    feats = extract_filter_features(args.csv, dna_profile_path=args.dna)
    out_json = json.dumps(feats, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"Features saved to {args.output}")
    else:
        print(out_json)


if __name__ == "__main__":
    main()
