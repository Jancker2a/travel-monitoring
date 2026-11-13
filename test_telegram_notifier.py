#!/usr/bin/env python3
"""
Unit tests for telegram_notifier.py, including Watchlist and Price Targets (Horizon 2.2).
"""

import json
import os
import tempfile
import unittest

from telegram_notifier import (
    FilterDataSummary,
    add_to_watchlist,
    format_hotel_alert_message,
    list_watchlist,
    match_watchlist_entry,
    remove_from_watchlist,
)


class TestTelegramWatchlist(unittest.TestCase):
    """Test suite for Watchlist matching and alert formatting."""

    def test_match_watchlist_entry_string(self):
        watchlist = ["Pickalbatros", "Rixos Premium"]

        match1 = match_watchlist_entry("Pickalbatros Aqua Park Resort", watchlist)
        self.assertIsNotNone(match1)
        self.assertEqual(match1["matched_pattern"], "pickalbatros")
        self.assertIsNone(match1["target_price"])
        self.assertTrue(match1["notify_on_any_drop"])

        match2 = match_watchlist_entry("rixos premium seagate", watchlist)
        self.assertIsNotNone(match2)
        self.assertEqual(match2["matched_pattern"], "rixos premium")

        self.assertIsNone(match_watchlist_entry("Hilton Sharks Bay", watchlist))

    def test_match_watchlist_entry_dict_with_filter_scoping(self):
        watchlist = [
            {
                "hotel_name": "Albatros Laguna",
                "target_price": 3200,
                "filter_id": "filter_sharm_1",
                "notify_on_any_drop": True,
            },
            {
                "hotel_name": "Steigenberger",
                "target_price": 4500,
                "notify_on_any_drop": False,
            },
        ]

        # Matching hotel and matching filter
        m1 = match_watchlist_entry("Albatros Laguna Vista Beach", watchlist, filter_id="filter_sharm_1")
        self.assertIsNotNone(m1)
        self.assertEqual(m1["target_price"], 3200)

        # Matching hotel but mismatched filter
        m2 = match_watchlist_entry("Albatros Laguna Vista Beach", watchlist, filter_id="filter_hurghada_2")
        self.assertIsNone(m2)

        # Global entry (no filter_id restriction)
        m3 = match_watchlist_entry("Steigenberger ALDAU Beach Hotel", watchlist, filter_id="filter_hurghada_2")
        self.assertIsNotNone(m3)
        self.assertEqual(m3["target_price"], 4500)
        self.assertFalse(m3["notify_on_any_drop"])

    def test_format_target_reached_alert(self):
        summary = FilterDataSummary(
            filter_id="test_filter",
            data_id="test_data",
            filter_title="Египет 7-10 ночей",
            filter_href="https://example.com/filter",
        )
        item = {
            "hotel_name": "Pickalbatros Aqua Blu",
            "current_price": 3150.0,
            "prev_price": 3400.0,
            "baseline_48h_price": 3500.0,
            "delta_48h_pct": -10.0,
            "delta_run_pct": -7.3,
            "deal_score": 92,
            "deal_category": "HOT DEAL",
            "is_historic_low": True,
            "confidence": "High",
            "ta_rating": 4.5,
            "ta_reviews": 1250,
            "duration": 7,
            "departure_dates": ["2026-11-15"],
            "airports": ["WAW"],
            "room_type": "Standard Room",
            "food_type": "All Inclusive",
            "hotel_url": "https://example.com/hotel",
            "operator": "Anex",
        }
        msg = format_hotel_alert_message(
            summary,
            item,
            alert_type="target_reached",
            extra_meta={"target_price": 3200.0},
        )
        self.assertIn("ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА", msg)
        self.assertIn("3 150 PLN", msg)
        self.assertIn("целевая цена: <b>≤ 3 200 PLN</b>", msg)
        self.assertIn("Pickalbatros Aqua Blu", msg)

    def test_format_watchlist_drop_alert(self):
        summary = FilterDataSummary(
            filter_id="test_filter",
            data_id="test_data",
            filter_title="Египет 7-10 ночей",
            filter_href="https://example.com/filter",
        )
        item = {
            "hotel_name": "Pickalbatros Aqua Blu",
            "current_price": 3300.0,
            "prev_price": 3600.0,
            "baseline_48h_price": 3600.0,
            "delta_48h_pct": -8.3,
            "delta_run_pct": -8.3,
            "deal_score": 85,
            "deal_category": "GOOD DEAL",
            "is_historic_low": False,
            "confidence": "Medium",
            "ta_rating": 4.5,
            "ta_reviews": 1250,
            "duration": 7,
            "departure_dates": ["2026-11-15"],
            "airports": ["WAW"],
            "room_type": "Standard Room",
            "food_type": "All Inclusive",
            "hotel_url": "https://example.com/hotel",
            "operator": "Anex",
        }
        msg = format_hotel_alert_message(
            summary,
            item,
            alert_type="watchlist_drop",
            extra_meta={"target_price": 3000.0},
        )
        self.assertIn("ОТЕЛЬ ИЗ ИЗБРАННОГО ПОДЕШЕВЕЛ", msg)
        self.assertIn("3 300 PLN", msg)
        self.assertIn("-8.3%", msg)
        self.assertIn("цель: <b>≤ 3 000 PLN</b>", msg)


class TestWatchlistManagementCLI(unittest.TestCase):
    """Test CLI add/remove/list operations on watchlist config."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "subscriptions.json")
        initial_data = {
            "version": 1,
            "subscribers": [
                {
                    "chat_id": "12345678",
                    "name": "Test User",
                    "watchlist": [
                        {"hotel_name": "Initial Hotel", "target_price": 2500}
                    ],
                }
            ],
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_watchlist(self):
        entries = list_watchlist(self.config_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["hotel_name"], "Initial Hotel")

    def test_add_to_watchlist(self):
        ok = add_to_watchlist(
            self.config_path,
            hotel_name="New Luxury Resort",
            target_price=3500,
            filter_id="turkey_filter",
        )
        self.assertTrue(ok)
        entries = list_watchlist(self.config_path)
        self.assertEqual(len(entries), 2)
        added = entries[1]
        self.assertEqual(added["hotel_name"], "New Luxury Resort")
        self.assertEqual(added["target_price"], 3500)
        self.assertEqual(added["filter_id"], "turkey_filter")

    def test_update_existing_in_watchlist(self):
        # Adding same hotel with updated target price updates existing entry
        ok = add_to_watchlist(
            self.config_path,
            hotel_name="initial hotel",
            target_price=2200,
        )
        self.assertTrue(ok)
        entries = list_watchlist(self.config_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["target_price"], 2200)

    def test_remove_from_watchlist(self):
        removed = remove_from_watchlist(self.config_path, "Initial Hotel")
        self.assertTrue(removed)
        entries = list_watchlist(self.config_path)
        self.assertEqual(len(entries), 0)

        # Removing non-existing returns False
        not_found = remove_from_watchlist(self.config_path, "Non Existing")
        self.assertFalse(not_found)


if __name__ == "__main__":
    unittest.main()
