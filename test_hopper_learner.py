#!/usr/bin/env python3
"""
Unit tests for Hopper Self-Learning Engine (HopperLearner).
"""

from datetime import date, datetime
import os
import unittest
import pandas as pd

from hopper_learner import HopperLearner, PredictionRecord


class TestHopperLearner(unittest.TestCase):
    def setUp(self):
        self.tmp_ledger = "/tmp/test_ledger.json"
        self.tmp_calib = "/tmp/test_calib.json"
        if os.path.exists(self.tmp_ledger):
            os.remove(self.tmp_ledger)
        if os.path.exists(self.tmp_calib):
            os.remove(self.tmp_calib)

        self.learner = HopperLearner(
            ledger_file=self.tmp_ledger,
            calibration_file=self.tmp_calib,
            learning_rate=0.25,
        )

    def tearDown(self):
        if os.path.exists(self.tmp_ledger):
            os.remove(self.tmp_ledger)
        if os.path.exists(self.tmp_calib):
            os.remove(self.tmp_calib)

    def test_record_prediction(self):
        offer = {
            "hotel_name": "Rixos Premium",
            "dates": "10.06.2026 - 17.06.2026",
            "price": 6000.0,
        }
        pred_id = self.learner.record_prediction(
            offer=offer,
            verdict="WAIT",
            drop_prob=0.70,
            target_price=5200.0,
            days_to_dep=10,
            quantile=0.60,
        )
        self.assertIsNotNone(pred_id)
        self.assertIn(pred_id, self.learner.ledger)
        rec = self.learner.ledger[pred_id]
        self.assertEqual(rec.hotel_name, "Rixos Premium")
        self.assertEqual(rec.predicted_verdict, "WAIT")
        self.assertFalse(rec.evaluated)

    def test_evaluate_successful_wait(self):
        # 1. Record WAIT prediction
        offer = {
            "hotel_name": "Sunrise Resort",
            "dates": "15.06.2026 - 22.06.2026",
            "price": 5000.0,
        }
        pred_id = self.learner.record_prediction(
            offer=offer,
            verdict="WAIT",
            drop_prob=0.75,
            target_price=4200.0,
            days_to_dep=8,
            quantile=0.50,
        )

        # 2. Provide subsequent history where price dropped to 4100 PLN (success!)
        history = pd.DataFrame([
            {"hotel_name": "Sunrise Resort", "dates": "15.06.2026 - 22.06.2026", "price": 4100.0},
        ])

        total, newly = self.learner.evaluate_outcomes(history)
        self.assertEqual(newly, 1)
        rec = self.learner.ledger[pred_id]
        self.assertTrue(rec.evaluated)
        self.assertEqual(rec.outcome_label, "SUCCESS_WAIT")
        self.assertTrue(rec.actual_drop_occurred)
        self.assertLess(rec.brier_score, 0.10)  # High prob (0.75) and occurred (1.0) -> low Brier

    def test_recalibration_adapts_priors(self):
        # Create records where actual drop did NOT happen (model was overconfident)
        for i in range(5):
            rec = PredictionRecord(
                prediction_id=f"test_{i}",
                hotel_name=f"Hotel_{i}",
                dates="10.06.2026 - 17.06.2026",
                departure_date="2026-06-10",
                days_to_departure=10,
                price_at_prediction=5000.0,
                predicted_verdict="WAIT",
                predicted_drop_prob=0.80,
                predicted_target_price=4500.0,
                created_at=datetime.now().isoformat(),
                d_bucket="panic_dump",
                price_tier="mid",
                evaluated=True,
                actual_min_price=5000.0,
                actual_drop_occurred=False,  # NO drop!
                outcome_label="MISSED_BOAT",
                brier_score=0.64,
            )
            self.learner.ledger[rec.prediction_id] = rec

        base_prior = self.learner.get_calibrated_prior("panic_dump", "mid")
        metrics = self.learner.recalibrate_model()
        new_prior = self.learner.get_calibrated_prior("panic_dump", "mid")

        # Because actual drops were 0%, prior should have dropped!
        self.assertLess(new_prior, base_prior)
        self.assertEqual(metrics["evaluated_total"], 5)


if __name__ == "__main__":
    unittest.main()
