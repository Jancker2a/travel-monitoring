import unittest
from build_hotel_catalog import extract_package_composition, parse_duration_days


class TestHotelCatalogAggregator(unittest.TestCase):
    def test_extract_composition_2_plus_1(self):
        config_turkey = {
            "id": "filter_turkey_7_10",
            "url": "https://fly.pl/szukaj-wycieczek/?adults=2&children=10-12-2020&durationFrom=7&durationTo=10",
            "subtitle": "24.12.2026–06.01.2027 • WAW • 2+1",
        }
        comp = extract_package_composition(config_turkey)
        self.assertEqual(comp["adults"], 2)
        self.assertEqual(comp["children"], 1)
        self.assertEqual(comp["label"], "2 взр. + 1 реб.")
        self.assertEqual(comp["short_label"], "2+1")

    def test_extract_composition_single_adult(self):
        config_cyprus = {
            "id": "filter_cyprus_7_10",
            "url": "https://fly.pl/szukaj-wycieczek/?filter[person]=1&filter[child]=0&filter[duration]=7:10",
            "subtitle": "9 аэр. • 1 взр • 7–10 дн.",
        }
        comp = extract_package_composition(config_cyprus)
        self.assertEqual(comp["adults"], 1)
        self.assertEqual(comp["children"], 0)
        self.assertEqual(comp["label"], "1 взр.")
        self.assertEqual(comp["short_label"], "1 чел.")

    def test_extract_composition_two_adults(self):
        config_germany = {
            "id": "config_germany_turkey_ber",
            "url": "https://fly.pl/szukaj-wycieczek/?filter[person]=2&filter[child]=0",
            "subtitle": "2 взр.",
        }
        comp = extract_package_composition(config_germany)
        self.assertEqual(comp["adults"], 2)
        self.assertEqual(comp["children"], 0)
        self.assertEqual(comp["label"], "2 взр.")
        self.assertEqual(comp["short_label"], "2 чел.")

    def test_parse_duration_days(self):
        self.assertEqual(parse_duration_days("8 dni"), 8)
        self.assertEqual(parse_duration_days("14 days"), 14)
        self.assertEqual(parse_duration_days("7-10"), 7)


if __name__ == "__main__":
    unittest.main()
