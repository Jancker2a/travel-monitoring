import unittest
from hotel_name_normalizer import (
    clean_hotel_title,
    slugify_hotel_name,
    normalize_for_matching,
    HotelCanonicalRegistry,
)


class TestHotelNameNormalizer(unittest.TestCase):
    def test_clean_hotel_title(self):
        # Strip ex-names
        self.assertEqual(clean_hotel_title("AMC Royal Hotel & Spa (ex. AMC Azur Resort)"), "AMC Royal Hotel & Spa")
        self.assertEqual(clean_hotel_title("Dream Lagoon & Aqua Park (ex. Floriana Dream Lagoon)"), "Dream Lagoon & Aqua Park")
        self.assertEqual(clean_hotel_title("Rixos Premium Belek (ex. Troy)"), "Rixos Premium Belek")

        # Strip geographic locations in parens
        self.assertEqual(clean_hotel_title("Delphin Imperial (Lara)"), "Delphin Imperial")
        self.assertEqual(clean_hotel_title("Pickalbatros Aqua Park (Hurghada)"), "Pickalbatros Aqua Park")
        self.assertEqual(clean_hotel_title("Alexander The Great Beach (Paphos)"), "Alexander The Great Beach")

        # Strip stars
        self.assertEqual(clean_hotel_title("Rixos Premium Hotel Belek 5*"), "Rixos Premium Hotel Belek")
        self.assertEqual(clean_hotel_title("Akassia Swiss Resort 4*"), "Akassia Swiss Resort")

    def test_slugify_hotel_name(self):
        self.assertEqual(slugify_hotel_name("Rixos Premium Belek"), "rixos-premium-belek")
        self.assertEqual(slugify_hotel_name("Rixos Premium Belek (ex. Troy)"), "rixos-premium-belek")
        self.assertEqual(slugify_hotel_name("Delphin Imperial Hotel (Lara) 5*"), "delphin-imperial-hotel")
        self.assertEqual(slugify_hotel_name("Alexander The Great Beach (Paphos)"), "alexander-the-great-beach")

    def test_canonical_registry_exact_and_fuzzy(self):
        registry = HotelCanonicalRegistry()

        # Register original
        h1 = registry.register_hotel("Rixos Premium Belek", destination="Турция")
        slug1 = h1["slug"]
        self.assertEqual(slug1, "rixos-premium-belek")

        # Register ex-name variation
        h2 = registry.register_hotel("Rixos Premium Belek (ex. Troy)", destination="Турция")
        self.assertEqual(h2["slug"], slug1)
        self.assertIn("Rixos Premium Belek (ex. Troy)", h2["aliases"])

        # Register hotel with generic "Hotel" addition
        h3 = registry.register_hotel("Rixos Premium Hotel Belek", destination="Турция")
        self.assertEqual(h3["slug"], slug1)

        # Register distinct hotel
        h_other = registry.register_hotel("Delphin Imperial Lara", destination="Турция")
        self.assertNotEqual(h_other["slug"], slug1)
        self.assertIn("delphin", h_other["slug"])


if __name__ == "__main__":
    unittest.main()
