#!/usr/bin/env python3
"""Unit tests for early_booking_analyzer.py."""

from datetime import date, datetime, timedelta
import unittest
import pandas as pd

from early_booking_analyzer import (
    classify_d_bucket,
    compute_ebas_score,
    make_cohort_key,
    normalize_hotel_name,
    analyze_dataframe,
)


class TestEarlyBookingAnalyzer(unittest.TestCase):
    def test_classify_d_bucket(self):
        self.assertEqual(classify_d_bucket(150), "EB")
        self.assertEqual(classify_d_bucket(120), "FM")
        self.assertEqual(classify_d_bucket(61), "FM")
        self.assertEqual(classify_d_bucket(60), "STD")
        self.assertEqual(classify_d_bucket(31), "STD")
        self.assertEqual(classify_d_bucket(30), "LATE")
        self.assertEqual(classify_d_bucket(15), "LATE")
        self.assertEqual(classify_d_bucket(14), "LM")
        self.assertEqual(classify_d_bucket(8), "LM")
        self.assertEqual(classify_d_bucket(7), "PANIC")
        self.assertEqual(classify_d_bucket(2), "PANIC")
        self.assertEqual(classify_d_bucket(0), "PANIC")

    def test_normalize_hotel_name(self):
        self.assertEqual(normalize_hotel_name("Hotel Rixos Premium Belek"), "rixos belek")
        self.assertEqual(normalize_hotel_name("Albatros Resort & Spa"), "albatros")
        self.assertEqual(normalize_hotel_name("Mirage World Deluxe"), "mirage world")

    def test_make_cohort_key(self):
        dep1 = date(2027, 7, 14)  # Wednesday
        dep2 = date(2027, 7, 16)  # Friday (same week)
        key1 = make_cohort_key("Grand Kaptan Hotel", dep1, 8)
        key2 = make_cohort_key("Grand Kaptan", dep2, 7)
        # Should resolve to the same cohort key due to fuzzy weekly anchor and duration group
        self.assertEqual(key1, key2)

    def test_analyze_dataframe_synthetic(self):
        # Build synthetic dataframe tracking 2 hotels:
        # Hotel A: starts at 5000 in FM (D=90), rises to 6000 in LM (D=10)
        # Hotel B: starts at 4000 in FM (D=90), disappears after D=35 (sold out)
        base_dep = date(2027, 7, 20)
        rows = []

        # Hotel A observations
        # D=90 -> scraped 2027-04-21
        dt_fm = datetime(2027, 4, 21, 10, 0, 0)
        rows.append({
            "hotel_name": "Hotel Luxury Palace",
            "price": 5000.0,
            "dates": "20.07.2027 - 28.07.2027",
            "scraped_at": dt_fm.isoformat(),
            "rating": 4.8,
            "duration": 8,
        })
        # D=40 (STD)
        dt_std = datetime(2027, 6, 10, 10, 0, 0)
        rows.append({
            "hotel_name": "Hotel Luxury Palace",
            "price": 5500.0,
            "dates": "20.07.2027 - 28.07.2027",
            "scraped_at": dt_std.isoformat(),
            "rating": 4.8,
            "duration": 8,
        })
        # D=10 (LM)
        dt_lm = datetime(2027, 7, 10, 10, 0, 0)
        rows.append({
            "hotel_name": "Hotel Luxury Palace",
            "price": 6000.0,
            "dates": "20.07.2027 - 28.07.2027",
            "scraped_at": dt_lm.isoformat(),
            "rating": 4.8,
            "duration": 8,
        })

        # Hotel B observations (disappears after D=35)
        rows.append({
            "hotel_name": "Family Resort Club",
            "price": 4000.0,
            "dates": "20.07.2027 - 28.07.2027",
            "scraped_at": dt_fm.isoformat(),
            "rating": 3.8,
            "duration": 8,
        })
        dt_b_last = datetime(2027, 6, 15, 10, 0, 0)  # D=35
        rows.append({
            "hotel_name": "Family Resort Club",
            "price": 4200.0,
            "dates": "20.07.2027 - 28.07.2027",
            "scraped_at": dt_b_last.isoformat(),
            "rating": 3.8,
            "duration": 8,
        })

        df = pd.DataFrame(rows)
        res = analyze_dataframe(df, filter_id="test_filter")

        self.assertNotIn("error", res)
        summary = res["summary"]
        self.assertEqual(summary["total_cohorts"], 2)
        self.assertEqual(summary["fm_tracked_cohorts"], 2)
        self.assertIn("verdict", summary)
        self.assertGreater(summary["ebas_score"], 50.0)

        # Check paired trajectory: Hotel A went from 5000 to 6000 (+20%)
        traj = res["paired_price_trajectory"]
        self.assertIn("LM", traj)
        self.assertEqual(traj["LM"]["median_delta_pct"], 20.0)

        # Check survival curve: at D=14, only Hotel A survived (50% survival rate)
        surv = {item["d"]: item["survival_rate"] for item in res["survival_curve"]}
        self.assertEqual(surv[60], 1.0)
        self.assertEqual(surv[14], 0.5)

    def test_compute_ebas_score(self):
        # Scenario 1: Prices rise +20% in LM and 40% sold out -> High score
        paired_deltas = {"LM": {"median_delta_pct": 20.0}}
        survival_curve = [{"d": 14, "survival_rate": 0.6}]  # 40% sold out
        score, verdict = compute_ebas_score(paired_deltas, survival_curve, prob_drop_in_lm=0.05, fm_cohort_count=10)
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 70.0)
        self.assertEqual(verdict, "EARLY_BOOKING_HIGHLY_FAVORABLE")

        # Scenario 2: Prices drop -25% in LM and 95% survived -> Low score
        paired_deltas_drop = {"LM": {"median_delta_pct": -25.0}}
        survival_curve_survived = [{"d": 14, "survival_rate": 0.95}]
        score_drop, verdict_drop = compute_ebas_score(paired_deltas_drop, survival_curve_survived, prob_drop_in_lm=0.4, fm_cohort_count=10)
        self.assertIsNotNone(score_drop)
        self.assertLess(score_drop, 40.0)
        self.assertEqual(verdict_drop, "WAIT_FOR_LAST_MINUTE")

        # Scenario 3: Insufficient cohorts
        score_insuf, verdict_insuf = compute_ebas_score(paired_deltas, survival_curve, prob_drop_in_lm=0.05, fm_cohort_count=1)
        self.assertIsNone(score_insuf)
        self.assertEqual(verdict_insuf, "INSUFFICIENT_DATA")

    def test_early_booking_not_archived_during_cadence_pause(self):
        from filter_trip import is_config_archived, skip_monitor_reason
        import filter_registry

        eb_cfg = {
            "early_booking_tracking": True,
            "trip_anchor_date": "2027-08-01",
            "retire_after": "2027-09-01",
            "scrape_interval_rules": [{"d_min": 60, "d_max": 9999, "every_hours": 24}],
        }
        ref_today = date(2026, 10, 29)
        # 1. Config should not be archived
        self.assertFalse(is_config_archived(eb_cfg, today=ref_today))

        # 2. In filter_registry, a filter dictionary with this config should not be archived
        flt_dict = {
            "id": "eb_test",
            "status": "active",
            "config": "config_ci_eb_greece_aug27_7_10.json",
        }
        self.assertFalse(filter_registry.is_filter_archived(flt_dict, today=ref_today))


if __name__ == "__main__":
    unittest.main()

