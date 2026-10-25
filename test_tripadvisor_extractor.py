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


if __name__ == "__main__":
    unittest.main()
