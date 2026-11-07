#!/usr/bin/env python3
"""Unit tests for HotelRepository knowledge base facade."""

import json
import tempfile
import unittest
from pathlib import Path

from hotel_repository import HotelRepository


class TestHotelRepository(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.temp_dir.name)

        # Mock KBs
        self.specs_path = self.td / "hotel_specs_kb.json"
        self.rep_path = self.td / "hotel_reputation_kb.json"
        self.gal_path = self.td / "hotel_galleries_kb.json"
        self.dna_path = self.td / "market_dna_profile.json"

        with open(self.specs_path, "w", encoding="utf-8") as f:
            json.dump({
                "hotels": {
                    "Jaz Grand Marsa (ex Resta Grand Resort)": {
                        "specs": {
                            "stars": 5,
                            "beach": {"line": "1-я линия", "type": "песчаный"},
                            "pools": {"heated": True, "count": 3},
                        }
                    }
                }
            }, f)

        with open(self.rep_path, "w", encoding="utf-8") as f:
            json.dump({
                "hotels": {
                    "Jaz Grand Marsa (ex Resta Grand Resort)": {
                        "rating": 4.9,
                        "reviews": 671,
                        "family_and_kids": {"suitable_for_children": True, "score": 8.8},
                    }
                }
            }, f)

        with open(self.gal_path, "w", encoding="utf-8") as f:
            json.dump({
                "galleries": {
                    "Jaz Grand Marsa": [
                        {"url": "https://img.example.com/1.jpg", "label": "Бассейн"},
                        {"url": "https://img.example.com/2.jpg", "label": "Пляж"},
                    ]
                }
            }, f)

        with open(self.dna_path, "w", encoding="utf-8") as f:
            json.dump({
                "hotel_profiles": {
                    "Jaz Grand Marsa": {
                        "archetype": "ROCK_SOLID",
                        "volatility_score": 3.2,
                    }
                }
            }, f)

        self.repo = HotelRepository(
            specs_path=self.specs_path,
            reputation_path=self.rep_path,
            galleries_path=self.gal_path,
            dna_path=self.dna_path,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exact_and_fuzzy_specs_lookup(self):
        # Exact match
        s1 = self.repo.get_specs("Jaz Grand Marsa (ex Resta Grand Resort)")
        self.assertIsNotNone(s1)
        self.assertEqual(s1["stars"], 5)
        self.assertTrue(s1["pools"]["heated"])

        # Fuzzy / cleaned title match (without '(ex Resta Grand Resort)')
        s2 = self.repo.get_specs("Jaz Grand Marsa")
        self.assertIsNotNone(s2)
        self.assertEqual(s2["stars"], 5)

    def test_reputation_and_gallery_lookup(self):
        rep = self.repo.get_reputation("Jaz Grand Marsa")
        self.assertIsNotNone(rep)
        self.assertEqual(rep["rating"], 4.9)
        self.assertEqual(rep["family_and_kids"]["score"], 8.8)

        gal = self.repo.get_gallery("Jaz Grand Marsa (ex Resta Grand Resort)")
        self.assertEqual(len(gal), 2)
        self.assertEqual(gal[0]["label"], "Бассейн")

    def test_dna_and_unified_passport(self):
        dna = self.repo.get_dna("Jaz Grand Marsa")
        self.assertIsNotNone(dna)
        self.assertEqual(dna["archetype"], "ROCK_SOLID")

        passport = self.repo.get_unified_passport("Jaz Grand Marsa (ex Resta Grand Resort)")
        self.assertTrue(passport["has_specs"])
        self.assertTrue(passport["has_reputation"])
        self.assertEqual(passport["photos_count"], 2)
        self.assertEqual(passport["archetype"], "ROCK_SOLID")
        self.assertEqual(passport["slug"], "jaz-grand-marsa")


if __name__ == "__main__":
    unittest.main()
