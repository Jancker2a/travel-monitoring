#!/usr/bin/env python3
"""Unit tests for germany_monitor.py."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from germany_monitor import GermanyTourMonitor, CHECK24_AREAS, GERMANY_PRICE_CSV_FIELDS


class TestGermanyMonitor(unittest.TestCase):
    def setUp(self):
        self.config = {
            "destination": "Turkey",
            "destination_key": "turkey_antalya",
            "departure_airport": "BER",
            "travel_period": "2026-06-01_2026-06-15",
            "duration": "7-10",
            "max_pages": 2,
            "max_offers": 10,
            "output_data_file": "/tmp/test_germany_prices.csv",
        }
        self.monitor = GermanyTourMonitor(self.config)

    def test_build_search_url_default(self):
        url = self.monitor._build_search_url(page_number=1)
        self.assertIn("airport=BER", url)
        self.assertIn("areaId=578", url)
        self.assertIn("departureDate=2026-06-01", url)
        self.assertIn("returnDate=2026-06-15", url)
        self.assertIn("days=7-10", url)
        self.assertNotIn("page=", url)

    def test_build_search_url_pagination(self):
        url = self.monitor._build_search_url(page_number=2)
        self.assertIn("page=2", url)

    def test_check24_areas_coverage(self):
        self.assertIn("turkey_antalya", CHECK24_AREAS)
        self.assertIn("egypt_hurghada", CHECK24_AREAS)
        self.assertIn("egypt_sharm", CHECK24_AREAS)
        self.assertIn("greece_crete", CHECK24_AREAS)

    def test_map_polish_config_to_germany_params(self):
        from germany_monitor import map_polish_config_to_germany_params

        # 1. Egypt filter with Russian title and fly.pl destinationLocation=11:
        cfg_eg = {
            "url": "https://fly.pl/szukaj-wycieczek/?destinationLocation=11:&startDateMin=28-05-2026&returnDate=30-06-2026&adults=2&children=10-12-2020&durationFrom=7&durationTo=10",
            "description": "CI filter • 7-10 дней • сбор 4000-20000 PLN, показ ≤10000",
            "required_offer_url_contains": ["/wycieczka/egipt"],
            "data_dir": "data/filters/filter_7_10_days",
            "dynamic_search_dates": False,
        }
        mapped_eg = map_polish_config_to_germany_params(cfg_eg, "config_ci_filter_7_10.json")
        self.assertEqual(mapped_eg['destination'], 'Egypt')
        self.assertEqual(mapped_eg['area_id'], 673)
        self.assertEqual(mapped_eg['travel_period'], '2026-05-28_2026-06-30')
        self.assertEqual(mapped_eg['duration'], '8-11')
        self.assertEqual(mapped_eg['room_allocation'], 'A-A-6')

        # 2. Sharm El Sheikh 1-person trip (destinationLocation=11_154)
        cfg_sharm = {
            "dynamic_search_dates": False,
            "url": "https://fly.pl/szukaj-wycieczek/?destinationLocation=11_154&startDateMin=20-12-2026&returnDate=29-12-2026&adults=1&durationFrom=7&durationTo=15",
            "description": "Египет • Шарм • 20-29 декабря • 1 человек",
        }
        mapped_sharm = map_polish_config_to_germany_params(cfg_sharm, "config_ci_filter_egypt_sharm_dec20_29_1p.json")
        self.assertEqual(mapped_sharm['destination'], 'Egypt')
        self.assertEqual(mapped_sharm['area_id'], 674)
        self.assertEqual(mapped_sharm['room_allocation'], 'A')
        self.assertEqual(mapped_sharm['travel_period'], '2026-12-20_2026-12-29')

        # 3. Greece filter (destinationLocation=14:)
        cfg_gr = {
            "url": "https://fly.pl/szukaj-wycieczek/?destinationLocation=14:&startDateMin=31-05-2026&returnDate=30-06-2026&adults=2&durationFrom=7&durationTo=10",
            "description": "Греция • 7-10 дней",
        }
        mapped_gr = map_polish_config_to_germany_params(cfg_gr, "config_ci_filter_greece_7_10.json")
        self.assertEqual(mapped_gr['destination'], 'Greece')
        self.assertEqual(mapped_gr['area_id'], 603)

    def test_save_offers_schema(self):
        import tempfile, os, csv
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            temp_path = f.name

        try:
            self.monitor.output_csv = temp_path
            mock_offers = [{
                'hotel_name': 'Test Hotel',
                'price': 999.0,
                'dates': '01.06 - 08.06',
                'duration': '7 Tage',
                'destination': 'Turkey',
                'location': 'Antalya',
                'departure_airport': 'BER',
                'scraped_at': '2026-10-20T12:00:00Z',
                'offer_url': 'https://urlaub.check24.de/test',
            }]
            saved = self.monitor.save_offers_to_csv(mock_offers)
            self.assertEqual(saved, temp_path)

            with open(temp_path, 'r', encoding='utf-8') as f:
                reader = list(csv.DictReader(f))
                self.assertEqual(len(reader), 1)
                self.assertEqual(reader[0]['hotel_name'], 'Test Hotel')
                self.assertEqual(float(reader[0]['price']), 999.0)
                self.assertEqual(reader[0]['departure_airport'], 'BER')
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == '__main__':
    unittest.main()
