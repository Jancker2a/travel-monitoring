#!/usr/bin/env python3
"""
Unit tests for AI Market Intelligence components:
- Market DNA Profiler (build_market_dna.py)
- Market Feature Extractor (market_feature_extractor.py)
- AI Market Oracle (ai_market_oracle.py)
"""

import os
import tempfile
import unittest
import pandas as pd

from build_market_dna import (
    parse_departure_date,
    get_d_bucket,
    extract_operator_from_url,
    build_market_dna,
)
from market_feature_extractor import extract_filter_features
from ai_market_oracle import (
    generate_rule_based_briefing,
    synthesize_market_oracle,
    compute_buy_now_recommendation,
)


class TestAIMarketIntelligence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "travel_prices.csv")
        self.dna_path = os.path.join(self.temp_dir.name, "market_dna_profile.json")

        # Create sample package tour dataset
        df = pd.DataFrame([
            {
                "hotel_name": "Rixos Premium Belek",
                "price": 8500.0,
                "dates": "06.06.2026 - 13.06.2026",
                "duration": "8 dni",
                "rating": "4.8",
                "scraped_at": "2026-05-20T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/1?operator=CORAL",
            },
            {
                "hotel_name": "Rixos Premium Belek",
                "price": 7200.0,
                "dates": "06.06.2026 - 13.06.2026",
                "duration": "8 dni",
                "rating": "4.8",
                "scraped_at": "2026-05-30T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/1?operator=CORAL",
            },
            {
                "hotel_name": "Delphin Imperial Hotel",
                "price": 6000.0,
                "dates": "06.06.2026 - 13.06.2026",
                "duration": "8 dni",
                "rating": "4.7",
                "scraped_at": "2026-05-20T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/2?operator=ITAKA",
            },
            {
                "hotel_name": "Delphin Imperial Hotel",
                "price": 5900.0,
                "dates": "06.06.2026 - 13.06.2026",
                "duration": "8 dni",
                "rating": "4.7",
                "scraped_at": "2026-05-30T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/2?operator=ITAKA",
            },
        ])
        df.to_csv(self.csv_path, index=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dna_profiling_and_archetypes(self):
        dna = build_market_dna(data_dirs=[self.temp_dir.name])
        self.assertIn("macro_profile", dna)
        self.assertIn("hotel_profiles", dna)

        hotels = dna["hotel_profiles"]
        self.assertIn("Rixos Premium Belek", hotels)
        rixos = hotels["Rixos Premium Belek"]

        # Dropped from 8500 to 7200 (>15% drop during D-minus clearance) -> LATE_DUMPER
        self.assertEqual(rixos["archetype"], "LATE_DUMPER")
        self.assertEqual(rixos["min_price"], 7200.0)
        self.assertEqual(rixos["max_price"], 8500.0)
        self.assertEqual(rixos["primary_operator"], "CORAL")

    def test_feature_extractor_compact_json(self):
        # Build DNA first
        dna = build_market_dna(data_dirs=[self.temp_dir.name])
        import json
        with open(self.dna_path, "w", encoding="utf-8") as f:
            json.dump(dna, f)

        features = extract_filter_features(
            prices_csv_path=self.csv_path,
            dna_profile_path=self.dna_path,
            filter_id="test_filter",
        )

        self.assertEqual(features["filter_id"], "test_filter")
        self.assertIn("market_stats", features)
        self.assertEqual(features["market_stats"]["hotel_count"], 2)
        self.assertIn("floor_saturation", features)
        self.assertIn("selected_hotel_dossiers", features)

    def test_oracle_two_tier_synthesis(self):
        report = synthesize_market_oracle(
            prices_csv_path=self.csv_path,
            dna_profile_path=self.dna_path,
            api_key=None,  # Tests deterministic rule-based engine
        )

        self.assertIn("macro_briefing", report)
        self.assertIn("hotel_dossiers", report)

        macro = report["macro_briefing"]
        self.assertIn("headline", macro)
        self.assertIn("market_phase", macro)
        self.assertIn("strategic_directive", macro)
        self.assertIn("key_anomalies", macro)

        dossiers = report["hotel_dossiers"]
        self.assertGreaterEqual(len(dossiers), 1)
        for h_name, d in dossiers.items():
            self.assertIn("verdict", d)
            self.assertIn("badge_text", d)
            self.assertIn("rationale", d)
            self.assertIn("risk_assessment", d)
            self.assertIn("action_advice", d)

    def test_wide_window_departure_timeline(self):
        # Create dataset spanning 30 days of departures
        from datetime import date, timedelta
        today = date.today()
        d_near = (today + timedelta(days=4)).strftime("%d.%m.%Y")
        d_far = (today + timedelta(days=34)).strftime("%d.%m.%Y")
        wide_csv = os.path.join(self.temp_dir.name, "wide_travel_prices.csv")
        df_wide = pd.DataFrame([
            {
                "hotel_name": "Near Resort",
                "price": 4000.0,
                "dates": f"{d_near} - 10.06.2026",
                "duration": "8 dni",
                "scraped_at": "2026-05-20T10:00:00Z",
            },
            {
                "hotel_name": "Far Resort",
                "price": 5500.0,
                "dates": f"{d_far} - 10.07.2026",
                "duration": "8 dni",
                "scraped_at": "2026-05-20T10:00:00Z",
            },
        ])
        df_wide.to_csv(wide_csv, index=False)

        feats = extract_filter_features(wide_csv, dna_profile_path=self.dna_path)
        stats = feats["market_stats"]
        self.assertTrue(stats["is_wide_window"])
        self.assertEqual(stats["min_days_to_departure"], 4)
        self.assertEqual(stats["max_days_to_departure"], 34)
        self.assertGreaterEqual(stats["departure_span_days"], 25)

        briefing = generate_rule_based_briefing(feats)
        macro = briefing["macro_briefing"]
        # Must clearly mention nearest departures (4 days) and sliding window
        self.assertIn("4", macro["charter_dynamics"])
        self.assertIn("ближайш", macro["charter_dynamics"].lower())
        self.assertIn("окн", macro["charter_dynamics"].lower())

    def test_smart_features_badges_and_dupes(self):
        from datetime import date, timedelta
        import json
        today = date.today()
        d_dep = (today + timedelta(days=6)).strftime("%d.%m.%Y") # D-6 -> in D-4...D-7 window

        smart_csv = os.path.join(self.temp_dir.name, "smart_features_prices.csv")
        df_smart = pd.DataFrame([
            {
                "hotel_name": "Luxury 5* Palace",
                "price": 9500.0,
                "dates": f"{d_dep} - 10.06.2026",
                "duration": "8 dni",
                "rating": "4.7",
                "scraped_at": "2026-05-20T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/lux",
            },
            {
                "hotel_name": "Smart 5* Twin Resort",
                "price": 5400.0,
                "dates": f"{d_dep} - 10.06.2026",
                "duration": "8 dni",
                "rating": "4.6",
                "scraped_at": "2026-05-20T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/twin",
            },
            {
                "hotel_name": "Hidden 4* Coral Gem",
                "price": 2800.0,
                "dates": f"{d_dep} - 10.06.2026",
                "duration": "8 dni",
                "rating": "4.6",
                "scraped_at": "2026-05-20T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/gem",
            },
            {
                "hotel_name": "Flash Drop Hotel 4*",
                "price": 3200.0,
                "dates": f"{d_dep} - 10.06.2026",
                "duration": "8 dni",
                "rating": "4.1",
                "scraped_at": "2026-05-20T10:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/flash",
            },
        ])
        df_smart.to_csv(smart_csv, index=False)

        # DNA profile with historical minimum for Flash Drop Hotel at 5000 PLN (so 3200 is -36% drop!)
        # and sweet spot for Flash Drop Hotel at D-4...D-7
        mock_dna = {
            "macro_profile": {},
            "hotel_profiles": {
                "Flash Drop Hotel 4*": {
                    "archetype": "LATE_DUMPER",
                    "min_price": 5000.0,
                    "max_price": 7000.0,
                    "sweet_spot_d_bucket": "D-4...D-7",
                    "price_volatility": 0.25,
                    "primary_operator": "CORAL",
                },
                "Luxury 5* Palace": {
                    "archetype": "ROCK_SOLID",
                    "min_price": 9200.0,
                    "max_price": 9800.0,
                    "sweet_spot_d_bucket": "D-30+",
                    "price_volatility": 0.05,
                    "primary_operator": "ITAKA",
                }
            }
        }
        smart_dna_path = os.path.join(self.temp_dir.name, "smart_dna.json")
        with open(smart_dna_path, "w", encoding="utf-8") as f:
            json.dump(mock_dna, f)

        report = synthesize_market_oracle(
            prices_csv_path=smart_csv,
            dna_profile_path=smart_dna_path,
            api_key=None,
        )

        dossiers = report["hotel_dossiers"]
        self.assertIn("Luxury 5* Palace", dossiers)
        self.assertIn("Hidden 4* Coral Gem", dossiers)
        self.assertIn("Flash Drop Hotel 4*", dossiers)

        # 1. AI Dupe test: Luxury 5* Palace should have Smart 5* Twin Resort as dupe
        lux = dossiers["Luxury 5* Palace"]
        self.assertIsNotNone(lux.get("dupe_suggestion"))
        dupe = lux["dupe_suggestion"]
        self.assertEqual(dupe["hotel_name"], "Smart 5* Twin Resort")
        self.assertEqual(dupe["savings"], 4100.0)
        self.assertEqual(dupe["rating"], 4.6)

        # 2. Hidden Gem test: Hidden 4* Coral Gem
        gem = dossiers["Hidden 4* Coral Gem"]
        self.assertIsNotNone(gem.get("gem_badge"))
        self.assertIn("жемчужина", gem["gem_badge"].lower())

        # 3. Flash Drop test: Flash Drop Hotel 4* (3200 vs 5000 historical min)
        flash = dossiers["Flash Drop Hotel 4*"]
        self.assertIsNotNone(flash.get("flash_drop_badge"))
        self.assertIn("FLASH DROP", flash["flash_drop_badge"])

        # 4. Optimal Booking Window test:
        # Flash drop hotel has sweet spot D-4...D-7 and current departure is in 6 days -> in_window
        self.assertEqual(flash.get("booking_window_class"), "in_window")
        self.assertIn("Окно покупки", flash.get("booking_window_badge", ""))

        # Luxury palace sweet spot is D-30+ but departure is D-6 -> late
        self.assertEqual(lux.get("booking_window_class"), "late")

        # 5. Buy Now Recommendation test:
        macro = report["macro_briefing"]
        self.assertIn("buy_now_recommendation", macro)
        buy_rec = macro["buy_now_recommendation"]
        self.assertTrue(buy_rec["has_worthy_deals"])
        self.assertGreaterEqual(len(buy_rec["top_picks"]), 1)
        self.assertIn("Flash Drop Hotel 4*", [p["hotel_name"] for p in buy_rec["top_picks"]])

        # 6. Test negative case: when all options are overpriced / no deals
        overpriced_context = {
            "all_hotel_intelligence": {
                "Overpriced Resort": {
                    "hotel_name": "Overpriced Resort",
                    "current_price": 9999.0,
                    "historical_min": 5000.0,
                    "fair_price": {"class": "expensive", "diff_pct": 50.0},
                    "flash_drop": {"is_flash": False},
                    "gem": {"is_gem": False},
                    "booking_window": {"window_class": "late"},
                    "rating": 3.8,
                }
            }
        }
        no_deals_rec = compute_buy_now_recommendation(
            overpriced_context,
            {"Overpriced Resort": {"verdict": "OVERPRICED"}},
        )
        self.assertFalse(no_deals_rec["has_worthy_deals"])
        self.assertEqual(no_deals_rec["top_picks"], [])
        self.assertIn("Лучше ничего не покупать", no_deals_rec["headline"])

    def test_peer_cohort_fair_pricing_and_booking_window_sanity(self):
        """
        Verify that:
        1. Cheap economy hotels are NOT falsely marked as '-20% below market'
           just because there are expensive luxury hotels in the wide filter range.
        2. A hotel selling above or at its ordinary median price does NOT get
           'Окно покупки' badge even if current departure is inside its historical bucket.
        """
        from market_feature_extractor import resolve_booking_window

        # Amwaj Oyoun scenario:
        # historical median: 8181, current price: 8026 (only 1.8% below median, essentially normal price)
        dna_amwaj = {
            "archetype": "BALANCED",
            "min_price": 7949.0,
            "median_price": 8181.0,
            "sweet_spot_d_bucket": "D-15…D-30",
        }
        # Departure in 23 days (inside D-15...D-30)
        bw_res = resolve_booking_window(dna_amwaj, d_days=23, cur_p=8026.0)
        # Should NOT scream "Окно покупки" because price is essentially ordinary
        self.assertEqual(bw_res["window_badge"], "")
        self.assertEqual(bw_res["window_status"], "in_window_normal")

        # But if price actually dropped to 7200 (>10% below median)
        bw_good = resolve_booking_window(dna_amwaj, d_days=23, cur_p=7200.0)
        self.assertIn("Окно покупки", bw_good["window_badge"])

    def test_no_zero_percent_good_price_false_positive(self):
        """
        Verify that a hotel selling at its ordinary median price (0% diff):
        1. Gets verdict WAIT (🟡 ПОДОЖДАТЬ), not GOOD_PRICE.
        2. Never produces rationale mentioning '0% ниже'.
        """
        from ai_market_oracle import enrich_oracle_report_with_smart_features

        mock_context = {
            "all_hotel_intelligence": {
                "Test Economy Hotel": {
                    "hotel_name": "Test Economy Hotel",
                    "current_price": 3269.0,
                    "historical_min": 3100.0,
                    "historical_median": 3269.0,  # Exactly 0% diff!
                    "quantile_in_filter": 0.10,   # In bottom 10% of filter
                    "rating": 4.1,
                    "stars": 4,
                    "fair_price": {"delta_pct": 0.0, "class": "fair", "tier": "эконом"},
                    "gem": {"is_gem": False},
                    "flash_drop": {"is_flash": False},
                    "booking_window": {},
                }
            }
        }
        mock_report = {"macro_briefing": {}, "hotel_dossiers": {}}
        enriched = enrich_oracle_report_with_smart_features(mock_report, mock_context)
        dossier = enriched["hotel_dossiers"]["Test Economy Hotel"]
        self.assertEqual(dossier["verdict"], "WAIT")
        self.assertEqual(dossier["badge_text"], "🟡 ПОДОЖДАТЬ")
        self.assertNotIn("0% ниже", dossier["rationale"])
        self.assertIn("обычная", dossier["rationale"])


    def test_rich_market_intelligence_payload(self):
        """
        Verify that extract_filter_features generates rich contextual payload:
        1. market_trends (7d/14d movements, direction)
        2. airports_comparison
        3. duration_comparison
        4. top_candidates with complete price history, archetypes, trip details, and reputation
        """
        features = extract_filter_features(
            prices_csv_path=self.csv_path,
            dna_profile_path=self.dna_path,
            filter_id="test_filter",
            filter_title="Египет • Шарм • 7-10 дней",
        )

        self.assertIn("market_trends", features)
        self.assertIn("airports_comparison", features)
        self.assertIn("duration_comparison", features)
        self.assertIn("top_candidates", features)

        candidates = features["top_candidates"]
        self.assertGreaterEqual(len(candidates), 1)

        first_cand = candidates[0]
        self.assertIn("price_history", first_cand)
        self.assertIn("historical_min", first_cand["price_history"])
        self.assertIn("historical_median", first_cand["price_history"])
        self.assertIn("behavioral_archetype", first_cand)
        self.assertIn("type", first_cand["behavioral_archetype"])
        self.assertIn("trip_details", first_cand)
        self.assertIn("tripadvisor", first_cand)
        self.assertIn("hotel_reputation", first_cand)

    def test_hotel_reviews_kb_builder(self):
        """
        Verify that build_hotel_reviews_kb produces a structured knowledge base
        and that extract_filter_features successfully integrates it.
        """
        from build_hotel_reviews_kb import build_hotel_reviews_kb

        kb_file = os.path.join(self.temp_dir.name, "test_hotel_reputation_kb.json")
        kb = build_hotel_reviews_kb(
            output_file=kb_file,
            dna_file=self.dna_path,
            max_hotels=2,
            data_dirs=[self.temp_dir.name],
        )

        self.assertIn("hotels", kb)
        self.assertGreaterEqual(len(kb["hotels"]), 1)

        hotel_data = next(iter(kb["hotels"].values()))
        self.assertIn("season_trend", hotel_data)
        self.assertIn("family_and_kids", hotel_data)
        self.assertIn("winter_suitability", hotel_data)
        self.assertIn("pros", hotel_data)
        self.assertIn("cons_and_red_flags", hotel_data)
        self.assertIn("verdict", hotel_data)

        # Test integration with extract_filter_features
        features = extract_filter_features(
            prices_csv_path=self.csv_path,
            dna_profile_path=self.dna_path,
            reputation_kb_path=kb_file,
        )
        first_cand = features["top_candidates"][0]
        rep = first_cand["hotel_reputation"]
        self.assertIn("family_and_kids", rep)
        self.assertIn("season_trend", rep)


    def test_ta_rating_parsing_and_resolution(self):
        """Verify robust parsing of comma ratings, reviews count, and historical cache resolution."""
        import generate_inline_charts_dashboard as g

        # 1. Parsing tests
        self.assertEqual(g._parse_ta_rating_value("4,5"), 4.5)
        self.assertEqual(g._parse_ta_rating_value("4.8/5"), 4.8)
        self.assertEqual(g._parse_ta_rating_value("9,0"), 4.5)  # 10-scale normalized
        self.assertEqual(g._parse_ta_rating_value("4.2"), 4.2)
        self.assertIsNone(g._parse_ta_rating_value(""))
        self.assertIsNone(g._parse_ta_rating_value(None))
        self.assertIsNone(g._parse_ta_rating_value("N/A"))

        # 2. Reviews parsing
        self.assertEqual(g._parse_ta_review_count("1 250 opinii"), 1250)
        self.assertEqual(g._parse_ta_review_count("3,450"), 3450)
        self.assertEqual(g._parse_ta_review_count(""), 0)

        # 3. Cache and resolution
        df_ta = pd.DataFrame([
            {
                "hotel_name": "Resort Comma Rating",
                "rating": "4,6",
                "review_count": "1 100",
                "scraped_at": "2026-05-18T10:00:00Z",
                "price": 4000.0,
            },
            {
                "hotel_name": "Resort Comma Rating",
                "rating": "",  # Latest row lost rating
                "review_count": "",
                "scraped_at": "2026-05-20T10:00:00Z",
                "price": 4100.0,
            },
        ])
        cache = g._build_hotel_ta_cache(df_ta)
        self.assertIn("Resort Comma Rating", cache)
        self.assertEqual(cache["Resort Comma Rating"]["ta_rating"], 4.6)
        self.assertEqual(cache["Resort Comma Rating"]["ta_review_count"], 1100)

        # 4. Resolve row ta with cache fallback
        last_row = df_ta.iloc[-1]
        r, revs, src = g._resolve_row_ta(last_row, df_ta, cache, "Resort Comma Rating")
        self.assertEqual(r, 4.6)
        self.assertEqual(revs, 1100)

        # 5. Render HTML
        rendered = g._render_ta_rating_html(r, revs)
        self.assertIn("4.6", rendered)
        self.assertIn("1100 opinii", rendered)
        self.assertNotIn("ta-rating--empty", rendered)

    def test_destination_context_and_today_departures(self):
        """Verify destination context detection, today departure warnings, and reputation KB fallback."""
        import json
        from datetime import date, timedelta
        from market_feature_extractor import extract_filter_features, get_hotel_reputation_metadata

        today_str = date.today().strftime("%d.%m.%Y")
        tomorrow_str = (date.today() + timedelta(days=5)).strftime("%d.%m.%Y")

        # 1. Geography and reputation metadata test
        rep_turkey = get_hotel_reputation_metadata("Eftalia Ocean (Alanya)", "Турция")
        self.assertIn("Аланья", rep_turkey["bay_or_area"])
        self.assertTrue(rep_turkey["has_aquapark"])
        self.assertTrue(rep_turkey["family_friendly"])

        rep_side = get_hotel_reputation_metadata("Club Side Coast", "Турция")
        self.assertIn("Сиде", rep_side["bay_or_area"])
        self.assertIn("песчаный", rep_side["beach_profile"].lower())

        # 2. Extract features test with today departure
        test_csv_path = os.path.join(self.temp_dir.name, "test_turkey_today.csv")
        df_test = pd.DataFrame([
            {
                "hotel_name": "Eftalia Ocean",
                "price": 6500.0,
                "rating": "",  # missing in CSV
                "review_count": "",
                "dates": f"{today_str} - 10.11.2026",
                "duration": "14 dni",
                "departure_airport": "Warszawa",
                "scraped_at": "2026-10-26T12:00:00Z",
            },
            {
                "hotel_name": "Delphin Imperial",
                "price": 9500.0,
                "rating": "",
                "review_count": "",
                "dates": f"{tomorrow_str} - 15.11.2026",
                "duration": "14 dni",
                "departure_airport": "Warszawa",
                "scraped_at": "2026-10-26T12:00:00Z",
            },
        ])
        df_test.to_csv(test_csv_path, index=False)

        mock_kb = {
            "hotels": {
                "Eftalia Ocean": {
                    "ta_rating": 4.4,
                    "ta_review_count": 3200,
                    "family_and_kids": {"beach_entry": "Пологий песок", "kids_facilities": "Аквапарк 12 горок", "suitable_for_children": True, "score": 9.0},
                    "winter_suitability": {"bay": "Аланья", "wind_shelter": "Теплый регион", "heated_pools": True},
                    "season_trend": {"trend": "BETTER", "summary": "Реновация номеров"},
                }
            }
        }
        kb_path = os.path.join(self.temp_dir.name, "test_kb.json")
        with open(kb_path, "w", encoding="utf-8") as f:
            json.dump(mock_kb, f)

        market_ctx = extract_filter_features(
            test_csv_path,
            filter_id="filter_turkey_13_16_days",
            filter_title="13–16 дней",
            reputation_kb_path=kb_path,
        )

        stats = market_ctx["market_stats"]
        self.assertEqual(stats["destination_context"]["country"], "Турция")
        self.assertTrue(stats["has_today_departures"])
        self.assertEqual(stats["today_departures_count"], 1)
        self.assertEqual(stats["next_realistic_days_to_departure"], 5)

        # Candidate check
        c0 = [c for c in market_ctx["top_candidates"] if c["hotel_name"] == "Eftalia Ocean"][0]
        self.assertEqual(c0["rating"], 4.4)
        self.assertEqual(c0["review_count"], 3200)
        self.assertTrue(c0["is_departing_today"])
        self.assertIn("СЕГОДНЯ", c0["departure_warning"])
        self.assertTrue(c0["hotel_reputation"]["has_heated_pool"])
        self.assertEqual(c0["hotel_reputation"]["season_trend"]["trend"], "BETTER")

    def test_cheaper_airport_alternatives(self):
        from generate_inline_charts_dashboard import (
            extract_airport_from_url,
            find_cheaper_airport_alternatives,
        )

        # Test URL extraction
        test_url_waw = "https://fly.pl/oferta/hotel-1/?fly_from_code=WAW&adults=2"
        self.assertEqual(extract_airport_from_url(test_url_waw), "WAW")
        test_url_wro = "https://fly.pl/oferta/hotel-1/?wylot=WRO"
        self.assertEqual(extract_airport_from_url(test_url_wro), "WRO")

        # Test finding cheaper alternative
        df_all = pd.DataFrame([
            {
                "hotel_name": "Sunrise Resort",
                "dates": "10.06.2026 - 17.06.2026",
                "price": 8000.0,
                "from_airport": "WAW",
                "offer_url": "https://fly.pl/waw",
                "scraped_at": "2026-05-20T10:00:00Z",
            },
            {
                "hotel_name": "Sunrise Resort",
                "dates": "10.06.2026 - 17.06.2026",
                "price": 6800.0,
                "from_airport": "KTW",
                "offer_url": "https://fly.pl/ktw",
                "scraped_at": "2026-05-20T10:00:00Z",
            },
            {
                "hotel_name": "Sunrise Resort",
                "dates": "11.06.2026 - 18.06.2026", # ±1 day difference
                "price": 6200.0,
                "from_airport": "KRK",
                "offer_url": "https://fly.pl/krk",
                "scraped_at": "2026-05-20T10:00:00Z",
            },
            {
                "hotel_name": "Sunrise Resort",
                "dates": "10.06.2026 - 17.06.2026",
                "price": 7950.0, # only 50 PLN cheaper -> should NOT qualify (< 150 PLN & < 3%)
                "from_airport": "POZ",
                "offer_url": "https://fly.pl/poz",
                "scraped_at": "2026-05-20T10:00:00Z",
            },
        ])

        # Current hotel: Sunrise Resort from WAW at 8000 PLN
        alts = find_cheaper_airport_alternatives(
            df_all_airports=df_all,
            hotel_name="Sunrise Resort",
            dates="10.06.2026 - 17.06.2026",
            current_price=8000.0,
            current_airport="WAW",
            min_savings_pln=150.0,
            min_savings_pct=3.0,
        )

        self.assertIsNotNone(alts)
        self.assertEqual(len(alts), 2) # KRK (6200) and KTW (6800), POZ excluded
        self.assertEqual(alts[0]["airport"], "KRK")
        self.assertEqual(alts[0]["price"], 6200.0)
        self.assertEqual(alts[0]["savings"], 1800.0)
        self.assertEqual(alts[0]["savings_percent"], 22.5)

        self.assertEqual(alts[1]["airport"], "KTW")
        self.assertEqual(alts[1]["price"], 6800.0)
        self.assertEqual(alts[1]["savings"], 1200.0)

    def test_ta_rating_parsing_and_resolution(self):
        from generate_inline_charts_dashboard import (
            _parse_ta_rating_value,
            _parse_ta_review_count,
            _resolve_row_ta,
            _build_hotel_ta_cache,
        )

        # 1. Comma floats and various formats
        self.assertEqual(_parse_ta_rating_value("4,5"), 4.5)
        self.assertEqual(_parse_ta_rating_value("4,8/5"), 4.8)
        self.assertEqual(_parse_ta_rating_value("4.2"), 4.2)
        self.assertEqual(_parse_ta_rating_value(4.5), 4.5)
        self.assertEqual(_parse_ta_rating_value(9.0), 4.5) # 10-point scale normalization
        self.assertIsNone(_parse_ta_rating_value(""))
        self.assertIsNone(_parse_ta_rating_value("—"))
        self.assertIsNone(_parse_ta_rating_value("brak"))

        # 2. Review counts
        self.assertEqual(_parse_ta_review_count("1 250"), 1250)
        self.assertEqual(_parse_ta_review_count("3,450 opinii"), 3450)
        self.assertEqual(_parse_ta_review_count(500), 500)

        # 3. Fallback resolution across historical dataframe
        df_hist = pd.DataFrame([
            {"hotel_name": "Test Grand Resort", "rating": "4,5", "reviews": "1200"},
            {"hotel_name": "Test Grand Resort", "rating": "", "reviews": ""},
        ])
        lookup = _build_hotel_ta_cache(df_hist)
        self.assertIn("Test Grand Resort", lookup)
        self.assertEqual(lookup["Test Grand Resort"]["ta_rating"], 4.5)
        self.assertEqual(lookup["Test Grand Resort"]["ta_review_count"], 1200)

        # Test _resolve_row_ta when latest row has empty rating but history has rating
        last_row = {"hotel_name": "Test Grand Resort", "rating": "", "ta_rating": ""}
        rating, reviews, source = _resolve_row_ta(
            last_row,
            grp=df_hist,
            hotel_ta_cache=lookup,
            hotel_name="Test Grand Resort",
        )
        self.assertEqual(rating, 4.5)
        self.assertEqual(reviews, 1200)

    def test_greece_destination_detection_and_reputation_sanitization(self):
        """Tests that Athens hotels with 'Residence' in the name are identified as Greece, not Turkey (Side),
        and that European hotels never inherit Red Sea coral reefs or panic dump phases on stable markets."""
        csv_p = os.path.join(self.temp_dir.name, "greece_test.csv")
        df_greece = pd.DataFrame([
            {
                "hotel_name": "Zeus Essence Wyndham Athens Residence",
                "price": 8419.0,
                "dates": "14.11.2026 - 21.11.2026",
                "duration": "8 dni",
                "departure_airport": "Modlin",
                "scraped_at": "2026-10-26T12:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/grecja/athens/oferta",
            },
            {
                "hotel_name": "NLH Fix",
                "price": 6677.0,
                "dates": "13.11.2026 - 20.11.2026",
                "duration": "8 dni",
                "departure_airport": "Modlin",
                "scraped_at": "2026-10-26T12:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/grecja/athens/oferta",
            },
        ])
        df_greece.to_csv(csv_p, index=False)

        features = extract_filter_features(
            prices_csv_path=csv_p,
            filter_id="filter_greece_7_10_days",
            filter_title="7–10 дней",
        )

        dest = features["market_stats"]["destination_context"]
        self.assertEqual(dest["country"], "Греция")
        self.assertEqual(dest["region"], "Афины и Аттика")
        self.assertIn("зима", dest["season_phase"].lower())

        # Dominant phase should not be panic dump when prices are stable
        self.assertNotEqual(features["market_stats"]["dominant_yield_phase"], "panic_dump")

        # Without price history, hotels should not be marked as floor breakers
        self.assertEqual(features["floor_saturation"]["floor_breaker_pct"], 0.0)
        self.assertFalse(features["floor_saturation"]["has_meaningful_history"])

        # Check reputation sanitization
        for cand in features["top_candidates"]:
            rep = cand.get("hotel_reputation", {})
            for pro in rep.get("pros", []):
                self.assertNotIn("коралловый", pro.lower())
                self.assertNotIn("снорклинг", pro.lower())
            self.assertNotIn("риф", rep.get("beach_profile", "").lower())

    def test_egypt_13_16_duration_and_destination_intelligence(self):
        """Tests that Egypt 13-16 days filter correctly identifies Egypt (not Turkey)
        and computes stay duration, is_long_trip=True, and cost per day."""
        from ai_market_oracle import generate_rule_based_briefing

        csv_p = os.path.join(self.temp_dir.name, "egypt_13_16_test.csv")
        df_egypt = pd.DataFrame([
            {
                "hotel_name": "Jaz Royal Palmariva",
                "price": 11427.0,
                "dates": "04.11.2026 - 18.11.2026",
                "duration": "14 dni",
                "departure_airport": "Warszawa",
                "scraped_at": "2026-10-26T12:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/egipt/hurghada/jaz-royal-palmariva",
            },
            {
                "hotel_name": "Pickalbatros Dana Beach",
                "price": 13500.0,
                "dates": "04.11.2026 - 19.11.2026",
                "duration": "15 dni",
                "departure_airport": "Warszawa",
                "scraped_at": "2026-10-26T12:00:00Z",
                "offer_url": "https://fly.pl/wycieczka/egipt/hurghada/pickalbatros-dana-beach",
            },
        ])
        df_egypt.to_csv(csv_p, index=False)

        features = extract_filter_features(
            prices_csv_path=csv_p,
            filter_id="filter_13_16_days",
            filter_title="13–16 дней",
        )

        dest = features["market_stats"]["destination_context"]
        self.assertEqual(dest["country"], "Египет")
        self.assertEqual(dest["region"], "Шарм-эль-Шейх / Хургада / Марса Алам")

        # Verify stay duration intelligence
        trip_dur = features["market_stats"]["trip_duration"]
        self.assertTrue(trip_dur["is_long_trip"])
        self.assertIn("14", trip_dur["label"])
        self.assertEqual(trip_dur["median_days"], 14)
        self.assertGreater(trip_dur["cost_per_day_median_pln"], 500)
        self.assertIn("две недели", trip_dur["context_note"].lower())

        # Verify candidate cost per day
        c1 = features["top_candidates"][0]
        self.assertEqual(c1["hotel_name"], "Jaz Royal Palmariva")
        self.assertEqual(c1["duration_days"], 14)
        self.assertEqual(c1["cost_per_day_pln"], round(11427.0 / 14))

        # Verify rule-based briefing includes Egypt and 14 nights
        briefing = generate_rule_based_briefing(features)
        charter_text = briefing["macro_briefing"]["charter_dynamics"]
        self.assertIn("Египет", charter_text)
        self.assertIn("14", charter_text)
        self.assertNotIn("Турци", charter_text)


    def test_hotel_reputation_geographic_isolation(self):
        """Tests that Turkish, Cypriot, and Spanish hotels are never assigned Egyptian bays/reefs,
        even if hotel name contains tokens like Sentido, Maritim, Barcelo."""
        from market_feature_extractor import get_hotel_reputation_metadata

        # 1. Turkish hotel with Sentido in name
        numa_rep = get_hotel_reputation_metadata(
            "Numa Bay Exclusive (ex Sentido Numa Bay)",
            destination_hint="Турция • 9–11 дней"
        )
        self.assertIn("Аланья", numa_rep["bay_or_area"])
        self.assertNotIn("Рас Ум Сид", numa_rep["bay_or_area"])
        self.assertNotIn("Хадаба", numa_rep["bay_or_area"])
        self.assertNotIn("риф", numa_rep["beach_profile"].lower())
        self.assertNotIn("красного моря", numa_rep["wind_shelter_winter"].lower())

        # 2. Turkish hotel with Belek / Maritim in name
        pine_rep = get_hotel_reputation_metadata(
            "Pine Beach Belek (ex. Maritim Pine Beach Resort)",
            destination_hint="Турция • 9–11 дней"
        )
        self.assertIn("Белек", pine_rep["bay_or_area"])
        self.assertNotIn("Наама", pine_rep["bay_or_area"])

        # 3. Spanish hotel with Barcelo in name
        barcelo_rep = get_hotel_reputation_metadata(
            "Barcelo Murcia Siete Coronas",
            destination_hint="Испания"
        )
        self.assertEqual(barcelo_rep["bay_or_area"], "Испания")
        self.assertNotIn("Набк", barcelo_rep["bay_or_area"])

        # 4. Legitimate Egypt Sharm hotel
        sharm_rep = get_hotel_reputation_metadata(
            "Novotel Sharm Beach",
            destination_hint="Египет • 7 дней"
        )
    def test_buy_now_rating_quality_guard(self):
        """Tests that compute_buy_now_recommendation and enrich_oracle_report_with_smart_features
        strictly disqualify unrated (0.0) or low-rated (< 4.0) hotels from top_picks."""
        from ai_market_oracle import compute_buy_now_recommendation, enrich_oracle_report_with_smart_features

        market_context = {
            "all_hotel_intelligence": {
                "Unrated Hotel (NLH Fix)": {
                    "hotel_name": "Unrated Hotel (NLH Fix)",
                    "current_price": 2000,
                    "historical_min": 2500,
                    "historical_median": 2600,
                    "historical_max": 3000,
                    "rating": 0.0,
                    "flash_drop": {"is_flash": True, "drop_pct": 20},
                    "fair_price": {"delta_pct": -15, "tier": "Economy", "class": "fair-deal"},
                },
                "Poor Rating Hotel": {
                    "hotel_name": "Poor Rating Hotel",
                    "current_price": 1800,
                    "historical_min": 2200,
                    "historical_median": 2300,
                    "historical_max": 2800,
                    "rating": 3.2,
                    "flash_drop": {"is_flash": True, "drop_pct": 20},
                    "fair_price": {"delta_pct": -15, "tier": "Economy", "class": "fair-deal"},
                },
                "Excellent Hotel (Navarria)": {
                    "hotel_name": "Excellent Hotel (Navarria)",
                    "current_price": 2400,
                    "historical_min": 3000,
                    "historical_median": 3100,
                    "historical_max": 3500,
                    "rating": 4.5,
                    "flash_drop": {"is_flash": True, "drop_pct": 20},
                    "fair_price": {"delta_pct": -15, "tier": "Standard", "class": "fair-deal"},
                },
            },
            "market_stats": {"min_days_to_departure": 14},
        }

        rec = compute_buy_now_recommendation(market_context, {})
        self.assertTrue(rec["has_worthy_deals"])
        picked_names = [p["hotel_name"] for p in rec["top_picks"]]
        self.assertIn("Excellent Hotel (Navarria)", picked_names)
        self.assertNotIn("Unrated Hotel (NLH Fix)", picked_names)
        self.assertNotIn("Poor Rating Hotel", picked_names)

        # Test enrichment rejection of unrated/low-rated hallucination
        raw_report = {
            "macro_briefing": {
                "buy_now_recommendation": {
                    "top_picks": [
                        {"hotel_name": "Unrated Hotel (NLH Fix)", "why_buy": "Отличный отель, рейтинг 4.5★"},
                        {"hotel_name": "Poor Rating Hotel", "why_buy": "Дешевый отель, рейтинг 4.5★"},
                    ]
                }
            },
            "hotel_dossiers": {},
        }
        enriched = enrich_oracle_report_with_smart_features(raw_report, market_context)
        enriched_rec = enriched["macro_briefing"]["buy_now_recommendation"]
        enriched_picks = [p["hotel_name"] for p in enriched_rec["top_picks"]]
        self.assertNotIn("Unrated Hotel (NLH Fix)", enriched_picks)
        self.assertNotIn("Poor Rating Hotel", enriched_picks)
        self.assertIn("Excellent Hotel (Navarria)", enriched_picks)

    def test_today_departure_quality_and_arbitrage_injection(self):
        """Verifies that:
        1. Awkward 'за 0 дн.' in market_phase is sanitized.
        2. Unrated hotel (rating 0.0) hallucinated by LLM is purged and replaced with high-quality pick.
        3. Next realistic flight (e.g. 31.10) is guaranteed in strategic_directive.
        4. Duration arbitrage anomaly is auto-injected if LLM returned empty key_anomalies.
        """
        from ai_market_oracle import enrich_oracle_report_with_smart_features

        market_context = {
            "market_stats": {
                "min_days_to_departure": 0,
                "has_today_departures": True,
                "nearest_departure_date": "29.10",
                "furthest_departure_date": "21.11",
                "is_wide_window": True,
                "next_realistic_departure_date": "31.10",
                "next_realistic_days_to_departure": 2,
            },
            "duration_comparison": {
                "multi_duration": True,
                "longer_duration_days": 10,
                "cost_per_extra_day_pln": 98.0,
                "insight": "Доплата за отдых 10 дн. вместо 8 дн. составляет 197 zł (98 zł в день)",
            },
            "all_hotel_intelligence": {
                "Titanic Pearl": {
                    "hotel_name": "Titanic Pearl",
                    "current_price": 6915.0,
                    "rating": 0.0,
                    "review_count": 0,
                    "historical_min": 7847.0,
                    "historical_median": 10921.0,
                },
                "Albatros Makadi Resort": {
                    "hotel_name": "Albatros Makadi Resort",
                    "current_price": 8206.0,
                    "rating": 4.5,
                    "review_count": 2800,
                    "historical_min": 6240.0,
                    "historical_median": 10272.0,
                    "flash_drop": {"is_flash": False},
                    "gem": {"is_gem": True, "rating": 4.5},
                    "fair_price": {"delta_pct": -12.0, "tier": "премиум", "class": "fair-deal"},
                    "booking_window": {"window_class": "panic", "window_badge": "🔥 Горящий тур"},
                },
            },
        }

        # Simulates the flawed raw LLM output from user prompt
        raw_report = {
            "macro_briefing": {
                "headline": "Горящие туры: до вылета 0 дней, туроператоры распродают места",
                "market_phase": "Горящие туры за 0 дн.",
                "charter_dynamics": "Туры на 8–9 ночей в Египет сейчас доступны по хорошей цене. Вылеты сегодня.",
                "strategic_directive": "Если готовы вылететь сегодня, сейчас лучшее время для бронирования.",
                "buy_now_recommendation": {
                    "has_worthy_deals": True,
                    "headline": "Стоит выбрать из этих вариантов:",
                    "advice": "Бронируйте сейчас, это проверенные отели с высоким рейтингом.",
                    "top_picks": [
                        {
                            "hotel_name": "Titanic Pearl",
                            "price": 6915,
                            "badge": "⚡ Сброс цены (−36.7%)",
                            "why_buy": "Цена на 36.7% ниже медианы, отличный шанс забронировать.",
                        }
                    ],
                },
                "key_anomalies": [],
            },
            "hotel_dossiers": {},
        }

        enriched = enrich_oracle_report_with_smart_features(raw_report, market_context)
        macro = enriched["macro_briefing"]

        # 1. Market phase sanitized
        self.assertNotIn("0 дн", macro["market_phase"])
        self.assertIn("29.10", macro["market_phase"])
        self.assertIn("21.11", macro["market_phase"])

        # 2. Rating quality guard: Titanic Pearl purged, Albatros picked
        top_picks = macro["buy_now_recommendation"]["top_picks"]
        picked_hotels = [p["hotel_name"] for p in top_picks]
        self.assertNotIn("Titanic Pearl", picked_hotels)
        self.assertIn("Albatros Makadi Resort", picked_hotels)

        # 3. Next realistic flight guaranteed in directive
        directive = macro["strategic_directive"]
        self.assertIn("31.10", directive)
        self.assertIn("2 дн", directive)

        # 4. Duration arbitrage auto-injected
        anomalies = macro["key_anomalies"]
        self.assertTrue(any(a.get("type") == "duration" for a in anomalies))

    def test_parse_departure_date_all_formats(self):
        """Verifies parse_departure_date handles all fly.pl variations and relative years."""
        from datetime import date
        from build_market_dna import parse_departure_date

        # Short format without year
        d_short = parse_departure_date("28.12 - 06.01")
        self.assertIsNotNone(d_short)
        self.assertEqual(d_short.month, 12)
        self.assertEqual(d_short.day, 28)

        # Full range
        d_full = parse_departure_date("28.12.2026 - 06.01.2027")
        self.assertEqual(d_full, date(2026, 12, 28))

        # Dash delimiter
        d_dash = parse_departure_date("28-12-2026")
        self.assertEqual(d_dash, date(2026, 12, 28))

        # ISO format
        d_iso = parse_departure_date("2026-12-28")
        self.assertEqual(d_iso, date(2026, 12, 28))

        # URL departureDate param
        d_url = parse_departure_date("", offer_url="https://fly.pl/hotel/?departureDate=2026-12-28")
        self.assertEqual(d_url, date(2026, 12, 28))

        # Duration string with parentheses
        d_dur = parse_departure_date("28.12 - 06.01 (8 dni)")
        self.assertEqual(d_dur.month, 12)
        self.assertEqual(d_dur.day, 28)

    def test_tourist_composition_and_dynamic_scope(self):
        """Verifies format_tourist_composition generates correct labels for 2+1, 1 adult, and 2 adults."""
        from market_feature_extractor import format_tourist_composition

        # 2 adults + 1 child (family)
        p_fam = format_tourist_composition(2, 1, 5)
        self.assertEqual(p_fam["short_label"], "2 взр. + 1 реб.")
        self.assertEqual(p_fam["price_scope"], "на семью (2 взр. + 1 реб.)")
        self.assertEqual(p_fam["per_day_scope"], "на семью")

        # 1 adult (solo)
        p_solo = format_tourist_composition(1, 0)
        self.assertEqual(p_solo["short_label"], "1 взр.")
        self.assertEqual(p_solo["price_scope"], "на одного")
        self.assertEqual(p_solo["per_day_scope"], "на одного")

        # 2 adults (standard couple)
        p_couple = format_tourist_composition(2, 0)
        self.assertEqual(p_couple["short_label"], "2 взр.")
        self.assertEqual(p_couple["price_scope"], "за двоих")
        self.assertEqual(p_couple["per_day_scope"], "за двоих")

    def test_overpriced_hotel_never_receives_good_price_or_buy_now(self):
        """Verifies that hotels with price spikes (+30% vs median or fair-overpriced) strictly get OVERPRICED."""
        from ai_market_oracle import enrich_oracle_report_with_smart_features, generate_rule_based_briefing

        # Case 1: Invidia Coral Beach Tiran scenario - price jumped to 6433 vs historical median 4908 (+31%)
        mock_intel = {
            "Invidia Coral Beach Tiran": {
                "hotel_name": "Invidia Coral Beach Tiran",
                "current_price": 6433.0,
                "historical_min": 4785.0,
                "historical_median": 4908.0,
                "historical_max": 6433.0,
                "quantile_in_filter": 0.85,
                "fair_price": {
                    "delta_pct": 28.0,
                    "class": "fair-overpriced",
                    "badge": "⚠️ +28% к премиум 4★",
                },
                "flash_drop": {"is_flash": False},
            }
        }
        ctx = {
            "all_hotel_intelligence": mock_intel,
            "filter_title": "Египет • 7-10 дней",
        }

        # 1. Rule-based briefing
        rule_report = generate_rule_based_briefing(ctx)
        dossier = rule_report["hotel_dossiers"]["Invidia Coral Beach Tiran"]
        self.assertEqual(dossier["verdict"], "OVERPRICED")
        self.assertEqual(dossier["badge_text"], "🔴 ДОРОГО")
        self.assertNotIn("ХОРОШАЯ ЦЕНА", dossier["badge_text"])
        self.assertNotIn("ПОКУПАТЬ", dossier["badge_text"])

        # 2. Enrich cached report that mistakenly had GOOD_PRICE from earlier in the day
        stale_cached_report = {
            "macro_briefing": {"headline": "Старый отчет"},
            "hotel_dossiers": {
                "Invidia Coral Beach Tiran": {
                    "verdict": "GOOD_PRICE",
                    "badge_text": "🔵 ХОРОШАЯ ЦЕНА",
                    "rationale": "Старая рекомендация",
                }
            }
        }
        enriched = enrich_oracle_report_with_smart_features(stale_cached_report, ctx)
        fixed_dossier = enriched["hotel_dossiers"]["Invidia Coral Beach Tiran"]
        self.assertEqual(fixed_dossier["verdict"], "OVERPRICED")
        self.assertEqual(fixed_dossier["badge_text"], "🔴 ДОРОГО")

    def test_deal_score_and_gem_never_wait_dissonance(self):
        """
        Verify that a hotel marked as Hidden Gem or fair-underpriced, or with Deal Score >= 75
        never receives a contradictory '🟡 ПОДОЖДАТЬ' or 'Наблюдать' recommendation.
        """
        from ai_market_oracle import generate_rule_based_briefing, enrich_oracle_report_with_smart_features
        from generate_inline_charts_dashboard import determine_price_forecast

        # 1. Oracle tests for Hidden Gem
        gem_context = {
            "all_hotel_intelligence": {
                "Jaz Grand Marsa (ex Resta Grand Resort)": {
                    "hotel_name": "Jaz Grand Marsa (ex Resta Grand Resort)",
                    "current_price": 6845.0,
                    "historical_min": 6500.0,
                    "historical_median": 6900.0,
                    "quantile_in_filter": 0.35,
                    "rating": 4.9,
                    "stars": 5,
                    "fair_price": {"delta_pct": -11.0, "class": "fair-underpriced", "tier": "комфорт 5*"},
                    "gem": {"is_gem": True, "badge": "💎 Жемчужина"},
                    "flash_drop": {"is_flash": False},
                    "booking_window": {},
                }
            }
        }
        rule_report = generate_rule_based_briefing(gem_context)
        dossier = rule_report["hotel_dossiers"]["Jaz Grand Marsa (ex Resta Grand Resort)"]
        self.assertNotEqual(dossier["verdict"], "WAIT")
        self.assertNotIn("ПОДОЖДАТЬ", dossier["badge_text"])
        self.assertIn("ВЫГОДНАЯ ЦЕНА", dossier["badge_text"])

        enriched = enrich_oracle_report_with_smart_features({"macro_briefing": {}, "hotel_dossiers": {}}, gem_context)
        enr_dossier = enriched["hotel_dossiers"]["Jaz Grand Marsa (ex Resta Grand Resort)"]
        self.assertNotEqual(enr_dossier["verdict"], "WAIT")
        self.assertNotIn("ПОДОЖДАТЬ", enr_dossier["badge_text"])

        # 2. determine_price_forecast check for Deal Score 99
        fc = determine_price_forecast(deal_score=99, confidence="High", avg_pct=-0.8, delta48_pct=0.0)
        self.assertEqual(fc["text"], "Покупать")
        self.assertEqual(fc["class"], "forecast-buy")
        self.assertEqual(fc["icon"], "🟢")


if __name__ == "__main__":
    unittest.main()





