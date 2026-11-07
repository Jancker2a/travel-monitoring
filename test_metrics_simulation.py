"""Synthetic Data Generator & Test Suite for Deal Score and Hopper metrics.

Applies Equivalence Partitioning, Boundary Value Analysis, and Edge Case testing.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
import pandas as pd
from hotel_deal_score import (
    compute_hotel_deal_metrics,
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


class TestMetricsSimulation(unittest.TestCase):
    def test_tc01_absolute_historic_min(self):
        # TC-01: Equivalence Class — Deep Discount / Absolute Historic Min
        df_min = make_history([(6000, 100), (5500, 100), (5000, 50), (3800, 12)])
        res_min = compute_hotel_deal_metrics(df_min, latest_price=3800, time_col="scraped_at", price_col="price")
        self.assertGreaterEqual(res_min["deal_score"], 80)
        self.assertLessEqual(res_min["avg_delta_pct"], -20.0)

    def test_tc02_historic_peak_overpriced(self):
        # TC-02: Equivalence Class — Historic Peak (Overpriced)
        df_high = make_history([(4000, 100), (4200, 100), (5500, 24)])
        res_high = compute_hotel_deal_metrics(df_high, latest_price=5500, time_col="scraped_at", price_col="price")
        self.assertLessEqual(res_high["deal_score"], 38)
        self.assertGreaterEqual(res_high["avg_delta_pct"], 20.0)

    def test_tc03_flat_line_no_variance(self):
        # TC-03: Boundary / Edge Case — Flat Line (No variance, price unchanging)
        df_flat = make_history([(5000, 200)])
        res_flat = compute_hotel_deal_metrics(df_flat, latest_price=5000, time_col="scraped_at", price_col="price")
        self.assertTrue(48 <= res_flat["deal_score"] <= 52)
        self.assertEqual(res_flat["avg_delta_pct"], 0.0)

    def test_tc04_continuity_across_p10(self):
        # TC-04: Boundary Value Analysis — Continuity across p10 (No step-function cliff)
        df_quantiles = make_history([(4000, 20), (5000, 100), (6000, 80)])
        res_below_p10 = compute_hotel_deal_metrics(df_quantiles, latest_price=4100, time_col="scraped_at", price_col="price")
        res_above_p10 = compute_hotel_deal_metrics(df_quantiles, latest_price=4120, time_col="scraped_at", price_col="price")
        diff = abs(res_below_p10["deal_score"] - res_above_p10["deal_score"])
        self.assertLessEqual(diff, 1)

    def test_tc05_minimal_data_warmup(self):
        # TC-05: Edge Case — Minimal Data Warm-Up (2 observations)
        df_warmup = make_history([(3000, 12), (2000, 12)])
        res_warmup = compute_hotel_deal_metrics(df_warmup, latest_price=2000, time_col="scraped_at", price_col="price")
        self.assertEqual(res_warmup["confidence"], "Low")
        self.assertTrue(50 <= res_warmup["deal_score"] <= 60)

    def test_tc06_comeback_from_premium(self):
        # TC-06: Equivalence Class — Comeback from Premium
        prem_info = {"history_max": 12000.0, "premium_peak": 12000.0}
        cb = comeback_from_premium(current_price=7500, premium_info=prem_info, display_ceiling=10000)
        self.assertIsNotNone(cb)
        self.assertEqual(cb["drop_from_peak_pct"], 37.5)

    def test_tc07_hopper_last_minute(self):
        # TC-07: Hopper Prediction Alignment — Last Minute Panic (D <= 3)
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
        self.assertEqual(pred_lm.verdict, "BUY_NOW")

    def test_tc08_hopper_early_bird_overpriced(self):
        # TC-08: Hopper Prediction Alignment — Early Bird with Overpriced Peak
        today = date.today()
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
        self.assertIn(pred_early_high.verdict, ("WAIT", "OVERPRICED"))
        self.assertGreaterEqual(pred_early_high.drop_probability_pct, 50.0)


if __name__ == "__main__":
    unittest.main()
