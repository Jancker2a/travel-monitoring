#!/usr/bin/env python3
"""
Cross-Border Tour Arbitrage Engine (Poland vs Germany).

Compares package tours for matching hotels, dates, and durations:
- Poland: Warsaw (WAW), Katowice (KTW), Poznań (POZ), Wrocław (WRO)
- Germany: Berlin Brandenburg (BER), Dresden (DRS)

Features:
1. Live / cached EUR to PLN conversion (via Narodowy Bank Polski - NBP API).
2. Transport Friction Model (e.g. PKP Intercity train or fuel to Berlin).
3. Entity Matching via HotelEntityMatcher.
4. Arbitrage opportunity scoring and spread calculation:
   Δ_spread = Price_PL_PLN - (Price_DE_EUR * Rate_EUR_PLN + Friction)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd
import requests

from germany_tour_client import GermanTourOffer, GermanyTourClient
from hotel_entity_matcher import HotelEntityMatcher, calculate_hotel_similarity

logger = logging.getLogger(__name__)

# Fallback exchange rate if NBP is unreachable
DEFAULT_EUR_PLN_RATE = 4.30
NBP_API_URL = "https://api.nbp.pl/api/exchangerates/rates/a/eur/?format=json"

# Default transport friction cost to BER (e.g. train Warsaw-Berlin or car fuel/parking)
DEFAULT_FRICTION_COST_PLN = 250.0

# Threshold for significant arbitrage deal
SIGNIFICANT_SPREAD_PLN = 1000.0


@dataclass
class ArbitrageMatch:
    hotel_name_pl: str
    hotel_name_de: str
    destination: str
    similarity_score: float
    dates_pl: str
    dates_de: str
    airport_pl: str
    airport_de: str
    price_pl_pln: float
    price_de_eur: float
    price_de_converted_pln: float
    friction_cost_pln: float
    net_price_de_pln: float
    spread_pln: float  # Positive means Germany is cheaper by this amount
    savings_pct: float  # Positive % saved by flying from Germany
    best_deal: str  # 'GERMANY' or 'POLAND'
    badge_text: str  # E.g. '🚨 ARBITRAGE: -2,150 PLN via BER'
    tour_operator_de: str
    url_pl: Optional[str]
    url_de: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_eur_pln_exchange_rate(timeout: int = 5) -> float:
    """
    Fetches the official mid exchange rate of EUR in PLN from Narodowy Bank Polski (NBP).
    Falls back to 4.30 if offline or error.
    """
    try:
        resp = requests.get(NBP_API_URL, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            rates = data.get("rates", [])
            if rates and "mid" in rates[0]:
                rate = float(rates[0]["mid"])
                logger.info(f"Fetched live EUR/PLN rate from NBP: {rate:.4f}")
                return round(rate, 4)
    except Exception as e:
        logger.debug(f"NBP exchange rate fetch failed: {e}, using fallback {DEFAULT_EUR_PLN_RATE}")
    return DEFAULT_EUR_PLN_RATE


def parse_departure_date(text: str) -> Optional[date]:
    """Extracts the first departure date from date range strings."""
    if not text or not isinstance(text, str):
        return None
    # Format DD.MM.YYYY
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        try:
            return datetime.strptime(f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "%Y-%m-%d").date()
        except ValueError:
            pass
    # Format YYYY-MM-DD
    m2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m2:
        try:
            return datetime.strptime(m2.group(0), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def parse_duration_days(text: Union[str, int, float]) -> Optional[int]:
    """Extracts duration in days from text strings (e.g. '8 dni', '7 Tage', '7 nocy')."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    m = re.search(r"(\d+)\s*(?:Tage|Tagen|dni|days|Nächte|nocy)", str(text), re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b(\d+)\b", str(text))
    return int(m2.group(1)) if m2 else None


def is_offer_comparable(
    dates_pl: str,
    dates_de: str,
    duration_pl: Any,
    duration_de: Any,
    max_date_diff_days: int = 4,
    max_duration_diff_days: int = 2,
) -> Tuple[bool, str]:
    """
    Verifies that Polish and German offers have matching parameters:
    - Departure dates within max_date_diff_days (e.g. +-4 days)
    - Durations within max_duration_diff_days (e.g. +-2 days)
    """
    d_pl = parse_departure_date(dates_pl)
    d_de = parse_departure_date(dates_de)

    if d_pl and d_de:
        diff_days = abs((d_pl - d_de).days)
        if diff_days > max_date_diff_days:
            return False, f"Dates mismatch: PL {d_pl} vs DE {d_de} (diff: {diff_days} days)"

    dur_pl = parse_duration_days(duration_pl)
    dur_de = parse_duration_days(duration_de)

    if dur_pl and dur_de:
        dur_diff = abs(dur_pl - dur_de)
        if dur_diff > max_duration_diff_days:
            return False, f"Duration mismatch: PL {dur_pl}d vs DE {dur_de}d (diff: {dur_diff} days)"

    return True, "OK"


class CrossBorderArbitrageEngine:
    def __init__(
        self,
        eur_rate: Optional[float] = None,
        friction_cost_pln: float = DEFAULT_FRICTION_COST_PLN,
        matcher: Optional[HotelEntityMatcher] = None,
        max_date_diff_days: int = 4,
        max_duration_diff_days: int = 2,
    ):
        self.eur_rate = eur_rate or get_eur_pln_exchange_rate()
        self.friction_cost_pln = friction_cost_pln
        self.matcher = matcher or HotelEntityMatcher()
        self.max_date_diff_days = max_date_diff_days
        self.max_duration_diff_days = max_duration_diff_days

    def compare_offers(
        self,
        polish_offers: Union[List[Dict[str, Any]], pd.DataFrame],
        german_offers: Union[List[GermanTourOffer], List[Dict[str, Any]], pd.DataFrame],
    ) -> List[ArbitrageMatch]:
        """
        Cross-matches Polish and German tour offers, finding arbitrage opportunities.
        Enforces entity matching, departure date window tolerances, and duration parity.
        """
        # Convert inputs to list of dicts
        pl_list: List[Dict[str, Any]] = (
            polish_offers.to_dict(orient="records")
            if isinstance(polish_offers, pd.DataFrame)
            else [dict(o) for o in polish_offers]
        )

        de_list: List[Dict[str, Any]] = []
        if isinstance(german_offers, pd.DataFrame):
            de_list = german_offers.to_dict(orient="records")
        else:
            for item in german_offers:
                if isinstance(item, GermanTourOffer):
                    de_list.append(item.to_dict())
                else:
                    de_list.append(dict(item))

        if not pl_list or not de_list:
            return []

        # Extract German hotel candidate names
        de_hotels = list(set(d.get("hotel_name", "") for d in de_list if d.get("hotel_name")))
        matches: List[ArbitrageMatch] = []

        for pl_item in pl_list:
            pl_name = pl_item.get("hotel_name", "")
            if not pl_name:
                continue

            try:
                pl_price = float(pl_item.get("price") or 0.0)
            except (ValueError, TypeError):
                continue

            if pl_price <= 0:
                continue

            # Match hotel name
            match_res = self.matcher.match_hotel(pl_name, de_hotels)
            if not match_res:
                continue

            matched_de_name, sim_score = match_res

            # Find matching German offers for this hotel
            matching_de_offers = [
                d for d in de_list if d.get("hotel_name") == matched_de_name
            ]

            for de_item in matching_de_offers:
                # Validate date and duration comparability
                dates_pl = str(pl_item.get("dates", ""))
                dates_de = str(de_item.get("dates", ""))
                dur_pl = pl_item.get("duration", "")
                dur_de = de_item.get("duration", "") or de_item.get("duration_days", "")

                comparable, reason = is_offer_comparable(
                    dates_pl=dates_pl,
                    dates_de=dates_de,
                    duration_pl=dur_pl,
                    duration_de=dur_de,
                    max_date_diff_days=self.max_date_diff_days,
                    max_duration_diff_days=self.max_duration_diff_days,
                )
                if not comparable:
                    logger.debug(f"Skipping incompatible pair '{pl_name}' vs '{matched_de_name}': {reason}")
                    continue

                try:
                    de_eur = float(de_item.get("price_eur") or 0.0)
                except (ValueError, TypeError):
                    continue

                if de_eur <= 0:
                    continue


                # Currency conversion and friction
                de_converted_pln = round(de_eur * self.eur_rate, 0)
                net_de_pln = round(de_converted_pln + self.friction_cost_pln, 0)
                spread_pln = round(pl_price - net_de_pln, 0)
                savings_pct = (
                    round((spread_pln / pl_price) * 100, 1) if pl_price > 0 else 0.0
                )

                if spread_pln >= SIGNIFICANT_SPREAD_PLN:
                    best_deal = "GERMANY"
                    badge = f"🚨 ВЫГОДНЕЕ В БЕРЛИНЕ (-{int(spread_pln):,} PLN / {savings_pct}%)".replace(",", " ")
                elif spread_pln > 0:
                    best_deal = "GERMANY"
                    badge = f"🟡 Небольшая выгода в BER (-{int(spread_pln):,} PLN)".replace(",", " ")
                else:
                    best_deal = "POLAND"
                    badge = f"🟢 Польша дешевле (+{int(abs(spread_pln)):,} PLN)".replace(",", " ")

                matches.append(
                    ArbitrageMatch(
                        hotel_name_pl=pl_name,
                        hotel_name_de=matched_de_name,
                        destination=de_item.get("destination", "Unknown"),
                        similarity_score=sim_score,
                        dates_pl=str(pl_item.get("dates", "")),
                        dates_de=str(de_item.get("dates", "")),
                        airport_pl=str(pl_item.get("departure_airport", "WAW")),
                        airport_de=str(de_item.get("departure_airport", "BER")),
                        price_pl_pln=pl_price,
                        price_de_eur=de_eur,
                        price_de_converted_pln=de_converted_pln,
                        friction_cost_pln=self.friction_cost_pln,
                        net_price_de_pln=net_de_pln,
                        spread_pln=spread_pln,
                        savings_pct=savings_pct,
                        best_deal=best_deal,
                        badge_text=badge,
                        tour_operator_de=str(de_item.get("tour_operator", "TUI DE")),
                        url_pl=pl_item.get("url") or pl_item.get("offer_url"),
                        url_de=de_item.get("offer_url"),
                    )
                )

        # Sort matches by maximum spread descending (biggest savings first)
        matches.sort(key=lambda m: m.spread_pln, reverse=True)
        return matches

    def to_dataframe(self, matches: List[ArbitrageMatch]) -> pd.DataFrame:
        """Converts matches to a clean analytical DataFrame."""
        if not matches:
            return pd.DataFrame()
        return pd.DataFrame([m.to_dict() for m in matches])
