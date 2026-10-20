#!/usr/bin/env python3
"""
Self-Learning & Continuous Calibration Engine for Hopper Predictions.

Implements a reinforcement and Bayesian calibration feedback loop:
1. Prediction Ledger: Tracks all issued predictions (verdict, predicted drop prob, target price, D).
2. Outcome Evaluator: Cross-references predictions against subsequent historical scrapes:
   - For 'BUY_NOW': Verifies if price stayed at floor or if a premature buy occurred.
   - For 'WAIT': Verifies if price dropped to target (Successful Wait) or climbed/sold out (Missed Boat).
3. Calibration & Parameter Optimization:
   - Calculates Brier score and directional calibration bias: Bias(D, tier) = mean(p_hat - actual_drop).
   - Dynamically updates prior probabilities and target drop factors.
   - Persists learned weights in `hopper_calibration.json` for continuous adaptation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from hopper_prediction_engine import (
    MIN_SIGNIFICANT_DROP_PCT,
    MIN_SIGNIFICANT_DROP_PLN,
    PRIOR_DROP_PROBABILITIES,
    get_d_bucket,
    get_price_tier,
    parse_departure_date,
    calculate_days_to_departure,
)

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_FILE = "hopper_prediction_ledger.json"
DEFAULT_CALIBRATION_FILE = "hopper_calibration.json"


@dataclass
class PredictionRecord:
    prediction_id: str
    hotel_name: str
    dates: str
    departure_date: str
    days_to_departure: int
    price_at_prediction: float
    predicted_verdict: str  # 'BUY_NOW', 'WAIT', 'OVERPRICED'
    predicted_drop_prob: float  # 0.0 - 1.0
    predicted_target_price: float
    created_at: str
    d_bucket: str
    price_tier: str
    evaluated: bool = False
    actual_min_price: Optional[float] = None
    actual_drop_occurred: Optional[bool] = None
    outcome_label: Optional[str] = None  # SUCCESS_WAIT, MISSED_BOAT, OPTIMAL_BUY, PREMATURE_BUY
    brier_score: Optional[float] = None
    evaluated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HopperLearner:
    def __init__(
        self,
        ledger_file: str = DEFAULT_LEDGER_FILE,
        calibration_file: str = DEFAULT_CALIBRATION_FILE,
        learning_rate: float = 0.20,
    ):
        self.ledger_file = ledger_file
        self.calibration_file = calibration_file
        self.learning_rate = learning_rate
        self.ledger: Dict[str, PredictionRecord] = {}
        self.calibrated_priors: Dict[str, float] = {}
        self.drop_scale_factor: float = 1.0

        self._load_ledger()
        self._load_calibration()

    def _load_ledger(self) -> None:
        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.ledger[k] = PredictionRecord(**v)
            except Exception as e:
                logger.debug(f"Could not load ledger: {e}")

    def save_ledger(self) -> None:
        try:
            with open(self.ledger_file, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self.ledger.items()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Could not save ledger: {e}")

    def _load_calibration(self) -> None:
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.calibrated_priors = data.get("priors", {})
                    self.drop_scale_factor = float(data.get("drop_scale_factor", 1.0))
            except Exception as e:
                logger.debug(f"Could not load calibration: {e}")

    def save_calibration(self) -> None:
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "drop_scale_factor": round(self.drop_scale_factor, 3),
                "priors": {k: round(v, 3) for k, v in self.calibrated_priors.items()},
            }
            with open(self.calibration_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Could not save calibration: {e}")

    def record_prediction(
        self,
        offer: Dict[str, Any],
        verdict: str,
        drop_prob: float,
        target_price: float,
        days_to_dep: int,
        quantile: float,
    ) -> Optional[str]:
        """Records a new prediction in the ledger."""
        hotel = str(offer.get("hotel_name") or "")
        dates = str(offer.get("dates") or "")
        dep_date = parse_departure_date(dates)
        if not dep_date:
            return None

        price = float(offer.get("price") or 0.0)
        now_iso = datetime.now().isoformat()
        key_raw = f"{hotel}_{dates}_{price:.0f}_{days_to_dep}_{now_iso[:10]}"
        pred_id = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()[:12]

        if pred_id in self.ledger:
            return pred_id

        d_bucket = get_d_bucket(days_to_dep)
        tier = get_price_tier(quantile)

        record = PredictionRecord(
            prediction_id=pred_id,
            hotel_name=hotel,
            dates=dates,
            departure_date=dep_date.isoformat(),
            days_to_departure=days_to_dep,
            price_at_prediction=price,
            predicted_verdict=verdict,
            predicted_drop_prob=round(drop_prob, 3),
            predicted_target_price=round(target_price, 0),
            created_at=now_iso,
            d_bucket=d_bucket,
            price_tier=tier,
            evaluated=False,
        )
        self.ledger[pred_id] = record
        return pred_id

    def evaluate_outcomes(self, history_df: pd.DataFrame) -> Tuple[int, int]:
        """
        Cross-references unevaluated predictions against subsequent historical scrape points.
        Returns: (evaluated_count, newly_evaluated_count).
        """
        if history_df is None or history_df.empty:
            return 0, 0

        work = history_df.dropna(subset=["price"]).copy()
        work["price_num"] = pd.to_numeric(work["price"], errors="coerce")
        work = work.dropna(subset=["price_num"])

        newly_evaluated = 0

        for pred_id, rec in self.ledger.items():
            if rec.evaluated:
                continue

            # Look up subsequent observations for this hotel and dates
            hotel_offers = work[
                (work["hotel_name"].astype(str) == rec.hotel_name)
                & (work["dates"].astype(str) == rec.dates)
            ]

            if hotel_offers.empty:
                continue

            # Check if departure date has passed or we have observations closer to departure
            dep_date = date.fromisoformat(rec.departure_date)
            today_d = (dep_date - date.today()).days

            # Observation prices that occurred at or after the prediction
            subsequent_prices = hotel_offers["price_num"].tolist()
            if not subsequent_prices:
                continue

            actual_min = float(np.min(subsequent_prices))
            price_diff = rec.price_at_prediction - actual_min
            rel_drop = price_diff / rec.price_at_prediction if rec.price_at_prediction > 0 else 0.0

            actual_drop = (
                rel_drop >= MIN_SIGNIFICANT_DROP_PCT
                or price_diff >= MIN_SIGNIFICANT_DROP_PLN
            )

            # Determine qualitative outcome
            if rec.predicted_verdict == "WAIT":
                if actual_drop and actual_min <= rec.predicted_target_price * 1.03:
                    outcome = "SUCCESS_WAIT"  # Price dropped as predicted!
                elif actual_drop:
                    outcome = "PARTIAL_WAIT"  # Dropped, but didn't quite hit target
                elif today_d <= 1:
                    outcome = "MISSED_BOAT"  # Departure reached without drop
                else:
                    continue  # Still time for drop, wait to evaluate
            elif rec.predicted_verdict == "BUY_NOW":
                if actual_drop:
                    outcome = "PREMATURE_BUY"  # Price dropped further after buying
                else:
                    outcome = "OPTIMAL_BUY"  # Floor was genuine!
            else:  # OVERPRICED
                outcome = "CORRECT_AVOID" if actual_drop else "PERSISTENT_HIGH"

            brier = float((rec.predicted_drop_prob - (1.0 if actual_drop else 0.0)) ** 2)

            rec.evaluated = True
            rec.actual_min_price = actual_min
            rec.actual_drop_occurred = actual_drop
            rec.outcome_label = outcome
            rec.brier_score = round(brier, 4)
            rec.evaluated_at = datetime.now().isoformat()
            newly_evaluated += 1

        if newly_evaluated > 0:
            self.save_ledger()
            self.recalibrate_model()

        total_evaluated = sum(1 for r in self.ledger.values() if r.evaluated)
        return total_evaluated, newly_evaluated

    def recalibrate_model(self) -> Dict[str, Any]:
        """
        Calculates calibration bias for each (D-bucket, price-tier) cluster
        and updates prior drop probabilities accordingly.
        """
        evaluated_records = [r for r in self.ledger.values() if r.evaluated]
        if not evaluated_records:
            return {"status": "no_data"}

        # Group by (d_bucket, price_tier)
        clusters: Dict[Tuple[str, str], List[PredictionRecord]] = {}
        for r in evaluated_records:
            key = (r.d_bucket, r.price_tier)
            clusters.setdefault(key, []).append(r)

        updated_priors = {}

        for (bucket, tier), recs in clusters.items():
            if len(recs) < 3:
                continue

            # Calculate empirical probability
            actual_drops = sum(1 for r in recs if r.actual_drop_occurred)
            empirical_rate = actual_drops / len(recs)

            prior_key = f"{bucket}:{tier}"
            base_prior = PRIOR_DROP_PROBABILITIES.get((bucket, tier), 0.50)
            current_prior = self.calibrated_priors.get(prior_key, base_prior)

            # Directional update towards empirical rate using learning rate
            new_prior = current_prior + self.learning_rate * (empirical_rate - current_prior)
            new_prior = float(np.clip(new_prior, 0.05, 0.95))
            updated_priors[prior_key] = new_prior

        self.calibrated_priors.update(updated_priors)
        self.save_calibration()

        brier_avg = float(np.mean([r.brier_score for r in evaluated_records if r.brier_score is not None]))
        accuracy_waits = sum(1 for r in evaluated_records if r.outcome_label == "SUCCESS_WAIT")
        total_waits = sum(1 for r in evaluated_records if r.predicted_verdict == "WAIT")

        return {
            "evaluated_total": len(evaluated_records),
            "average_brier_score": round(brier_avg, 4),
            "wait_accuracy_pct": round((accuracy_waits / max(1, total_waits)) * 100, 1),
            "calibrated_clusters": len(updated_priors),
        }

    def get_calibrated_prior(self, d_bucket: str, price_tier: str) -> float:
        """Returns the learned prior drop probability for a given cluster."""
        key = f"{d_bucket}:{price_tier}"
        if key in self.calibrated_priors:
            return self.calibrated_priors[key]
        return PRIOR_DROP_PROBABILITIES.get((d_bucket, price_tier), 0.50)
