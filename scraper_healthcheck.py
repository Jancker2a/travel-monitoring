#!/usr/bin/env python3
"""
scraper_healthcheck.py — Scraper Health Check & Circuit Breaker.

Provides anomaly detection and safeguards against scraper regressions:
- Analyzes newly scraped offers against historical expectations (baseline count).
- Detects DOM changes, selector breakages, or IP bans when offers count drops precipitously.
- Circuit breaker triggers when:
  1. Zero offers found for an active filter (unless explicitly allow_empty_offers or expired).
  2. Severe volume drop (e.g., > 75% drop compared to historical baseline with >= 10 offers).
- Actions on trip:
  - Suppresses runaway 'missing hotel' alerts (preventing alert spam storm).
  - Emits structured health audit in `data/scraper_health.json`.
  - Optionally notifies administrator via Telegram if credentials exist.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("scraper_healthcheck")


@dataclass
class ScraperHealthResult:
    filter_id: str
    status: str  # "healthy", "empty_allowed", "critical_empty", "anomaly_drop"
    circuit_breaker_tripped: bool
    current_count: int
    baseline_count: int
    drop_pct: float
    message: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ScraperHealthChecker:
    """Evaluates scraping output quality and guards against upstream selector drift."""

    def __init__(
        self,
        health_log_path: str = "data/scraper_health.json",
        min_baseline_for_drop_check: int = 10,
        severe_drop_threshold_pct: float = 0.75,
    ):
        self.health_log_path = health_log_path
        self.min_baseline_for_drop_check = min_baseline_for_drop_check
        self.severe_drop_threshold_pct = severe_drop_threshold_pct

    def compute_historical_baseline(self, data_file: str, runs_to_sample: int = 5) -> int:
        """Computes median offers count from recent historical runs in travel_prices.csv."""
        if not os.path.exists(data_file):
            return 0
        try:
            # Read only relevant column to save memory and time
            df = pd.read_csv(data_file, usecols=["scraped_at"], on_bad_lines="skip")
            if df.empty or "scraped_at" not in df.columns:
                return 0
            counts_per_run = df["scraped_at"].value_counts()
            if counts_per_run.empty:
                return 0
            recent_counts = counts_per_run.iloc[:runs_to_sample]
            return int(recent_counts.median())
        except Exception as e:
            logger.debug(f"Could not compute historical baseline from {data_file}: {e}")
            return 0

    def evaluate(
        self,
        config: Dict[str, Any],
        current_offers: List[Dict[str, Any]],
        data_dir: Optional[str] = None,
    ) -> ScraperHealthResult:
        """Evaluates scraped offers and decides whether the circuit breaker should trip."""
        cfg = config or {}
        filter_id = cfg.get("filter_id") or os.path.basename(data_dir or "") or "unknown_filter"
        target_dir = data_dir or cfg.get("data_dir", "data")
        data_file = os.path.join(target_dir, "travel_prices.csv")

        current_count = len(current_offers)
        baseline = self.compute_historical_baseline(data_file)

        allow_empty = (
            cfg.get("allow_empty_offers", False)
            or not cfg.get("dynamic_search_dates", True)
            or bool(cfg.get("retire_after"))
        )

        # Case 1: Zero offers
        if current_count == 0:
            if allow_empty:
                return ScraperHealthResult(
                    filter_id=filter_id,
                    status="empty_allowed",
                    circuit_breaker_tripped=False,
                    current_count=0,
                    baseline_count=baseline,
                    drop_pct=1.0 if baseline > 0 else 0.0,
                    message="Zero offers collected, but filter permits empty results.",
                )
            else:
                return ScraperHealthResult(
                    filter_id=filter_id,
                    status="critical_empty",
                    circuit_breaker_tripped=True,
                    current_count=0,
                    baseline_count=baseline,
                    drop_pct=1.0 if baseline > 0 else 0.0,
                    message=f"Zero offers collected for active filter (baseline: ~{baseline}). Upstream parse failure suspected.",
                )

        # Case 2: Significant baseline exists, check for severe anomaly drop
        drop_pct = 0.0
        if baseline >= self.min_baseline_for_drop_check:
            if current_count < baseline:
                drop_pct = (baseline - current_count) / baseline
                if drop_pct >= self.severe_drop_threshold_pct:
                    return ScraperHealthResult(
                        filter_id=filter_id,
                        status="anomaly_drop",
                        circuit_breaker_tripped=True,
                        current_count=current_count,
                        baseline_count=baseline,
                        drop_pct=round(drop_pct, 3),
                        message=(
                            f"Scraper anomaly: collected {current_count} offers, drop of {drop_pct:.1%} "
                            f"vs baseline {baseline}. Possible DOM layout changes or anti-bot challenge."
                        ),
                    )

        # Case 3: Healthy
        return ScraperHealthResult(
            filter_id=filter_id,
            status="healthy",
            circuit_breaker_tripped=False,
            current_count=current_count,
            baseline_count=baseline,
            drop_pct=round(drop_pct, 3),
            message=f"Scraper healthy: {current_count} offers collected (baseline: ~{baseline}).",
        )

    def record_health(self, result: ScraperHealthResult) -> None:
        """Persists the health check result into data/scraper_health.json."""
        try:
            parent = os.path.dirname(self.health_log_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            history = {}
            if os.path.exists(self.health_log_path):
                try:
                    with open(self.health_log_path, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    history = {}

            if "filters" not in history:
                history["filters"] = {}

            history["filters"][result.filter_id] = result.to_dict()
            history["last_updated_utc"] = result.timestamp

            with open(self.health_log_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Could not record scraper health to {self.health_log_path}: {e}")

    def notify_telegram_circuit_breaker(self, result: ScraperHealthResult) -> bool:
        """Sends an administrative warning via Telegram if bot token and chat ID are present in environment."""
        if not result.circuit_breaker_tripped:
            return False

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not bot_token or not chat_id:
            logger.debug("Telegram credentials not configured; skipping breaker notification.")
            return False

        try:
            from telegram_notifier import send_telegram_message

            text = (
                f"🚨 <b>[Scraper Circuit Breaker] Аномалия парсинга!</b>\n\n"
                f"• <b>Фильтр:</b> <code>{result.filter_id}</code>\n"
                f"• <b>Собрано офферов:</b> <b>{result.current_count}</b> (норма: ~{result.baseline_count})\n"
                f"• <b>Просадка:</b> <b>{result.drop_pct:.1%}</b>\n"
                f"• <b>Статус:</b> <code>{result.status}</code>\n\n"
                f"⚠️ <i>Массовая отправка алертов о пропавших отелях заблокирована во избежание спама. "
                f"Проверьте доступность и DOM-структуру fly.pl.</i>"
            )
            return send_telegram_message(bot_token, chat_id, text)
        except Exception as e:
            logger.warning(f"Could not dispatch telegram breaker alert: {e}")
            return False

