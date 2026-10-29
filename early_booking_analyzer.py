#!/usr/bin/env python3
"""Early Booking (First Minute) analysis engine.

Evaluates whether booking early (D > 60-120 days) was economically advantageous
compared to standard (30-60d), late (14-30d) or last-minute (<= 14d) booking.
Implements:
  1. Paired Hotel Cohort Analysis (mitigates survivorship & composition bias).
  2. Sold-out & Survival Rate curve (S(d)).
  3. Early Booking Advantage Score (EBAS).
  4. Normalized price trajectory by D-buckets.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import json
import math
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

try:
    from departure_identity import parse_dates_text, parse_duration
except ImportError:
    # Standalone fallback if invoked outside project root
    def parse_dates_text(value: str) -> tuple[str, str]:
        text = str(value or "").strip()
        match = re.search(
            r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",
            text,
        )
        if match:
            d1, m1, y1, d2, m2, y2 = match.groups()
            return f"{int(y1):04d}-{int(m1):02d}-{int(d1):02d}", f"{int(y2):04d}-{int(m2):02d}-{int(d2):02d}"
        return "", ""

    def parse_duration(value: str) -> tuple[Optional[int], Optional[int]]:
        text = str(value or "").strip()
        m = re.search(r"(\d+)\s*dni", text)
        days = int(m.group(1)) if m else None
        m_n = re.search(r"(\d+)\s*nocy", text)
        nights = int(m_n.group(1)) if m_n else None
        return days, nights


# D-bucket definitions: (bucket_code, min_d_exclusive, max_d_inclusive, human_label)
D_BUCKETS = [
    ("EB", 120, 9999, "Early Bird (>120d)"),
    ("FM", 60, 120, "First Minute (60-120d)"),
    ("STD", 30, 60, "Standard (30-60d)"),
    ("LATE", 14, 30, "Late (14-30d)"),
    ("LM", 7, 14, "Last Minute (7-14d)"),
    ("PANIC", -999, 7, "Panic Dump (≤7d)"),
]

SURVIVAL_CHECKPOINTS = [180, 120, 90, 60, 45, 30, 21, 14, 7, 3]


def classify_d_bucket(d_days: int) -> str:
    """Classify days-to-departure into canonical D-bucket."""
    for code, min_d, max_d, _ in D_BUCKETS:
        if min_d < d_days <= max_d:
            return code
    return "PANIC" if d_days <= 7 else "EB"


def normalize_hotel_name(name: str) -> str:
    """Normalize hotel title for cohort grouping."""
    raw = str(name or "").strip().lower()
    raw = re.sub(r"\b(hotel|resort|spa|club|deluxe|village|beach|premium|palace)\b", "", raw)
    raw = re.sub(r"[^a-zа-я0-9\s]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw or str(name or "").strip().lower()


def make_cohort_key(hotel_name: str, dep_date: Optional[date], duration: Optional[int]) -> str:
    """Generate cohort key with +-1 day weekly anchor to absorb charter schedule shifts."""
    hotel_norm = normalize_hotel_name(hotel_name)
    if dep_date is None:
        return f"{hotel_norm}::no_date::{duration or 0}"
    # Anchor to Monday of departure week
    monday_anchor = dep_date - timedelta(days=dep_date.weekday())
    # Group duration into 7-10 vs 13-16 or exact
    dur_group = "7-10" if (duration and 7 <= duration <= 10) else ("13-16" if (duration and 13 <= duration <= 16) else str(duration or "other"))
    return f"{hotel_norm}::{monday_anchor.isoformat()}::{dur_group}"


def parse_row_departure_date(row: Dict[str, Any]) -> Optional[date]:
    """Extract departure date from offer URL departureDate query param or dates text."""
    offer_url = str(row.get("offer_url") or "")
    if offer_url:
        try:
            qs = parse_qs(urlparse(offer_url).query)
            dep_param = (qs.get("departureDate") or qs.get("filter[whenFrom]") or [""])[0]
            if dep_param:
                # Can be YYYY-MM-DD or DD-MM-YYYY
                if re.match(r"^\d{4}-\d{2}-\d{2}$", dep_param):
                    return datetime.strptime(dep_param, "%Y-%m-%d").date()
                if re.match(r"^\d{2}-\d{2}-\d{4}$", dep_param):
                    return datetime.strptime(dep_param, "%d-%m-%Y").date()
        except Exception:
            pass

    dates_text = str(row.get("dates") or "")
    dep_iso, _ = parse_dates_text(dates_text)
    if dep_iso:
        try:
            return datetime.strptime(dep_iso, "%Y-%m-%d").date()
        except Exception:
            pass
    return None


def parse_row_scraped_at(row: Dict[str, Any]) -> Optional[datetime]:
    """Parse scraped_at timestamp."""
    val = str(row.get("scraped_at") or "").strip()
    if not val:
        return None
    try:
        # Handle ISO strings with possible timezone
        val_clean = val.replace("Z", "+00:00")
        return datetime.fromisoformat(val_clean)
    except Exception:
        match = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", val)
        if match:
            return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S")
    return None


@dataclass
class OfferObservation:
    price: float
    scraped_at: datetime
    departure_date: date
    d_days: int
    d_bucket: str
    hotel_name: str
    rating: Optional[float]
    duration: Optional[int]


@dataclass
class CohortSummary:
    cohort_key: str
    hotel_name: str
    rating: Optional[float]
    first_seen_d: int
    last_seen_d: int
    fm_price: Optional[float]           # Baseline median price during FM (D 60-120)
    lm_price: Optional[float]           # Median price during LM (D 7-14)
    min_price_ever: float
    min_price_bucket: str
    is_sold_out_before_lm: bool
    bucket_prices: Dict[str, float] = field(default_factory=dict)
    paired_deltas: Dict[str, float] = field(default_factory=dict)


def compute_ebas_score(
    paired_deltas: Dict[str, Dict[str, Any]],
    survival_curve: List[Dict[str, Any]],
    prob_drop_in_lm: float,
    *,
    fm_cohort_count: int = 0,
) -> Tuple[Optional[float], str]:
    """Compute Early Booking Advantage Score (0 to 100) and recommendation string.
    
    EBAS >= 70: HIGHLY_FAVORABLE (Early booking brings substantial savings and eliminates sold out risk)
    EBAS 55-69: FAVORABLE (Early booking is recommended, modest savings)
    EBAS 40-54: NEUTRAL (Prices stay flat or variance is high)
    EBAS < 40: WAIT_FOR_LM (Last minute drops are frequent and outweigh sold-out risk)
    """
    if fm_cohort_count < 2:
        return None, "INSUFFICIENT_DATA"

    # 1. Price advantage: median delta in LM vs FM baseline
    lm_delta_pct = 0.0
    if "LM" in paired_deltas and paired_deltas["LM"].get("median_delta_pct") is not None:
        lm_delta_pct = paired_deltas["LM"]["median_delta_pct"]
    elif "LATE" in paired_deltas and paired_deltas["LATE"].get("median_delta_pct") is not None:
        lm_delta_pct = paired_deltas["LATE"]["median_delta_pct"]

    # 2. Sold out risk at D=14
    surv_14 = 0.5
    for item in survival_curve:
        if item["d"] == 14:
            surv_14 = item["survival_rate"]
            break
    sold_out_rate_14 = max(0.0, min(1.0, 1.0 - surv_14))

    # Weight components
    # Base 50
    # + if LM is more expensive than FM (+lm_delta_pct * 1.2)
    # + if sold-out risk is high (sold_out_rate_14 * 30)
    # - if probability of large drop (>15%) in LM is high
    raw_score = 50.0 + (lm_delta_pct * 1.2) + (sold_out_rate_14 * 30.0) - (prob_drop_in_lm * 40.0)
    score = max(0.0, min(100.0, round(raw_score, 1)))

    if score >= 70:
        verdict = "EARLY_BOOKING_HIGHLY_FAVORABLE"
    elif score >= 55:
        verdict = "EARLY_BOOKING_RECOMMENDED"
    elif score >= 40:
        verdict = "NEUTRAL"
    else:
        verdict = "WAIT_FOR_LAST_MINUTE"

    return score, verdict


def analyze_dataframe(df: pd.DataFrame, filter_id: str = "") -> Dict[str, Any]:
    """Core analysis logic for early booking patterns."""
    if df.empty:
        return {"error": "empty_dataframe", "filter_id": filter_id}

    # Normalize column names
    col_map = {c.lower(): c for c in df.columns}
    hotel_col = col_map.get("hotel_name") or col_map.get("hotel") or "hotel_name"
    price_col = col_map.get("price") or "price"
    dates_col = col_map.get("dates") or "dates"
    scraped_col = col_map.get("scraped_at") or "scraped_at"
    url_col = col_map.get("offer_url") or "offer_url"
    rating_col = col_map.get("hotel_rating") or col_map.get("rating")

    # Clean rows and extract timestamps
    observations: List[OfferObservation] = []
    cohort_map: Dict[str, List[OfferObservation]] = {}

    for _, row in df.iterrows():
        try:
            price = float(row.get(price_col) or 0)
        except (ValueError, TypeError):
            continue
        if price <= 100:
            continue

        hotel = str(row.get(hotel_col) or "").strip()
        if not hotel:
            continue

        scraped_dt = parse_row_scraped_at(row.to_dict())
        dep_date = parse_row_departure_date(row.to_dict())
        if not scraped_dt or not dep_date:
            continue

        scraped_date = scraped_dt.date() if isinstance(scraped_dt, datetime) else scraped_dt
        d_days = (dep_date - scraped_date).days
        # Ignore expired offers
        if d_days < 0:
            continue

        rating = None
        if rating_col and rating_col in row:
            try:
                r_val = float(row[rating_col])
                if not math.isnan(r_val) and r_val > 0:
                    rating = r_val
            except (ValueError, TypeError):
                pass

        duration = None
        if "duration" in col_map:
            try:
                duration = int(row[col_map["duration"]])
            except Exception:
                pass
        if duration is None and dates_col in col_map:
            d_parsed, _ = parse_duration(str(row[dates_col]))
            duration = d_parsed

        bucket = classify_d_bucket(d_days)
        obs = OfferObservation(
            price=price,
            scraped_at=scraped_dt,
            departure_date=dep_date,
            d_days=d_days,
            d_bucket=bucket,
            hotel_name=hotel,
            rating=rating,
            duration=duration,
        )
        observations.append(obs)

        ckey = make_cohort_key(hotel, dep_date, duration)
        cohort_map.setdefault(ckey, []).append(obs)

    if not observations:
        return {"error": "no_valid_observations", "filter_id": filter_id}

    # Aggregate cohorts
    cohort_summaries: List[CohortSummary] = []
    fm_cohorts: List[CohortSummary] = []

    for ckey, obs_list in cohort_map.items():
        if len(obs_list) < 2:
            continue

        hotel_name = obs_list[0].hotel_name
        ratings = [o.rating for o in obs_list if o.rating is not None]
        avg_rating = round(float(np.mean(ratings)), 1) if ratings else None
        
        d_vals = [o.d_days for o in obs_list]
        first_seen_d = max(d_vals)
        last_seen_d = min(d_vals)

        # Bucket median prices for this cohort
        b_prices: Dict[str, list[float]] = {}
        for o in obs_list:
            b_prices.setdefault(o.d_bucket, []).append(o.price)

        median_b_prices = {b: float(np.median(prices)) for b, prices in b_prices.items()}

        # Find minimum price bucket
        min_p = min(o.price for o in obs_list)
        min_bucket = "UNKNOWN"
        for o in obs_list:
            if o.price == min_p:
                min_bucket = o.d_bucket
                break

        # FM baseline: median of FM (or EB if FM missing)
        fm_baseline = median_b_prices.get("FM") or median_b_prices.get("EB")

        # Sold out before LM if last observed at D > 14
        is_sold_out = last_seen_d > 14

        # Paired deltas against FM baseline
        paired_deltas: Dict[str, float] = {}
        if fm_baseline and fm_baseline > 0:
            for b_code in ["EB", "FM", "STD", "LATE", "LM", "PANIC"]:
                if b_code in median_b_prices:
                    delta_pct = ((median_b_prices[b_code] - fm_baseline) / fm_baseline) * 100.0
                    paired_deltas[b_code] = round(delta_pct, 1)

        summary = CohortSummary(
            cohort_key=ckey,
            hotel_name=hotel_name,
            rating=avg_rating,
            first_seen_d=first_seen_d,
            last_seen_d=last_seen_d,
            fm_price=round(fm_baseline, 1) if fm_baseline else None,
            lm_price=round(median_b_prices["LM"], 1) if "LM" in median_b_prices else None,
            min_price_ever=min_p,
            min_price_bucket=min_bucket,
            is_sold_out_before_lm=is_sold_out,
            bucket_prices=median_b_prices,
            paired_deltas=paired_deltas,
        )
        cohort_summaries.append(summary)

        # Cohorts that were present during First Minute window (D > 60)
        if first_seen_d >= 60 and fm_baseline is not None:
            fm_cohorts.append(summary)

    # Calculate overall paired price trajectory
    paired_trajectory: Dict[str, Dict[str, Any]] = {}
    for b_code, _, _, label in D_BUCKETS:
        deltas = [c.paired_deltas[b_code] for c in fm_cohorts if b_code in c.paired_deltas]
        if deltas:
            paired_trajectory[b_code] = {
                "label": label,
                "median_delta_pct": round(float(np.median(deltas)), 1),
                "mean_delta_pct": round(float(np.mean(deltas)), 1),
                "p25_delta_pct": round(float(np.percentile(deltas, 25)), 1),
                "p75_delta_pct": round(float(np.percentile(deltas, 75)), 1),
                "sample_count": len(deltas),
            }
        else:
            paired_trajectory[b_code] = {
                "label": label,
                "median_delta_pct": None,
                "sample_count": 0,
            }

    # Calculate Survival Curve S(d)
    survival_curve: List[Dict[str, Any]] = []
    total_fm_count = len(fm_cohorts) or len(cohort_summaries) or 1
    target_cohorts = fm_cohorts if fm_cohorts else cohort_summaries

    for cp_d in SURVIVAL_CHECKPOINTS:
        # A cohort survived to cp_d if its last_seen_d <= cp_d
        survived = sum(1 for c in target_cohorts if c.last_seen_d <= cp_d)
        rate = round(survived / total_fm_count, 3)
        survival_curve.append({
            "d": cp_d,
            "survival_rate": rate,
            "sold_out_rate": round(1.0 - rate, 3),
            "survived_count": survived,
        })

    # Probability of price drop > 15% in LM
    lm_drops = [c.paired_deltas["LM"] for c in fm_cohorts if "LM" in c.paired_deltas]
    prob_drop_in_lm = round(sum(1 for d in lm_drops if d < -15.0) / max(1, len(lm_drops)), 3)

    # Segment breakdown: Premium (rating >= 8.0 or >= 4.0/5) vs Mass market
    premium_cohorts = [c for c in fm_cohorts if (c.rating and c.rating >= 4.0)]
    mass_cohorts = [c for c in fm_cohorts if not (c.rating and c.rating >= 4.0)]

    def _summarize_segment(cohorts_sub: List[CohortSummary]) -> Dict[str, Any]:
        if not cohorts_sub:
            return {"sample_count": 0}
        lm_deltas = [c.paired_deltas["LM"] for c in cohorts_sub if "LM" in c.paired_deltas]
        sold_outs = sum(1 for c in cohorts_sub if c.is_sold_out_before_lm)
        return {
            "sample_count": len(cohorts_sub),
            "sold_out_rate_lm": round(sold_outs / len(cohorts_sub), 3),
            "median_delta_lm_vs_fm": round(float(np.median(lm_deltas)), 1) if lm_deltas else None,
        }

    segments = {
        "premium_hotels": _summarize_segment(premium_cohorts),
        "mass_market": _summarize_segment(mass_cohorts),
    }

    # Compute EBAS Score
    ebas_score, verdict = compute_ebas_score(
        paired_trajectory,
        survival_curve,
        prob_drop_in_lm,
        fm_cohort_count=len(fm_cohorts),
    )

    # Price stats for raw D-buckets (for box plots)
    raw_bucket_stats: Dict[str, Dict[str, Any]] = {}
    for b_code, _, _, label in D_BUCKETS:
        b_prices = [o.price for o in observations if o.d_bucket == b_code]
        if b_prices:
            raw_bucket_stats[b_code] = {
                "label": label,
                "median_price": round(float(np.median(b_prices)), 1),
                "p25": round(float(np.percentile(b_prices, 25)), 1),
                "p75": round(float(np.percentile(b_prices, 75)), 1),
                "min": round(float(min(b_prices)), 1),
                "max": round(float(max(b_prices)), 1),
                "sample_count": len(b_prices),
            }

    # Best bucket overall
    best_bucket = "FM"
    bucket_counts: Dict[str, int] = {}
    for c in cohort_summaries:
        bucket_counts[c.min_price_bucket] = bucket_counts.get(c.min_price_bucket, 0) + 1
    if bucket_counts:
        best_bucket = max(bucket_counts.items(), key=lambda x: x[1])[0]

    return {
        "filter_id": filter_id,
        "analyzed_at": datetime.now().isoformat(),
        "summary": {
            "total_observations": len(observations),
            "total_cohorts": len(cohort_summaries),
            "fm_tracked_cohorts": len(fm_cohorts),
            "ebas_score": ebas_score,
            "verdict": verdict,
            "best_price_d_bucket": best_bucket,
            "prob_drop_gt_15pct_in_lm": prob_drop_in_lm,
        },
        "paired_price_trajectory": paired_trajectory,
        "survival_curve": survival_curve,
        "raw_bucket_stats": raw_bucket_stats,
        "segments": segments,
    }


def analyze_csv(csv_path: str, filter_id: str = "") -> Dict[str, Any]:
    """Load CSV and run early booking analysis."""
    if not os.path.isfile(csv_path):
        return {"error": "file_not_found", "path": csv_path}
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return {"error": f"read_csv_failed: {exc}", "path": csv_path}
    return analyze_dataframe(df, filter_id=filter_id or os.path.basename(os.path.dirname(csv_path)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Early Booking (First Minute) price trajectories")
    parser.add_argument("--data-file", "-f", help="Path to travel_prices.csv")
    parser.add_argument("--output", "-o", help="Optional output JSON path")
    parser.add_argument("--filter-id", help="Optional filter identifier")
    args = parser.parse_args()

    if not args.data_file:
        print("Usage: python3 early_booking_analyzer.py --data-file path/to/travel_prices.csv [--output out.json]")
        return 1

    res = analyze_csv(args.data_file, filter_id=args.filter_id or "")
    out_json = json.dumps(res, indent=2, ensure_ascii=False)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out_json)
        print(f"✅ Saved early booking report to {args.output}")
    else:
        print(out_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
