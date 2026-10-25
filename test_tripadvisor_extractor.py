#!/usr/bin/env python3
"""Unit tests for extract_tripadvisor_from_card_html in hotel_deal_score.py."""

import unittest
from hotel_deal_score import extract_tripadvisor_from_card_html


class TestTripadvisorExtractor(unittest.TestCase):
    def test_legacy_card_with_svg_image_over_schema(self):
        """Image rating (4.0) must take priority over mismatched schema:ratingValue (4.1)."""
        card_html = """
        <div class="card-offer-search">
            <h2>Hotel Emerald</h2>
            <div class="t-m-l">
                <img src="data:image/png;base64,..." data-src="//pl.tripadvisor.com/img/cdsi/img2/ratings/traveler/4.0-37146-5.svg" class="tripadvisor-img">
                <span class="c"> 731 opinii</span>
            </div>
            <meta property="schema:ratingValue" content="4.1">
            <meta property="schema:ratingCount" content="731">
        </div>
        """
        res = extract_tripadvisor_from_card_html(card_html)
        self.assertEqual(res["ta_rating"], 4.0)
        self.assertEqual(res["ta_review_count"], 731)
        self.assertEqual(res["ta_source"], "tripadvisor")

    def test_multi_source_google_and_tripadvisor(self):
        """When both Google (4.5 / 154) and TripAdvisor (3.2 / 612) are present, extract TripAdvisor 3.2."""
        card_html = """
        <div class="card-offer-search">
            <h2>Luxury Resort</h2>
            <div class="rating-widget">
                <div class="aggregate">3,5 Przeciętny 766 opinii z 2 źródeł</div>
                <div class="pill-google">
                    <span class="google-icon">G</span> 4,5 (154 opinii)
                </div>
                <div class="pill-tripadvisor">
                    <span class="tripadvisor-icon">🦉</span> 3,2 (612 opinii)
                </div>
            </div>
            <meta property="schema:ratingValue" content="4.5">
            <meta property="schema:ratingCount" content="154">
        </div>
        """
        res = extract_tripadvisor_from_card_html(card_html)
        self.assertEqual(res["ta_rating"], 3.2)
        self.assertEqual(res["ta_review_count"], 612)
        self.assertEqual(res["ta_source"], "tripadvisor")

    def test_google_only_does_not_masquerade_as_tripadvisor(self):
        """If a hotel only has Google ratings, TripAdvisor rating must be None (not Google 4.6)."""
        card_html = """
        <div class="card-offer-search">
            <h2>Boutique Hotel</h2>
            <div class="google-rating">
                <span>Google</span> 4,6 (120 opinii)
            </div>
            <meta property="schema:ratingValue" content="4.6">
            <meta property="schema:ratingCount" content="120">
        </div>
        """
        res = extract_tripadvisor_from_card_html(card_html)
        self.assertIsNone(res["ta_rating"])
        self.assertIsNone(res["ta_review_count"])
        self.assertEqual(res["ta_source"], "")

    def test_bubble_class_fallback(self):
        """Bubble rating pattern (bubble_35 -> 3.5)."""
        card_html = """
        <div class="card">
            <h2>Sunny Beach</h2>
            <div class="ui_bubble_rating bubble_35" title="3.5 of 5 bubbles"></div>
            <div>TripAdvisor: 84 opinii</div>
        </div>
        """
        res = extract_tripadvisor_from_card_html(card_html)
        self.assertEqual(res["ta_rating"], 3.5)
        self.assertEqual(res["ta_review_count"], 84)
        self.assertEqual(res["ta_source"], "tripadvisor")

    def test_empty_card(self):
        res = extract_tripadvisor_from_card_html("")
        self.assertIsNone(res["ta_rating"])
        self.assertIsNone(res["ta_review_count"])

    def test_dashboard_ta_parsers(self):
        from generate_inline_charts_dashboard import (
            _parse_ta_rating_value,
            _parse_ta_review_count,
            _build_hotel_ta_cache,
            _resolve_row_ta,
        )
        import pandas as pd

        # Rating parser tests
        self.assertEqual(_parse_ta_rating_value("4,5"), 4.5)
        self.assertEqual(_parse_ta_rating_value("4.5"), 4.5)
        self.assertEqual(_parse_ta_rating_value("4.8/5"), 4.8)
        self.assertEqual(_parse_ta_rating_value(" 4,2 "), 4.2)
        self.assertEqual(_parse_ta_rating_value("9.0"), 4.5)
        self.assertIsNone(_parse_ta_rating_value(""))
        self.assertIsNone(_parse_ta_rating_value("—"))
        self.assertIsNone(_parse_ta_rating_value(None))
        self.assertIsNone(_parse_ta_rating_value(float("nan")))

        # Review count parser tests
        self.assertEqual(_parse_ta_review_count("1200"), 1200)
        self.assertEqual(_parse_ta_review_count("1 250"), 1250)
        self.assertEqual(_parse_ta_review_count("731 opinii"), 731)
        self.assertEqual(_parse_ta_review_count(""), 0)
        self.assertEqual(_parse_ta_review_count("—"), 0)
        self.assertEqual(_parse_ta_review_count(None), 0)

        # Historical cache & resolution fallback tests
        df = pd.DataFrame([
            {"hotel_name": "Hotel Alpha", "ta_rating": "4,5", "ta_review_count": "500", "scraped_at": "2026-10-24 10:00:00"},
            {"hotel_name": "Hotel Beta", "rating": "4.2", "review_count": "120", "scraped_at": "2026-10-24 10:00:00"},
        ])
        cache = _build_hotel_ta_cache(df)
        self.assertIn("Hotel Alpha", cache)
        self.assertEqual(cache["Hotel Alpha"]["ta_rating"], 4.5)
        self.assertEqual(cache["Hotel Alpha"]["ta_review_count"], 500)
        self.assertIn("Hotel Beta", cache)
        self.assertEqual(cache["Hotel Beta"]["ta_rating"], 4.2)

        # Row with missing TA rating restored from cache
        last_empty = pd.Series({"hotel_name": "Hotel Alpha", "ta_rating": "", "ta_review_count": ""})
        grp_empty = pd.DataFrame([last_empty])
        r, c, s = _resolve_row_ta(last_empty, grp_empty, cache, "Hotel Alpha")
        self.assertEqual(r, 4.5)
        self.assertEqual(c, 500)
        self.assertEqual(s, "tripadvisor")


if __name__ == "__main__":
    unittest.main()

