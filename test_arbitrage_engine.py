#!/usr/bin/env python3
"""
Unit tests for Cross-Border Arbitrage Engine and Hotel Entity Matcher.
"""

import unittest
import pandas as pd

from hotel_entity_matcher import (
    clean_hotel_name,
    calculate_hotel_similarity,
    HotelEntityMatcher,
)
from cross_border_arbitrage import (
    CrossBorderArbitrageEngine,
    get_eur_pln_exchange_rate,
)
from germany_tour_client import GermanTourOffer, GermanyTourClient


class TestArbitrageEngine(unittest.TestCase):
    def test_clean_hotel_name(self):
        # Strips operator codes in parentheses
        cleaned1 = clean_hotel_name("Delphin Imperial Resort & Spa (AYT12045)")
        self.assertIn("delphin", cleaned1)
        self.assertIn("imperial", cleaned1)
        self.assertNotIn("ayt12045", cleaned1)
        self.assertNotIn("spa", cleaned1)

        # Strips (ex. former name)
        cleaned2 = clean_hotel_name("Casa Mare Resort (ex. Royal Tulip Beach Resort)")
        self.assertIn("casa", cleaned2)
        self.assertIn("mare", cleaned2)
        self.assertNotIn("tulip", cleaned2)

    def test_calculate_hotel_similarity(self):
        # High similarity for slightly differing naming conventions
        score = calculate_hotel_similarity(
            "Delphin Imperial Hotel Lara",
            "Delphin Imperial Resort & Spa (AYT)",
        )
        self.assertGreaterEqual(score, 0.80)

        # Different hotels should have low score
        diff_score = calculate_hotel_similarity(
            "Delphin Imperial Hotel Lara",
            "Rixos Premium Belek",
        )
        self.assertLess(diff_score, 0.40)

    def test_hotel_entity_matcher(self):
        matcher = HotelEntityMatcher(similarity_threshold=0.75)
        candidates = [
            "Rixos Premium Belek Resort",
            "Delphin Imperial Resort & Spa",
            "Amarina Queen Resort & Aqua Park",
        ]
        match = matcher.match_hotel("Delphin Imperial Hotel", candidates)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "Delphin Imperial Resort & Spa")

    def test_arbitrage_spread_calculation(self):
        # Fixed rate: 4.30 PLN/EUR, Friction: 250 PLN
        engine = CrossBorderArbitrageEngine(eur_rate=4.30, friction_cost_pln=250.0)

        # Poland price: 10,000 PLN
        # Germany price: 1,500 EUR -> 1,500 * 4.30 = 6,450 PLN + 250 friction = 6,700 PLN net
        # Spread = 10,000 - 6,700 = 3,300 PLN savings!
        pl_offers = [
            {
                "hotel_name": "Delphin Imperial Hotel",
                "price": 10000.0,
                "dates": "06.06.2026 - 13.06.2026",
                "departure_airport": "WAW",
            }
        ]
        de_offers = [
            GermanTourOffer(
                hotel_name="Delphin Imperial Resort & Spa",
                destination="Antalya",
                departure_airport="BER",
                dates="06.06.2026 - 13.06.2026",
                duration_days=8,
                board_type="All Inclusive",
                price_eur=1500.0,
                tour_operator="TUI Deutschland",
                offer_url="https://urlaub.check24.de/test",
                scraped_at="2026-10-20T10:00:00",
            )
        ]

        matches = engine.compare_offers(pl_offers, de_offers)
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.best_deal, "GERMANY")
        self.assertEqual(m.spread_pln, 3300.0)
        self.assertEqual(m.savings_pct, 33.0)
        self.assertIn("ВЫГОДНЕЕ В БЕРЛИНЕ", m.badge_text)

    def test_arbitrage_when_poland_is_cheaper(self):
        engine = CrossBorderArbitrageEngine(eur_rate=4.30, friction_cost_pln=250.0)
        pl_offers = [
            {
                "hotel_name": "Amarina Queen Resort",
                "price": 5000.0,
                "dates": "06.06.2026 - 13.06.2026",
                "departure_airport": "WAW",
            }
        ]
        de_offers = [
            GermanTourOffer(
                hotel_name="Amarina Queen Resort & Aqua Park",
                destination="Hurghada",
                departure_airport="BER",
                dates="06.06.2026 - 13.06.2026",
                duration_days=8,
                board_type="All Inclusive",
                price_eur=1400.0,  # 1400 * 4.30 + 250 = 6270 PLN (more expensive than PL)
                tour_operator="Alltours",
                offer_url="https://urlaub.check24.de/test",
                scraped_at="2026-10-20T10:00:00",
            )
        ]
        matches = engine.compare_offers(pl_offers, de_offers)
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.best_deal, "POLAND")
        self.assertLess(m.spread_pln, 0)
        self.assertIn("Польша дешевле", m.badge_text)

    def test_offer_comparability_filter(self):
        engine = CrossBorderArbitrageEngine(eur_rate=4.30, max_date_diff_days=3, max_duration_diff_days=2)
        pl_offers = [
            {
                "hotel_name": "Delphin Imperial Hotel",
                "price": 10000.0,
                "dates": "06.06.2026 - 13.06.2026",
                "duration": "8 dni",
                "departure_airport": "WAW",
            }
        ]
        # Incompatible German offer: 5 months later (October) and 14 days duration
        de_offers_incompatible = [
            GermanTourOffer(
                hotel_name="Delphin Imperial Resort & Spa",
                destination="Antalya",
                departure_airport="BER",
                dates="15.10.2026 - 29.10.2026",
                duration_days=14,
                board_type="All Inclusive",
                price_eur=1200.0,
                tour_operator="TUI Deutschland",
                offer_url="https://urlaub.check24.de/test",
                scraped_at="2026-10-20T10:00:00",
            )
        ]
        matches = engine.compare_offers(pl_offers, de_offers_incompatible)
        # Must be rejected because dates (June vs October) and duration (8d vs 14d) differ
        self.assertEqual(len(matches), 0)

    def test_filter_western_german_airports(self):
        engine = CrossBorderArbitrageEngine(eur_rate=4.30)
        pl_offers = [
            {
                "hotel_name": "Delphin Imperial Hotel",
                "price": 10000.0,
                "dates": "06.06.2026 - 13.06.2026",
                "duration": "8 dni",
                "departure_airport": "WAW",
            }
        ]
        # Western / Southern German airports (too far to drive from Poland)
        de_offers_far = [
            GermanTourOffer(
                hotel_name="Delphin Imperial Resort & Spa",
                destination="Antalya",
                departure_airport="FRA",  # Frankfurt am Main (800+ km from Poland)
                dates="06.06.2026 - 13.06.2026",
                duration_days=8,
                board_type="All Inclusive",
                price_eur=1000.0,
                tour_operator="TUI Deutschland",
                offer_url="https://urlaub.check24.de/test",
                scraped_at="2026-10-20T10:00:00",
            ),
            GermanTourOffer(
                hotel_name="Delphin Imperial Resort & Spa",
                destination="Antalya",
                departure_airport="MUC",  # Munich (700+ km from Poland)
                dates="06.06.2026 - 13.06.2026",
                duration_days=8,
                board_type="All Inclusive",
                price_eur=1000.0,
                tour_operator="TUI Deutschland",
                offer_url="https://urlaub.check24.de/test",
                scraped_at="2026-10-20T10:00:00",
            ),
        ]
        matches = engine.compare_offers(pl_offers, de_offers_far)
        # Must be rejected because FRA and MUC are not allowed border hubs
        self.assertEqual(len(matches), 0)

    def test_is_offer_comparable_wide_window_rejection(self):
        from cross_border_arbitrage import is_offer_comparable

        # 1. Wide 2-month window (Check24 default) with December departure must be REJECTED
        ok, reason = is_offer_comparable(
            dates_pl="20.12.2026 - 29.12.2026",
            dates_de="2026-10-27_2026-12-22",
            duration_pl="8 dni",
            duration_de="5 Tage",
            offer_url_de="https://urlaub.check24.de/suche/angebot?departureDate=2026-10-27&returnDate=2026-12-22&days=5-9&hotelId=25",
        )
        self.assertFalse(ok)
        self.assertIn("Dates mismatch", reason)

        # 2. Narrow matching window (20-29 Dec) must be ACCEPTED
        ok_valid, reason_valid = is_offer_comparable(
            dates_pl="20.12.2026 - 29.12.2026",
            dates_de="2026-12-20_2026-12-29",
            duration_pl="8 dni",
            duration_de="8 Tage",
            offer_url_de="https://urlaub.check24.de/suche/angebot?departureDate=2026-12-20&returnDate=2026-12-29&days=8-10&hotelId=25948",
        )
        self.assertTrue(ok_valid)
        self.assertEqual(reason_valid, "OK")

        # 3. Duration mismatch (> 2 days difference) must be REJECTED
        ok_dur, reason_dur = is_offer_comparable(
            dates_pl="20.12.2026 - 29.12.2026",
            dates_de="2026-12-20_2026-12-29",
            duration_pl="8 dni",
            duration_de="5 Tage",
        )
        self.assertFalse(ok_dur)
        self.assertIn("Duration mismatch", reason_dur)

    def test_germany_tour_client_parses_duration(self):
        import tempfile, csv, os
        from germany_tour_client import GermanyTourClient

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["hotel_name", "price", "dates", "duration", "destination", "location", "departure_airport", "scraped_at", "offer_url"])
            writer.writerow(["Pickalbatros Palace Resort", "631.0", "2026-12-20_2026-12-29", "5 Tage | 1 Pers.", "Egypt", "Sharm el Sheikh", "BER", "2026-10-20T12:00:00", "https://urlaub.check24.de/suche/angebot?hotelId=25948"])
            writer.writerow(["Delphin Imperial", "1200.0", "2026-06-01_2026-06-15", "10 Tage", "Turkey", "Antalya", "BER", "2026-10-20T12:00:00", "https://urlaub.check24.de/suche/angebot?hotelId=555"])
            tmp_csv = f.name

        try:
            client = GermanyTourClient()
            offers = client.load_offers_from_csv(tmp_csv, destination_filter="egypt_sharm")
            self.assertEqual(len(offers), 1)
            # Duration must be 5 days, NOT hardcoded 8
            self.assertEqual(offers[0].duration_days, 5)
            self.assertEqual(offers[0].offer_url, "https://urlaub.check24.de/suche/angebot?hotelId=25948")
        finally:
            if os.path.exists(tmp_csv):
                os.remove(tmp_csv)

    def test_compare_offers_prefers_direct_hotel_url(self):
        engine = CrossBorderArbitrageEngine(eur_rate=4.30)
        pl_offers = [
            {
                "hotel_name": "Pickalbatros Palace Resort",
                "price": 7569.0,
                "dates": "20.12.2026 - 27.12.2026",
                "duration": "8 dni",
                "departure_airport": "KTW",
                "url": "https://fly.pl/szukaj-wycieczek/?destinationLocation=11_154",
                "offer_url": "https://fly.pl/wycieczka/egipt,sharm-el-sheikh/pickalbatros-palace-resort/?objectId=26358",
            }
        ]
        de_offers = [
            GermanTourOffer(
                hotel_name="Pickalbatros Palace Resort",
                destination="Sharm El Sheikh",
                departure_airport="BER",
                dates="2026-12-20_2026-12-29",
                duration_days=8,
                board_type="All Inclusive",
                price_eur=1120.0,
                tour_operator="TUI DE",
                offer_url="https://urlaub.check24.de/suche/angebot?hotelId=25948&days=8",
                scraped_at="2026-10-20T12:00:00",
            )
        ]
        matches = engine.compare_offers(pl_offers, de_offers)
        self.assertEqual(len(matches), 1)
        # Must prefer direct hotel tour URL over search filter URL
        self.assertEqual(
            matches[0].url_pl,
            "https://fly.pl/wycieczka/egipt,sharm-el-sheikh/pickalbatros-palace-resort/?objectId=26358"
        )
        self.assertNotIn("szukaj-wycieczek", matches[0].url_pl)


    def test_parse_duration_days(self):
        from cross_border_arbitrage import parse_duration_days
        import math
        self.assertEqual(parse_duration_days(7), 7)
        self.assertEqual(parse_duration_days("8 dni"), 8)
        self.assertEqual(parse_duration_days("10 Tage"), 10)
        self.assertEqual(parse_duration_days(7.0), 7)
        self.assertIsNone(parse_duration_days(None))
        self.assertIsNone(parse_duration_days(float("nan")))
        self.assertIsNone(parse_duration_days("nan"))
        self.assertIsNone(parse_duration_days(""))

    def test_traveler_composition_strict_match(self):
        from cross_border_arbitrage import is_offer_comparable
        # 2+1 vs 2+0 must be REJECTED
        ok, reason = is_offer_comparable(
            dates_pl="29.10.2026 - 05.11.2026",
            dates_de="2026-10-29",
            duration_pl="8 dni/7 nocy",
            duration_de="8 Tage",
            offer_url_pl="https://fly.pl/.../?adults=2&children=2020-12-10",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A-A",
        )
        self.assertFalse(ok)
        self.assertIn("Children mismatch", reason)

        # 2+1 vs 2+1 must be ACCEPTED (both comma and hyphen Check24 syntax with matching 7 nights)
        ok_same, reason_same = is_offer_comparable(
            dates_pl="29.10.2026 - 05.11.2026",
            dates_de="2026-10-29",
            duration_pl="8 dni/7 nocy",
            duration_de="8 Tage",
            offer_url_pl="https://fly.pl/.../?adults=2&children=2020-12-10",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A-A,6",
        )
        self.assertTrue(ok_same)

        ok_hyphen, _ = is_offer_comparable(
            dates_pl="29.10.2026 - 05.11.2026",
            dates_de="2026-10-29",
            duration_pl="8 dni/7 nocy",
            duration_de="8 Tage",
            offer_url_pl="https://fly.pl/.../?adults=2&children=2020-12-10",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A-A-6",
        )
        self.assertTrue(ok_hyphen)

    def test_nights_strict_match(self):
        from cross_border_arbitrage import is_offer_comparable
        # 7 nights (8 dni) vs 6 nights (7 Tage) must be REJECTED
        ok_6n, reason_6n = is_offer_comparable(
            dates_pl="20.12.2026 - 27.12.2026",
            dates_de="2026-12-20",
            duration_pl="8 dni/7 nocy",
            duration_de="7 Tage",
            offer_url_pl="https://fly.pl/.../?adults=1",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A",
        )
        self.assertFalse(ok_6n)
        self.assertIn("Duration mismatch", reason_6n)

        # 7 nights vs 5 days (4 nights) must be REJECTED
        ok, reason = is_offer_comparable(
            dates_pl="29.10.2026 - 05.11.2026",
            dates_de="2026-10-29",
            duration_pl="8 dni/7 nocy",
            duration_de="5 Tage",
            offer_url_pl="https://fly.pl/.../?adults=2",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A-A",
        )
        self.assertFalse(ok)
        self.assertIn("Duration mismatch", reason)

        # Integer duration_days: 7 days (6 nights) vs '8 dni' (7 nights) must be REJECTED
        ok_int7, reason_int7 = is_offer_comparable(
            dates_pl="20.12.2026 - 27.12.2026",
            dates_de="2026-12-20",
            duration_pl="8 dni",
            duration_de=7,
            offer_url_pl="https://fly.pl/.../?adults=1",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A",
        )
        self.assertFalse(ok_int7)
        self.assertIn("Duration mismatch", reason_int7)

        # Integer duration_days: 8 days (7 nights) vs '8 dni' (7 nights) must be ACCEPTED
        ok_int8, _ = is_offer_comparable(
            dates_pl="20.12.2026 - 27.12.2026",
            dates_de="2026-12-20",
            duration_pl="8 dni",
            duration_de=8,
            offer_url_pl="https://fly.pl/.../?adults=1",
            offer_url_de="https://urlaub.check24.de/.../?roomAllocation=A&days=8-10",
        )
        self.assertTrue(ok_int8)

        # Check24 URL days=7-10 allows 6-night tours, so must be REJECTED against 7-night Polish tour
        ok_url7, reason_url7 = is_offer_comparable(
            dates_pl="20.12.2026 - 27.12.2026",
            dates_de="2026-12-20",
            duration_pl="8 dni",
            duration_de="8 Tage",
            offer_url_pl="https://fly.pl/.../?adults=1",
            offer_url_de="https://urlaub.check24.de/suche/angebot?days=7-10&departureDate=2026-12-20&roomAllocation=A",
        )
        self.assertFalse(ok_url7)
        self.assertIn("allows tours shorter", reason_url7)

        # Test monthly monitoring window (up to 35 days)
        ok_win, _ = is_offer_comparable(
            dates_pl="03.11.2026 - 10.11.2026",
            dates_de="2026-10-22_2026-11-21",
            duration_pl="8 dni",
            duration_de="8 Tage",
            offer_url_pl="https://fly.pl/.../?adults=2",
            offer_url_de="https://urlaub.check24.de/suche/angebot?days=8-11&departureDate=2026-10-22&returnDate=2026-11-21&roomAllocation=A-A",
        )
        self.assertTrue(ok_win)

        # Date outside the monthly window must be rejected
        ok_out, reason_out = is_offer_comparable(
            dates_pl="01.12.2026 - 08.12.2026",
            dates_de="2026-10-22_2026-11-21",
            duration_pl="8 dni",
            duration_de="8 Tage",
            offer_url_pl="https://fly.pl/.../?adults=2",
            offer_url_de="https://urlaub.check24.de/suche/angebot?days=8-11&departureDate=2026-10-22&returnDate=2026-11-21&roomAllocation=A-A",
        )
        self.assertFalse(ok_out)
        self.assertIn("Dates mismatch", reason_out)

    def test_german_tour_offer_duration_field(self):
        offer = GermanTourOffer(
            hotel_name="Test Hotel",
            destination="Egypt",
            departure_airport="BER",
            dates="2026-12-20",
            duration_days=8,
            board_type="All Inclusive",
            price_eur=500.0,
            tour_operator="Test",
            offer_url="https://urlaub.check24.de",
            scraped_at="2026-10-21T12:00:00",
        )
        d = offer.to_dict()
        self.assertEqual(d["duration"], "8 Tage")
        self.assertEqual(d["duration_days"], 8)


    def test_hotel_entity_matcher_prevents_false_positives(self):
        # 1. 'The Grand Hotel Sharm El Sheikh' must NEVER match luxury hotels in the same region
        self.assertEqual(
            calculate_hotel_similarity("Rixos Sharm el Sheikh", "The Grand Hotel Sharm El Sheikh"),
            0.0,
        )
        self.assertEqual(
            calculate_hotel_similarity("Rixos Radamis Sharm El Sheikh", "The Grand Hotel Sharm El Sheikh"),
            0.0,
        )
        self.assertEqual(
            calculate_hotel_similarity("Baron Palms Sharm El Sheikh", "The Grand Hotel Sharm El Sheikh"),
            0.0,
        )
        self.assertEqual(
            calculate_hotel_similarity("Pickalbatros Palace Resort - Sharm El Sheikh", "The Grand Hotel Sharm El Sheikh"),
            0.0,
        )

        # 2. 'The Grand Hotel' matches 'Grand Hotel Sharm El Sheikh'
        grand_score = calculate_hotel_similarity("The Grand Hotel", "Grand Hotel Sharm El Sheikh")
        self.assertGreaterEqual(grand_score, 0.85)

        # 3. Conflicting brands in the same region must be 0.0
        self.assertEqual(
            calculate_hotel_similarity("Rixos Premium Belek", "Delphin Imperial Lara"),
            0.0,
        )

        # 4. Conflicting sub-properties in the same chain must not match (e.g. Remal vs Diamond)
        chain_score = calculate_hotel_similarity("Sunrise Remal Resort", "Sunrise Diamond Beach Resort")
        self.assertLess(chain_score, 0.70)

        # 5. Conflicting major geographic regions must not match
        geo_score = calculate_hotel_similarity("Hilton Hurghada Plaza", "Hilton Sharks Bay Resort")
        self.assertEqual(geo_score, 0.0)


if __name__ == "__main__":
    unittest.main()



