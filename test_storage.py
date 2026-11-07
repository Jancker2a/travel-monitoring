#!/usr/bin/env python3
"""
Unit tests for the storage package (TravelDatabase, PriceRepository, Migrator).
"""

import os
import tempfile
import unittest

import pandas as pd

from storage.database import TravelDatabase
from storage.migrator import export_filter_to_csv, import_csv_to_db
from storage.repository import PriceRepository


class TestStoragePackage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_travel.db")
        self.db = TravelDatabase(self.db_path)
        self.repo = PriceRepository(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initialization(self):
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM schema_meta WHERE key = 'schema_version';")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "1")
        finally:
            conn.close()

    def test_save_and_query_scrape_run(self):
        offers_run1 = [
            {"hotel_name": "Rixos Premium", "price": 4500, "scraped_at": "2026-11-01T10:00:00Z"},
            {"hotel_name": "Viva Sharm", "price": 1800, "scraped_at": "2026-11-01T10:00:00Z"},
        ]
        self.repo.save_scrape_run(
            filter_id="test_filter",
            offers=offers_run1,
            scraped_at="2026-11-01T10:00:00Z",
        )

        offers_run2 = [
            {"hotel_name": "Rixos Premium", "price": 4200, "scraped_at": "2026-11-02T10:00:00Z"},
            {"hotel_name": "Viva Sharm", "price": 1900, "scraped_at": "2026-11-02T10:00:00Z"},
        ]
        self.repo.save_scrape_run(
            filter_id="test_filter",
            offers=offers_run2,
            scraped_at="2026-11-02T10:00:00Z",
        )

        # 1. Total count
        self.assertEqual(self.repo.count_offers("test_filter"), 4)

        # 2. Latest slice should only return the 2 offers from run2 (2026-11-02)
        latest_df = self.repo.get_latest_slice("test_filter")
        self.assertEqual(len(latest_df), 2)
        # Lowest price first
        self.assertEqual(latest_df.iloc[0]["hotel_name"], "Viva Sharm")
        self.assertEqual(latest_df.iloc[0]["price"], 1900.0)
        self.assertEqual(latest_df.iloc[1]["hotel_name"], "Rixos Premium")
        self.assertEqual(latest_df.iloc[1]["price"], 4200.0)

        # 3. Hotel history
        rixos_hist = self.repo.get_hotel_price_history("Rixos Premium", filter_id="test_filter")
        self.assertEqual(len(rixos_hist), 2)
        self.assertEqual(list(rixos_hist["price"]), [4500.0, 4200.0])

        # 4. Price range
        min_p, max_p = self.repo.get_price_range("test_filter")
        self.assertEqual(min_p, 1800.0)
        self.assertEqual(max_p, 4500.0)

        # 5. Filter dataframe & All offers dataframe
        filter_df = self.repo.get_filter_dataframe("test_filter")
        self.assertEqual(len(filter_df), 4)

        all_df = self.repo.get_all_offers_df(min_price=2000.0)
        self.assertEqual(len(all_df), 2)

    def test_csv_import_and_export_roundtrip(self):
        sample_csv = os.path.join(self.temp_dir.name, "sample.csv")
        sample_data = pd.DataFrame([
            {
                "hotel_name": "Albatros Aqua Park",
                "price": 2500.0,
                "dates": "10.12 - 17.12",
                "duration": "7 dni",
                "duration_bucket": "7_10",
                "rating": "5.0",
                "ta_rating": 4.5,
                "ta_review_count": 1200,
                "ta_source": "fly.pl",
                "departure_airport": "WAW",
                "scraped_at": "2026-11-05T12:00:00Z",
                "url": "https://example.com/search",
                "image_url": "https://example.com/img.jpg",
                "offer_url": "https://example.com/offer",
            },
            {
                "hotel_name": "Albatros Aqua Park",
                "price": 2400.0,
                "dates": "10.12 - 17.12",
                "duration": "7 dni",
                "duration_bucket": "7_10",
                "rating": "5.0",
                "ta_rating": 4.5,
                "ta_review_count": 1200,
                "ta_source": "fly.pl",
                "departure_airport": "WAW",
                "scraped_at": "2026-11-06T12:00:00Z",
                "url": "https://example.com/search",
                "image_url": "https://example.com/img.jpg",
                "offer_url": "https://example.com/offer",
            },
        ])
        sample_data.to_csv(sample_csv, index=False)

        # Import
        imported_count = import_csv_to_db(sample_csv, "filter_albatros", self.repo)
        self.assertEqual(imported_count, 2)
        self.assertEqual(self.repo.count_offers("filter_albatros"), 2)

        # Export back
        exported_csv = os.path.join(self.temp_dir.name, "exported.csv")
        exported_count = export_filter_to_csv("filter_albatros", exported_csv, self.repo)
        self.assertEqual(exported_count, 2)

        # Validate identical contents
        reloaded_df = pd.read_csv(exported_csv)
        self.assertEqual(len(reloaded_df), 2)
        self.assertEqual(reloaded_df.iloc[0]["price"], 2500.0)
        self.assertEqual(reloaded_df.iloc[1]["price"], 2400.0)
        self.assertEqual(reloaded_df.iloc[0]["hotel_name"], "Albatros Aqua Park")

    def test_travel_monitor_dual_write(self):
        """Verifies that TravelPriceMonitor saves to both CSV and SQLite concurrently."""
        from travel_monitor import TravelPriceMonitor

        config = {
            "url": "https://example.com/search",
            "filter_mode": "fixed_trip",
            "dynamic_search_dates": False,
            "data_dir": self.temp_dir.name,
            "output_data_file": "dual_test_prices.csv",
            "database_path": self.db_path,
            "filter_id": "filter_dual_test",
        }
        monitor = TravelPriceMonitor(config)

        sample_offers = [
            {
                "hotel_name": "Sunrise Resort",
                "price": 3100.0,
                "dates": "01.12 - 08.12",
                "duration": "8 dni",
                "duration_bucket": "7_10",
                "departure_airport": "WAW",
                "url": "https://example.com/sunrise",
                "offer_url": "https://example.com/sunrise/offer",
                "scraped_at": "2026-11-07T10:00:00Z",
            },
            {
                "hotel_name": "Baron Palms",
                "price": 4200.0,
                "dates": "01.12 - 08.12",
                "duration": "8 dni",
                "duration_bucket": "7_10",
                "departure_airport": "WAW",
                "url": "https://example.com/baron",
                "offer_url": "https://example.com/baron/offer",
                "scraped_at": "2026-11-07T10:00:00Z",
            },
        ]

        # 1. Trigger save_data_append
        monitor.save_data_append(sample_offers)

        # 2. Verify CSV was written
        csv_file = os.path.join(self.temp_dir.name, "dual_test_prices.csv")
        self.assertTrue(os.path.exists(csv_file))
        df_csv = pd.read_csv(csv_file)
        self.assertEqual(len(df_csv), 2)
        self.assertEqual(list(df_csv["hotel_name"]), ["Sunrise Resort", "Baron Palms"])

        # 3. Verify SQLite received the exact same data
        db_count = self.repo.count_offers("filter_dual_test")
        self.assertEqual(db_count, 2)

        latest_slice = self.repo.get_latest_slice("filter_dual_test")
        self.assertEqual(len(latest_slice), 2)
        hotel_names = set(latest_slice["hotel_name"])
        self.assertEqual(hotel_names, {"Sunrise Resort", "Baron Palms"})
        prices = dict(zip(latest_slice["hotel_name"], latest_slice["price"]))
        self.assertEqual(prices["Sunrise Resort"], 3100.0)
        self.assertEqual(prices["Baron Palms"], 4200.0)


if __name__ == "__main__":
    unittest.main()
