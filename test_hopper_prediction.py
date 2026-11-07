#!/usr/bin/env python3
"""
Unit tests for Hopper-Style Predictive Engine using standard unittest.
"""

from datetime import date
import unittest
import pandas as pd

from hopper_prediction_engine import (
    calculate_days_to_departure,
    get_d_bucket,
    get_price_tier,
    parse_departure_date,
    predict_offer_action,
    batch_predict_offers,
)


class TestHopperPrediction(unittest.TestCase):
    def test_parse_departure_date(self):
        self.assertEqual(parse_departure_date("01.06.2026 - 08.06.2026"), date(2026, 6, 1))
        self.assertEqual(parse_departure_date("15.10 - 22.10.2026"), date(2026, 10, 15))
        self.assertEqual(parse_departure_date("2026-11-05"), date(2026, 11, 5))
        self.assertEqual(parse_departure_date("23.10 - 30.10", reference_date=date(2026, 10, 20)), date(2026, 10, 23))
        self.assertEqual(parse_departure_date("23.10 - 30.10 (8 dni)", reference_date=date(2026, 10, 20)), date(2026, 10, 23))
        self.assertEqual(parse_departure_date("15.01 - 22.01", reference_date=date(2026, 10, 20)), date(2027, 1, 15))
        self.assertEqual(
            parse_departure_date("", offer_url="https://fly.pl/wycieczka/?departureDate=2026-10-23&returnDate=2026-10-30"),
            date(2026, 10, 23),
        )
        self.assertIsNone(parse_departure_date("invalid_date"))
        self.assertIsNone(parse_departure_date(""))
        self.assertIsNone(parse_departure_date(None))

    def test_calculate_days_to_departure(self):
        dep = date(2026, 6, 10)
        ref = date(2026, 6, 1)
        self.assertEqual(calculate_days_to_departure(dep, ref), 9)

        # Past date
        ref_past = date(2026, 6, 15)
        self.assertEqual(calculate_days_to_departure(dep, ref_past), -5)

    def test_get_d_bucket(self):
        self.assertEqual(get_d_bucket(1), "last_minute")
        self.assertEqual(get_d_bucket(3), "last_minute")
        self.assertEqual(get_d_bucket(7), "panic_dump")
        self.assertEqual(get_d_bucket(14), "panic_dump")
        self.assertEqual(get_d_bucket(20), "mid_term")
        self.assertEqual(get_d_bucket(45), "early_bird")

    def test_get_price_tier(self):
        self.assertEqual(get_price_tier(0.10), "low")
        self.assertEqual(get_price_tier(0.25), "low")
        self.assertEqual(get_price_tier(0.50), "mid")
        self.assertEqual(get_price_tier(0.75), "mid")
        self.assertEqual(get_price_tier(0.85), "high")

    def test_predict_expired_offer(self):
        offer = {
            "dates": "01.05.2026 - 08.05.2026",
            "price": 5000,
        }
        ref_date = date(2026, 5, 10)
        pred = predict_offer_action(offer, reference_date=ref_date)
        self.assertEqual(pred.verdict, "EXPIRED")
        self.assertLess(pred.days_to_departure, 0)

    def test_predict_last_minute_floor(self):
        # 2 days to departure, reasonable price -> BUY_NOW
        offer = {
            "dates": "12.06.2026 - 19.06.2026",
            "price": 4200,
        }
        history = pd.DataFrame({
            "dates": ["12.06.2026 - 19.06.2026"] * 5,
            "price": [5000, 4800, 4500, 4300, 4200],
            "scraped_at": ["2026-06-01", "2026-06-03", "2026-06-05", "2026-06-08", "2026-06-10"],
        })
        ref_date = date(2026, 6, 10)
        pred = predict_offer_action(offer, history_df=history, reference_date=ref_date)
        self.assertEqual(pred.verdict, "BUY_NOW")
        self.assertEqual(pred.days_to_departure, 2)
        self.assertIn("риск закрытия продажи", pred.reasoning.lower())

    def test_predict_wait_in_yield_window(self):
        # 12 days to departure, price is currently high, past trajectory shows drops
        offer = {
            "dates": "24.06.2026 - 01.07.2026",
            "price": 7500,
            "hotel_name": "Grand Resort",
        }
        history = pd.DataFrame({
            "hotel_name": ["Grand Resort"] * 6,
            "dates": ["24.06.2026 - 01.07.2026"] * 6,
            "price": [7800, 7700, 7600, 7500, 5800, 5500],
            "scraped_at": ["2026-05-20", "2026-05-25", "2026-06-01", "2026-06-12", "2026-06-17", "2026-06-20"],
        })
        ref_date = date(2026, 6, 12)  # D = 12 (panic dump window)
        pred = predict_offer_action(offer, history_df=history, reference_date=ref_date)
        self.assertIn(pred.verdict, ("WAIT", "OVERPRICED"))
        self.assertEqual(pred.days_to_departure, 12)
        self.assertLess(pred.target_price, 7500)
        self.assertGreater(pred.expected_savings, 0)

    def test_predict_overpriced_spike(self):
        # Price is 30% above median
        offer = {
            "dates": "15.07.2026 - 22.07.2026",
            "price": 9500,
            "hotel_name": "Spike Hotel",
        }
        history = pd.DataFrame({
            "hotel_name": ["Spike Hotel"] * 5,
            "dates": ["15.07.2026 - 22.07.2026"] * 5,
            "price": [6000, 6200, 6100, 6050, 6300],
            "scraped_at": ["2026-06-01", "2026-06-05", "2026-06-10", "2026-06-15", "2026-06-20"],
        })
        ref_date = date(2026, 6, 25)
        pred = predict_offer_action(offer, history_df=history, reference_date=ref_date)
        self.assertEqual(pred.verdict, "OVERPRICED")
        self.assertIn("выше типичной", pred.reasoning.lower())

    def test_batch_predict_offers(self):
        df = pd.DataFrame([
            {"hotel_name": "Hotel A", "dates": "10.08.2026 - 17.08.2026", "price": 4000, "scraped_at": "2026-08-01"},
            {"hotel_name": "Hotel B", "dates": "10.08.2026 - 17.08.2026", "price": 8000, "scraped_at": "2026-08-01"},
        ])
        enriched = batch_predict_offers(df, reference_date=date(2026, 8, 1))
        self.assertIn("hopper_verdict", enriched.columns)
        self.assertIn("hopper_badge", enriched.columns)
        self.assertIn("hopper_target_price", enriched.columns)
        self.assertEqual(len(enriched), 2)

    def test_luxury_hotel_at_historical_minimum(self):
        # Sunrise White Hills scenario: price dropped from ~19000 to 10671 (historical min)
        history = pd.DataFrame({
            "hotel_name": ["Sunrise White Hills Resort"] * 6,
            "dates": ["20.12.2026 - 27.12.2026"] * 6,
            "price": [19092, 19092, 19092, 18767, 10721, 10671],
            "scraped_at": ["2026-10-18", "2026-10-19", "2026-10-19", "2026-10-20", "2026-10-20", "2026-10-21"],
        })
        offer = {
            "hotel_name": "Sunrise White Hills Resort",
            "dates": "20.12.2026 - 27.12.2026",
            "price": 10671,
            "deal_score": 85,
        }
        ref_date = date(2026, 10, 21)
        pred = predict_offer_action(offer, history_df=history, reference_date=ref_date)
        self.assertEqual(pred.verdict, "BUY_NOW")
        self.assertEqual(pred.badge_text, "🟢 ПОКУПАТЬ")
        self.assertNotIn("ДОРОГО", pred.badge_text)

    def test_batch_predict_with_history_df_sharm_scenario(self):
        # Table contains cheap hotels (median 5752) and luxury hotel (10671, dropped from 19092)
        current_table = pd.DataFrame([
            {"hotel_name": "Cheap Hotel 1", "dates": "20.12.2026 - 27.12.2026", "price": 4000, "scraped_at": "2026-10-21"},
            {"hotel_name": "Cheap Hotel 2", "dates": "20.12.2026 - 27.12.2026", "price": 5752, "scraped_at": "2026-10-21"},
            {"hotel_name": "Cheap Hotel 3", "dates": "20.12.2026 - 27.12.2026", "price": 6000, "scraped_at": "2026-10-21"},
            {"hotel_name": "Sunrise White Hills Resort", "dates": "20.12.2026 - 27.12.2026", "price": 10671, "scraped_at": "2026-10-21"},
        ])
        history_df = pd.DataFrame([
            {"hotel_name": "Cheap Hotel 1", "dates": "20.12.2026 - 27.12.2026", "price": 4000, "scraped_at": "2026-10-18"},
            {"hotel_name": "Cheap Hotel 2", "dates": "20.12.2026 - 27.12.2026", "price": 5752, "scraped_at": "2026-10-18"},
            {"hotel_name": "Cheap Hotel 3", "dates": "20.12.2026 - 27.12.2026", "price": 6000, "scraped_at": "2026-10-18"},
            {"hotel_name": "Sunrise White Hills Resort", "dates": "20.12.2026 - 27.12.2026", "price": 19092, "scraped_at": "2026-10-18"},
            {"hotel_name": "Sunrise White Hills Resort", "dates": "20.12.2026 - 27.12.2026", "price": 19092, "scraped_at": "2026-10-19"},
            {"hotel_name": "Sunrise White Hills Resort", "dates": "20.12.2026 - 27.12.2026", "price": 10671, "scraped_at": "2026-10-21"},
        ])
        enriched = batch_predict_offers(current_table, history_df=history_df, reference_date=date(2026, 10, 21))
        sunrise_row = enriched[enriched["hotel_name"] == "Sunrise White Hills Resort"].iloc[0]
        self.assertEqual(sunrise_row["hopper_verdict"], "BUY_NOW")
        self.assertEqual(sunrise_row["hopper_badge"], "🟢 ПОКУПАТЬ")
        self.assertNotIn("ДОРОГО", sunrise_row["hopper_badge"])

    def test_cohort_median_alone_never_labels_luxury_hotel_overpriced(self):
        # Even without hotel history, a higher-end hotel should never be called OVERPRICED based solely on cheap cohort
        current_table = pd.DataFrame([
            {"hotel_name": "Cheap 1", "dates": "20.12.2026 - 27.12.2026", "price": 3000, "scraped_at": "2026-10-21"},
            {"hotel_name": "Cheap 2", "dates": "20.12.2026 - 27.12.2026", "price": 4000, "scraped_at": "2026-10-21"},
            {"hotel_name": "Cheap 3", "dates": "20.12.2026 - 27.12.2026", "price": 5000, "scraped_at": "2026-10-21"},
            {"hotel_name": "Cheap 4", "dates": "20.12.2026 - 27.12.2026", "price": 5500, "scraped_at": "2026-10-21"},
            {"hotel_name": "Luxury Resort", "dates": "20.12.2026 - 27.12.2026", "price": 12000, "scraped_at": "2026-10-21"},
        ])
        enriched = batch_predict_offers(current_table, reference_date=date(2026, 10, 21))
        lux_row = enriched[enriched["hotel_name"] == "Luxury Resort"].iloc[0]
        self.assertNotEqual(lux_row["hopper_verdict"], "OVERPRICED")
        self.assertNotIn("ДОРОГО", lux_row["hopper_badge"])


if __name__ == "__main__":
    unittest.main()
