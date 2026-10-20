#!/usr/bin/env python3
"""
Hopper-Style Predictive Engine for Package Tours.

Analyzes travel package offers based on:
1. Days-to-departure (D-Minus: D = departure_date - scraped_date).
2. Historical price position (quantiles, plateaus, recent velocity).
3. Empirical conditional drop probability: P(price_drop >= threshold | D, current_price_tier).
4. Charter yield-management cycles (panic dumps at D-14, D-7, D-3).

Outputs actionable forward-looking recommendations:
- BUY_NOW: Price floor reached, low probability of future drop, or last-minute risk.
- WAIT: High probability of drop (>=5%) before departure, with target price & trigger date.
- OVERPRICED: Significant overpay risk, price far above baseline.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


# Thresholds and parameters for Hopper prediction
MIN_SIGNIFICANT_DROP_PCT = 0.04  # 4% price drop considered significant
MIN_SIGNIFICANT_DROP_PLN = 150.0  # Or at least 150 PLN drop

# Base prior drop probabilities by (D bucket, price tier) when history is sparse
# D buckets: 'last_minute' (1-3), 'panic_dump' (4-14), 'mid_term' (15-30), 'early_bird' (>30)
# Price tiers: 'low' (q <= 0.25), 'mid' (0.25 < q <= 0.75), 'high' (q > 0.75)
PRIOR_DROP_PROBABILITIES = {
    ("last_minute", "low"): 0.12,
    ("last_minute", "mid"): 0.35,
    ("last_minute", "high"): 0.60,
    ("panic_dump", "low"): 0.25,
    ("panic_dump", "mid"): 0.65,
    ("panic_dump", "high"): 0.85,
    ("mid_term", "low"): 0.30,
    ("mid_term", "mid"): 0.55,
    ("mid_term", "high"): 0.78,
    ("early_bird", "low"): 0.35,
    ("early_bird", "mid"): 0.50,
    ("early_bird", "high"): 0.70,
}

# Typical charter markdown schedule (approximate days before departure when drops trigger)
CHARTER_DUMP_DAYS = [14, 10, 7, 3]


@dataclass
class HopperPrediction:
    verdict: str  # 'BUY_NOW', 'WAIT', 'OVERPRICED', 'EXPIRED'
    badge_text: str  # E.g. '🟢 BUY NOW', '🟡 WAIT'
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW'
    confidence_pct: int  # 0 to 100
    drop_probability_pct: int  # Probability of future price drop before departure (0-100)
    days_to_departure: int  # D-minus
    departure_date: Optional[str]  # ISO 'YYYY-MM-DD'
    current_price: float
    target_price: float  # Expected price if waiting
    expected_savings: float  # current_price - target_price
    recommended_by_date: Optional[str]  # When to make final decision
    price_quantile: float  # 0.0 to 1.0 (relative position in history)
    reasoning: str  # Concise human explanation in Russian

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_departure_date(dates_str: Any) -> Optional[date]:
    """
    Parses departure date from strings like:
    - '01.06.2026 - 08.06.2026'
    - '01.06 - 08.06.2026'
    - '2026-06-01'
    - '01.06.2026'
    """
    if not dates_str or pd.isna(dates_str):
        return None

    text = str(dates_str).strip()

    # Format: YYYY-MM-DD
    iso_m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso_m:
        try:
            return date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3)))
        except ValueError:
            return None

    # Format: DD.MM.YYYY - DD.MM.YYYY or DD.MM.YYYY
    full_m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if full_m:
        try:
            return date(int(full_m.group(3)), int(full_m.group(2)), int(full_m.group(1)))
        except ValueError:
            return None

    # Format: DD.MM - DD.MM.YYYY (year only at the end)
    short_m = re.search(r"(\d{1,2})\.(\d{1,2})\s*-\s*\d{1,2}\.\d{1,2}\.(\d{4})", text)
    if short_m:
        try:
            return date(int(short_m.group(3)), int(short_m.group(2)), int(short_m.group(1)))
        except ValueError:
            return None

    return None


def calculate_days_to_departure(
    dep_date: Optional[date],
    scrape_timestamp: Any = None,
) -> Optional[int]:
    """Calculates D = (dep_date - scrape_date).days."""
    if not dep_date:
        return None

    if scrape_timestamp is None:
        ref_date = date.today()
    elif isinstance(scrape_timestamp, (datetime, pd.Timestamp)):
        ref_date = scrape_timestamp.date()
    elif isinstance(scrape_timestamp, date):
        ref_date = scrape_timestamp
    else:
        try:
            parsed = pd.to_datetime(str(scrape_timestamp), errors="coerce")
            if pd.isna(parsed):
                ref_date = date.today()
            else:
                ref_date = parsed.date()
        except Exception:
            ref_date = date.today()

    return (dep_date - ref_date).days


def get_d_bucket(days: int) -> str:
    """Classifies D into strategic charter windows."""
    if days <= 3:
        return "last_minute"
    if days <= 14:
        return "panic_dump"
    if days <= 30:
        return "mid_term"
    return "early_bird"


def get_price_tier(quantile: float) -> str:
    """Classifies price quantile into tier."""
    if quantile <= 0.25:
        return "low"
    if quantile <= 0.75:
        return "mid"
    return "high"


def _estimate_empirical_drop_probability(
    hist_prices: List[float],
    hist_days: List[int],
    current_price: float,
    current_d: int,
) -> Tuple[float, float, int]:
    """
    Analyzes historical trajectories of this or similar offers.
    Returns:
    - empirical_drop_prob: float (0.0 to 1.0)
    - empirical_min_seen_after_d: float
    - valid_comparisons: int
    """
    if len(hist_prices) < 2 or len(hist_days) < 2:
        return 0.5, current_price, 0

    # Pair observations by order (sorted by time/days descending towards 0)
    pairs = sorted(zip(hist_days, hist_prices), key=lambda x: -x[0])  # largest D to smallest D

    drops_count = 0
    total_evaluable = 0
    future_mins = []

    for i in range(len(pairs)):
        d_i, p_i = pairs[i]
        # Look at observations where offer had similar or greater D
        if abs(d_i - current_d) <= max(3, current_d // 3):
            # Look at all subsequent observations closer to departure (d_j < d_i)
            subsequent = [p_j for (d_j, p_j) in pairs if d_j < d_i]
            if subsequent:
                total_evaluable += 1
                min_subsequent = min(subsequent)
                future_mins.append(min_subsequent)
                rel_drop = (p_i - min_subsequent) / p_i if p_i > 0 else 0.0
                abs_drop = p_i - min_subsequent
                if rel_drop >= MIN_SIGNIFICANT_DROP_PCT or abs_drop >= MIN_SIGNIFICANT_DROP_PLN:
                    drops_count += 1

    if total_evaluable > 0:
        prob = drops_count / total_evaluable
        avg_future_min = float(np.median(future_mins))
        return prob, avg_future_min, total_evaluable

    return 0.5, current_price, 0


def _find_next_dump_date(dep_date: date, current_d: int, ref_date: date) -> Optional[str]:
    """Finds next expected charter markdown date before departure."""
    for dump_d in CHARTER_DUMP_DAYS:
        if current_d > dump_d:
            action_date = dep_date - timedelta(days=dump_d)
            return action_date.isoformat()
    # If already past D-3, action is immediate
    action_date = max(ref_date, dep_date - timedelta(days=1))
    return action_date.isoformat()


def predict_offer_action(
    offer: Dict[str, Any],
    history_df: Optional[pd.DataFrame] = None,
    reference_date: Optional[date] = None,
    precomputed_hist_prices: Optional[List[float]] = None,
    precomputed_hist_days: Optional[List[int]] = None,
    precomputed_cohort_prices: Optional[List[float]] = None,
) -> HopperPrediction:
    """
    Generates a Hopper-style prediction for a given tour package offer.

    Args:
        offer: Dict containing at least 'price' and 'dates'. May contain 'hotel_name', 'scraped_at'.
        history_df: DataFrame of historical observations for this hotel/offer (or filter).
        reference_date: Evaluation date (defaults to date.today() or offer['scraped_at']).
        precomputed_hist_prices: Optional pre-extracted prices for this hotel.
        precomputed_hist_days: Optional pre-extracted D-values for this hotel.
        precomputed_cohort_prices: Optional pre-extracted prices for the cohort.
    """
    dates_str = offer.get("dates")
    dep_date = parse_departure_date(dates_str)

    try:
        current_price = float(offer.get("price") or 0.0)
    except (ValueError, TypeError):
        current_price = 0.0

    ref_date = reference_date
    if ref_date is None:
        if offer.get("scraped_at"):
            try:
                ref_date = pd.to_datetime(offer["scraped_at"]).date()
            except Exception:
                ref_date = date.today()
        else:
            ref_date = date.today()

    if not dep_date:
        return HopperPrediction(
            verdict="UNKNOWN",
            badge_text="⚪ НЕТ ДАННЫХ",
            confidence="LOW",
            confidence_pct=10,
            drop_probability_pct=50,
            days_to_departure=0,
            departure_date=None,
            current_price=current_price,
            target_price=current_price,
            expected_savings=0.0,
            recommended_by_date=None,
            price_quantile=0.5,
            reasoning="Не удалось распознать точную дату вылета.",
        )

    days_to_dep = (dep_date - ref_date).days

    if days_to_dep < 0:
        return HopperPrediction(
            verdict="EXPIRED",
            badge_text="⚫ ИСТЁК",
            confidence="HIGH",
            confidence_pct=100,
            drop_probability_pct=0,
            days_to_departure=days_to_dep,
            departure_date=dep_date.isoformat(),
            current_price=current_price,
            target_price=current_price,
            expected_savings=0.0,
            recommended_by_date=None,
            price_quantile=0.5,
            reasoning=f"Тур уже вылетел ({dep_date.strftime('%d.%m.%Y')}).",
        )

    d_bucket = get_d_bucket(days_to_dep)

    # Analyze history if available
    if precomputed_hist_prices is not None:
        hist_prices = precomputed_hist_prices
        hist_days = precomputed_hist_days or []
        cohort_prices = precomputed_cohort_prices or []
    else:
        hist_prices = []
        cohort_prices = []
        hist_days = []

        if history_df is not None and not history_df.empty and "price" in history_df.columns:
            work = history_df.dropna(subset=["price"]).copy()
            work["price_num"] = pd.to_numeric(work["price"], errors="coerce")
            work = work.dropna(subset=["price_num"])
            cohort_prices = work["price_num"].tolist()

            # Filter by same hotel if provided
            hotel_name = offer.get("hotel_name")
            if hotel_name and "hotel_name" in work.columns:
                hotel_work = work[work["hotel_name"].astype(str) == str(hotel_name)]
                if not hotel_work.empty:
                    hist_prices = hotel_work["price_num"].tolist()

            # Compute D for historical rows
            if "dates" in work.columns:
                for _, row in work.iterrows():
                    row_dep = parse_departure_date(row["dates"])
                    row_scraped = row.get("scraped_at")
                    if row_dep:
                        r_days = calculate_days_to_departure(row_dep, row_scraped)
                        if r_days is not None and r_days >= 0:
                            hist_days.append(r_days)

    has_hotel_variation = (
        len(hist_prices) >= 3 and (float(np.max(hist_prices)) - float(np.min(hist_prices))) >= 100.0
    )

    if has_hotel_variation:
        eval_prices = hist_prices
        history_source = "hotel"
    elif cohort_prices and len(cohort_prices) >= 5:
        eval_prices = cohort_prices
        history_source = "cohort"
    elif hist_prices:
        eval_prices = hist_prices
        history_source = "hotel_sparse"
    else:
        eval_prices = [current_price] if current_price > 0 else [1000.0]
        history_source = "none"

    # Calculate price quantiles from evaluated prices
    p_min = float(np.min(eval_prices))
    p_max = float(np.max(eval_prices))
    p_15 = float(np.percentile(eval_prices, 15))
    p_median = float(np.percentile(eval_prices, 50))
    p_80 = float(np.percentile(eval_prices, 80))

    if p_max > p_min:
        quantile = float(np.clip((current_price - p_min) / (p_max - p_min), 0.0, 1.0))
    else:
        quantile = 0.5

    price_tier = get_price_tier(quantile)
    try:
        from hopper_learner import HopperLearner
        _learner = HopperLearner()
        prior_prob = _learner.get_calibrated_prior(d_bucket, price_tier)
    except Exception:
        prior_prob = PRIOR_DROP_PROBABILITIES.get((d_bucket, price_tier), 0.50)

    # Empirical probability from history
    emp_prob, emp_min, comparisons = _estimate_empirical_drop_probability(
        hist_prices=hist_prices,
        hist_days=hist_days,
        current_price=current_price,
        current_d=days_to_dep,
    )

    # Bayesian blending of prior and empirical
    n_prior = 4
    drop_probability = (comparisons * emp_prob + n_prior * prior_prob) / (comparisons + n_prior)
    drop_prob_pct = int(round(drop_probability * 100))

    # Calculate confidence based on data depth
    sample_size = len(hist_prices)
    if sample_size >= 25 and comparisons >= 5:
        confidence = "HIGH"
        confidence_pct = min(95, 70 + comparisons * 4)
    elif sample_size >= 8:
        confidence = "MEDIUM"
        confidence_pct = min(75, 45 + sample_size * 3)
    else:
        confidence = "LOW"
        confidence_pct = max(30, 20 + sample_size * 5)

    # Target price and expected savings calculation
    if drop_probability >= 0.50:
        # If drop is expected, target the historical p15 or median drop
        expected_drop_factor = max(0.06, (drop_probability - 0.40) * 0.25)
        target = min(current_price * (1.0 - expected_drop_factor), max(p_min, p_15))
        if target >= current_price:
            target = current_price * 0.95
    else:
        target = current_price

    target_price = round(float(target), 0)
    expected_savings = max(0.0, round(current_price - target_price, 0))

    # Next action / dump date
    recommended_date = _find_next_dump_date(dep_date, days_to_dep, ref_date)

    # Decision Matrix: BUY_NOW vs WAIT vs OVERPRICED
    # 1. Last minute floor
    if days_to_dep <= 3:
        if current_price <= p_median * 1.10:
            verdict = "BUY_NOW"
            badge = "🟢 ПОКУПАТЬ"
            reasoning = f"Вылет через {days_to_dep} дн. Риск закрытия продажи отеля критический, цена на дне."
        else:
            verdict = "WAIT"
            badge = "🟡 ПОСЛЕДНИЙ ШАНС"
            reasoning = f"Вылет через {days_to_dep} дн., но цена завышена. Ожидайте сброса в последние часы или ищите альтернативу."

    # 2. Severe overprice
    elif quantile >= 0.80 or current_price > p_median * 1.20:
        verdict = "OVERPRICED"
        badge = "🔴 ДОРОГО"
        pct_over = int(round((current_price / p_median - 1.0) * 100)) if p_median > 0 else 0
        reasoning = f"Цена на {pct_over}% выше типичной ({int(p_median)} PLN). Покупка сейчас несет высокий риск переплаты."

    # 3. Strong BUY NOW conditions:
    elif (has_hotel_variation and current_price <= p_15 * 1.03) or (quantile <= 0.15 and drop_probability < 0.40):
        verdict = "BUY_NOW"
        badge = "🟢 ПОКУПАТЬ"
        source_label = "отеля" if has_hotel_variation else "рынка"
        reasoning = f"Цена в нижних 15% выборки {source_label} ({int(current_price)} PLN). Вероятность дальнейшего снижения всего {drop_prob_pct}%."

    # 4. High drop probability in prime yield windows (D-14 to D-4)
    elif drop_probability >= 0.55 and days_to_dep >= 4:
        verdict = "WAIT"
        badge = "🟡 ЖДАТЬ"
        reasoning = (
            f"Высокая вероятность сброса цены ({drop_prob_pct}%). "
            f"Ожидаемый таргет ~{int(target_price)} PLN (экономия ~{int(expected_savings)} PLN). "
            f"Оптимально проверить {recommended_date or 'ближе к D-7'}."
        )

    # 5. Default balanced case
    elif drop_probability > 0.45:
        verdict = "WAIT"
        badge = "🟡 ЖДАТЬ"
        reasoning = f"Цена около нормы, но до вылета {days_to_dep} дн. Возможен демпинг туроператора ближе к чартерному окну."
    else:
        verdict = "BUY_NOW"
        badge = "🟢 ПОКУПАТЬ"
        reasoning = f"Стабильная цена ({int(current_price)} PLN), предпосылок к существенному падению нет."

    return HopperPrediction(
        verdict=verdict,
        badge_text=badge,
        confidence=confidence,
        confidence_pct=confidence_pct,
        drop_probability_pct=drop_prob_pct,
        days_to_departure=days_to_dep,
        departure_date=dep_date.isoformat(),
        current_price=current_price,
        target_price=target_price,
        expected_savings=expected_savings,
        recommended_by_date=recommended_date,
        price_quantile=round(quantile, 3),
        reasoning=reasoning,
    )


def batch_predict_offers(
    df: pd.DataFrame,
    reference_date: Optional[date] = None,
) -> pd.DataFrame:
    """
    Enriches a DataFrame of offers with Hopper prediction columns:
    - hopper_verdict
    - hopper_badge
    - hopper_confidence
    - hopper_drop_prob_pct
    - hopper_days_to_dep
    - hopper_target_price
    - hopper_expected_savings
    - hopper_recommended_date
    - hopper_reasoning
    """
    if df is None or df.empty:
        return df

    result_df = df.copy()

    verdicts = []
    badges = []
    confidences = []
    drop_probs = []
    days_to_deps = []
    target_prices = []
    expected_savings_list = []
    recommended_dates = []
    reasonings = []

    ref_eval_date = reference_date or date.today()

    # Pre-parse numeric prices and cohort
    prices_s = pd.to_numeric(result_df["price"], errors="coerce").fillna(0.0)
    cohort_prices_all = [p for p in prices_s.tolist() if p > 0]

    # Pre-parse dates
    dates_s = result_df["dates"] if "dates" in result_df.columns else pd.Series([""] * len(result_df))
    parsed_deps = [parse_departure_date(d) for d in dates_s]
    scraped_s = result_df["scraped_at"] if "scraped_at" in result_df.columns else pd.Series([None] * len(result_df))

    # Pre-index by hotel
    hotel_names = (
        result_df["hotel_name"].astype(str).tolist()
        if "hotel_name" in result_df.columns
        else [""] * len(result_df)
    )
    hotel_prices_map: Dict[str, List[float]] = {}
    hotel_days_map: Dict[str, List[int]] = {}

    for h_name, p, dep, sc in zip(hotel_names, prices_s, parsed_deps, scraped_s):
        if p <= 0:
            continue
        if h_name not in hotel_prices_map:
            hotel_prices_map[h_name] = []
            hotel_days_map[h_name] = []
        hotel_prices_map[h_name].append(p)
        if dep:
            d_val = calculate_days_to_departure(dep, sc or ref_eval_date)
            if d_val is not None and d_val >= 0:
                hotel_days_map[h_name].append(d_val)

    # Fast evaluation loop
    for _, row in result_df.iterrows():
        h_name = str(row.get("hotel_name") or "")
        pred = predict_offer_action(
            offer=row.to_dict(),
            history_df=None,
            reference_date=reference_date,
            precomputed_hist_prices=hotel_prices_map.get(h_name, []),
            precomputed_hist_days=hotel_days_map.get(h_name, []),
            precomputed_cohort_prices=cohort_prices_all,
        )
        verdicts.append(pred.verdict)
        badges.append(pred.badge_text)
        confidences.append(pred.confidence)
        drop_probs.append(pred.drop_probability_pct)
        days_to_deps.append(pred.days_to_departure)
        target_prices.append(pred.target_price)
        expected_savings_list.append(pred.expected_savings)
        recommended_dates.append(pred.recommended_by_date)
        reasonings.append(pred.reasoning)

    result_df["hopper_verdict"] = verdicts
    result_df["hopper_badge"] = badges
    result_df["hopper_confidence"] = confidences
    result_df["hopper_drop_prob_pct"] = drop_probs
    result_df["hopper_days_to_dep"] = days_to_deps
    result_df["hopper_target_price"] = target_prices
    result_df["hopper_expected_savings"] = expected_savings_list
    result_df["hopper_recommended_date"] = recommended_dates
    result_df["hopper_reasoning"] = reasonings

    return result_df
