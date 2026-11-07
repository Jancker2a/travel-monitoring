#!/usr/bin/env python3
"""Run all unit test suites for Travel Price Monitor."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_MODULES = [
    "test_ai_market_oracle",
    "test_arbitrage_engine",
    "test_early_booking_analyzer",
    "test_filter_scope",
    "test_germany_monitor",
    "test_hopper_learner",
    "test_hopper_prediction",
    "test_hotel_catalog",
    "test_hotel_name_normalizer",
    "test_hotel_repository",
    "test_scraper_healthcheck",
    "test_storage",
    "test_metrics_simulation",
    "test_tripadvisor_extractor",
]


def main() -> int:
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    for mod_name in TEST_MODULES:
        try:
            mod = __import__(mod_name)
            suite.addTests(loader.loadTestsFromModule(mod))
        except Exception as e:
            print(f"❌ Failed to load test module {mod_name}: {e}", file=sys.stderr)
            return 1

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

