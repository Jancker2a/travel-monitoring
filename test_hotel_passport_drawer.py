#!/usr/bin/env python3
"""
Unit tests for hotel_passport_drawer.py and price chart tooltip data.
"""

import unittest
from hotel_passport_drawer import (
    generate_hotel_ai_profile,
    get_hotel_passport_js,
    render_hotel_passport_drawer_html,
)


class TestHotelPassportDrawer(unittest.TestCase):
    """Test suite for Hotel Passport Drawer markup and JS logic."""

    def test_passport_js_contains_trip_dates_in_hover(self):
        js = get_hotel_passport_js()
        self.assertIn("Даты поездки", js)
        self.assertIn("defaultDates", js)
        self.assertIn("zł", js)

    def test_passport_drawer_markup(self):
        html = render_hotel_passport_drawer_html()
        self.assertIn("drawerPlotlyChart", html)
        self.assertIn("tabPanel-history", html)
        self.assertIn("drawerPackagesTbody", html)

    def test_generate_hotel_ai_profile(self):
        profile = generate_hotel_ai_profile(
            hotel_name="Test Beach Resort",
            country="Египет",
            destination="Шарм-эль-Шейх",
            specs={"beach_line": 1, "aquapark": True},
            rep_data=None,
            current_price=3500.0,
            min_price=3200.0,
            max_price=4200.0,
            price_drop_pct=16.6,
        )
        self.assertEqual(profile["stars"], 4)
        self.assertIn("Шарм-эль-Шейх", profile["verdict"])
        self.assertTrue(profile["has_aquapark"])


if __name__ == "__main__":
    unittest.main()
