"""Synthetic Data Generator & Test Suite for Deal Score and Hopper metrics.

Applies Equivalence Partitioning, Boundary Value Analysis, and Edge Case testing.
"""

from datetime import date, datetime, timedelta, timezone
import pandas as pd
from hotel_deal_score import (
    compute_hotel_deal_metrics,
    compute_smooth_rarity_score,
    time_weighted_price_ecdf,
    _price_plateau_segments,
    time_weighted_price_baseline_from_segments,
    time_weighted_price_quantile_from_segments,
    comeback_from_premium,
)
from hopper_prediction_engine import predict_offer_action


def make_history(prices_with_hours, start_dt=None):
    """Generate DataFrame from list of (price, duration_hours)."""
    if start_dt is None:
        start_dt = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    rows = []
    cur_t = start_dt
    for price, hours in prices_with_hours:
        # Create observations every 6 hours within this plateau
        n_points = max(1, int(round(hours / 6.0)))
        step = timedelta(hours=hours / n_points)
        for _ in range(n_points):
            rows.append({
                "scraped_at": cur_t,
                "price": float(price),
                "hotel_name": "Test Hotel",
            })
            cur_t += step
    return pd.DataFrame(rows)


def run_test_suite():
    print("=" * 70)
    print("🧪 RUNNING COMPREHENSIVE METRICS VERIFICATION SUITE")
    print("=" * 70)

    # ---------------------------------------------------------
    # TC-01: Equivalence Class — Deep Discount / Absolute Historic Min
    # ---------------------------------------------------------
    df_min = make_history([(6000, 100), (5500, 100), (5000, 50), (3800, 12)])
    res_min = compute_hotel_deal_metrics(df_min, latest_price=3800, time_col="scraped_at", price_col="price")
    print("\n[TC-01] Absolute Historic Min (3800 vs baseline ~5500):")
    print(f"  Deal Score: {res_min['deal_score']}/100, Delta avg: {res_min['avg_delta_pct']}%, Confidence: {res_min['confidence']}")
    assert res_min["deal_score"] >= 80, f"Expected Deal Score >= 80, got {res_min['deal_score']}"
    assert res_min["avg_delta_pct"] <= -20.0, f"Expected delta <= -20%, got {res_min['avg_delta_pct']}"
    print("  ✅ TC-01 PASSED")

    # ---------------------------------------------------------
    # TC-02: Equivalence Class — Historic Peak (Overpriced)
    # ---------------------------------------------------------
    df_high = make_history([(4000, 100), (4200, 100), (5500, 24)])
    res_high = compute_hotel_deal_metrics(df_high, latest_price=5500, time_col="scraped_at", price_col="price")
    print("\n[TC-02] Historic Peak (5500 vs baseline ~4100):")
    print(f"  Deal Score: {res_high['deal_score']}/100, Delta avg: {res_high['avg_delta_pct']}%, Confidence: {res_high['confidence']}")
    assert res_high["deal_score"] <= 38, f"Expected Deal Score <= 38, got {res_high['deal_score']}"
    assert res_high["avg_delta_pct"] >= 20.0, f"Expected delta >= 20%, got {res_high['avg_delta_pct']}"
    print("  ✅ TC-02 PASSED")

    # ---------------------------------------------------------
    # TC-03: Boundary / Edge Case — Flat Line (No variance, price unchanging)
    # ---------------------------------------------------------
    df_flat = make_history([(5000, 200)])
    res_flat = compute_hotel_deal_metrics(df_flat, latest_price=5000, time_col="scraped_at", price_col="price")
    print("\n[TC-03] Flat Line (All observations exactly 5000):")
    print(f"  Deal Score: {res_flat['deal_score']}/100, Delta avg: {res_flat['avg_delta_pct']}%, Confidence: {res_flat['confidence']}")
    assert 48 <= res_flat["deal_score"] <= 52, f"Expected neutral Deal Score ~50, got {res_flat['deal_score']}"
    assert res_flat["avg_delta_pct"] == 0.0, f"Expected delta == 0.0, got {res_flat['avg_delta_pct']}"
    print("  ✅ TC-03 PASSED")

    # ---------------------------------------------------------
    # TC-04: Boundary Value Analysis — Continuity across p10 (No step-function cliff)
    # ---------------------------------------------------------
    df_quantiles = make_history([(4000, 20), (5000, 100), (6000, 80)])
    res_below_p10 = compute_hotel_deal_metrics(df_quantiles, latest_price=4100, time_col="scraped_at", price_col="price")
    res_above_p10 = compute_hotel_deal_metrics(df_quantiles, latest_price=4120, time_col="scraped_at", price_col="price")
    diff = abs(res_below_p10["deal_score"] - res_above_p10["deal_score"])
    print("\n[TC-04] Continuity across boundary (20 zł difference):")
    print(f"  Score at 4100: {res_below_p10['deal_score']}, Score at 4120: {res_above_p10['deal_score']}, Diff: {diff}")
    assert diff <= 1, f"Expected smooth continuous transition (diff <= 1), got {diff}!"
    print("  ✅ TC-04 PASSED (Smooth ECDF verified)")

    # ---------------------------------------------------------
    # TC-05: Edge Case — Minimal Data Warm-Up (2 observations)
    # ---------------------------------------------------------
    df_warmup = make_history([(3000, 12), (2000, 12)])
    res_warmup = compute_hotel_deal_metrics(df_warmup, latest_price=2000, time_col="scraped_at", price_col="price")
    print("\n[TC-05] Warm-up with only 2 observations:")
    print(f"  Deal Score: {res_warmup['deal_score']}/100, Confidence: {res_warmup['confidence']}")
    assert res_warmup["confidence"] == "Low", f"Expected Low confidence, got {res_warmup['confidence']}"
    assert 50 <= res_warmup["deal_score"] <= 60, f"Expected shrinkage towards 50, got {res_warmup['deal_score']}"
    print("  ✅ TC-05 PASSED (Bayesian shrinkage verified)")

    # ---------------------------------------------------------
    # TC-06: Equivalence Class — Comeback from Premium
    # ---------------------------------------------------------
    prem_info = {"history_max": 12000.0, "premium_peak": 12000.0}
    cb = comeback_from_premium(current_price=7500, premium_info=prem_info, display_ceiling=10000)
    print("\n[TC-06] Comeback from Premium (Peak 12000 -> Current 7500, Ceiling 10000):")
    assert cb is not None, "Expected comeback info to be returned"
    drop_pct = cb["drop_from_peak_pct"]
    print(f"  Drop percentage from peak: {drop_pct:.1f}%")
    assert drop_pct == 37.5, f"Expected 37.5% drop, got {drop_pct}"
    print("  ✅ TC-06 PASSED")

    # ---------------------------------------------------------
    # TC-07: Hopper Prediction Alignment — Last Minute Panic (D <= 3)
    # ---------------------------------------------------------
    today = date.today()
    dep_date_lm = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    offer_last_minute = {
        "hotel_name": "Test Hotel",
        "price": 3500.0,
        "departure_date": dep_date_lm,
        "dates": dep_date_lm,
    }
    pred_lm = predict_offer_action(
        offer_last_minute,
        history_df=None,
        precomputed_hist_prices=[3500.0, 3600.0, 4000.0],
        precomputed_hist_days=[2, 5, 10],
    )
    print("\n[TC-07] Hopper Last Minute (D=2, price near historic min):")
    print(f"  Verdict: {pred_lm.verdict}, Badge: {pred_lm.badge_text}, D: {pred_lm.days_to_departure}")
    assert pred_lm.verdict == "BUY_NOW", f"Expected BUY_NOW for last-minute min price, got {pred_lm.verdict}"
    print("  ✅ TC-07 PASSED")

    # ---------------------------------------------------------
    # TC-08: Hopper Prediction Alignment — Early Bird with Overpriced Peak
    # ---------------------------------------------------------
    dep_date_eb = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    offer_early_high = {
        "hotel_name": "Test Hotel",
        "price": 6000.0,
        "departure_date": dep_date_eb,
        "dates": dep_date_eb,
    }
    pred_early_high = predict_offer_action(
        offer_early_high,
        history_df=None,
        precomputed_hist_prices=[4000.0, 4200.0, 4500.0, 6000.0],
        precomputed_hist_days=[90, 95, 100, 105],
    )
    print("\n[TC-08] Hopper Early Bird (D=90, price at highest tier):")
    print(f"  Verdict: {pred_early_high.verdict}, Drop Prob: {pred_early_high.drop_probability_pct}%, Badge: {pred_early_high.badge_text}")
    assert pred_early_high.verdict in ("WAIT", "OVERPRICED"), f"Expected WAIT or OVERPRICED, got {pred_early_high.verdict}"
    assert pred_early_high.drop_probability_pct >= 50.0, f"Expected high drop prob, got {pred_early_high.drop_probability_pct}"
    print("  ✅ TC-08 PASSED")

    print("\n" + "=" * 70)
    print("🎉 ALL 8 TEST SUITE SCENARIOS PASSED WITH EXPECTED METRIC BEHAVIOR!")
    print("=" * 70)


if __name__ == "__main__":
    run_test_suite()
