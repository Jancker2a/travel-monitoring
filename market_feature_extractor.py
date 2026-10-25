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

BUCKET_CONFIG: Dict[str, Tuple[str, int, int]] = {
    "last_minute": ("D-1…D-3", 1, 3),
    "panic_dump": ("D-4…D-7", 4, 7),
    "first_markdown": ("D-8…D-14", 8, 14),
    "mid_term": ("D-15…D-30", 15, 30),
    "early_bird": ("D-30+", 31, 180),
    # Display label aliases
    "D-1…D-3": ("D-1…D-3", 1, 3),
    "D-1...D-3": ("D-1…D-3", 1, 3),
    "D-4…D-7": ("D-4…D-7", 4, 7),
    "D-4...D-7": ("D-4…D-7", 4, 7),
    "D-8…D-14": ("D-8…D-14", 8, 14),
    "D-8...D-14": ("D-8…D-14", 8, 14),
    "D-15…D-30": ("D-15…D-30", 15, 30),
    "D-15...D-30": ("D-15…D-30", 15, 30),
    "D-30+": ("D-30+", 31, 180),
}


def infer_stars(hotel_name: str, row: pd.Series, dna: Optional[Dict[str, Any]] = None) -> int:
    """Infers hotel star rating (3, 4, 5). Defaults to 5 if luxury brand, else 4."""
    for col in ("stars", "hotel_stars", "star_rating"):
        if col in row and pd.notna(row[col]):
            try:
                s = int(float(row[col]))
                if s in (3, 4, 5):
                    return s
            except (ValueError, TypeError):
                pass
    h_lower = hotel_name.lower()
    m = re.search(r"(\d)\s*(?:\*|★|star)", h_lower)
    if m:
        s = int(m.group(1))
        if s in (3, 4, 5):
            return s
    if dna and "stars" in dna:
        try:
            return int(dna["stars"])
        except (ValueError, TypeError):
            pass
    luxury_chains = [
        "rixos", "baron", "four seasons", "kempinski", "albatros", "steigenberger",
        "hilton", "marriott", "sheraton", "movenpick", "jaz", "concorde", "sentido",
        "delphin", "voyage", "maxx royal", "titanic", "gural", "crystal"
    ]
    if any(c in h_lower for c in luxury_chains):
        return 5
    return 4


def resolve_booking_window(
    h_dna: Optional[Dict[str, Any]],
    d_days: Optional[int],
    cur_p: Optional[float] = None,
) -> Dict[str, str]:
    """Computes hotel-specific optimal booking window based on historical D-Minus yield curve."""
    default_res = {
        "optimal_window": "D-14…D-21",
        "window_status": "unknown",
        "window_badge": "",
        "window_class": "early",
        "window_tip": "Историческое окно максимальной выгоды для этого типа отелей наступает за 14–21 день до вылета.",
    }
    best_bucket = None
    if h_dna:
        if h_dna.get("sweet_spot_d_bucket") in BUCKET_CONFIG:
            best_bucket = h_dna.get("sweet_spot_d_bucket")
        elif "d_bucket_medians" in h_dna:
            b_medians = {k: v for k, v in h_dna.get("d_bucket_medians", {}).items() if v > 0 and k in BUCKET_CONFIG}
            if b_medians:
                best_bucket = min(b_medians.items(), key=lambda x: x[1])[0]

    if not best_bucket or best_bucket not in BUCKET_CONFIG:
        return default_res

    w_label, w_min, w_max = BUCKET_CONFIG[best_bucket]
    hist_med = float(h_dna.get("median_price", 0.0)) if h_dna else 0.0

    if d_days is None:
        return {
            "optimal_window": w_label,
            "window_status": "unknown",
            "window_badge": "",
            "window_class": "early",
            "window_tip": f"Исторический минимум цены для этого отеля достигается за {w_label}.",
        }

    if w_min <= d_days <= w_max:
        # Rule of Silence: Only award "🎯 Окно покупки" if the price is actually good (not overpriced or ordinary!)
        # The price must be noticeably below historical median (at least 2% below median)
        if cur_p is not None and hist_med > 0 and cur_p > (hist_med * 0.98):
            return {
                "optimal_window": w_label,
                "window_status": "in_window_normal",
                "window_badge": "",
                "window_class": "in_window",
                "window_tip": f"Период {w_label} исторически благоприятен для покупки, но сейчас отель продаётся по обычной цене ({cur_p:,.0f} zł при норме {hist_med:,.0f} zł).",
            }
        return {
            "optimal_window": w_label,
            "window_status": "in_window",
            "window_badge": f"🎯 Окно покупки: {w_label} (сейчас!)",
            "window_class": "in_window",
            "window_tip": f"Текущий момент (D-{d_days}) совпадает со скидочным окном ({w_label}), и цена снижена относительно нормы ({cur_p:,.0f} zł при медиане {hist_med:,.0f} zł).",
        }
    elif d_days > w_max:
        return {
            "optimal_window": w_label,
            "window_status": "early",
            "window_badge": "",
            "window_class": "early",
            "window_tip": f"Историческое дно цены наступает за {w_label}. Сейчас D-{d_days} (рано).",
        }
    else:
        return {
            "optimal_window": w_label,
            "window_status": "late",
            "window_badge": "",
            "window_class": "late",
            "window_tip": f"Окно максимальных скидок ({w_label}) уже прошло. Текущий день: D-{d_days}.",
        }


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

    # Calculate Days-to-Departure (D-Minus) timeline & horizon
    d_values: List[int] = []
    dep_dates: List[date] = []
    d_buckets_count: Dict[str, int] = {}
    today = date.today()

    for _, row in latest_per_hotel.iterrows():
        dep_d = parse_departure_date(str(row.get("dates", "")))
        if dep_d:
            d = (dep_d - today).days
            if d >= 0:
                d_values.append(d)
                dep_dates.append(dep_d)
                b = get_d_bucket(d)
                d_buckets_count[b] = d_buckets_count.get(b, 0) + 1

    min_d = int(np.min(d_values)) if d_values else 14
    max_d = int(np.max(d_values)) if d_values else 14
    avg_d = int(np.median(d_values)) if d_values else 14
    span_d = max(0, max_d - min_d)
    is_wide_window = span_d >= 7

    nearest_dep = min(dep_dates).strftime("%d.%m") if dep_dates else ""
    furthest_dep = max(dep_dates).strftime("%d.%m") if dep_dates else ""

    dominant_phase = max(d_buckets_count.items(), key=lambda x: x[1])[0] if d_buckets_count else "mid_term"

    # 1. Pre-calculate star clusters, price tiers, and ratings (Peer Group Benchmarking)
    hotel_stars_map: Dict[str, int] = {}
    hotel_ratings_map: Dict[str, float] = {}
    hotel_tier_map: Dict[str, str] = {}
    star_prices_map: Dict[int, List[float]] = {4: [], 5: []}
    peer_cohort_prices: Dict[Tuple[int, str], List[float]] = {}

    if len(prices) >= 6:
        tier_p33 = float(np.percentile(prices, 33.3))
        tier_p67 = float(np.percentile(prices, 66.7))
    elif len(prices) > 0:
        tier_p33 = float(np.percentile(prices, 50.0))
        tier_p67 = float(np.percentile(prices, 50.0))
    else:
        tier_p33 = 0.0
        tier_p67 = 0.0

    for _, row in latest_per_hotel.iterrows():
        hn = str(row["hotel_name"])
        p = float(row["price"])
        st = infer_stars(hn, row, dna_hotels.get(hn))
        hotel_stars_map[hn] = st
        star_prices_map.setdefault(st, []).append(p)

        # Classify hotel into comparable price tier
        if p <= tier_p33:
            tier_name = "эконом"
        elif p <= tier_p67:
            tier_name = "комфорт"
        else:
            tier_name = "премиум"
        hotel_tier_map[hn] = tier_name
        peer_cohort_prices.setdefault((st, tier_name), []).append(p)

        r_val = 0.0
        for r_col in ("ta_rating", "rating", "hotel_rating"):
            if r_col in row and pd.notna(row[r_col]):
                try:
                    r_val = float(str(row[r_col]).replace(",", "."))
                    if r_val > 5.0:  # normalize 10-scale to 5
                        r_val = round(r_val / 2.0, 1)
                    break
                except (ValueError, TypeError):
                    pass
        hotel_ratings_map[hn] = r_val

    # Peer cohort medians (comparing only with roughly equal hotels)
    peer_medians: Dict[Tuple[int, str], float] = {
        k: float(np.median(plist)) for k, plist in peer_cohort_prices.items() if plist
    }
    cluster_medians: Dict[int, float] = {
        st: float(np.median(plist)) if plist else med_price
        for st, plist in star_prices_map.items()
    }

    # 2. Identify Floor Breakers, Flash Drops, Gems, Dupes & Hotel Intelligence
    floor_breakers: List[Dict[str, Any]] = []
    flash_drops: List[Dict[str, Any]] = []
    gems: List[Dict[str, Any]] = []
    active_candidates: List[Dict[str, Any]] = []
    all_hotel_intelligence: Dict[str, Dict[str, Any]] = {}

    # Temporary storage for second-pass dupe finding
    hotel_records_list: List[Dict[str, Any]] = []

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

        # Departure days for this hotel
        h_dep_d = parse_departure_date(str(row.get("dates", "")))
        h_d_days = (h_dep_d - today).days if h_dep_d else None

        # Feature 1: Optimal Booking Window
        bw_res = resolve_booking_window(h_dna, h_d_days, cur_p)

        # Feature 2: Fair Price Index & Peer Cohort Benchmarking
        st = hotel_stars_map.get(h_name, 4)
        tier_name = hotel_tier_map.get(h_name, "комфорт")

        # Benchmark strictly against comparable peer cohort (same stars AND same price tier)
        peer_med = peer_medians.get((st, tier_name))
        if not peer_med:
            plist = star_prices_map.get(st, prices)
            peer_med = float(np.median(plist)) if len(plist) > 0 else med_price

        fair_delta_pct = ((cur_p - peer_med) / max(1.0, peer_med)) * 100.0

        # Self-benchmarking sanity checks:
        # A hotel can ONLY be considered underpriced/bargain if:
        # 1. It is below peer cohort median (fair_delta_pct <= -10.0%)
        # 2. AND it is NOT selling above its own historical median (cur_p <= hist_med * 1.02)
        # 3. AND it has a decent rating (r_val >= 3.8 or unrated)
        is_truly_underpriced = (
            fair_delta_pct <= -10.0
            and cur_p <= (hist_med * 1.02)
            and (r_val >= 3.8 or r_val == 0.0)
        )

        is_overpriced = (
            fair_delta_pct >= 20.0
            or cur_p >= (hist_med * 1.15)
        )

        if is_truly_underpriced:
            fair_badge = f"🔥 −{abs(fair_delta_pct):.0f}% в {tier_name} {st}★"
            fair_class = "fair-underpriced"
            fair_tip = (
                f"Цена на {abs(fair_delta_pct):.0f}% ниже медианы равных отелей сегмента "
                f"{tier_name} {st}★ ({peer_med:,.0f} zł) и не превышает обычную цену отеля ({hist_med:,.0f} zł)."
            )
        elif is_overpriced:
            fair_badge = f"⚠️ +{fair_delta_pct:.0f}% к {tier_name} {st}★" if fair_delta_pct >= 15.0 else "⚠️ Дороже обычного"
            fair_class = "fair-overpriced"
            fair_tip = (
                f"Цена на {fair_delta_pct:+.0f}% отличается от сопоставимых отелей сегмента "
                f"{tier_name} {st}★ ({peer_med:,.0f} zł) или превышает историческую норму отеля ({hist_med:,.0f} zł)."
            )
        else:
            fair_badge, fair_class, fair_tip = "", "", ""

        # Feature 3: Hidden Gem
        # A true gem is a high quality hotel (rating >= 4.4) priced in the economy or lower comfort tier
        is_gem = (
            r_val >= 4.4
            and cur_p <= (tier_p33 * 1.08)
            and cur_p <= (hist_med * 1.03)
        )
        gem_badge = "💎 Скрытая жемчужина" if is_gem else ""
        gem_tip = f"Высокий рейтинг ({r_val:g}★) при цене в бюджетном сегменте {st}★ ({cur_p:,.0f} zł)." if is_gem else ""

        if is_gem:
            gems.append({
                "hotel_name": h_name,
                "price": cur_p,
                "rating": r_val,
                "stars": st,
            })

        # Feature 4: Glitch & Flash Drop Radar
        is_flash = False
        flash_badge = ""
        flash_tip = ""
        if hist_min > 0 and cur_p <= (hist_min * 0.85):
            drop_below = ((hist_min - cur_p) / hist_min) * 100.0
            is_flash = True
            flash_badge = f"⚡ FLASH DROP (−{drop_below:.0f}%)"
            flash_tip = f"Аномалия: цена пробила исторический минимум на {drop_below:.0f}% ({hist_min:,.0f} zł → {cur_p:,.0f} zł)!"
            flash_drops.append({
                "hotel_name": h_name,
                "current_price": cur_p,
                "historical_min": hist_min,
                "drop_pct": round(drop_below, 1),
            })

        cand_info = {
            "hotel_name": h_name,
            "current_price": cur_p,
            "historical_min": hist_min,
            "historical_median": hist_med,
            "quantile_in_filter": round(cur_rank, 2),
            "archetype": archetype,
            "stars": st,
            "rating": r_val,
            "dates": str(row.get("dates", "")),
            "duration": str(row.get("duration", "")),
            "offer_url": str(row.get("offer_url") or row.get("url") or ""),
            "booking_window": bw_res,
            "fair_price": {
                "delta_pct": round(fair_delta_pct, 1),
                "badge": fair_badge,
                "class": fair_class,
                "tip": fair_tip,
                "tier": tier_name,
                "cluster_median": round(peer_med, 0),
            },
            "gem": {
                "is_gem": is_gem,
                "badge": gem_badge,
                "tip": gem_tip,
            },
            "flash_drop": {
                "is_flash": is_flash,
                "badge": flash_badge,
                "tip": flash_tip,
            },
            "dupe_suggestion": None,
        }

        if is_floor:
            floor_breakers.append(cand_info)

        has_buy_catalyst = (
            (is_floor and cur_p <= hist_med * 0.98)
            or is_flash
            or is_gem
            or (is_truly_underpriced and r_val >= 4.2)
        )
        # Low rating (< 4.0) hotels should NEVER be candidates for buy recommendations
        if has_buy_catalyst and (r_val >= 4.0 or r_val == 0.0):
            active_candidates.append(cand_info)

        hotel_records_list.append(cand_info)

    # 3. Second pass: AI Dupe (Двойник / Альтернатива) Matching for expensive hotels
    for cand in hotel_records_list:
        cur_p = cand["current_price"]
        st = cand["stars"]
        tier_name = cand["fair_price"].get("tier", "комфорт")
        peer_med = peer_medians.get((st, tier_name), med_price)
        r_val = cand["rating"]

        # Only search dupes for hotels with premium pricing or elevated prices
        if cur_p >= 5000.0 and (cur_p >= (peer_med * 1.20) or cur_p >= (cand["historical_median"] * 1.15)):
            dupe_candidates = [
                other for other in hotel_records_list
                if other["hotel_name"] != cand["hotel_name"]
                and other["current_price"] <= (cur_p - 1000.0)
                and other["rating"] >= max(4.3, r_val - 0.2)
            ]
            if dupe_candidates:
                # Pick dupe with same star tier if possible, then highest rating, then lowest price
                dupe_candidates.sort(key=lambda x: (abs(x["stars"] - st), -x["rating"], x["current_price"]))
                best_dupe = dupe_candidates[0]
                cand["dupe_suggestion"] = {
                    "hotel_name": best_dupe["hotel_name"],
                    "price": best_dupe["current_price"],
                    "savings": round(cur_p - best_dupe["current_price"], 0),
                    "savings_pln": round(cur_p - best_dupe["current_price"], 0),
                    "rating": best_dupe["rating"],
                    "offer_url": best_dupe["offer_url"],
                }

        all_hotel_intelligence[cand["hotel_name"]] = cand

    # Balanced selection for AI prompt across price tiers:
    # Ensures AI sees worthy candidates in economy, comfort, and premium segments (not just bottom 12 cheapest!)
    tier_candidates: Dict[str, List[Dict[str, Any]]] = {"эконом": [], "комфорт": [], "премиум": []}
    for c in active_candidates:
        tier = c["fair_price"].get("tier", "комфорт")
        tier_candidates.setdefault(tier, []).append(c)

    selected_for_ai = []
    # Take up to 4 best deals from each tier (sorted by highest rating and biggest discount)
    for tier in ("премиум", "комфорт", "эконом"):
        t_list = tier_candidates.get(tier, [])
        t_list.sort(key=lambda x: (-x["rating"], x["fair_price"].get("delta_pct", 0), x["current_price"]))
        selected_for_ai.extend(t_list[:4])

    if not selected_for_ai:
        selected_for_ai = hotel_records_list[:12]

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
            "min_days_to_departure": min_d,
            "max_days_to_departure": max_d,
            "departure_span_days": span_d,
            "is_wide_window": is_wide_window,
            "nearest_departure_date": nearest_dep,
            "furthest_departure_date": furthest_dep,
            "dominant_yield_phase": dominant_phase,
            "phase_distribution": d_buckets_count,
            "near_term_count": len([d for d in d_values if d <= 7]),
            "mid_term_count": len([d for d in d_values if 8 <= d <= 21]),
            "far_term_count": len([d for d in d_values if d >= 22]),
        },
        "floor_saturation": {
            "floor_breaker_count": len(floor_breakers),
            "floor_breaker_pct": round((len(floor_breakers) / max(1, len(latest_per_hotel))) * 100.0, 1),
            "sample_floor_hotels": [f["hotel_name"] for f in floor_breakers[:6]],
        },
        "arbitrage_highlights": arbitrage_summary,
        "selected_hotel_dossiers": selected_for_ai,
        "all_hotel_intelligence": all_hotel_intelligence,
        "gems": gems,
        "flash_drops": flash_drops,
        "cluster_medians": cluster_medians,
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
