#!/usr/bin/env python3
"""
Unit tests for scraper_healthcheck.py.
"""

import json
import os
import tempfile
import unittest

import pandas as pd

from scraper_healthcheck import ScraperHealthChecker, ScraperHealthResult


class TestScraperHealthcheck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.health_log = os.path.join(self.temp_dir.name, "scraper_health.json")
        self.checker = ScraperHealthChecker(
            health_log_path=self.health_log,
            min_baseline_for_drop_check=10,
            severe_drop_threshold_pct=0.75,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_baseline_calculation(self):
        csv_path = os.path.join(self.temp_dir.name, "travel_prices.csv")
        # Create CSV with 3 runs having 40, 50, and 60 rows
        rows = []
        for i in range(40):
            rows.append({"scraped_at": "2026-11-01 10:00:00", "price": 2000})
        for i in range(50):
            rows.append({"scraped_at": "2026-11-02 10:00:00", "price": 2000})
        for i in range(60):
            rows.append({"scraped_at": "2026-11-03 10:00:00", "price": 2000})

        pd.DataFrame(rows).to_csv(csv_path, index=False)
        baseline = self.checker.compute_historical_baseline(csv_path)
        self.assertEqual(baseline, 50)

    def test_zero_offers_allowed_empty(self):
        config = {"filter_id": "filter_test", "allow_empty_offers": True}
        res = self.checker.evaluate(config, [], data_dir=self.temp_dir.name)
        self.assertEqual(res.status, "empty_allowed")
        self.assertFalse(res.circuit_breaker_tripped)

    def test_zero_offers_critical_empty(self):
        config = {"filter_id": "filter_test", "allow_empty_offers": False}
        res = self.checker.evaluate(config, [], data_dir=self.temp_dir.name)
        self.assertEqual(res.status, "critical_empty")
        self.assertTrue(res.circuit_breaker_tripped)

    def test_healthy_scrape(self):
        # Prepare baseline 50
        csv_path = os.path.join(self.temp_dir.name, "travel_prices.csv")
        rows = [{"scraped_at": "2026-11-01 10:00:00", "price": 2000} for _ in range(50)]
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        config = {"filter_id": "filter_test"}
        current_offers = [{"hotel_name": f"Hotel {i}"} for i in range(45)]
        res = self.checker.evaluate(config, current_offers, data_dir=self.temp_dir.name)

        self.assertEqual(res.status, "healthy")
        self.assertFalse(res.circuit_breaker_tripped)
        self.assertEqual(res.baseline_count, 50)
        self.assertEqual(res.current_count, 45)

    def test_severe_drop_trips_breaker(self):
        # Baseline 100, current 10 -> drop 90% >= 75%
        csv_path = os.path.join(self.temp_dir.name, "travel_prices.csv")
        rows = [{"scraped_at": "2026-11-01 10:00:00", "price": 2000} for _ in range(100)]
        pd.DataFrame(rows).to_csv(csv_path, index=False)

        config = {"filter_id": "filter_test"}
        current_offers = [{"hotel_name": f"Hotel {i}"} for i in range(10)]
        res = self.checker.evaluate(config, current_offers, data_dir=self.temp_dir.name)

        self.assertEqual(res.status, "anomaly_drop")
        self.assertTrue(res.circuit_breaker_tripped)
        self.assertGreaterEqual(res.drop_pct, 0.75)

    def test_record_health_persists_json(self):
        res = ScraperHealthResult(
            filter_id="turkey_7_10",
            status="healthy",
            circuit_breaker_tripped=False,
            current_count=85,
            baseline_count=80,
            drop_pct=0.0,
            message="All good",
        )
        self.checker.record_health(res)

        self.assertTrue(os.path.exists(self.health_log))
        with open(self.health_log, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("filters", data)
        self.assertEqual(data["filters"]["turkey_7_10"]["current_count"], 85)


if __name__ == "__main__":
    unittest.main()

