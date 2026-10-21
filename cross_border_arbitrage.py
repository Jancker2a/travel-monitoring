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
from datetime import date, datetime, timedelta
import json
import logging
import math
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

# Allowed German border airports close to Poland (East Germany):
# BER: Berlin Brandenburg (~80 km from border; direct train/motorway from Warsaw/Poznań)
# DRS: Dresden (~100 km from Zgorzelec; direct A4 from Wrocław/Dolny Śląsk)
# LEJ: Leipzig/Halle (~200 km from border)
BORDER_AIRPORT_FRICTION_DEFAULTS: Dict[str, float] = {
    "BER": 250.0,
    "DRS": 220.0,
    "LEJ": 350.0,
}
ALLOWED_GERMAN_BORDER_AIRPORTS = set(BORDER_AIRPORT_FRICTION_DEFAULTS.keys())

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


def parse_departure_date(text: str, reference_date: Optional[date] = None) -> Optional[date]:
    """Extracts the first departure date from date range strings."""
    if not text or not isinstance(text, str):
        return None
    ref = reference_date or date.today()
    clean = str(text).strip()
    clean = re.sub(r'\s*\([^)]*\)', '', clean).strip()

    # Format YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", clean)
    if m_iso:
        try:
            return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass

    # Format DD.MM.YYYY - ... or single DD.MM.YYYY
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", clean)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # Format DD.MM - DD.MM (no year)
    m_short = re.search(r"(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})", clean)
    if m_short:
        try:
            d = int(m_short.group(1))
            mon = int(m_short.group(2))
            year = ref.year
            if mon < ref.month - 1:
                year += 1
            return date(year, mon, d)
        except ValueError:
            pass

    return None


def parse_duration_days(text: Union[str, int, float]) -> Optional[int]:
    """Extracts duration in days from text strings (e.g. '8 dni', '7 Tage', '7 nocy')."""
    if text is None:
        return None
    if isinstance(text, float):
        if math.isnan(text):
            return None
        return int(text)
    if isinstance(text, int):
        return text
    text_str = str(text).strip()
    if not text_str or text_str.lower() in ("nan", "none", ""):
        return None
    m = re.search(r"(\d+)\s*(?:Tage|Tagen|dni|days|Nächte|nocy)", text_str, re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b(\d+)\b", text_str)
    return int(m2.group(1)) if m2 else None


def parse_nights(text: Union[str, int, float]) -> Optional[int]:
    """Extracts nights from duration string, or days as fallback."""
    if text is None:
        return None
    if isinstance(text, float):
        if math.isnan(text):
            return None
        return int(text)
    if isinstance(text, int):
        return text
    text_str = str(text).strip()
    if not text_str or text_str.lower() in ("nan", "none", ""):
        return None

    # 1. Explicit nights (e.g. '7 nocy', '7 Nächte')
    m_noc = re.search(r"(\d+)\s*(?:nocy|noclegów|noclegi|noc|Nächte|Nacht)", text_str, re.I)
    if m_noc:
        return int(m_noc.group(1))

    # 2. Polish 'dni' (e.g. '8 dni' usually represents 7 nights in hotel)
    m_dni = re.search(r"(\d+)\s*(?:dni|dzień)", text_str, re.I)
    if m_dni:
        val = int(m_dni.group(1))
        return val - 1 if val > 1 else 1

    # 3. German 'Tage' (e.g. '7 Tage' corresponds to 7 nights package, '5 Tage' to 4-5 nights)
    m_tage = re.search(r"(\d+)\s*(?:Tage|Tag|days|day)", text_str, re.I)
    if m_tage:
        return int(m_tage.group(1))

    m_num = re.search(r"\b(\d+)\b", text_str)
    return int(m_num.group(1)) if m_num else None


def parse_travelers(url: str = "", text: str = "") -> Tuple[int, int]:
    """Extracts (adults, children) count from URL parameters and duration/text."""
    s = str(url or "") + " " + str(text or "")
    m_alloc = re.search(r"roomAllocation=([A-Za-z0-9\-,]+)", s)
    if m_alloc:
        alloc = m_alloc.group(1)
        parts = alloc.split(",")
        ad_part = parts[0].split("-")
        adults = len([p for p in ad_part if p.upper() == "A"])
        children = len(parts) - 1
        return adults, children

    adults = 2
    children = 0
    m_ad = re.search(r"(?:adults|filter\[person\])=(\d+)", s)
    if m_ad:
        adults = int(m_ad.group(1))

    if "children=" in s or "filter[child]" in s or "childAge" in s:
        m_ch = re.search(r"(?:children|filter\[child\])=([^&]+)", s)
        if m_ch and m_ch.group(1).strip() and m_ch.group(1).strip() not in ("0", "none", "None"):
            children = 1

    m_pers = re.search(r"(\d+)\s*Pers", s, re.I)
    if m_pers and "roomAllocation=" not in s and "adults=" not in s and "filter[person]=" not in s:
        adults = int(m_pers.group(1))

    return adults, children


def is_offer_comparable(
    dates_pl: str,
    dates_de: str,
    duration_pl: Any,
    duration_de: Any,
    max_date_diff_days: int = 2,
    max_duration_diff_days: int = 0,
    offer_url_pl: str = "",
    offer_url_de: str = "",
) -> Tuple[bool, str]:
    """
    Verifies that Polish and German offers have matching parameters:
    - Same traveler composition (adults and children must match).
    - Departure dates within +-max_date_diff_days (default +-2 days). Wide 30-day windows are rejected.
    - Durations in hotel nights match strictly (default +-0 nights difference).
    """
    # 1. Traveler Composition Check
    if offer_url_pl or offer_url_de:
        ad_pl, ch_pl = parse_travelers(offer_url_pl, duration_pl)
        ad_de, ch_de = parse_travelers(offer_url_de, duration_de)
        if ad_pl != ad_de:
            return False, f"Adults mismatch: PL {ad_pl} vs DE {ad_de}"
        if ch_pl != ch_de:
            return False, f"Children mismatch: PL {ch_pl} vs DE {ch_de}"

    # 2. Departure Date Check (+-2 days max)
    d_pl = parse_departure_date(dates_pl)
    date_matched = False
    date_err = ""

    # Check exact departureDate in offer_url_de
    if offer_url_de and d_pl:
        m_dep = re.search(r"departureDate=(\d{4}-\d{2}-\d{2})", offer_url_de)
        if m_dep:
            d_u = parse_departure_date(m_dep.group(1))
            if d_u:
                diff_d = abs((d_pl - d_u).days)
                if diff_d <= max_date_diff_days:
                    date_matched = True
                else:
                    date_err = f"Departure mismatch: PL {d_pl} vs DE {d_u} ({diff_d}d > {max_date_diff_days}d)"

    # Check dates_de as single date
    if not date_matched and dates_de and "_" not in str(dates_de):
        d_de = parse_departure_date(dates_de)
        if d_pl and d_de:
            diff_d = abs((d_pl - d_de).days)
            if diff_d <= max_date_diff_days:
                date_matched = True
            else:
                date_err = f"Dates mismatch: PL {d_pl} vs DE {d_de} ({diff_d}d > {max_date_diff_days}d)"

    # Check dates_de as search window (only allowed if narrow: <= 3 days)
    if not date_matched and dates_de and "_" in str(dates_de):
        parts = str(dates_de).split("_")
        w_start = parse_departure_date(parts[0])
        w_end = parse_departure_date(parts[1]) if len(parts) > 1 else None
        if d_pl and w_start:
            win_len = (w_end - w_start).days if w_end else 0
            if 0 <= win_len <= 10:
                win_lo = w_start - timedelta(days=max_date_diff_days)
                win_hi = (w_end or w_start) + timedelta(days=max_date_diff_days)
                if win_lo <= d_pl <= win_hi:
                    date_matched = True
                else:
                    date_err = f"Dates mismatch: PL {d_pl} outside DE window [{w_start}, {w_end}]"
            else:
                date_err = f"Dates mismatch: DE search window [{w_start}, {w_end}] too wide ({win_len}d) for exact comparison"

    if not date_matched and (dates_de or offer_url_de) and d_pl:
        return False, date_err or "Dates mismatch"

    # 3. Strict Duration (Nights) Check
    n_pl = parse_nights(duration_pl)
    n_de = parse_nights(duration_de)

    if n_pl is not None and n_de is not None:
        dur_diff = abs(n_pl - n_de)
        if dur_diff > max_duration_diff_days:
            return False, f"Duration mismatch: PL {n_pl} nights vs DE {n_de} nights (diff: {dur_diff} > {max_duration_diff_days})"

    return True, "OK"


class CrossBorderArbitrageEngine:
    def __init__(
        self,
        eur_rate: Optional[float] = None,
        friction_cost_pln: float = DEFAULT_FRICTION_COST_PLN,
        matcher: Optional[HotelEntityMatcher] = None,
        max_date_diff_days: int = 2,
        max_duration_diff_days: int = 0,
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
                    offer_url_pl=str(pl_item.get("offer_url") or pl_item.get("url") or ""),
                    offer_url_de=str(de_item.get("offer_url") or ""),
                )
                if not comparable:
                    logger.debug(f"Skipping incompatible pair '{pl_name}' vs '{matched_de_name}': {reason}")
                    continue

                try:
                    de_eur = float(de_item.get("price_eur") or de_item.get("price") or 0.0)
                except (ValueError, TypeError):
                    continue

                if de_eur <= 0:
                    continue

                # Check that German airport is close to Polish border (BER, DRS, LEJ)
                de_ap = str(de_item.get("departure_airport") or "BER").upper().strip()
                if de_ap and de_ap not in ALLOWED_GERMAN_BORDER_AIRPORTS:
                    logger.debug(f"Skipping German offer from {de_ap}: too far from Polish border.")
                    continue

                # Airport-specific friction cost (train/fuel/parking to border hub)
                friction = (
                    self.friction_cost_pln
                    if self.friction_cost_pln != DEFAULT_FRICTION_COST_PLN
                    else BORDER_AIRPORT_FRICTION_DEFAULTS.get(de_ap, DEFAULT_FRICTION_COST_PLN)
                )

                # Currency conversion and friction
                de_converted_pln = round(de_eur * self.eur_rate, 0)
                net_de_pln = round(de_converted_pln + friction, 0)
                spread_pln = round(pl_price - net_de_pln, 0)
                savings_pct = (
                    round((spread_pln / pl_price) * 100, 1) if pl_price > 0 else 0.0
                )

                ap_label = "БЕРЛИНЕ (BER)" if de_ap == "BER" else f"{de_ap}"
                if spread_pln >= SIGNIFICANT_SPREAD_PLN:
                    best_deal = "GERMANY"
                    badge = f"🚨 ВЫГОДНЕЕ В {ap_label} (-{int(spread_pln):,} PLN / {savings_pct}%)".replace(",", " ")
                elif spread_pln > 0:
                    best_deal = "GERMANY"
                    badge = f"🟡 Небольшая выгода в {de_ap} (-{int(spread_pln):,} PLN)".replace(",", " ")
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
                        airport_de=de_ap,
                        price_pl_pln=pl_price,
                        price_de_eur=de_eur,
                        price_de_converted_pln=de_converted_pln,
                        friction_cost_pln=friction,
                        net_price_de_pln=net_de_pln,
                        spread_pln=spread_pln,
                        savings_pct=savings_pct,
                        best_deal=best_deal,
                        badge_text=badge,
                        tour_operator_de=str(de_item.get("tour_operator", "TUI DE")),
                        url_pl=(
                            f"https://fly.pl{pl_item.get('offer_url')}"
                            if str(pl_item.get("offer_url") or "").startswith("/")
                            else (pl_item.get("offer_url") or pl_item.get("url"))
                        ),
                        url_de=de_item.get("offer_url"),
                    )
                )

        # Sort matches by maximum spread descending (biggest savings first)
        matches.sort(key=lambda m: m.spread_pln, reverse=True)

        # Deduplicate matches by (hotel_name_pl, hotel_name_de, airport_de) keeping the highest spread
        unique_matches: List[ArbitrageMatch] = []
        seen_pairs = set()
        for m in matches:
            pair_key = (m.hotel_name_pl.lower().strip(), m.hotel_name_de.lower().strip(), m.airport_de)
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                unique_matches.append(m)

        return unique_matches

    def to_dataframe(self, matches: List[ArbitrageMatch]) -> pd.DataFrame:
        """Converts matches to a clean analytical DataFrame."""
        if not matches:
            return pd.DataFrame()
        return pd.DataFrame([m.to_dict() for m in matches])
