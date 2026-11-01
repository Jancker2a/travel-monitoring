import unittest
from build_hotel_catalog import extract_package_composition, parse_duration_days


class TestHotelCatalogAggregator(unittest.TestCase):
    def test_extract_composition_2_plus_1(self):
        long_lbl, short_lbl = extract_package_composition("filter_turkey_7_10", "24.12.2026 • 2+1")
        self.assertEqual(long_lbl, "2 взр. + 1 реб.")
        self.assertEqual(short_lbl, "2+1")

    def test_extract_composition_single_adult(self):
        long_lbl, short_lbl = extract_package_composition("filter_cyprus_7_10", "1 adult single")
        self.assertEqual(long_lbl, "1 взрослый")
        self.assertEqual(short_lbl, "1 взр.")

    def test_extract_composition_two_adults(self):
        long_lbl, short_lbl = extract_package_composition("config_germany_turkey_ber", "2 adults double")
        self.assertEqual(long_lbl, "2 взрослых")
        self.assertEqual(short_lbl, "2 взр.")

    def test_parse_duration_days(self):
        self.assertEqual(parse_duration_days("8 dni"), 8)
        self.assertEqual(parse_duration_days("14 days"), 14)
        self.assertEqual(parse_duration_days("7-10"), 7)


if __name__ == "__main__":
    unittest.main()
