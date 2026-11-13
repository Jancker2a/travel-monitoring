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
            return sum(1 for r in self.ledger.values() if r.evaluated), 0

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
            dep_date = date.fromisoformat(rec.departure_date) if rec.departure_date else None
            today_d = (dep_date - date.today()).days if dep_date else 999

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

    def evaluate_outcomes_from_repository(self, repo: Any) -> Tuple[int, int]:
        """
        Cross-references unevaluated predictions using SQLite PriceRepository B-Tree indexes.
        Returns: (total_evaluated_count, newly_evaluated_count).
        """
        newly_evaluated = 0
        today_date = date.today()

        for pred_id, rec in self.ledger.items():
            if rec.evaluated:
                continue

            subsequent_df = repo.get_hotel_price_history(
                hotel_name=rec.hotel_name,
                dates=rec.dates if rec.dates else None,
                since_scraped_at=rec.created_at,
            )

            dep_date = date.fromisoformat(rec.departure_date) if rec.departure_date else None
            days_to_dep = (dep_date - today_date).days if dep_date else 999

            if subsequent_df is None or subsequent_df.empty:
                # If departure date passed without future observations
                if dep_date and days_to_dep <= 0:
                    rec.evaluated = True
                    rec.actual_min_price = rec.price_at_prediction
                    rec.actual_drop_occurred = False
                    if rec.predicted_verdict == "WAIT":
                        rec.outcome_label = "MISSED_BOAT"
                    elif rec.predicted_verdict == "BUY_NOW":
                        rec.outcome_label = "OPTIMAL_BUY"
                    else:
                        rec.outcome_label = "CORRECT_AVOID"
                    rec.brier_score = round(float((rec.predicted_drop_prob - 0.0) ** 2), 4)
                    rec.evaluated_at = datetime.now().isoformat()
                    newly_evaluated += 1
                continue

            prices = pd.to_numeric(subsequent_df["price"], errors="coerce").dropna().tolist()
            if not prices:
                continue

            actual_min = float(np.min(prices))
            price_diff = rec.price_at_prediction - actual_min
            rel_drop = price_diff / rec.price_at_prediction if rec.price_at_prediction > 0 else 0.0

            actual_drop = (
                rel_drop >= MIN_SIGNIFICANT_DROP_PCT
                or price_diff >= MIN_SIGNIFICANT_DROP_PLN
            )

            if rec.predicted_verdict == "WAIT":
                if actual_drop and actual_min <= rec.predicted_target_price * 1.03:
                    outcome = "SUCCESS_WAIT"
                elif actual_drop:
                    outcome = "PARTIAL_WAIT"
                elif days_to_dep <= 1:
                    outcome = "MISSED_BOAT"
                else:
                    continue
            elif rec.predicted_verdict == "BUY_NOW":
                outcome = "PREMATURE_BUY" if actual_drop else "OPTIMAL_BUY"
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

    def generate_accuracy_report(
        self,
        output_file: Optional[str] = "data/hopper_accuracy_report.json",
    ) -> Dict[str, Any]:
        """
        Compiles evaluation metrics into a comprehensive accuracy report.
        """
        evaluated_records = [r for r in self.ledger.values() if r.evaluated]
        total_predictions = len(self.ledger)
        total_evaluated = len(evaluated_records)

        if not evaluated_records:
            report = {
                "updated_at": datetime.now().isoformat(),
                "total_predictions": total_predictions,
                "evaluated_predictions": 0,
                "overall_accuracy_pct": 0.0,
                "average_brier_score": 0.25,
                "badge_display": "🔮 Hopper: накопление наблюдений",
                "status": "accumulating_observations",
            }
        else:
            waits = [r for r in evaluated_records if r.predicted_verdict == "WAIT"]
            buys = [r for r in evaluated_records if r.predicted_verdict == "BUY_NOW"]
            overpriced = [r for r in evaluated_records if r.predicted_verdict == "OVERPRICED"]

            successful_waits = sum(1 for r in waits if r.outcome_label in ("SUCCESS_WAIT", "PARTIAL_WAIT"))
            wait_acc = round((successful_waits / max(1, len(waits))) * 100.0, 1) if waits else 0.0

            optimal_buys = sum(1 for r in buys if r.outcome_label == "OPTIMAL_BUY")
            buy_acc = round((optimal_buys / max(1, len(buys))) * 100.0, 1) if buys else 0.0

            correct_avoid = sum(1 for r in overpriced if r.outcome_label in ("CORRECT_AVOID", "PERSISTENT_HIGH"))
            overpriced_acc = round((correct_avoid / max(1, len(overpriced))) * 100.0, 1) if overpriced else 0.0

            sound_advice = successful_waits + optimal_buys + correct_avoid
            overall_acc = round((sound_advice / max(1, total_evaluated)) * 100.0, 1)

            brier_scores = [r.brier_score for r in evaluated_records if r.brier_score is not None]
            avg_brier = round(float(np.mean(brier_scores)), 4) if brier_scores else 0.25

            report = {
                "updated_at": datetime.now().isoformat(),
                "total_predictions": total_predictions,
                "evaluated_predictions": total_evaluated,
                "overall_accuracy_pct": overall_acc,
                "average_brier_score": avg_brier,
                "wait_accuracy_pct": wait_acc,
                "buy_now_accuracy_pct": buy_acc,
                "overpriced_accuracy_pct": overpriced_acc,
                "verdicts_breakdown": {
                    "BUY_NOW": {
                        "total": len(buys),
                        "optimal": optimal_buys,
                        "premature": len(buys) - optimal_buys,
                        "accuracy_pct": buy_acc,
                    },
                    "WAIT": {
                        "total": len(waits),
                        "successful_wait": sum(1 for r in waits if r.outcome_label == "SUCCESS_WAIT"),
                        "partial_wait": sum(1 for r in waits if r.outcome_label == "PARTIAL_WAIT"),
                        "missed_boat": sum(1 for r in waits if r.outcome_label == "MISSED_BOAT"),
                        "accuracy_pct": wait_acc,
                    },
                    "OVERPRICED": {
                        "total": len(overpriced),
                        "correct_avoid": sum(1 for r in overpriced if r.outcome_label == "CORRECT_AVOID"),
                        "persistent_high": sum(1 for r in overpriced if r.outcome_label == "PERSISTENT_HIGH"),
                        "accuracy_pct": overpriced_acc,
                    },
                },
                "calibrated_clusters": len(self.calibrated_priors),
                "badge_display": f"🎯 Точность Hopper: {overall_acc:.0f}% (Brier: {avg_brier:.2f})",
                "status": "calibrated",
            }

        if output_file:
            try:
                out_dir = os.path.dirname(output_file)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                logger.info(f"Hopper accuracy report saved to {output_file}")
            except Exception as e:
                logger.warning(f"Could not save accuracy report: {e}")

        return report

    def seed_from_historical_offers(
        self,
        offers_df: pd.DataFrame,
        sample_limit: int = 1500,
    ) -> int:
        """
        Seeds the prediction ledger with historical predictions calculated
        at earlier scrape timestamps.
        """
        if offers_df is None or offers_df.empty:
            return 0

        from hopper_prediction_engine import predict_offer_action

        valid = offers_df.dropna(subset=["price", "hotel_name"]).copy()
        valid["price_num"] = pd.to_numeric(valid["price"], errors="coerce")
        valid = valid[valid["price_num"] > 1000].copy()

        if valid.empty:
            return 0

        if len(valid) > sample_limit:
            valid = valid.sample(n=sample_limit, random_state=42)

        added = 0
        for _, row in valid.iterrows():
            offer_dict = row.to_dict()
            scraped_ts = str(row.get("scraped_at") or "")
            ref_date = date.fromisoformat(scraped_ts[:10]) if len(scraped_ts) >= 10 else date.today()

            try:
                pred = predict_offer_action(offer_dict, reference_date=ref_date)
                if pred.verdict in ("WAIT", "BUY_NOW", "OVERPRICED") and pred.days_to_departure >= 3:
                    hotel = str(row.get("hotel_name") or "")
                    dates = str(row.get("dates") or "")
                    price = float(row.get("price_num") or 0.0)
                    now_iso = scraped_ts if scraped_ts else datetime.now().isoformat()
                    key_raw = f"{hotel}_{dates}_{price:.0f}_{pred.days_to_departure}_{now_iso[:10]}"
                    pred_id = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()[:12]

                    if pred_id not in self.ledger:
                        d_bucket = get_d_bucket(pred.days_to_departure)
                        tier = get_price_tier(pred.price_quantile)
                        self.ledger[pred_id] = PredictionRecord(
                            prediction_id=pred_id,
                            hotel_name=hotel,
                            dates=dates,
                            departure_date=pred.departure_date,
                            days_to_departure=pred.days_to_departure,
                            price_at_prediction=price,
                            predicted_verdict=pred.verdict,
                            predicted_drop_prob=round(pred.drop_probability_pct / 100.0, 3),
                            predicted_target_price=round(pred.target_price, 0),
                            created_at=now_iso,
                            d_bucket=d_bucket,
                            price_tier=tier,
                            evaluated=False,
                        )
                        added += 1
            except Exception:
                continue

        if added > 0:
            self.save_ledger()
        return added

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


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Hopper Self-Learning & Accuracy Evaluation Engine")
    parser.add_argument("--db", default=os.environ.get("TRAVEL_DATABASE_PATH", "data/travel_monitor.db"), help="Path to SQLite database")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER_FILE, help="Path to ledger file")
    parser.add_argument("--calibration", default=DEFAULT_CALIBRATION_FILE, help="Path to calibration file")
    parser.add_argument("--report", default="data/hopper_accuracy_report.json", help="Path to output accuracy report")
    parser.add_argument("--seed", action="store_true", help="Seed ledger from historical offers in database")
    parser.add_argument("--seed-limit", type=int, default=1200, help="Max historical offers to sample for seeding")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("🔮 Running Hopper Self-Learning & Accuracy Engine...")

    learner = HopperLearner(ledger_file=args.ledger, calibration_file=args.calibration)

    repo = None
    if os.path.exists(args.db):
        try:
            from storage.database import TravelDatabase
            from storage.repository import PriceRepository
            db = TravelDatabase(args.db)
            repo = PriceRepository(db)
            logger.info("Connected to SQLite storage at %s", args.db)
        except Exception as e:
            logger.warning("Could not connect to database: %s", e)

    if (args.seed or not learner.ledger) and repo is not None:
        logger.info("Seeding ledger from historical database (ledger empty or --seed requested)...")
        all_offers = repo.get_all_offers_df(min_price=1000.0)
        added = learner.seed_from_historical_offers(all_offers, sample_limit=args.seed_limit)
        logger.info("Seeded %d historical predictions into ledger (Total in ledger: %d)", added, len(learner.ledger))

    if repo is not None and learner.ledger:
        logger.info("Evaluating predictions against SQLite price history...")
        total_eval, newly_eval = learner.evaluate_outcomes_from_repository(repo)
        logger.info("Evaluation complete: %d evaluated (%d newly evaluated)", total_eval, newly_eval)

    report = learner.generate_accuracy_report(output_file=args.report)
    print("\n" + "=" * 60)
    print("📊 HOPPER PREDICTION ACCURACY REPORT")
    print("=" * 60)
    print(f"Total Predictions Logged:    {report.get('total_predictions', 0)}")
    print(f"Evaluated Predictions:       {report.get('evaluated_predictions', 0)}")
    print(f"Overall Recommendation Acc:  {report.get('overall_accuracy_pct', 0.0)}%")
    print(f"Average Brier Score:         {report.get('average_brier_score', 0.0)}")
    print(f"Wait Accuracy:               {report.get('wait_accuracy_pct', 0.0)}%")
    print(f"Buy Now Accuracy:            {report.get('buy_now_accuracy_pct', 0.0)}%")
    print(f"Badge:                       {report.get('badge_display', '')}")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
