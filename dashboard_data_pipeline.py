#!/usr/bin/env python3
"""Data pipeline, time series analysis, and metric classification for travel price dashboard."""

from __future__ import annotations

import csv
import hashlib
import html as html_lib
import json
import logging
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from departure_analytics import (
    COHORT_LOOKBACK_TARGET_HOURS,
    HOT_DEPARTURE_CHART_DAYS_MAX,
    MIN_COMMON_HOTELS,
    MIN_DEAL_HOTELS,
    _hot_score,
    build_departure_hotel_histories,
    build_departure_offers_index,
    build_departure_price_curves,
    build_hot_departure_history,
    cheap_tier_label,
    departure_status_label,
    load_combined_departure_offers,
    load_stored_departure_cohorts,
)
from filter_trip import (
    _duration_bucket_is_missing,
    archive_reason,
    infer_offer_duration_bucket,
    is_config_archived,
    is_fixed_trip_config,
    offer_duration_days,
    parse_trip_duration_buckets,
    should_skip_monitor_config,
    skip_monitor_reason,
    trip_duration_bucket_id,
)
from hotel_deal_score import (
    _price_plateau_segments,
    _typical_observation_gap_hours,
    blend_tripadvisor_into_deal_score,
    build_premium_history_by_hotel,
    comeback_from_premium,
    compute_hotel_deal_metrics,
    compute_smooth_rarity_score,
    fetch_tripadvisor_from_listing_url,
    robust_premium_peak,
    time_weighted_price_baseline_from_segments,
    time_weighted_price_quantile_from_segments,
)

logger = logging.getLogger('dashboard_data_pipeline')

def _parse_ta_rating_value(value: Any) -> Optional[float]:
    """Parse rating value into a float between 1.0 and 5.0.

    Handles Polish comma formats ("4,5"), slashes ("4.5/5"),
    10-point scales ("9.0" -> 4.5), and empty placeholders ("—", "None", "nan").
    """
    if value is None or pd.isna(value):
        return None
    val_str = str(value).strip().replace(',', '.')
    if not val_str or val_str in ('—', 'None', 'nan', 'null', '0', '0.0'):
        return None
    m = re.search(r'\b([1-5](?:\.\d+)?)\b', val_str)
    if m:
        try:
            rating = float(m.group(1))
            if 0 < rating <= 5.0:
                return rating
        except (TypeError, ValueError):
            pass
    try:
        rating = float(val_str)
        if 5.0 < rating <= 10.0:
            rating = rating / 2.0
        return rating if 0 < rating <= 5.0 else None
    except (TypeError, ValueError):
        return None


def _parse_ta_review_count(value: Any) -> int:
    """Parse review count into a non-negative integer.

    Handles numbers with spaces ("1 250"), commas ("3,450"), dots ("3.450"),
    pandas float strings ("1454.0"), textual counts ("731 opinii"), and empty placeholders.
    """
    if value is None or pd.isna(value):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    val_str = str(value).strip()
    if not val_str or val_str in ('—', 'None', 'nan', 'null'):
        return 0
    try:
        f = float(val_str)
        return max(0, int(f))
    except (ValueError, TypeError):
        pass
    m = re.search(r'([\d\s,.\xa0]+)', val_str)
    if m:
        cleaned = m.group(1).replace('\xa0', ' ').strip()
        if cleaned.endswith('.0'):
            cleaned = cleaned[:-2]
        digits_only = re.sub(r'[^\d]', '', cleaned)
        if digits_only:
            try:
                return max(0, int(digits_only))
            except (TypeError, ValueError):
                return 0
    return 0


def _build_hotel_ta_cache(
    df: pd.DataFrame,
    reputation_kb_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Builds a lookup {hotel_name: {'ta_rating': float, 'ta_review_count': int, 'ta_source': str}}
    from historical data in df and reputation_kb_data so hotels don't lose their rating if the latest scrape row had empty rating.
    """
    cache: Dict[str, Dict[str, Any]] = {}
    if df is not None and not df.empty and 'hotel_name' in df.columns:
        rating_cols = [c for c in ('ta_rating', 'rating', 'hotel_rating') if c in df.columns]
        review_cols = [c for c in ('ta_review_count', 'review_count', 'reviews') if c in df.columns]
        source_cols = [c for c in ('ta_source', 'source') if c in df.columns]

        if rating_cols:
            work_df = df
            if 'scraped_at_display' in df.columns:
                work_df = df.sort_values('scraped_at_display')
            elif 'scraped_at' in df.columns:
                work_df = df.sort_values('scraped_at')

            for hotel_name, grp in work_df.groupby('hotel_name', sort=False):
                found_rating = None
                for col in rating_cols:
                    for val in reversed(grp[col].tolist()):
                        parsed = _parse_ta_rating_value(val)
                        if parsed is not None:
                            found_rating = parsed
                            break
                    if found_rating is not None:
                        break

                found_reviews = 0
                for col in review_cols:
                    for val in reversed(grp[col].tolist()):
                        parsed = _parse_ta_review_count(val)
                        if parsed > 0:
                            found_reviews = parsed
                            break
                    if found_reviews > 0:
                        break

                found_source = ""
                for col in source_cols:
                    for val in reversed(grp[col].tolist()):
                        if pd.notna(val) and str(val).strip():
                            found_source = str(val).strip()
                            break
                    if found_source:
                        break

                if found_rating is not None:
                    cache[hotel_name] = {
                        'ta_rating': found_rating,
                        'ta_review_count': found_reviews,
                        'ta_source': found_source or 'tripadvisor',
                    }

    # Fallback to AI hotel reputation knowledge base if rating was not in scrape CSV
    if reputation_kb_data:
        for h_name, rep in reputation_kb_data.items():
            if h_name not in cache:
                r_val = _parse_ta_rating_value(
                    rep.get('ta_rating') or rep.get('rating') or (rep.get('ratings') or {}).get('tripadvisor')
                )
                if r_val is not None:
                    rev_cnt = _parse_ta_review_count(
                        rep.get('ta_review_count') or rep.get('review_count') or (rep.get('ratings') or {}).get('tripadvisor_reviews')
                    )
                    cache[h_name] = {
                        'ta_rating': r_val,
                        'ta_review_count': rev_cnt,
                        'ta_source': 'tripadvisor',
                    }
    return cache


def _resolve_row_ta(
    last: Any,
    grp: Optional[pd.DataFrame],
    hotel_ta_cache: Dict[str, Dict[str, Any]],
    hotel_name: str,
    reputation_kb_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], int, str]:
    """Resolves TripAdvisor rating, review count, and source with fallback to grp, other cols, and historical cache."""
    ta_rating = None
    for col in ('ta_rating', 'rating', 'hotel_rating'):
        if hasattr(last, '__contains__') and col in last:
            ta_rating = _parse_ta_rating_value(last.get(col))
            if ta_rating is not None:
                break

    ta_reviews = 0
    for col in ('ta_review_count', 'review_count', 'reviews'):
        if hasattr(last, '__contains__') and col in last:
            ta_reviews = _parse_ta_review_count(last.get(col))
            if ta_reviews > 0:
                break

    ta_source = str(last.get('ta_source') or '').strip() if hasattr(last, 'get') else ''

    if grp is not None and not grp.empty:
        if ta_rating is None:
            for col in ('ta_rating', 'rating', 'hotel_rating'):
                if col in grp.columns:
                    for prev_val in reversed(list(grp[col])):
                        parsed = _parse_ta_rating_value(prev_val)
                        if parsed is not None:
                            ta_rating = parsed
                            break
                    if ta_rating is not None:
                        break
        if ta_reviews == 0:
            for col in ('ta_review_count', 'review_count', 'reviews'):
                if col in grp.columns:
                    for prev_val in reversed(list(grp[col])):
                        parsed = _parse_ta_review_count(prev_val)
                        if parsed > 0:
                            ta_reviews = parsed
                            break
                    if ta_reviews > 0:
                        break

    cached = hotel_ta_cache.get(hotel_name) if hotel_ta_cache else None
    if cached:
        if ta_rating is None:
            ta_rating = cached.get('ta_rating')
        if ta_reviews == 0:
            ta_reviews = cached.get('ta_review_count', 0)
        if not ta_source:
            ta_source = cached.get('ta_source', 'tripadvisor')

    if reputation_kb_data and hotel_name in reputation_kb_data:
        rep = reputation_kb_data[hotel_name]
        if ta_rating is None:
            ta_rating = _parse_ta_rating_value(
                rep.get('ta_rating') or rep.get('rating') or (rep.get('ratings') or {}).get('tripadvisor')
            )
        if ta_reviews == 0:
            ta_reviews = _parse_ta_review_count(
                rep.get('ta_review_count') or rep.get('review_count') or (rep.get('ratings') or {}).get('tripadvisor_reviews')
            )
        if not ta_source and ta_rating is not None:
            ta_source = 'tripadvisor'

    if not ta_source and ta_rating is not None:
        ta_source = 'tripadvisor'

    return ta_rating, ta_reviews, ta_source


def extract_airport_from_url(url: Any) -> Optional[str]:
    """Извлекает аэропорт вылета из URL (filter[from], fly_from_code, wylot, etc.)"""
    if not url or pd.isna(url):
        return None
    url_str = str(url).strip()
    try:
        parsed_url = urlparse(url_str)
        query_params = parse_qs(parsed_url.query)
        for key in ('filter[from]', 'fly_from_code', 'wylot', 'from', 'departure'):
            val = query_params.get(key, [None])[0]
            if val:
                airports = [a.strip() for a in str(val).split(',') if a.strip()]
                if airports:
                    return airports[0]
        # Regex search if encoded or missing in parsed params
        match = re.search(r'(?:filter\[from\]|fly_from_code|wylot)=([^&]+)', url_str)
        if match:
            raw = unquote(match.group(1))
            return raw.split(',')[0].strip()
    except Exception:
        pass
    return None


def normalize_text(value: Any) -> str:
    try:
        return ' '.join(str(value).strip().lower().split())
    except Exception:
        return str(value)


def normalize_dates(value: Any) -> str:
    """Нормализует строку дат к формату YYYY-MM-DD|YYYY-MM-DD для устойчивого сравнения."""
    try:
        s = str(value)
        m = re.findall(r"(\d{1,2})[\.-](\d{1,2})[\.-](\d{4})", s)
        if len(m) >= 2:
            def to_iso(t):
                d, mth, y = t
                return f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"
            return f"{to_iso(m[0])}|{to_iso(m[1])}"
    except Exception:
        pass
    return str(value).strip()


_CHEAPER_ALTS_CACHE: Dict[Tuple, List[Dict[str, Any]]] = {}


def find_cheaper_airport_alternatives(
    df_all_airports: Optional[pd.DataFrame],
    hotel_name: str,
    dates: str,
    current_price: float,
    current_airport: Optional[str] = None,
    min_savings_pln: float = 150.0,
    min_savings_pct: float = 3.0,
) -> List[Dict[str, Any]]:
    """Находит более дешевые предложения того же отеля на те же даты (или ±1 день) из других аэропортов."""
    if df_all_airports is None or df_all_airports.empty or not hotel_name or current_price <= 0:
        return []

    cache_key = (hotel_name, dates, current_price, current_airport, min_savings_pln, min_savings_pct)
    if cache_key in _CHEAPER_ALTS_CACHE:
        return _CHEAPER_ALTS_CACHE[cache_key]

    try:
        hotel_name_norm = normalize_text(hotel_name)
        dates_norm = normalize_dates(dates)
        current_airport_norm = (str(current_airport).strip() if current_airport else '') or 'Warszawa'

        # Предобработка столбцов в df_all_airports
        if '__hotel_norm' not in df_all_airports.columns:
            df_all_airports['__hotel_norm'] = df_all_airports['hotel_name'].astype(str).map(normalize_text)
        if '__dates_norm' not in df_all_airports.columns:
            df_all_airports['__dates_norm'] = df_all_airports['dates'].astype(str).map(normalize_dates)

        # Парсинг дат текущего предложения
        cur_dep, cur_ret = None, None
        if '|' in dates_norm:
            parts = dates_norm.split('|')
            try:
                cur_dep = datetime.strptime(parts[0], "%Y-%m-%d").date()
                cur_ret = datetime.strptime(parts[1], "%Y-%m-%d").date()
            except Exception:
                pass

        # 1. Поиск совпадений по отелю
        hotel_mask = (df_all_airports['__hotel_norm'] == hotel_name_norm)
        if not hotel_mask.any():
            base_name = hotel_name_norm.split('(')[0].strip()
            if len(base_name) >= 6:
                hotel_mask = df_all_airports['__hotel_norm'].str.startswith(base_name)

        same_hotel = df_all_airports[hotel_mask]
        if same_hotel.empty:
            _CHEAPER_ALTS_CACHE[cache_key] = []
            return []

        # 2. Фильтрация по датам: сначала точное совпадение
        exact_dates_mask = (same_hotel['__dates_norm'] == dates_norm)
        matched_candidates = same_hotel[exact_dates_mask]

        # Если есть dates_norm и cur_dep, также допускаем ±1 день по вылету
        if cur_dep and cur_ret:
            def dates_within_1_day(d_norm_str: str) -> bool:
                if '|' not in str(d_norm_str):
                    return False
                try:
                    p = str(d_norm_str).split('|')
                    d_dep = datetime.strptime(p[0], "%Y-%m-%d").date()
                    d_ret = datetime.strptime(p[1], "%Y-%m-%d").date()
                    return abs((d_dep - cur_dep).days) <= 1 and abs((d_ret - cur_ret).days) <= 1
                except Exception:
                    return False

            close_dates_mask = same_hotel['__dates_norm'].map(dates_within_1_day)
            matched_candidates = same_hotel[exact_dates_mask | close_dates_mask]

        if matched_candidates.empty:
            _CHEAPER_ALTS_CACHE[cache_key] = []
            return []

        matched_candidates = matched_candidates.copy()

        # 3. Извлечение аэропорта
        matched_candidates['airport'] = None
        if 'departure_airport' in matched_candidates.columns:
            matched_candidates['airport'] = matched_candidates['departure_airport']
        if 'from_airport' in matched_candidates.columns:
            matched_candidates['airport'] = matched_candidates['airport'].fillna(matched_candidates['from_airport'])

        matched_candidates['airport'] = matched_candidates['airport'].where(
            matched_candidates['airport'].astype(str).str.strip().ne('') &
            matched_candidates['airport'].astype(str).str.strip().ne('Все аэропорты') &
            matched_candidates['airport'].astype(str).str.strip().ne('None'),
            None
        )
        url_col = 'offer_url' if 'offer_url' in matched_candidates.columns else ('url' if 'url' in matched_candidates.columns else None)
        if url_col:
            matched_candidates['airport'] = matched_candidates['airport'].fillna(
                matched_candidates[url_col].apply(extract_airport_from_url)
            )
        matched_candidates['airport'] = matched_candidates['airport'].fillna('Другой город')
        matched_candidates.loc[matched_candidates['airport'].astype(str).str.strip() == '', 'airport'] = 'Другой город'

        # 4. Выбор записи с минимальной ценой для каждого альтернативного аэропорта
        idx_min_by_airport = matched_candidates.groupby('airport')['price'].idxmin()
        cols_to_keep = ['airport', 'price']
        for col in ('offer_url', 'url'):
            if col in matched_candidates.columns:
                cols_to_keep.append(col)
        airport_prices = matched_candidates.loc[idx_min_by_airport, cols_to_keep].reset_index(drop=True)

        cur_ap_lower = current_airport_norm.lower()
        is_cur_warsaw = any(w in cur_ap_lower for w in ('warszaw', 'waw', 'wmi', 'rdo')) or not cur_ap_lower

        def is_same_airport(alt_ap: Any) -> bool:
            alt_lower = str(alt_ap).strip().lower()
            if is_cur_warsaw and any(w in alt_lower for w in ('warszaw', 'waw', 'wmi', 'rdo')):
                return True
            return alt_lower == cur_ap_lower

        # 5. Фильтрация более дешевых предложений из других аэропортов
        mask_cheaper = (airport_prices['price'] < current_price) & (~airport_prices['airport'].apply(is_same_airport))
        cheaper_alternatives = airport_prices[mask_cheaper].sort_values('price')

        alternatives = []
        for _, row in cheaper_alternatives.iterrows():
            row_p = float(row['price'])
            savings = current_price - row_p
            savings_percent = (savings / current_price) * 100.0

            if savings < min_savings_pln or savings_percent < min_savings_pct:
                continue

            alt_url = ''
            if 'offer_url' in row and row['offer_url']:
                alt_url = str(row['offer_url']).strip()
            if not alt_url and 'url' in row and row['url']:
                alt_url = str(row['url']).strip()

            alternatives.append({
                'airport': str(row['airport']).strip(),
                'price': row_p,
                'savings': float(savings),
                'savings_percent': float(savings_percent),
                'url': alt_url,
            })

        _CHEAPER_ALTS_CACHE[cache_key] = alternatives
        return alternatives
    except Exception as e:
        print(f"Ошибка при поиске альтернативных аэропортов: {e}")
        _CHEAPER_ALTS_CACHE[cache_key] = []
        return []


def _resolve_listing_url_for_backfill(
    df: pd.DataFrame,
    config_file: Optional[str],
    data_file: str,
) -> str:
    if config_file and os.path.isfile(config_file):
        try:
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            url = resolve_config_url(cfg)
            if url:
                return url
        except Exception:
            pass
    if not df.empty and "url" in df.columns:
        for val in reversed(df["url"].dropna().astype(str).tolist()):
            if "fly.pl" in val and ("/oferta/" in val or "/szukaj-wycieczek/" in val or "/kierunek/" in val):
                return val
    cfg_path = resolve_config_path(data_file, config_file)
    if cfg_path and os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                return resolve_config_url(json.load(f))
        except Exception:
            pass
    return ""


def _backfill_ta_for_latest_rows(
    latest_rows: List[dict],
    df: pd.DataFrame,
    config_file: Optional[str],
    data_file: str,
    enable_live_crawl: bool = False,
) -> int:
    if not latest_rows:
        return 0
    missing = [
        row for row in latest_rows
        if _parse_ta_rating_value(row.get("ta_rating")) is None
    ]
    if not missing:
        return 0
    if not enable_live_crawl:
        return 0
    search_url = _resolve_listing_url_for_backfill(df, config_file, data_file)
    if not search_url:
        print("⚠️ TA backfill: не найден URL выдачи fly.pl")
        return 0
    print(f"⭐ TA backfill: live-выдача fly.pl для {len(missing)} отелей без оценки...")
    lookup = fetch_tripadvisor_from_listing_url(search_url, max_pages=8)
    by_name = lookup.get("by_name") or {}
    by_offer = lookup.get("by_offer") or {}
    filled = 0
    for row in latest_rows:
        if _parse_ta_rating_value(row.get("ta_rating")) is not None:
            continue
        offer_url = str(row.get("offer_url") or "").strip()
        hotel_name = str(row.get("hotel_name") or "").strip()
        ta = by_offer.get(offer_url) or by_name.get(hotel_name)
        if not ta:
            continue
        row.update(ta)
        filled += 1
    print(f"⭐ TA backfill: заполнено {filled}/{len(missing)}")
    return filled


# Официальный logomark TripAdvisor (owl), cropped from TA_logo_primary.svg (tacdn.com).
TRIPADVISOR_HEADER_ICON_HTML = (
    '<span class="th-ta-icon" aria-hidden="true">'
    '<svg class="th-ta-svg" viewBox="0 0 50 30" xmlns="http://www.w3.org/2000/svg">'
    '<path fill="#FAC415" d="M8.69853,6.34985C13.42485,5.74015,26.834,5.32015,23.16029,24.69632l4.16692-.339C25.50191,12.41381,29.31986,6.324,41.25838,5.74015,21.45779-5.22456,10.18426,6.15809,8.69853,6.34985Z"/>'
    '<path fill="#fff" d="M27.13191,21.62794A11.34312,11.34312,0,1,0,33.84147,7.055,11.347,11.347,0,0,0,27.13191,21.62794Z"/>'
    '<circle fill="#fff" cx="12.62599" cy="17.65102" r="11.34537"/>'
    '<circle fill="#EE6946" cx="12.4632" cy="17.53993" r="2.0971"/>'
    '<circle fill="#00AF87" cx="37.74486" cy="17.53993" r="2.09618"/>'
    '<path fill="#000" d="M47.89824,10.18a16.25082,16.25082,0,0,1,2.48088-5.0444l-8.41926-.00647A30.65918,30.65918,0,0,0,25.14368.461,31.36745,31.36745,0,0,0,7.90015,5.18868L0,5.19309a16.3389,16.3389,0,0,1,2.46941,5.00044A12.60265,12.60265,0,0,0,22.46235,25.53426L25.14721,29.554l2.71074-4.05353A12.61369,12.61369,0,0,0,47.89824,10.18ZM37.37,5.094A12.57259,12.57259,0,0,0,25.19676,16.73368,12.6202,12.6202,0,0,0,12.87912,5.04515,31.17654,31.17654,0,0,1,25.14368,2.66044,29.67419,29.67419,0,0,1,37.37,5.094ZM12.62632,27.71926A10.06971,10.06971,0,1,1,22.695,17.652,10.08062,10.08062,0,0,1,12.62632,27.71926Zm28.63412-.57147a10.07577,10.07577,0,0,1-12.93515-5.96V21.185A10.07008,10.07008,0,1,1,41.26044,27.14779Z"/>'
    '<path fill="#000" d="M12.47059,11.3094a6.231,6.231,0,1,0,6.22191,6.23A6.24029,6.24029,0,0,0,12.47059,11.3094Zm0,10.31575a4.08509,4.08509,0,1,1,4.07706-4.08574A4.09513,4.09513,0,0,1,12.47059,21.62515Z"/>'
    '<path fill="#000" d="M37.74486,11.3094a6.231,6.231,0,1,0,6.22779,6.23A6.23822,6.23822,0,0,0,37.74486,11.3094Zm0,10.31575a4.08508,4.08508,0,1,1,4.08367-4.08574A4.091,4.091,0,0,1,37.74486,21.62515Z"/>'
    '</svg></span>'
)


def _render_ta_rating_html(ta_rating: Any, ta_review_count: Any) -> str:
    rating = _parse_ta_rating_value(ta_rating)
    reviews = _parse_ta_review_count(ta_review_count)
    if rating is None:
        return (
            '<span class="ta-rating ta-rating--empty" data-sort-value="-1" '
            'title="Новый отель или нет отзывов TripAdvisor">'
            '<span class="ta-stars ta-stars--empty">—</span>'
            '<span class="ta-meta"><span class="ta-score">—</span></span>'
            '</span>'
        )
    full = int(rating)
    frac = rating - full
    stars = []
    for idx in range(1, 6):
        if rating >= idx:
            stars.append('<span class="ta-star ta-star--full">★</span>')
        elif idx - 1 < rating < idx and frac >= 0.25:
            stars.append('<span class="ta-star ta-star--half">★</span>')
        else:
            stars.append('<span class="ta-star ta-star--empty">☆</span>')
    stars_html = "".join(stars)
    reviews_html = (
        f'<span class="ta-reviews">{reviews} opinii</span>'
        if reviews > 0 else '<span class="ta-reviews ta-reviews--new">новый</span>'
    )
    return (
        f'<span class="ta-rating" data-sort-value="{rating:.2f}" '
        f'title="TripAdvisor {rating:.1f}/5 · {reviews} opinii">'
        f'<span class="ta-stars" style="--ta-fill:{min(100, rating / 5 * 100):.0f}%">{stars_html}</span>'
        f'<span class="ta-meta"><span class="ta-score">{rating:.1f}</span>{reviews_html}</span>'
        f'</span>'
    )


def _merge_departure_cohorts(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [frame for frame in frames if frame is not None and not frame.empty]
    if not parts:
        return pd.DataFrame()
    merged = pd.concat(parts, ignore_index=True, sort=False)
    key_cols = ["run_started_at", "departure_key"]
    if all(col in merged.columns for col in key_cols):
        merged = merged.drop_duplicates(subset=key_cols, keep="last")
    return merged


def _prepare_departure_cohorts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.copy()
    work["_run_ts"] = pd.to_datetime(work["run_started_at"], errors="coerce", utc=True)
    work = work.dropna(subset=["_run_ts"])
    for col in [
        "hot_score", "hotel_count", "below_10000_count", "days_to_departure",
        "min_price", "p10_price", "median_price", "p10_change_pct",
        "median_change_pct", "min_change_pct", "hotel_count_delta", "common_hotel_count",
        "avg_deal_score", "mean_avg_delta_pct", "hot_deal_count", "good_deal_count",
        "median_ta_rating", "ta_rated_hotel_count",
    ]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work[work["days_to_departure"].fillna(9999) >= 0]
    return work


def _load_departure_cohort_frames(data_dir: str, data_file: str):
    """Load cohorts + hot history from monitor cache (no full rebuild in CI)."""
    return load_stored_departure_cohorts(data_dir, travel_prices_file=data_file)


def _hotel_chart_viewer_href(filter_id: str, hotel_slug: str) -> str:
    return f"hotel-chart.html?filter={quote(str(filter_id))}&hotel={quote(str(hotel_slug))}"


def slugify(text: str) -> str:
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip('-')
    return text or "hotel"


def _hotel_series_payload_hash(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_hotel_series_manifest(series_dir: str) -> dict:
    path = os.path.join(series_dir, "manifest.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_hotel_series_manifest(series_dir: str, manifest: dict) -> None:
    os.makedirs(series_dir, exist_ok=True)
    with open(os.path.join(series_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)


def _parse_price_ceiling(display_price_ceiling):
    if display_price_ceiling is None:
        return None
    try:
        return float(display_price_ceiling)
    except (TypeError, ValueError):
        return None


def _resolve_history_ceiling(display_ceiling, history_ceiling):
    """History band for charts/vanished: defaults to 20k when display ceiling is set."""
    parsed = _parse_price_ceiling(history_ceiling)
    if parsed is not None:
        return parsed
    if display_ceiling is not None:
        return 20000.0
    return None


def _lowest_price_row(grp):
    """Строка с минимальной ценой среди офферов одного отеля."""
    prices = grp['price'].astype(float)
    return grp.loc[prices.idxmin()]


def _typical_observation_gap_hours(times, default=1.0):
    """Median interval between consecutive observations (hours), ignoring long data gaps."""
    gaps = []
    for i in range(1, len(times)):
        gaps.append((times[i] - times[i - 1]).total_seconds() / 3600.0)
    if not gaps:
        return max(default, 0.5)
    sorted_gaps = sorted(gaps)
    if len(sorted_gaps) >= 3:
        core = sorted_gaps[: max(1, (len(sorted_gaps) * 2) // 3)]
        typical = core[len(core) // 2]
    elif len(sorted_gaps) == 2:
        typical = sorted_gaps[0]
    else:
        typical = sorted_gaps[0]
    return max(typical, 0.5)


def _data_gap_threshold_hours(typical_gap):
    """Gap longer than this is treated as missing data, not price continuity."""
    return max(6.0, float(typical_gap) * 3.0)


def _iter_price_plateaus(times, prices):
    """Yield (price, duration_hours) for each constant-price plateau."""
    if not times or not prices:
        return
    if len(times) != len(prices):
        return

    typical_gap = _typical_observation_gap_hours(times)
    gap_threshold = _data_gap_threshold_hours(typical_gap)

    idx = 0
    while idx < len(prices):
        price = float(prices[idx])
        end = idx
        while end + 1 < len(prices) and float(prices[end + 1]) == price:
            end += 1
        if end + 1 < len(times):
            gap_after = (times[end + 1] - times[end]).total_seconds() / 3600.0
            if gap_after > gap_threshold:
                # No data after this plateau — do not count silence as this price.
                if end > idx:
                    hours = (times[end] - times[idx]).total_seconds() / 3600.0 + typical_gap
                else:
                    hours = typical_gap
            else:
                hours = (times[end + 1] - times[idx]).total_seconds() / 3600.0
        elif end > idx:
            hours = (times[end] - times[idx]).total_seconds() / 3600.0 + typical_gap
        elif idx > 0:
            hours = (times[idx] - times[idx - 1]).total_seconds() / 3600.0
        else:
            hours = typical_gap
        yield price, max(hours, 0.5)
        idx = end + 1


def _break_series_at_data_gaps(x_values, y_values, extra_series=None):
    """Insert None between points when the interval implies missing observations."""
    if not x_values or not y_values:
        return x_values, y_values, extra_series or []
    times = pd.to_datetime(pd.Series(x_values), utc=True).tolist()
    typical_gap = _typical_observation_gap_hours(times)
    gap_threshold = _data_gap_threshold_hours(typical_gap)
    extras = extra_series if extra_series is not None else []
    out_x, out_y = [], []
    out_extras = [[] for _ in extras] if extras else None
    for i in range(len(y_values)):
        if i > 0:
            gap_h = (times[i] - times[i - 1]).total_seconds() / 3600.0
            if gap_h > gap_threshold:
                out_x.append(None)
                out_y.append(None)
                if out_extras is not None:
                    for bucket in out_extras:
                        bucket.append(None)
        out_x.append(x_values[i])
        out_y.append(y_values[i])
        if out_extras is not None:
            for j, bucket in enumerate(out_extras):
                bucket.append(extras[j][i])
    if out_extras is None:
        return out_x, out_y, None
    return out_x, out_y, out_extras


def _baseline_from_segments(segments):
    if not segments:
        return None
    total_hours = sum(h for _, h in segments)
    if total_hours <= 0:
        return float(segments[-1][0])
    return sum(p * h for p, h in segments) / total_hours


def _quantile_from_segments(segments, quantile):
    if not segments:
        return None
    q = max(0.0, min(1.0, float(quantile)))
    ordered = sorted(segments, key=lambda x: x[0])
    total_hours = sum(h for _, h in ordered)
    if total_hours <= 0:
        return float(ordered[-1][0])
    target = total_hours * q
    seen = 0.0
    for price, hours in ordered:
        seen += hours
        if seen >= target:
            return float(price)
    return float(ordered[-1][0])


def _volatility_from_segments(segments):
    if len(segments) < 2:
        return None
    total_hours = sum(h for _, h in segments)
    if total_hours <= 0:
        return None
    mean = sum(p * h for p, h in segments) / total_hours
    if mean <= 0:
        return None
    var = sum(h * (p - mean) ** 2 for p, h in segments) / total_hours
    return float(var ** 0.5 / mean)


def _time_weighted_price_baseline(grp, time_col='scraped_at_display', price_col='price', segments=None):
    """Typical price: weighted mean by how long each plateau was held (hours/days)."""
    if segments is None:
        segments = _price_plateau_segments(grp, time_col=time_col, price_col=price_col)
    return _baseline_from_segments(segments)


def _price_plateau_segments(grp, time_col='scraped_at_display', price_col='price'):
    if grp is None or grp.empty:
        return []
    work = grp.sort_values(time_col).dropna(subset=[time_col, price_col])
    if work.empty:
        return []
    times_series = work[time_col]
    if not pd.api.types.is_datetime64_any_dtype(times_series):
        times = pd.to_datetime(times_series, utc=True).tolist()
    else:
        if times_series.dt.tz is None:
            times = times_series.dt.tz_localize('UTC').tolist()
        else:
            times = times_series.dt.tz_convert('UTC').tolist()
    prices = work[price_col].astype(float).tolist()
    return list(_iter_price_plateaus(times, prices))


def _time_weighted_price_quantile(grp, quantile, time_col='scraped_at_display', price_col='price', segments=None):
    """Quantile weighted by plateau duration (not by scrape count)."""
    if segments is None:
        segments = _price_plateau_segments(grp, time_col=time_col, price_col=price_col)
    return _quantile_from_segments(segments, quantile)


def _time_weighted_price_volatility(grp, time_col='scraped_at_display', price_col='price', segments=None):
    """Coefficient of variation using duration-weighted mean/std."""
    if segments is None:
        segments = _price_plateau_segments(grp, time_col=time_col, price_col=price_col)
    return _volatility_from_segments(segments)


def _last_run_slice(df, time_col='scraped_at_display', gap_minutes=5):
    """Последний ран скрейпа как DataFrame."""
    runs = list(iter_scrape_runs(df, time_col=time_col, gap_minutes=gap_minutes))
    if not runs:
        return df.iloc[0:0].copy()
    return runs[-1][2].copy()


def iter_scrape_runs(df, time_col='scraped_at_display', gap_minutes=5):
    """Итератор ранов скрейпа: (start_pos, end_pos, slice), позиции для iloc."""
    if df.empty:
        return
    df_time = df.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
    tdiff = df_time[time_col].diff()
    boundaries = df_time.index[tdiff > pd.Timedelta(minutes=gap_minutes)].tolist()
    starts = [0] + boundaries
    ends = boundaries + [len(df_time)]
    for start_idx, end_idx in zip(starts, ends):
        yield start_idx, end_idx, df_time.iloc[start_idx:end_idx]


def collapse_canonical_per_run(df, ceiling_val=None, run_gap_minutes=5, group_cols=None):
    """One canonical row per hotel (and optional duration bucket) per scrape run.

    With a display ceiling, consider only offers at or below it, then pick
    the cheapest. Hotels only seen above the ceiling in a run are omitted
    from that band (they remain in the wider history band up to history ceiling).
    """
    group_cols = group_cols or ['hotel_name']
    if df.empty:
        return df.copy()

    work = df.dropna(subset=['scraped_at_display']).copy()
    if work.empty:
        return pd.DataFrame(columns=df.columns)

    if '__price_num' not in work.columns:
        work['__price_num'] = pd.to_numeric(work['price'], errors='coerce')
    work = work.dropna(subset=['__price_num']).sort_values('scraped_at_display')
    work = work[work['__price_num'] >= 1000.0]
    if work.empty:
        return pd.DataFrame(columns=df.columns)

    # Assign run_id vectorially
    tdiff = work['scraped_at_display'].diff()
    is_new_run = (tdiff > pd.Timedelta(minutes=run_gap_minutes)).fillna(False)
    work['__run_id'] = is_new_run.cumsum()

    if ceiling_val is not None:
        work = work[work['__price_num'] <= float(ceiling_val)]
        if work.empty:
            return pd.DataFrame(columns=df.columns)

    # Pick lowest price per run per hotel
    work_sorted = work.sort_values(by=['__price_num', 'scraped_at_display'])
    dedup_cols = ['__run_id'] + list(group_cols)
    res = work_sorted.drop_duplicates(subset=dedup_cols, keep='first')
    sort_cols = list(group_cols) + ['scraped_at_display']
    return res.drop(columns=['__run_id', '__price_num'], errors='ignore').sort_values(by=sort_cols).reset_index(drop=True)


def build_daily_offers_count_timeline(
    df,
    ceiling_val=None,
    group_cols=None,
    tz='Europe/Warsaw',
    pick='last',
    run_gap_minutes=5,
    canon_df=None,
):
    """One point per calendar day: canonical offer count from first/last scrape run that day."""
    empty = {'dates': [], 'counts': [], 'meta': []}
    if df is None or df.empty:
        return empty

    group_cols = group_cols or ['hotel_name']
    if canon_df is not None:
        canon = canon_df
    else:
        canon = collapse_canonical_per_run(
            df,
            ceiling_val,
            group_cols=group_cols,
            run_gap_minutes=run_gap_minutes,
        )
    if canon.empty:
        return empty

    runs = []
    for _, _, run_slice in iter_scrape_runs(canon, gap_minutes=run_gap_minutes):
        if run_slice.empty:
            continue
        run_time = run_slice['scraped_at_display'].iloc[0]
        try:
            day = pd.Timestamp(run_time).tz_convert(tz).date()
        except Exception:
            day = pd.Timestamp(run_time).date()
        runs.append({
            'day': day,
            'time': run_time,
            'count': len(run_slice),
        })

    if not runs:
        return empty

    run_df = pd.DataFrame(runs).sort_values('time')
    if pick == 'first':
        daily = run_df.groupby('day', as_index=False).first()
    else:
        daily = run_df.groupby('day', as_index=False).last()

    meta = []
    dates = []
    counts = []
    for _, row in daily.iterrows():
        day_ts = pd.Timestamp(row['day'])
        run_ts = pd.Timestamp(row['time'])
        try:
            run_label = run_ts.tz_convert(tz).strftime('%d.%m.%Y %H:%M')
        except Exception:
            run_label = run_ts.strftime('%d.%m.%Y %H:%M')
        dates.append(day_ts.strftime('%Y-%m-%d'))
        counts.append(int(row['count']))
        meta.append({
            'day': day_ts.strftime('%d.%m.%Y'),
            'count': int(row['count']),
            'run_time': run_label,
            'pick': pick,
        })

    return {'dates': dates, 'counts': counts, 'meta': meta}


def _prepare_trip_duration_columns(df: pd.DataFrame, filter_config: dict) -> tuple[list[str], list[dict], bool]:
    buckets = (
        parse_trip_duration_buckets(filter_config)
        if is_fixed_trip_config(filter_config)
        else []
    )
    if not buckets:
        return ['hotel_name'], buckets, False
    if 'duration_bucket' not in df.columns:
        df['duration_bucket'] = ''
    mask = df['duration_bucket'].apply(
        lambda value: _duration_bucket_is_missing(value)
    )
    if mask.any():
        df.loc[mask, 'duration_bucket'] = df.loc[mask].apply(
            lambda row: infer_offer_duration_bucket(row.to_dict(), filter_config),
            axis=1,
        )
    known_ids = {str(b['id']) for b in buckets}
    stale = ~df['duration_bucket'].astype(str).isin(known_ids)
    if stale.any():
        df.loc[stale, 'duration_bucket'] = df.loc[stale].apply(
            lambda row: trip_duration_bucket_id(
                offer_duration_days(row.to_dict()), buckets
            ),
            axis=1,
        )
    df.drop(
        df[~df['duration_bucket'].astype(str).isin(known_ids)].index,
        inplace=True,
    )
    return ['hotel_name', 'duration_bucket'], buckets, True


def _unpack_table_group_key(group_key, use_trip_buckets: bool) -> tuple[str, str, str]:
    if use_trip_buckets:
        if isinstance(group_key, tuple):
            hotel_name = str(group_key[0])
            bucket = str(group_key[1] if len(group_key) > 1 else '')
        else:
            hotel_name = str(group_key)
            bucket = ''
        return hotel_name, bucket, trip_row_key(hotel_name, bucket)
    hotel_name = str(group_key[0] if isinstance(group_key, tuple) else group_key)
    return hotel_name, '', hotel_name


def _build_premium_history_index(df_history, display_ceiling, group_cols):
    out = {}
    if df_history is None or df_history.empty:
        return out
    use_buckets = 'duration_bucket' in group_cols
    for group_key, grp in df_history.groupby(group_cols, sort=False):
        _, _, row_id = _unpack_table_group_key(group_key, use_buckets)
        prices = grp['price'].astype(float)
        if prices.empty:
            continue
        premium_peak = robust_premium_peak(grp, display_ceiling, 'scraped_at_display', 'price')
        out[row_id] = {
            'history_max': float(prices.max()),
            'premium_peak': premium_peak,
        }
    return out


def classify_deal_badge(deal_score, confidence, delta48_pct=None, avg_pct=None, comeback_drop_pct=None):
    """Returns (label, css_class, display_badge)."""
    is_bad = (
        delta48_pct is not None and delta48_pct > 0
        and avg_pct is not None and avg_pct > 0
    )
    strong_comeback = comeback_drop_pct is not None and comeback_drop_pct >= 8.0
    if confidence == "Low" and not strong_comeback:
        return "Warm-up", "warm", "⏳ Warm-up"
    if is_bad and not strong_comeback:
        return "Bad", "bad", "📈 Bad"
    if deal_score >= 80:
        return "Hot", "hot", "🔥 Hot"
    if deal_score >= 65:
        return "Good", "good", "✅ Good"
    return "Normal", "normal", "↔️ Normal"


def determine_price_forecast(
    deal_score, confidence, avg_pct, delta48_pct, comeback_drop_pct=None,
):
    """Returns price forecast classification: {text, class, icon}."""
    strong_comeback = comeback_drop_pct is not None and comeback_drop_pct >= 8.0
    if confidence == "Low":
        if strong_comeback:
            return {'text': 'Наблюдать', 'class': 'forecast-wait', 'icon': '🟡'}
        return {'text': 'Мало данных', 'class': 'forecast-nodata', 'icon': '⏳'}

    avg_pct_val = float(avg_pct) if avg_pct is not None else 0.0
    delta48_pct_val = float(delta48_pct) if delta48_pct is not None else 0.0
    is_bad = (
        delta48_pct is not None and delta48_pct_val > 0
        and avg_pct is not None and avg_pct_val > 0
    )

    if strong_comeback:
        if avg_pct_val < -5.0 and delta48_pct_val <= 0.0:
            return {'text': 'Покупать', 'class': 'forecast-buy', 'icon': '🟢'}
        return {'text': 'Наблюдать', 'class': 'forecast-wait', 'icon': '🟡'}

    if avg_pct_val < -5.0:
        if delta48_pct_val <= 0.0:
            return {'text': 'Покупать', 'class': 'forecast-buy', 'icon': '🟢'}
        return {'text': 'Наблюдать', 'class': 'forecast-wait', 'icon': '🟡'}
    if deal_score >= 85 and avg_pct_val <= 3.0 and delta48_pct_val <= 5.0:
        return {'text': 'Покупать', 'class': 'forecast-buy', 'icon': '🟢'}
    if deal_score >= 75 and avg_pct_val <= 3.0 and delta48_pct_val <= 5.0:
        return {'text': 'Выгодно', 'class': 'forecast-buy', 'icon': '🟢'}
    if -5.0 <= avg_pct_val <= 5.0:
        return {'text': 'Наблюдать', 'class': 'forecast-wait', 'icon': '🟡'}
    if is_bad or deal_score < 80:
        return {'text': 'Дорого', 'class': 'forecast-expensive', 'icon': '🔴'}
    return {'text': 'Наблюдать', 'class': 'forecast-wait', 'icon': '🟡'}


def _table_deal_badge_compact(display_badge: str) -> str:
    text = str(display_badge or "").strip()
    return text.split()[0] if text else ""


def _table_duration_compact(duration: str) -> str:
    match = re.search(r"(\d+)\s*dni/(\d+)\s*noc", str(duration), re.I)
    if match:
        return f"{match.group(1)}d/{match.group(2)}n"
    return str(duration)


