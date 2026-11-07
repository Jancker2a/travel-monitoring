#!/usr/bin/env python3
"""
Дашборд с встроенными графиками вместо модальных окон
"""

import pandas as pd
import json
import csv
import hashlib
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple
import os
import re
import html as html_lib
from urllib.parse import urlparse, parse_qs, quote, unquote
from purchase_timing_analysis import analyze_purchase_timing
from departure_analytics import (
    build_departure_offers_index,
    build_departure_hotel_histories,
    build_hot_departure_history,
    build_departure_price_curves,
    cheap_tier_label,
    departure_status_label,
    _hot_score,
    HOT_DEPARTURE_CHART_DAYS_MAX,
    load_combined_departure_offers,
    load_stored_departure_cohorts,
    MIN_COMMON_HOTELS,
    MIN_DEAL_HOTELS,
    COHORT_LOOKBACK_TARGET_HOURS,
)
from hotel_deal_score import (
    blend_tripadvisor_into_deal_score,
    build_premium_history_by_hotel,
    comeback_from_premium,
    compute_hotel_deal_metrics,
    fetch_tripadvisor_from_listing_url,
    robust_premium_peak,
    compute_smooth_rarity_score,
    time_weighted_price_baseline_from_segments,
    time_weighted_price_quantile_from_segments,
    _price_plateau_segments,
    _typical_observation_gap_hours,
    _data_gap_threshold_hours,
)
from departure_identity import parse_offer_path
from departure_airports import (
    aggregate_cohorts_by_arrival_airport,
    arrival_hub_label,
    hub_regions_subtitle,
    should_group_by_arrival_airport,
)
from filter_registry import (
    active_filter_groups,
    archived_filter_group,
    active_filter_id,
    filter_href_by_charts_subdir,
    iter_filters,
    is_filter_paused,
)
from filter_params import (
    DATA_DIR_CONFIG_FILES,
    load_filter_config,
    resolve_config_url,
    render_filter_params_html,
    render_global_duration_switch_html,
    resolve_config_path,
    _country_label,
    _airports_parts,
    _airport_compact_label,
    _party_counts,
    _duration_label,
    _stars_min,
    _format_pln,
    _price_bounds,
    fly_query_param,
    COUNTRY_FLAGS,
    CATERING_LABELS,
)
from filter_trip import (
    _duration_bucket_is_missing,
    infer_offer_duration_bucket,
    is_fixed_trip_config,
    offer_duration_days,
    parse_trip_duration_buckets,
    trip_duration_bucket_id,
    trip_row_key,
)
from hopper_prediction_engine import batch_predict_offers, predict_offer_action
from germany_tour_client import GermanyTourClient
from cross_border_arbitrage import CrossBorderArbitrageEngine
from hotel_passport_drawer import (
    generate_hotel_ai_profile,
    get_hotel_passport_css,
    get_hotel_passport_js,
    render_hotel_card_horiz,
    render_hotel_passport_drawer_html,
)

try:
    from ai_market_oracle import synthesize_market_oracle
except ImportError:
    synthesize_market_oracle = None

try:
    from early_booking_analyzer import analyze_dataframe as analyze_early_booking
except ImportError:
    analyze_early_booking = None



from dashboard_data_pipeline import (
    _parse_ta_rating_value,
    _parse_ta_review_count,
    _build_hotel_ta_cache,
    _resolve_row_ta,
    extract_airport_from_url,
    normalize_text,
    normalize_dates,
    find_cheaper_airport_alternatives,
    _resolve_listing_url_for_backfill,
    _backfill_ta_for_latest_rows,
    _render_ta_rating_html,
    TRIPADVISOR_HEADER_ICON_HTML,
    _merge_departure_cohorts,
    _prepare_departure_cohorts,
    _load_departure_cohort_frames,
    _hotel_chart_viewer_href,
    slugify,
    _hotel_series_payload_hash,
    _load_hotel_series_manifest,
    _save_hotel_series_manifest,
    _parse_price_ceiling,
    _resolve_history_ceiling,
    _lowest_price_row,
    _typical_observation_gap_hours,
    _data_gap_threshold_hours,
    _iter_price_plateaus,
    _break_series_at_data_gaps,
    _baseline_from_segments,
    _quantile_from_segments,
    _volatility_from_segments,
    _time_weighted_price_baseline,
    _price_plateau_segments,
    _time_weighted_price_quantile,
    _time_weighted_price_volatility,
    _last_run_slice,
    iter_scrape_runs,
    collapse_canonical_per_run,
    build_daily_offers_count_timeline,
    _prepare_trip_duration_columns,
    _unpack_table_group_key,
    _build_premium_history_index,
    classify_deal_badge,
    determine_price_forecast,
    _table_deal_badge_compact,
    _table_duration_compact,
)
from dashboard_analytics_panel import (
    render_ai_market_briefing_html,
    render_early_booking_section_html,
    _should_show_alert,
    _hotel_base_name,
    _register_chart_href,
    _resolve_chart_href,
    _alert_is_current,
    _alert_display_fields,
    _render_note_price_block,
    _render_alert_card,
    _render_alert_history_row,
    _alert_matches_scope,
    _build_alerts_panel_html,
    _compute_chart_point_meta,
    _build_gap_jump_series,
    _render_hotel_chart_page,
)
from dashboard_card_renderer import (
    _metric_card,
    _render_top_movers_html,
)
from dashboard_styles import (
    get_dashboard_css,
)
from hotel_repository import HotelRepository

def generate_inline_charts_dashboard(data_file: str = 'data/travel_prices.csv', output_file: str = 'index.html', title: str = 'Travel Price Monitor • Расширенный дашборд', charts_subdir: str = 'hotel-charts', tz: str = 'Europe/Warsaw', alerts_file: str = None, all_airports_data_file: str = None, disappeared_after_runs: int = 2, display_price_ceiling: float = None, history_price_ceiling: float = None, write_legacy_hotel_html: bool = False, config_file: str = None, enable_ta_live_backfill: bool = False, force_ai: bool = False):
    """Генерирует дашборд с встроенными графиками"""
    
    # Загружаем данные (текущий месяц + архивные месяцы для полной истории сезона)
    try:
        frames = []
        data_file_abs = os.path.abspath(data_file)
        data_dir = os.path.dirname(data_file_abs)
        base_name = os.path.splitext(os.path.basename(data_file_abs))[0]  # e.g. 'travel_prices'
        archive_dir = os.path.join(data_dir, 'archive')
        # Читаем архивные файлы прошлых месяцев (отсортированы хронологически)
        if os.path.isdir(archive_dir):
            archive_files = sorted(
                f for f in os.listdir(archive_dir)
                if f.startswith(f"{base_name}_") and f.endswith('.csv')
            )
            for af in archive_files:
                try:
                    frames.append(pd.read_csv(os.path.join(archive_dir, af), quoting=csv.QUOTE_ALL, on_bad_lines='skip'))
                except Exception as ae:
                    print(f"⚠️ Ошибка чтения архива {af}: {ae}")
        # Текущий месяц
        frames.append(pd.read_csv(data_file, quoting=csv.QUOTE_ALL, on_bad_lines='skip'))
        df = pd.concat(frames, ignore_index=True, sort=False) if len(frames) > 1 else frames[0]
        if archive_files if os.path.isdir(archive_dir) else []:
            print(f"📦 Загружено архивных файлов: {len(archive_files)}, итого строк: {len(df)}")
        # Нормализуем время: аккуратно обрабатываем смешанные строки (с/без таймзоны)
        raw = df['scraped_at'].astype(str)
        mask_tz = raw.str.contains(r"Z$|[+-]\d{2}:\d{2}$", regex=True)
        tz_series = pd.to_datetime(raw.where(mask_tz), errors='coerce', utc=True)
        tz_series = tz_series.dt.tz_convert(tz)
        naive_series = pd.to_datetime(raw.where(~mask_tz), errors='coerce')
        try:
            naive_series = naive_series.dt.tz_localize(tz)
        except Exception:
            # Если часть уже осознанно tz-aware/NaT — оставим как есть
            pass
        df['scraped_at_local'] = tz_series.combine_first(naive_series)
        # Убираем строки с некорректной датой
        df = df.dropna(subset=['scraped_at_local']).copy()
        # Очищаем некорректные и мусорные цены (промо-бэйджи < 1000 PLN)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df = df.dropna(subset=['price'])
        df = df[df['price'] >= 1000.0]

        # Фильтрация по допустимому диапазону дат вылета для фиксированных фильтров (например, НГ 28.12-30.12)
        # Отсекает предложения fly.pl с другими датами («рекомендации в других месяцах»), ошибочно попавшие в выборку
        lo_d = None
        hi_d = None
        try:
            cfg_for_dates = load_filter_config(data_file, config_file)
            if cfg_for_dates and (cfg_for_dates.get("dynamic_search_dates") is False or is_fixed_trip_config(cfg_for_dates) or bool(cfg_for_dates.get("retire_after"))):
                url_for_dates = str(cfg_for_dates.get("url") or "")
                import urllib.parse
                parsed_u = urllib.parse.urlparse(url_for_dates)
                qs_u = urllib.parse.parse_qs(parsed_u.query)
                s_min_val = (
                    qs_u.get("startDateMin", [None])[0]
                    or qs_u.get("whenFrom", [None])[0]
                    or qs_u.get("filter[whenFrom]", [None])[0]
                )
                s_max_val = (
                    qs_u.get("startDateMax", [None])[0]
                    or qs_u.get("whenTo", [None])[0]
                    or qs_u.get("filter[whenTo]", [None])[0]
                )

                def _parse_d(s):
                    if not s:
                        return None
                    m1 = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', str(s).strip())
                    if m1:
                        return date(int(m1.group(3)), int(m1.group(2)), int(m1.group(1)))
                    m2 = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', str(s).strip())
                    if m2:
                        return date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
                    return None

                d_min = _parse_d(s_min_val)
                d_max = _parse_d(s_max_val)
                if d_min and d_max:
                    lo_d, hi_d = min(d_min, d_max), max(d_min, d_max)
                    ref_yr = lo_d.year

                    def _extract_dep(row):
                        u = str(row.get('offer_url') or '')
                        m = re.search(r'departureDate=(\d{4}-\d{2}-\d{2})', u)
                        if m:
                            try:
                                return datetime.strptime(m.group(1), '%Y-%m-%d').date()
                            except Exception:
                                pass
                        d_str = str(row.get('dates') or '').strip()
                        if d_str:
                            first = d_str.split('-')[0].strip()
                            m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', first)
                            if m:
                                p1, p2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                                if p1 > 12:
                                    return date(y, p2, p1)
                                elif p2 > 12:
                                    return date(y, p1, p2)
                                else:
                                    return date(y, p2, p1)
                            m = re.match(r'^(\d{1,2})\.(\d{1,2})$', first)
                            if m:
                                p1, p2 = int(m.group(1)), int(m.group(2))
                                return date(ref_yr, p2, p1)
                        return None

                    def _is_valid_dep(row):
                        d = _extract_dep(row)
                        if d is None:
                            return True
                        return lo_d <= d <= hi_d

                    before_cnt = len(df)
                    valid_mask = df.apply(_is_valid_dep, axis=1)
                    df = df[valid_mask].copy()
                    dropped_cnt = before_cnt - len(df)
                    if dropped_cnt > 0:
                        print(f"🧹 Исключено {dropped_cnt} устаревших/внедиапазонных записей вне диапазона [{lo_d} .. {hi_d}]")
        except Exception as date_filter_err:
            print(f"⚠️ Ошибка фильтрации диапазона дат вылета: {date_filter_err}")

        # Scope / country URL filtering: гарантируем, что в дашборд не попадут офферы не той страны
        # (например, мусорные офферы Испании/Албании при сбросе параметров поиска fly.pl или из старого кэша)
        try:
            cfg_for_scope = load_filter_config(data_file, config_file)
            if cfg_for_scope:
                req_contains = cfg_for_scope.get("required_offer_url_contains") or []
                if isinstance(req_contains, str):
                    req_contains = [req_contains]
                req_contains = [str(x).strip().lower() for x in req_contains if str(x).strip()]

                excl_contains = cfg_for_scope.get("excluded_offer_url_contains") or []
                if isinstance(excl_contains, str):
                    excl_contains = [excl_contains]
                excl_contains = [str(x).strip().lower() for x in excl_contains if str(x).strip()]

                if req_contains or excl_contains:
                    country_tokens = [t for t in req_contains if t.startswith('/wycieczka/')]
                    other_tokens = [t for t in req_contains if not t.startswith('/wycieczka/')]

                    def _is_valid_scope(row):
                        u = str(row.get('offer_url') or '').strip().lower()
                        if not u:
                            return True
                        if country_tokens and not any(ct in u for ct in country_tokens):
                            return False
                        if other_tokens:
                            for ot in other_tokens:
                                if ot == 'transport=accommodation_flight':
                                    if 'transport=accommodation&' in u and 'transport=accommodation_flight' not in u:
                                        return False
                                elif ot not in u:
                                    return False
                        if excl_contains and any(et in u for et in excl_contains):
                            return False
                        return True

                    scope_before = len(df)
                    scope_mask = df.apply(_is_valid_scope, axis=1)
                    df = df[scope_mask].copy()
                    dropped_scope = scope_before - len(df)
                    if dropped_scope > 0:
                        print(f"🧹 Исключено {dropped_scope} офферов, не соответствующих целевой стране/scope фильтра")
        except Exception as scope_filter_err:
            print(f"⚠️ Ошибка фильтрации scope офферов: {scope_filter_err}")

        # Нормализуем названия отелей: срезаем стрелочные хлебные крошки и хвосты локаций fly.pl
        def _clean_hotel_title(name):
            if not name or pd.isna(name):
                return ""
            s = str(name).strip()
            if "→" in s or "->" in s:
                s = re.split(r'\s*(?:→|->)\s*', s)[0].strip()
            s = re.sub(r'\s+(?:Turcja|Egipt|Grecja|Hiszpania|Cypr)(?:,\s*[^,]+)*$', '', s, flags=re.I).strip()
            return s
        df['hotel_name'] = df['hotel_name'].apply(_clean_hotel_title)
        # Используем локализованное время без дополнительных сдвигов
        df['scraped_at_display'] = df['scraped_at_local']
        for col in ('ta_rating', 'ta_review_count', 'ta_source', 'duration_bucket'):
            if col not in df.columns:
                df[col] = ''
        print(f"✅ Загружено {len(df)} записей")
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        return

    # Загружаем данные альтернативных аэропортов для сравнения, если переданы или обнаружены
    df_all_airports = None
    alt_file_to_load = None
    if all_airports_data_file and os.path.exists(all_airports_data_file):
        alt_file_to_load = all_airports_data_file
    else:
        candidates = [
            os.path.join(data_dir, "travel_prices_any_airports.csv"),
        ]
        haystack = f"{data_dir} {title}".lower()
        if any(k in haystack for k in ["egypt", "egipt", "египет", "7_10", "13_16"]):
            candidates.extend([
                os.path.join("data", "filters", "filter_egypt_autumn_2026_7_10_days", "travel_prices_any_airports.csv"),
                os.path.join("data", "filters", "filter_egypt_autumn_2026_13_16_days", "travel_prices_any_airports.csv"),
                os.path.join("data", "egypt_travel_prices_any_airports.csv"),
            ])
        if any(k in haystack for k in ["turkey", "turcja", "турция"]):
            candidates.append(os.path.join("data", "turkey_travel_prices_any_airports.csv"))
        candidates.append(os.path.join("data", "travel_prices_any_airports.csv"))

        for cand in candidates:
            if cand and os.path.exists(cand):
                alt_file_to_load = cand
                break

    if alt_file_to_load:
        try:
            df_all_airports = pd.read_csv(alt_file_to_load, quoting=csv.QUOTE_ALL, on_bad_lines='skip')
            df_all_airports['price'] = pd.to_numeric(df_all_airports['price'], errors='coerce')
            df_all_airports = df_all_airports.dropna(subset=['price'])
            df_all_airports = df_all_airports[df_all_airports['price'] >= 1000.0]
            df_all_airports['hotel_name'] = df_all_airports['hotel_name'].apply(_clean_hotel_title)
            print(f"✈️ Загружено {len(df_all_airports)} записей альтернативных аэропортов из {alt_file_to_load}")
        except Exception as e:
            print(f"⚠️ Ошибка чтения файла альтернативных аэропортов {alt_file_to_load}: {e}")
            df_all_airports = None

    filter_config = load_filter_config(data_file, config_file)
    group_cols, trip_buckets, use_trip_buckets = _prepare_trip_duration_columns(df, filter_config or {})
    df_all_durations = df.copy()
    default_trip_duration_bucket = ''
    if use_trip_buckets:
        bucket_ids = [str(b['id']) for b in trip_buckets]
        default_trip_duration_bucket = str(
            (filter_config or {}).get('default_trip_duration_bucket') or bucket_ids[-1]
        ).strip()
        if default_trip_duration_bucket not in bucket_ids:
            default_trip_duration_bucket = bucket_ids[-1]
        df = df[df['duration_bucket'].astype(str) == default_trip_duration_bucket].copy()
        group_cols = ['hotel_name']
        default_label = next(
            (b['label'] for b in trip_buckets if str(b['id']) == default_trip_duration_bucket),
            default_trip_duration_bucket,
        )
        print(f"📏 Корзины длительности: {', '.join(b['label'] for b in trip_buckets)}")
        print(f"📏 Стартовый фильтр (как отдельная страница): {default_label}")
    
    ceiling_val = _parse_price_ceiling(display_price_ceiling)
    history_val = _resolve_history_ceiling(ceiling_val, history_price_ceiling)
    df_canonical = collapse_canonical_per_run(df, ceiling_val, group_cols=group_cols)
    if history_val == ceiling_val:
        df_history = df_canonical.copy()
    else:
        df_history = collapse_canonical_per_run(df, history_val, group_cols=group_cols)

    if ceiling_val is None:
        df_full = df_canonical.copy()
    elif history_val is None:
        df_full = df_history.copy()
    else:
        df_full = collapse_canonical_per_run(df, None, group_cols=group_cols)
    if ceiling_val is not None:
        print(f"📊 Показ ≤{ceiling_val:.0f} PLN (таблица, алерты): {len(df_canonical)} записей")
    if history_val is not None:
        print(f"📈 История ≤{history_val:.0f} PLN (графики, выпавшие): {len(df_history)} записей")
    elif len(df_history) > len(df_canonical):
        print(f"📈 Расширенная история: {len(df_history)} записей")
    if len(df_full) > len(df_history):
        print(f"📉 Полная история (без потолка): {len(df_full)} записей")

    try:
        offers_count_timeline = build_daily_offers_count_timeline(
            df,
            ceiling_val=ceiling_val,
            group_cols=group_cols,
            tz=tz,
            pick='last',
            canon_df=df_canonical,
        )
        offers_count_dates = offers_count_timeline['dates']
        offers_count_values = offers_count_timeline['counts']
        offers_count_meta = offers_count_timeline['meta']
        if offers_count_dates:
            print(
                f"📈 Предложений по дням: {len(offers_count_dates)} точек "
                f"(последний ран дня, последнее: {offers_count_values[-1]})"
            )
    except Exception as e:
        print(f"⚠️ Не удалось посчитать динамику количества предложений: {e}")
        offers_count_dates = []
        offers_count_values = []
        offers_count_meta = []

    # Модель данных:
    # • df_canonical — ≤ display (10k): таблица, карточки, алерты.
    # • df_history — ≤ history (20k): графики, выпавшие, контекст «было дороже».
    # • df_full — вся история: типичная средняя (Δ к средней, Deal Score).

    # Анализ «когда покупать»: статистика снижения цен по часу/дню недели/части месяца/месяцу
    try:
        timing_analysis = analyze_purchase_timing(df, tz=tz)
    except Exception as e:
        print(f"⚠️ Не удалось посчитать timing-аналитику: {e}")
        timing_analysis = {"available": False, "status": "error", "recommendation": "", "dimensions": {}}
    timing_json = json.dumps(timing_analysis, ensure_ascii=False, default=str)

    # Вычисляем статистику (заполним после сборки таблицы — см. history_* ниже)
    total_offers = 0
    unique_hotels = 0
    avg_price = 0.0
    history_min_price = 0.0
    history_max_price = 0.0
    current_table_hotels = 0

    # Функция для генерации hover-данных с использованием встроенных возможностей Plotly
    def generate_hover_data(detailed_data):
        """Генерирует данные для hover с детальной информацией о ране"""
        hover_data = {
            'title': f"📊 ТОП-10 ({detailed_data['run_time']})",
            'avg_price': detailed_data.get('avg_price', 0),
            'avg_change': None,
            'price_changes': [],
            'new_hotels': [],
            'removed_hotels': [],
            'no_changes': False
        }
        
        # Изменение средней цены
        if detailed_data.get('avg_price_change', 0) != 0:
            change = detailed_data['avg_price_change']
            change_percent = detailed_data.get('avg_price_change_percent', 0)
            arrow = "↗️" if change > 0 else "↘️"
            sign = "+" if change > 0 else ""
            
            hover_data['avg_change'] = {
                'arrow': arrow,
                'change': change,
                'change_percent': change_percent,
                'sign': sign
            }
        
        # Изменения цен отелей
        if detailed_data.get('price_changes') and len(detailed_data['price_changes']) > 0:
            for change in detailed_data['price_changes']:
                arrow = "↗️" if change['change'] > 0 else "↘️"
                sign = "+" if change['change'] > 0 else ""
                
                hover_data['price_changes'].append({
                    'name': change['name'],
                    'old_price': change['old_price'],
                    'new_price': change['new_price'],
                    'change': change['change'],
                    'change_percent': change['change_percent'],
                    'arrow': arrow,
                    'sign': sign
                })
        
        # Новые отели в ТОП-10
        if detailed_data.get('new_hotels') and len(detailed_data['new_hotels']) > 0:
            for hotel in detailed_data['new_hotels']:
                hover_data['new_hotels'].append({
                    'name': hotel['name'],
                    'price': hotel['price'],
                    'position': hotel['position']
                })
        
        # Отели, покинувшие ТОП-10
        if detailed_data.get('removed_hotels') and len(detailed_data['removed_hotels']) > 0:
            for hotel in detailed_data['removed_hotels']:
                hover_data['removed_hotels'].append({
                    'name': hotel['name'],
                    'price': hotel['price'],
                    'position': hotel['position']
                })
        
        # Если нет изменений
        if (not detailed_data.get('price_changes') or len(detailed_data['price_changes']) == 0) and \
           (not detailed_data.get('new_hotels') or len(detailed_data['new_hotels']) == 0) and \
           (not detailed_data.get('removed_hotels') or len(detailed_data['removed_hotels']) == 0) and \
           detailed_data.get('avg_price_change', 0) == 0:
            hover_data['no_changes'] = True
        
        return hover_data

    # Use module-level find_cheaper_airport_alternatives and helpers

    # Средняя цена ТОП-10 дешёвых предложений по ранам с детальной информацией
    run_slices = list(iter_scrape_runs(df_canonical))
    try:
        run_data = []
        top10_detailed_data = []  # Детальная информация для hover
        
        print(f"🔍 Найдено {len(run_slices)} ранов")
        
        # Обрабатываем каждый ран
        for i, (_, _, run_data_slice) in enumerate(run_slices):
            if len(run_data_slice) == 0:
                continue
                
            run_time = run_data_slice['scraped_at_display'].iloc[0]  # Время начала рана
            
            # Для каждого рана берем последние данные по каждому отелю в этом ране
            hotel_prices = {}
            for h_name, p_val in zip(run_data_slice['hotel_name'], run_data_slice['price']):
                p_float = float(p_val)
                if h_name not in hotel_prices or p_float < hotel_prices[h_name]:
                    hotel_prices[h_name] = p_float
            latest_prices = list(hotel_prices.values())
            
            if len(latest_prices) >= 10:
                # Берем ТОП-10 дешевых из всех отелей на этот ран
                sorted_prices = sorted(latest_prices)
                top10_prices = sorted_prices[:10]
                avg_price = sum(top10_prices) / len(top10_prices)
                min_price = top10_prices[0]
                max_price = top10_prices[-1]
                
                # Находим отели, которые попали в ТОП-10
                top10_hotels = []
                price_positions = {p: sorted_prices.index(p) + 1 for p in top10_prices}
                for hotel_name, price in hotel_prices.items():
                    if price in top10_prices:
                        top10_hotels.append({
                            'name': hotel_name,
                            'price': price,
                            'position': price_positions[price]
                        })
                
                # Сортируем по позиции в ТОП-10 (с детерминированным тай-брейком по имени)
                top10_hotels.sort(key=lambda x: (x['position'], x['name']))
                
                # Добавляем точку для каждого рана (убираем фильтрацию по одинаковым ценам)
                run_data.append((run_time, avg_price))
                top10_detailed_data.append({
                    'run_time': run_time,
                    'avg_price': avg_price,
                    'min_price': min_price,
                    'max_price': max_price,
                    'top10_hotels': top10_hotels
                })
            elif len(latest_prices) > 0:
                # Если отелей меньше 10, берем все
                sorted_prices = sorted(latest_prices)
                avg_price = sum(sorted_prices) / len(sorted_prices)
                min_price = sorted_prices[0]
                max_price = sorted_prices[-1]
                
                # Все отели попадают в "ТОП"
                top_hotels = []
                for hotel_name, price in hotel_prices.items():
                    top_hotels.append({
                        'name': hotel_name,
                        'price': price,
                        'position': sorted_prices.index(price) + 1
                    })
                
                # Добавляем точку для каждого рана (убираем фильтрацию по одинаковым ценам)
                run_data.append((run_time, avg_price))
                top10_detailed_data.append({
                    'run_time': run_time,
                    'avg_price': avg_price,
                    'min_price': min_price,
                    'max_price': max_price,
                    'top10_hotels': top_hotels
                })
        
        if run_data:
            # Use clean standard datetime format without microseconds or raw timezone offsets
            # to avoid recursive Plotly dateTime2ms stack overflow on 1000+ data points
            top10_x_values = [pd.Timestamp(ts).strftime('%Y-%m-%d %H:%M:%S') for ts, _ in run_data]
            top10_y_values = [float(price) for _, price in run_data]
            top10_min_values = [float(d.get('min_price', y)) for d, y in zip(top10_detailed_data, top10_y_values)]
            top10_max_values = [float(d.get('max_price', y)) for d, y in zip(top10_detailed_data, top10_y_values)]
            
            # Добавляем информацию об изменениях цен для каждого рана
            for i, detailed in enumerate(top10_detailed_data):
                if i == 0:
                    # Первый ран - нет изменений
                    detailed['price_changes'] = []
                    detailed['new_hotels'] = []
                    detailed['removed_hotels'] = []
                else:
                    # Сравниваем с предыдущим раном
                    prev_detailed = top10_detailed_data[i-1]
                    current_hotels = {h['name']: h for h in detailed['top10_hotels']}
                    prev_hotels = {h['name']: h for h in prev_detailed['top10_hotels']}
                    
                    # Находим изменения цен
                    price_changes = []
                    for hotel_name, current_hotel in current_hotels.items():
                        if hotel_name in prev_hotels:
                            prev_price = prev_hotels[hotel_name]['price']
                            current_price = current_hotel['price']
                            if prev_price != current_price:
                                price_changes.append({
                                    'name': hotel_name,
                                    'old_price': prev_price,
                                    'new_price': current_price,
                                    'change': current_price - prev_price,
                                    'change_percent': ((current_price - prev_price) / prev_price) * 100,
                                    'position': current_hotel['position']
                                })
                    
                    # Находим новые и удаленные отели
                    new_hotels = []
                    removed_hotels = []
                    
                    for hotel_name in current_hotels:
                        if hotel_name not in prev_hotels:
                            new_hotels.append({
                                'name': hotel_name,
                                'price': current_hotels[hotel_name]['price'],
                                'position': current_hotels[hotel_name]['position']
                            })
                    
                    for hotel_name in prev_hotels:
                        if hotel_name not in current_hotels:
                            removed_hotels.append({
                                'name': hotel_name,
                                'price': prev_hotels[hotel_name]['price'],
                                'position': prev_hotels[hotel_name]['position']
                            })
                    
                    detailed['price_changes'] = price_changes
                    detailed['new_hotels'] = new_hotels
                    detailed['removed_hotels'] = removed_hotels
                
                # Добавляем информацию об изменении средней цены
                if i > 0:
                    prev_avg = top10_detailed_data[i-1]['avg_price']
                    current_avg = detailed['avg_price']
                    detailed['avg_price_change'] = current_avg - prev_avg
                    detailed['avg_price_change_percent'] = ((current_avg - prev_avg) / prev_avg) * 100
                else:
                    detailed['avg_price_change'] = 0
                    detailed['avg_price_change_percent'] = 0
                
                # Создаем данные для hover с использованием встроенных возможностей Plotly
                detailed['hover_data'] = generate_hover_data(detailed)
            
            print(f"🔍 Отладка ТОП-10: {len(run_data)} точек данных")
            if run_data:
                print(f"   Последняя точка: {run_data[-1][1]:.2f} PLN")
        else:
            top10_x_values, top10_y_values = [], []
            top10_min_values, top10_max_values = [], []
            top10_detailed_data = []
            print("❌ Нет данных для ТОП-10 графика")
            
    except Exception as e:
        print(f"Ошибка расчета ТОП-10: {e}")
        top10_x_values, top10_y_values = [], []
        top10_min_values, top10_max_values = [], []
        top10_detailed_data = []
        run_slices = []
    
    # Индекс ценовой динамики (Price Trend Index)
    try:
        print("📊 Расчет индекса ценовой динамики...")
        trend_index_x_values, trend_index_y_values = [], []
        trend_index_detailed_data = []
        
        # Словарь для хранения предыдущих цен каждого отеля
        prev_hotel_prices = {}
        
        # Обрабатываем каждый ран
        for i, (_, _, run_data_slice) in enumerate(run_slices):
            if len(run_data_slice) == 0:
                continue
                
            run_time = run_data_slice['scraped_at_display'].iloc[0]  # Время начала рана
            
            # Собираем текущие цены отелей в этом ране
            current_hotel_prices = {}
            for h_name, p_val in zip(run_data_slice['hotel_name'], run_data_slice['price']):
                p_float = float(p_val)
                if h_name not in current_hotel_prices or p_float < current_hotel_prices[h_name]:
                    current_hotel_prices[h_name] = p_float
            
            # Рассчитываем индекс ценовой динамики
            total_price_change = 0
            hotels_with_changes = 0
            price_changes = []
            
            for hotel_name in sorted(current_hotel_prices.keys()):
                current_price = current_hotel_prices[hotel_name]
                if hotel_name in prev_hotel_prices:
                    prev_price = prev_hotel_prices[hotel_name]
                    if prev_price > 0:  # Избегаем деления на ноль
                        price_change_pct = ((current_price - prev_price) / prev_price) * 100
                        total_price_change += price_change_pct
                        hotels_with_changes += 1
                        price_changes.append({
                            'hotel': hotel_name,
                            'prev_price': prev_price,
                            'current_price': current_price,
                            'change_pct': price_change_pct
                        })
            
            # Рассчитываем средний индекс (если есть изменения)
            if hotels_with_changes > 0:
                avg_price_change = total_price_change / hotels_with_changes
                
                # Добавляем точку для каждого рана (чистый формат без микросекунд для Plotly)
                trend_index_x_values.append(pd.Timestamp(run_time).strftime('%Y-%m-%d %H:%M:%S'))
                trend_index_y_values.append(avg_price_change)
                trend_index_detailed_data.append({
                    'run_time': run_time.strftime('%Y-%m-%d %H:%M'),
                    'avg_change_pct': avg_price_change,
                    'hotels_with_changes': hotels_with_changes,
                    'total_hotels': len(current_hotel_prices),
                    'price_changes': price_changes
                })
            
            # Обновляем предыдущие цены для следующего рана
            prev_hotel_prices = current_hotel_prices.copy()
        
        print(f"🔍 Отладка индекса тренда: {len(trend_index_x_values)} точек данных")
        if trend_index_x_values:
            print(f"   Последняя точка: {trend_index_y_values[-1]:.2f}%")
    except Exception as e:
        print(f"Ошибка расчета индекса тренда: {e}")
        trend_index_x_values, trend_index_y_values = [], []
        trend_index_detailed_data = []
    
    
    # --- Таблица: только последний ран (актуальные цены «сейчас») ---
    # Канонизация: 1 строка / отель / ран = min цена (≤ display_price_ceiling).
    latest_run_slice = _last_run_slice(df_canonical)
    full_latest_run_slice = _last_run_slice(df)

    df_sorted_all = latest_run_slice.sort_values(group_cols + ['scraped_at_display'])
    hotel_repo = HotelRepository.get_instance()
    reputation_kb_data = hotel_repo.reputation_kb.get("hotels", {})

    hotel_ta_cache = _build_hotel_ta_cache(df, reputation_kb_data=reputation_kb_data)
    latest_rows = []
    skipped_above_ceiling = 0
    if ceiling_val is not None and not full_latest_run_slice.empty:
        for group_key, grp in full_latest_run_slice.groupby(group_cols):
            if grp[grp['price'].astype(float) <= ceiling_val].empty:
                skipped_above_ceiling += 1
    for group_key, grp in df_sorted_all.groupby(group_cols):
        hotel_name, bucket, row_id = _unpack_table_group_key(group_key, use_trip_buckets)
        # В каноническом ране — одна строка на отель; берём актуальную, не мин. по всей истории.
        last = grp.sort_values('scraped_at_display').iloc[-1]
        offer_url_val = last.get('offer_url', None)
        if not offer_url_val or pd.isna(offer_url_val) or not str(offer_url_val).strip() or str(offer_url_val).strip() in ('—', 'None', 'nan'):
            # Look backwards in the group for any row that has a valid offer_url
            for prev_url in reversed(list(grp.get('offer_url', []))):
                if pd.notna(prev_url) and str(prev_url).strip() and str(prev_url).strip() not in ('—', 'None', 'nan'):
                    offer_url_val = prev_url
                    break

        ta_rating_val, ta_reviews_val, ta_source_val = _resolve_row_ta(
            last, grp, hotel_ta_cache, hotel_name, reputation_kb_data
        )

        latest_rows.append({
            'hotel_name': hotel_name,
            'duration_bucket': bucket,
            'row_id': row_id,
            'price': float(last['price']),
            'dates': last.get('dates', None),
            'duration': last.get('duration', None),
            'scraped_at_local': last['scraped_at_local'],
            'url': last.get('url', None),
            'from_airport': last.get('from_airport', None),
            'offer_url': offer_url_val,
            'image_url': last.get('image_url', None),
            'ta_rating': ta_rating_val if ta_rating_val is not None else '',
            'ta_review_count': ta_reviews_val if ta_reviews_val > 0 else '',
            'ta_source': ta_source_val,
            'departure_date': last.get('departure_date', None),
            'departure_key': last.get('departure_key', None),
        })
    _backfill_ta_for_latest_rows(
        latest_rows, df, config_file, data_file, enable_live_crawl=enable_ta_live_backfill
    )
    if latest_rows:
        all_hotels = pd.DataFrame(latest_rows).sort_values('price').reset_index(drop=True)
    else:
        all_hotels = pd.DataFrame(columns=[
            'hotel_name', 'duration_bucket', 'row_id', 'price', 'dates', 'duration',
            'scraped_at_local', 'url', 'from_airport', 'offer_url', 'image_url',
            'ta_rating', 'ta_review_count', 'ta_source', 'departure_date', 'departure_key',
        ])
    # Актуальная цена для таблицы — только последний ран; дельты — vs вся df_canonical.
    table_prices = {row['row_id']: float(row['price']) for row in latest_rows}

    arrival_hub_by_hotel = {}
    arrival_hub_labels = set()
    for _, _hotel_row in all_hotels.iterrows():
        _path = parse_offer_path(str(_hotel_row.get("offer_url") or ""))
        _hub_label = arrival_hub_label(_path.get("country"), _path.get("region"))
        _hotel_key = str(_hotel_row.get("row_id") or _hotel_row.get("hotel_name") or "")
        arrival_hub_by_hotel[_hotel_key] = _hub_label
        if _hub_label and _hub_label != "—":
            arrival_hub_labels.add(_hub_label)

    total_offers = len(df_canonical)
    unique_hotels = int(df_canonical['hotel_name'].nunique()) if not df_canonical.empty else 0
    if not df_canonical.empty:
        avg_price = float(df_canonical['price'].mean())
        history_min_price = float(df_canonical['price'].min())
        history_max_price = float(df_canonical['price'].max())
    current_table_hotels = len(all_hotels)
    if ceiling_val is not None and skipped_above_ceiling:
        print(f"💎 Дороже потолка показа (>{ceiling_val:.0f} PLN, только в истории): {skipped_above_ceiling}")
    print(f"🧹 Таблица отфильтрована по последнему рану: {len(all_hotels)} актуальных отелей")

    # ── Config & Module Toggles ──────────────────────────────────────────────
    _cfg_data = {}
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as _cf:
                _cfg_data = json.load(_cf)
        except Exception:
            _cfg_data = {}
    _cfg_modules = _cfg_data.get('modules') or {}
    _is_early_booking = bool(_cfg_data.get('early_booking_tracking')) or (_cfg_data.get('group') == 'early_booking')

    # ── Hopper Prediction Engine Enrichment ──────────────────────────────────
    run_hopper = (not _is_early_booking) and bool(_cfg_modules.get('hopper_predictor', True))
    if not all_hotels.empty and run_hopper:
        try:
            hist_input = df_history if (df_history is not None and not df_history.empty) else df_canonical
            all_hotels = batch_predict_offers(all_hotels, history_df=hist_input)
            print(f"🔮 Hopper Engine: рассчитаны прогнозы для {len(all_hotels)} отелей")
        except Exception as e:
            print(f"⚠️ Hopper Engine calculation failed: {e}")
    elif _is_early_booking:
        print("⏭️ Hopper Engine: отключен для раннего бронирования (D > 60 дн.)")

    # ── Cross-Border Arbitrage Engine (Poland vs Germany) ────────────────────
    arbitrage_matches = []
    arbitrage_by_hotel = {}
    run_arbitrage = (not _is_early_booking) and bool(_cfg_modules.get('arbitrage_germany', True))
    if run_arbitrage:
        dest_str = str(data_file or "") + " " + str(config_file or "") + " " + str(title or "")
        dest_str += " " + str(_cfg_data.get('url', ''))
        dest_str += " " + str(_cfg_data.get('description', ''))
        dest_str += " " + " ".join(_cfg_data.get('required_offer_url_contains', []))
        dest_str += " " + str(_cfg_data.get('data_dir', ''))
        dest_str = dest_str.lower()

        if any(k in dest_str for k in ["sharm", "11_154", "шарм"]):
            dest_code = "egypt_sharm"
        elif any(k in dest_str for k in ["egypt", "egipt", "египет", "хургада", "hurghada", "11:", "11_"]):
            dest_code = "egypt"
        elif any(k in dest_str for k in ["greece", "grecja", "греция", "kreta", "крит", "rhodes", "rodos", "родос", "14:", "14_"]):
            dest_code = "greece"
        elif any(k in dest_str for k in ["turkey", "turcja", "турция", "antalya", "анталья", "анталия", "39:", "39_"]):
            dest_code = "turkey"
        else:
            dest_code = "turkey"
        try:
            de_client = GermanyTourClient()
            cur_data_dir = os.path.dirname(os.path.abspath(data_file)) if data_file else None
            filter_de_csv = os.path.join(cur_data_dir, "germany_prices.csv") if cur_data_dir else None
            de_packages = de_client.fetch_destination_packages(
                dest_code, ["BER", "DRS"], use_mock_fallback=True, csv_path=filter_de_csv
            )
            arb_engine = CrossBorderArbitrageEngine()
            if 'df_canonical' in locals() and not df_canonical.empty:
                canonical_latest = (
                    df_canonical.sort_values('scraped_at')
                    .groupby('hotel_name', as_index=False)
                    .last()
                )
                arb_pl_candidates = canonical_latest.to_dict('records')
            else:
                arb_pl_candidates = all_hotels

            arbitrage_matches = arb_engine.compare_offers(arb_pl_candidates, de_packages)
            for m in arbitrage_matches:
                if m.spread_pln > 0 and m.hotel_name_pl not in arbitrage_by_hotel:
                    arbitrage_by_hotel[m.hotel_name_pl] = m
            print(f"🌍 Cross-Border Arbitrage: найдено {len(arbitrage_matches)} совпадений ({len(arbitrage_by_hotel)} выгоднее в Германии)")
        except Exception as e:
            print(f"⚠️ Cross-Border Arbitrage skipped: {e}")
    elif _is_early_booking:
        print("⏭️ Cross-Border Arbitrage: отключен для раннего бронирования")

    if not reputation_kb_data:
        reputation_kb_data = hotel_repo.reputation_kb.get("hotels", {})
    specs_kb = hotel_repo.specs_kb.get("hotels", {})

    oracle_report = None
    run_oracle = (not _is_early_booking) and bool(_cfg_modules.get('ai_market_oracle', True))
    if run_oracle:
        try:
            if synthesize_market_oracle and data_file and os.path.exists(data_file):
                oracle_cache_file = os.path.join(os.path.dirname(data_file), "ai_market_oracle_report.json")
                force_ai = bool(force_ai or os.getenv("FORCE_AI_ANALYSIS", "").strip().lower() in ("true", "1", "yes"))
                print(f"🔄 AI Market Oracle mode: force_ai={force_ai} (flag={force_ai}, env='{os.getenv('FORCE_AI_ANALYSIS', '')}')")

                if force_ai:
                    oracle_report = None
                    print(f"🚀 FORCE_AI_ANALYSIS active: принудительный сброс кэша для {oracle_cache_file}")
                    if os.path.exists(oracle_cache_file):
                        try:
                            os.remove(oracle_cache_file)
                            print(f"✓ Кэш-файл {oracle_cache_file} удален.")
                        except Exception as e:
                            print(f"⚠️ Не удалось удалить кэш-файл {oracle_cache_file}: {e}")

                # Determine accurate country label and filter ID
                cfg_oracle = load_filter_config(data_file, config_file)
                c_label = _country_label(cfg_oracle, cfg_oracle.get("url", "")) if cfg_oracle else ""

                full_oracle_title = title
                if c_label and c_label not in ("—", "") and c_label.lower() not in (title or "").lower():
                    full_oracle_title = f"{c_label} • {title}"

                filter_id_str = os.path.basename(os.path.dirname(data_file))

                # Reuse cached AI briefing if generated less than 6 hours ago AND country matches
                if os.path.exists(oracle_cache_file) and not force_ai:
                    try:
                        cache_age_sec = time.time() - os.path.getmtime(oracle_cache_file)
                        if cache_age_sec < 6 * 3600:
                            with open(oracle_cache_file, "r", encoding="utf-8") as f:
                                cached_res = json.load(f)
                            if cached_res and "macro_briefing" in cached_res:
                                # Sanity check: invalidate if cached report talks about Turkey when filter is Egypt/Greece/Cyprus!
                                cached_text = str(cached_res["macro_briefing"]).lower()
                                is_country_mismatch = False
                                if c_label == "Египет" and "турци" in cached_text:
                                    is_country_mismatch = True
                                elif c_label == "Греция" and "турци" in cached_text:
                                    is_country_mismatch = True
                                elif c_label == "Кипр" and "турци" in cached_text:
                                    is_country_mismatch = True

                                if not is_country_mismatch:
                                    oracle_report = cached_res
                                    print(f"🧠 AI Market Oracle: отчет загружен из кэша (возраст {cache_age_sec / 3600:.1f} ч)")
                                else:
                                    print(f"🔄 AI Market Oracle: сброс старого кэша из-за несовпадения страны ({c_label} vs кэш)")
                    except Exception as e:
                        pass

                if not oracle_report:
                    dna_path = "market_dna_profile.json"
                    if not os.path.exists(dna_path):
                        from build_market_dna import build_market_dna
                        dna_res = build_market_dna()
                        if dna_res:
                            with open(dna_path, "w", encoding="utf-8") as f:
                                json.dump(dna_res, f, ensure_ascii=False, indent=2)
                    oracle_report = synthesize_market_oracle(
                        data_file,
                        dna_profile_path=dna_path,
                        filter_title=full_oracle_title,
                        filter_id=filter_id_str,
                    )
                    if oracle_report and "macro_briefing" in oracle_report:
                        print(f"🧠 AI Market Oracle: свежий отчет успешно сгенерирован ({len(oracle_report.get('hotel_dossiers', {}))} досье)")
                        try:
                            with open(oracle_cache_file, "w", encoding="utf-8") as f:
                                json.dump(oracle_report, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            pass
        except Exception as e:
            print(f"⚠️ AI Market Oracle skipped: {e}")
    elif _is_early_booking:
        print("⏭️ AI Market Oracle: отключен для раннего бронирования (используется First Minute EBAS анализ)")


    #
    # Откат: отключаем блок "до 8000 из любого вылета, отсутствующие из Варшавы"
    missing_hotels_under_8000 = []
    if False:
        try:
            warsaw_hotel_names = set(df['hotel_name'].dropna().unique())
            # Определяем slug направления (например, 'egipt') на основе URL текущего набора
            def dest_slug_from_url(u: str):
                try:
                    s = str(u or '')
                    m = re.search(r"/kierunek/([^/?#]+)/?", s)
                    if m:
                        return m.group(1).lower()
                    m = re.search(r"/wycieczka/([^,/?#]+),", s)
                    if m:
                        return m.group(1).lower()
                except Exception:
                    pass
                return ''

            current_dest_slug = ''
            for candidate in (df.get('offer_url'), df.get('url')):
                if candidate is not None:
                    for v in candidate.dropna().astype(str).values.tolist():
                        current_dest_slug = dest_slug_from_url(v)
                        if current_dest_slug:
                            break
                if current_dest_slug:
                    break

            # Набор дат (нормализованных) из варшавского датасета для согласованности выборки
            warsaw_dates_norm = set(df['dates'].astype(str).map(normalize_dates).dropna().unique().tolist())

            df_gen = df_all_airports.dropna(subset=['hotel_name', 'price']).copy()
            # Фильтруем только по текущему направлению (например, только Egipt)
            def row_dest_slug(row):
                u1 = row.get('offer_url', '')
                u2 = row.get('url', '')
                return dest_slug_from_url(u1) or dest_slug_from_url(u2)
            df_gen['__dest'] = df_gen.apply(row_dest_slug, axis=1)
            if current_dest_slug:
                df_gen = df_gen[df_gen['__dest'] == current_dest_slug]

            # Оставляем строки только с подходящими датами
            if len(warsaw_dates_norm) > 0:
                df_gen['__dates_norm'] = df_gen['dates'].astype(str).map(normalize_dates)
                df_gen = df_gen[df_gen['__dates_norm'].isin(warsaw_dates_norm)]

            # Ищем минимальную цену по каждому отелю и берем соответствующую строку
            idx_min = df_gen.groupby('hotel_name')['price'].idxmin()
            gen_best = df_gen.loc[idx_min].copy()
            gen_best = gen_best[gen_best['price'] <= 8000]
            # Отбрасываем те, что уже есть в варшавском датасете
            gen_best = gen_best[~gen_best['hotel_name'].isin(warsaw_hotel_names)]
            # Аэропорт: сначала берем from_airport, потом fallback к извлечению из URL
            if 'from_airport' in gen_best.columns:
                gen_best['airport'] = gen_best['from_airport']
                gen_best['airport'] = gen_best['airport'].where(
                    gen_best['airport'].astype(str).str.strip().ne(''), None
                )
                gen_best['airport'] = gen_best['airport'].fillna(gen_best['url'].apply(extract_airport_from_url))
            else:
                gen_best['airport'] = gen_best['url'].apply(extract_airport_from_url)
            # Собираем элементы для вывода (ограничим до 20 для компактности)
            gen_best = gen_best.sort_values('price').head(20)
            for _, row in gen_best.iterrows():
                missing_hotels_under_8000.append({
                    'hotel_name': row['hotel_name'],
                    'price': float(row['price']),
                    'dates': row.get('dates', None),
                    'airport': row.get('airport', None),
                    'offer_url': row.get('offer_url', None)
                })
            print(f"🛫 Отели до 8000 (любой вылет), отсутствующие из Варшавы: {len(missing_hotels_under_8000)}")
        except Exception as e:
            print(f"Ошибка вычисления блока 'до 8000 из любого вылета, нет из Варшавы': {e}")
    
    # Дельты: «текущая» цена = таблица (последний ран), база = каноническая история (все раны).
    df_sorted = df_canonical.sort_values(group_cols + ['scraped_at_display'])
    df_sorted_full = df_full.sort_values(group_cols + ['scraped_at_display'])
    ref_time_series = df_canonical['scraped_at_display'] if not df_canonical.empty else df['scraped_at_display']

    def compute_changes(window_hours: int):
        cutoff = (ref_time_series.max() or datetime.now()) - timedelta(hours=window_hours)
        changes = []
        deltas_map = {}
        for group_key, grp in df_sorted.groupby(group_cols):
            hotel_name, _, row_id = _unpack_table_group_key(group_key, use_trip_buckets)
            if row_id not in table_prices:
                continue
            grp = grp.sort_values('scraped_at_display')
            latest_price = table_prices[row_id]
            latest_time = grp.iloc[-1]['scraped_at_display']
            win = grp[grp['scraped_at_display'] >= cutoff]
            if len(win) >= 2:
                baseline_row = win.iloc[0]
            elif len(grp) >= 2:
                baseline_row = grp.iloc[-2]
            else:
                deltas_map[row_id] = None
                continue
            baseline_price = float(baseline_row['price'])
            if baseline_price == 0:
                deltas_map[row_id] = None
                continue
            change = latest_price - baseline_price
            change_percent = (change / baseline_price) * 100.0 if baseline_price > 0 else 0.0
            if change != 0:
                changes.append({
                    'hotel_name': hotel_name,
                    'old_price': baseline_price,
                    'new_price': latest_price,
                    'change': change,
                    'change_percent': change_percent,
                    'timestamp': str(latest_time)
                })
            deltas_map[row_id] = (change, change_percent)
        decreases = sorted([h for h in changes if h['change'] < 0], key=lambda x: x['change'])[:5]
        increases = sorted([h for h in changes if h['change'] > 0], key=lambda x: x['change'], reverse=True)[:5]
        return decreases, increases, deltas_map

    # Для таблицы оставляем 48ч, для блоков добавим 24ч и 7д
    decreases_48h, increases_48h, deltas_by_hotel = compute_changes(48)
    decreases_24h, increases_24h, _ = compute_changes(24)
    decreases_7d, increases_7d, _ = compute_changes(24 * 7)

    # Метки нового минимума/максимума за 7д и 30д
    ref_time = ref_time_series.max() or datetime.now()
    minmax_labels_by_hotel = {}
    for group_key, grp in df_sorted.groupby(group_cols):
        _, _, row_id = _unpack_table_group_key(group_key, use_trip_buckets)
        if row_id not in table_prices:
            continue
        grp = grp.sort_values('scraped_at_display')
        latest_price = table_prices[row_id]
        labels = []
        for days in (7, 30):
            cutoff_d = ref_time - timedelta(days=days)
            window = grp[grp['scraped_at_local'] >= cutoff_d]
            if len(window) == 0:
                continue
            win_min = float(window['price'].min())
            win_max = float(window['price'].max())
            if latest_price <= win_min:
                labels.append(f"Новый минимум {days}д")
            if latest_price >= win_max:
                labels.append(f"Новый максимум {days}д")
        minmax_labels_by_hotel[row_id] = labels

    # Pre-index full history by hotel/group key to avoid O(N*M) full dataframe scans
    full_history_by_group = {}
    for group_key, grp in df_sorted_full.groupby(group_cols, sort=False):
        _, _, row_id = _unpack_table_group_key(group_key, use_trip_buckets)
        full_history_by_group[row_id] = grp.sort_values('scraped_at_display')

    # Отклонение от "типичной" цены отеля:
    # baseline = time-weighted mean по всей истории (без потолка показа).
    avg_baseline_delta = {}
    for row_id, last_price in table_prices.items():
        grp = full_history_by_group.get(row_id)
        if grp is None or grp.empty:
            avg_baseline_delta[row_id] = None
            continue
        baseline = _time_weighted_price_baseline(grp)
        if baseline is None or baseline == 0:
            avg_baseline_delta[row_id] = None
            continue
        change_abs = float(last_price) - baseline
        change_pct = (change_abs / baseline) * 100.0
        avg_baseline_delta[row_id] = (change_abs, change_pct)

    # Deal Score: насколько предложение выгодно относительно своей исторической цены
    if use_trip_buckets:
        premium_history_by_hotel = _build_premium_history_index(df_history, ceiling_val, group_cols)
    else:
        premium_history_by_hotel = build_premium_history_by_hotel(
            df_history, ceiling_val, time_col='scraped_at_display', price_col='price'
        )

    def _clamp(v, lo, hi):
        if v is None:
            return lo
        try:
            val = float(v)
            if val != val or math.isnan(val):
                return lo
            return max(lo, min(hi, val))
        except (TypeError, ValueError):
            return lo

    deal_score_by_hotel = {}
    entry_candidates = []
    ta_by_hotel = {
        str(row.get('row_id') or row['hotel_name']): {
            'ta_rating': row.get('ta_rating', ''),
            'ta_review_count': row.get('ta_review_count', ''),
        }
        for _, row in all_hotels.iterrows()
    }

    for group_key, grp in df_sorted.groupby(group_cols):
        hotel_name, bucket, row_id = _unpack_table_group_key(group_key, use_trip_buckets)
        grp = grp.sort_values('scraped_at_display')
        grp_full = full_history_by_group.get(row_id)
        hist_grp = grp_full if grp_full is not None and not grp_full.empty else grp
        prices = hist_grp['price'].astype(float).tolist()
        if not prices:
            continue

        latest = float(table_prices.get(row_id, prices[-1]))
        series = pd.Series(prices, dtype='float64')
        samples = len(series)
        plateau_segments = _price_plateau_segments(hist_grp)
        typical = _baseline_from_segments(plateau_segments) or latest
        median = float(typical)
        p25 = _quantile_from_segments(plateau_segments, 0.25) or latest
        p10 = _quantile_from_segments(plateau_segments, 0.10) or latest
        min_p = float(min(p for p, _ in plateau_segments)) if plateau_segments else latest
        max_p = float(max(p for p, _ in plateau_segments)) if plateau_segments else latest

        # Насколько цена ниже своей типичной (взвешенной по времени) истории
        rel_discount = 0.0
        if median > 0:
            rel_discount = (median - latest) / median
        score_discount = _clamp(50 + rel_discount * 200, 0, 100)

        # Редкость: непрерывная плавная оценка [10, 100] на основе ECDF (без ступенчатых скачков)
        score_rarity = compute_smooth_rarity_score(plateau_segments, latest)

        # Моментум: короткий нисходящий тренд добавляет баллы
        recent = prices[-3:] if len(prices) >= 3 else prices
        score_momentum = 50
        if len(recent) >= 3 and (recent[-1] < recent[-2] <= recent[-3] or recent[-1] <= recent[-2] < recent[-3]):
            score_momentum = 85
        elif len(recent) >= 2 and recent[-1] < recent[-2]:
            score_momentum = 70
        elif len(recent) >= 2 and recent[-1] > recent[-2]:
            score_momentum = 35

        # Стабильность: низкий шум без тренда = нейтральный балл (CV по времени, не по точкам)
        score_stability = 50
        cv = _volatility_from_segments(plateau_segments)
        if cv is not None:
            if cv < 0.01:
                score_stability = 50
            else:
                score_stability = _clamp(70 - cv * 120, 20, 85)

        raw_deal_score = (
            score_discount * 0.40 +
            score_rarity * 0.30 +
            score_momentum * 0.20 +
            score_stability * 0.10
        )
        raw_deal_score = float(_clamp(raw_deal_score, 0, 100))

        # Confidence-aware shrinkage: на короткой истории тянем скор к нейтральному 50
        confidence_weight = _clamp(samples / 20.0, 0.15, 1.0)
        adj_deal_score = 50.0 + (raw_deal_score - 50.0) * confidence_weight
        deal_score = int(round(_clamp(adj_deal_score, 0, 100)))

        if samples < 8:
            confidence_level = "Low"
        elif samples < 20:
            confidence_level = "Medium"
        else:
            confidence_level = "High"

        delta48_info = deltas_by_hotel.get(row_id)
        avg_info = avg_baseline_delta.get(row_id)
        d48_pct = float(delta48_info[1]) if delta48_info is not None else None
        d_avg_pct = float(avg_info[1]) if avg_info is not None else None

        comeback = comeback_from_premium(
            latest, premium_history_by_hotel.get(row_id), ceiling_val
        )
        comeback_drop_pct = float(comeback['drop_from_peak_pct']) if comeback else None
        if comeback_drop_pct is not None:
            comeback_floor = _clamp(55 + comeback_drop_pct * 1.1, 55, 92)
            deal_score = int(max(deal_score, round(comeback_floor)))

        is_flat = (
            comeback_drop_pct is None
            and (d48_pct is None or abs(d48_pct) < 0.5)
            and (d_avg_pct is None or abs(d_avg_pct) < 0.5)
            and abs(rel_discount) < 0.02
        )
        if is_flat:
            deal_score = int(round(50 + (deal_score - 50) * 0.2))

        is_bad = (
            d48_pct is not None and d48_pct > 0
            and d_avg_pct is not None and d_avg_pct > 0
        )
        if is_bad and comeback_drop_pct is None:
            penalty = (d48_pct + d_avg_pct) / 2.0
            deal_score = int(_clamp(50 - penalty * 1.2, 5, 42))

        ta_info = ta_by_hotel.get(str(row_id), {})
        deal_score, ta_weight = blend_tripadvisor_into_deal_score(
            deal_score,
            ta_info.get('ta_rating'),
            ta_info.get('ta_review_count'),
        )

        deal_score_by_hotel[row_id] = {
            'score': deal_score,
            'raw_score': int(round(raw_deal_score)),
            'confidence': confidence_level,
            'samples': samples,
            'latest': latest,
            'median': median,
            'p25': p25,
            'min': min_p,
            'is_bad': is_bad,
            'comeback_drop_pct': comeback_drop_pct,
            'typical_price': median,
            'ta_rating': _parse_ta_rating_value(ta_info.get('ta_rating')),
            'ta_review_count': _parse_ta_review_count(ta_info.get('ta_review_count')),
            'ta_weight': ta_weight,
        }

        delta48 = delta48_info

        # Кандидаты для "раннего входа" (цена + TA при достаточных отзывах)
        ta_rating_val = _parse_ta_rating_value(ta_info.get('ta_rating'))
        ta_reviews_val = _parse_ta_review_count(ta_info.get('ta_review_count'))
        ta_ok = (
            ta_rating_val is None
            or ta_reviews_val < 15
            or ta_rating_val >= 3.8
        )
        if (
            delta48 is not None and delta48[1] <= -2.0 and latest <= p25
            and deal_score >= 72 and confidence_level != "Low" and ta_ok
        ):
            entry_candidates.append({
                'hotel_name': hotel_name,
                'deal_score': deal_score,
                'latest': latest,
                'discount_pct': ((median - latest) / median * 100.0) if median > 0 else 0.0,
                'delta48_pct': float(delta48[1]),
                'confidence': confidence_level,
            })

    # Synchronize Hopper predictions with Deal Score to eliminate contradictory overpriced badges
    if not all_hotels.empty and 'hopper_verdict' in all_hotels.columns:
        for idx, row in all_hotels.iterrows():
            rid = row.get('row_id') or row['hotel_name']
            ds_info = deal_score_by_hotel.get(rid)
            if ds_info:
                ds = ds_info.get('score', 0)
                cur_verdict = str(row.get('hopper_verdict') or '')
                p_val = int(row.get('price', 0))
                med_val = float(ds_info.get('median', 0.0) or 0.0)
                d_avg_v = ((p_val - med_val) / max(1.0, med_val)) * 100.0 if med_val > 0 else 0.0
                if ds >= 70 and cur_verdict == "OVERPRICED":
                    all_hotels.at[idx, 'hopper_verdict'] = 'BUY_NOW'
                    all_hotels.at[idx, 'hopper_badge'] = '🟢 ПОКУПАТЬ'
                    all_hotels.at[idx, 'hopper_reasoning'] = (
                        f"Отличная цена: отель на историческом минимуме (Deal Score {ds}/100, {p_val} PLN). "
                        f"Несмотря на раннее окно, цена исключительно выгодна."
                    )
                elif (ds <= 35 or d_avg_v >= 8.0) and cur_verdict in ("BUY_NOW", "GOOD_PRICE"):
                    all_hotels.at[idx, 'hopper_verdict'] = 'OVERPRICED'
                    all_hotels.at[idx, 'hopper_badge'] = '🔴 ДОРОГО'
                    all_hotels.at[idx, 'hopper_reasoning'] = (
                        f"Цена завышена (+{d_avg_v:.1f}% к типичной цене отеля, Deal Score {ds}/100). "
                        f"Рекомендуется подождать снижения или рассмотреть альтернативы."
                    )
                elif ds >= 85 and cur_verdict == "WAIT":
                    all_hotels.at[idx, 'hopper_verdict'] = 'BUY_NOW'
                    all_hotels.at[idx, 'hopper_badge'] = '🟢 ПОКУПАТЬ'
                    all_hotels.at[idx, 'hopper_reasoning'] = (
                        f"Топ-предложение (Deal Score {ds}/100): исключительное соотношение цены и качества, откладывать покупку рискованно."
                    )
                elif ds >= 65 and cur_verdict == "WAIT":
                    all_hotels.at[idx, 'hopper_verdict'] = 'GOOD_PRICE'
                    all_hotels.at[idx, 'hopper_badge'] = '🟢 ВЫГОДНАЯ ЦЕНА'
                    all_hotels.at[idx, 'hopper_reasoning'] = (
                        f"Цена привлекательна (Deal Score {ds}/100): отличное качество для этой стоимости."
                    )

    entry_candidates = sorted(
        entry_candidates,
        key=lambda x: (x['deal_score'], x['discount_pct'], -x['latest']),
        reverse=True
    )
    entry_top = entry_candidates[:5]
    # Market breadth (48ч): доля отелей, которые подешевели среди отелей с валидной базовой точкой.
    # Считаем по актуальным отелям из последнего рана, чтобы метрика отражала "сейчас".
    current_hotels_for_breadth = (
        set(all_hotels['row_id'].astype(str).tolist()) if not all_hotels.empty else set()
    )
    breadth_total = 0
    breadth_down = 0
    for group_key, grp in df_sorted.groupby(group_cols):
        _, _, row_id = _unpack_table_group_key(group_key, use_trip_buckets)
        if current_hotels_for_breadth and row_id not in current_hotels_for_breadth:
            continue
        grp = grp.sort_values('scraped_at_display')
        if len(grp) < 2:
            continue
        latest_row = grp.iloc[-1]
        cutoff = (df['scraped_at_display'].max() or datetime.now()) - timedelta(hours=48)
        win = grp[grp['scraped_at_display'] >= cutoff]
        if len(win) >= 2:
            baseline_row = win.iloc[0]
        else:
            baseline_row = grp.iloc[-2]
        latest_price = float(latest_row['price'])
        baseline_price = float(baseline_row['price'])
        if baseline_price <= 0:
            continue
        breadth_total += 1
        if latest_price < baseline_price:
            breadth_down += 1
    market_breadth = (breadth_down / breadth_total) if breadth_total > 0 else 0.0

    # --- Журнал «выпавших»: когда-либо в зоне отслеживания, сейчас не в основной таблице ---
    def _dest_token_from_offer_url(url: str) -> str:
        # fly.pl: .../wycieczka/<страна>,<регион>,.../...  -> возвращаем токен страны
        try:
            s = str(url or '').lower()
            marker = '/wycieczka/'
            i = s.find(marker)
            if i < 0:
                return ''
            tail = s[i + len(marker):]
            seg = tail.split('/', 1)[0]
            return seg.split(',', 1)[0].strip()
        except Exception:
            return ''

    disappeared_events = []
    try:
        canonical_runs = list(iter_scrape_runs(df_canonical))
        full_runs = list(iter_scrape_runs(df_history))
        if canonical_runs and table_prices is not None:
            all_seen_hotels = set(df_canonical['hotel_name'].astype(str).tolist())
            current_hotel_names = set()
            for key in table_prices.keys():
                key_str = str(key)
                current_hotel_names.add(key_str.split('|', 1)[0] if '|' in key_str else key_str)
            gone_hotels = all_seen_hotels - current_hotel_names

            latest_full_hotels = set()
            if full_runs:
                _, _, latest_full_slice = full_runs[-1]
                latest_full_hotels = set(latest_full_slice['hotel_name'].astype(str).tolist())

            valid_dests = set()
            if 'offer_url' in df_canonical.columns:
                _, _, latest_canonical = canonical_runs[-1]
                for u in latest_canonical['offer_url'].astype(str).tolist():
                    tok = _dest_token_from_offer_url(u)
                    if tok:
                        valid_dests.add(tok)

            typical_prices = [
                float(v['median']) for v in deal_score_by_hotel.values()
                if v.get('median') is not None and float(v.get('median') or 0) > 0
            ]
            expensive_threshold = (
                float(pd.Series(typical_prices, dtype='float64').quantile(0.70))
                if len(typical_prices) >= 4 else (max(typical_prices) if typical_prices else 0.0)
            )

            for name in gone_hotels:
                hist = df_canonical[df_canonical['hotel_name'].astype(str) == name].dropna(subset=['scraped_at_display']).sort_values('scraped_at_display')
                if hist.empty:
                    continue
                full_hist = df_history[df_history['hotel_name'].astype(str) == name].dropna(subset=['scraped_at_display']).sort_values('scraped_at_display')
                prices = hist['price'].astype(float)
                if len(prices) == 0:
                    continue
                last_row = hist.iloc[-1]
                still_in_scrape = name in latest_full_hotels
                current_raw_price = None
                current_raw_dates = None
                current_raw_seen = None
                if not full_hist.empty:
                    raw_last = full_hist.iloc[-1]
                    current_raw_price = float(raw_last['price'])
                    current_raw_seen = raw_last['scraped_at_display']
                    current_raw_dates = raw_last.get('dates') if pd.notna(raw_last.get('dates')) else None
                if valid_dests:
                    hotel_dest = ''
                    for u in hist['offer_url'].astype(str).tolist():
                        hotel_dest = _dest_token_from_offer_url(u)
                        if hotel_dest:
                            break
                    if hotel_dest and hotel_dest not in valid_dests:
                        continue
                first_seen = hist['scraped_at_display'].iloc[0]
                last_seen = hist['scraped_at_display'].iloc[-1]
                try:
                    visible_hours = max(0.0, (last_seen - first_seen).total_seconds() / 3600.0)
                except Exception:
                    visible_hours = 0.0
                last_price = float(prices.iloc[-1])
                hotel_min_price = float(prices.min())
                hotel_max_price = float(prices.max())

                deal_info = deal_score_by_hotel.get(name, {})
                typical_price = float(
                    deal_info.get('typical_price')
                    or deal_info.get('median')
                    or 0.0
                )
                if typical_price <= 0 and not full_hist.empty:
                    typical_price = _time_weighted_price_baseline(full_hist) or 0.0
                if typical_price <= 0:
                    typical_price = float(prices.median())

                avg_info = avg_baseline_delta.get(name)
                baseline_pct = float(avg_info[1]) if avg_info else None
                if len(prices) < 3 and not full_hist.empty:
                    if current_raw_price and typical_price > 0:
                        baseline_pct = (current_raw_price - typical_price) / typical_price * 100.0
                elif baseline_pct is None and not full_hist.empty and typical_price > 0 and current_raw_price:
                    baseline_pct = (current_raw_price - typical_price) / typical_price * 100.0
                # Глубина падения к своей норме (положительное число = насколько ниже базы).
                drop_depth = max(0.0, -baseline_pct) if baseline_pct is not None else 0.0
                # Насколько дешевле своей нормы он опускался в минимуме.
                min_below_pct = ((hotel_min_price - typical_price) / typical_price * 100.0) if typical_price > 0 else 0.0

                # Последнее движение цены перед исчезновением.
                last_move_pct = 0.0
                if len(prices) >= 2:
                    prev_price = float(prices.iloc[-2])
                    if prev_price > 0:
                        last_move_pct = (last_price - prev_price) / prev_price * 100.0

                is_expensive = typical_price >= expensive_threshold and expensive_threshold > 0

                # Классификация причины исчезновения.
                if still_in_scrape and current_raw_price is not None:
                    delta_from_last = (
                        (current_raw_price - last_price) / last_price * 100.0
                        if last_price > 0 else 0.0
                    )
                    if ceiling_val is not None and current_raw_price > ceiling_val:
                        reason_code = 'above_ceiling'
                        band_hi = history_val if history_val else current_raw_price
                        reason_text = (
                            f'Сейчас {current_raw_price:.0f} PLN — выше потолка показа'
                            f' ({ceiling_val:.0f}–{band_hi:.0f})'
                            f' ({delta_from_last:+.0f}% к последней цене в фильтре)'
                        )
                        last_dates = str(last_row.get('dates') or '')
                        raw_dates = str(current_raw_dates or '')
                        if raw_dates and raw_dates != last_dates:
                            reason_text += '; другие даты поездки'
                    elif delta_from_last > 2.0 or last_move_pct > 0.5:
                        reason_code = 'up'
                        reason_text = f'Подорожал до {current_raw_price:.0f} PLN и вышел из фильтра'
                    else:
                        reason_code = 'flat'
                        reason_text = f'Сейчас {current_raw_price:.0f} PLN — в выдаче, но вне фильтра по цене'
                elif last_move_pct > 0.5:
                    reason_code = 'up'
                    reason_text = 'Вышел вверх из диапазона (цена росла)'
                elif baseline_pct is not None and baseline_pct <= -3.0 and last_move_pct <= 0.5:
                    reason_code = 'sold'
                    reason_text = 'Похоже на распроданный дил (был заметно ниже своей нормы)'
                elif last_move_pct < -0.5:
                    reason_code = 'sold'
                    reason_text = 'Цена падала перед исчезновением (возможно, раскупили)'
                else:
                    reason_code = 'flat'
                    reason_text = 'Пропал без явного движения цены'

                # Значимость: глубина падения + бонус за дорогой сегмент.
                significance = drop_depth + (drop_depth * 0.5 if is_expensive else 0.0)
                # "Заметный дил": дорогой отель, который заметно подешевел и пропал.
                notable = bool(is_expensive and drop_depth >= 5.0 and reason_code == 'sold')

                disappeared_events.append({
                    'hotel_name': name,
                    'dates': last_row.get('dates') if pd.notna(last_row.get('dates')) else '—',
                    'duration': last_row.get('duration') if pd.notna(last_row.get('duration')) else '—',
                    'airport': last_row.get('departure_airport') if pd.notna(last_row.get('departure_airport')) else '',
                    'offer_url': last_row.get('offer_url') if pd.notna(last_row.get('offer_url')) else '',
                    'first_seen': first_seen,
                    'last_seen': last_seen,
                    'visible_hours': visible_hours,
                    'observations': int(len(prices)),
                    'observations_full': int(len(full_hist)) if not full_hist.empty else int(len(prices)),
                    'last_price': last_price,
                    'current_raw_price': current_raw_price,
                    'current_raw_dates': current_raw_dates,
                    'current_raw_seen': current_raw_seen,
                    'still_in_scrape': still_in_scrape,
                    'min_price': hotel_min_price,
                    'max_price': hotel_max_price,
                    'typical_price': typical_price,
                    'baseline_pct': baseline_pct,
                    'min_below_pct': min_below_pct,
                    'deal_score': int(deal_info.get('score', 0)) if deal_info else 0,
                    'confidence': deal_info.get('confidence', 'Low') if deal_info else 'Low',
                    'is_expensive': is_expensive,
                    'reason_code': reason_code,
                    'reason_text': reason_text,
                    'significance': significance,
                    'notable': notable,
                })

            disappeared_events.sort(
                key=lambda x: (x['notable'], x['significance'], x['typical_price']),
                reverse=True
            )
    except Exception as e:
        print(f"⚠️ Не удалось посчитать журнал выпавших отелей: {e}")
        disappeared_events = []
    vanished_notable_count = sum(1 for e in disappeared_events if e['notable'])
    print(f"🫥 Выпавших отелей: {len(disappeared_events)} (заметных: {vanished_notable_count})")

    if len(entry_candidates) >= 5 and market_breadth >= 0.45:
        entry_signal_level = "high"
        entry_signal_title = "🔥 Сильный сигнал раннего входа"
        entry_signal_note = "Много отелей одновременно дешевеют и уже торгуются в нижнем квартиле своих цен."
    elif len(entry_candidates) >= 2 and market_breadth >= 0.30:
        entry_signal_level = "medium"
        entry_signal_title = "⚡ Умеренный сигнал раннего входа"
        entry_signal_note = "Есть несколько сильных кандидатов; рынок начинает смещаться в сторону более выгодных цен."
    else:
        entry_signal_level = "low"
        entry_signal_title = "🟢 Нейтральный сигнал"
        entry_signal_note = "Явного массового снижения пока нет, но отдельные выгодные точки могут появляться."
    
    # Загружаем историю алертов (если есть)
    alerts = []
    # Автоматически определяем файл алертов на основе файла данных
    if alerts_file is None:
        if 'egypt' in data_file:
            alerts_file = 'data/egypt_travel_prices_alerts.json'
        elif 'turkey' in data_file:
            alerts_file = 'data/turkey_travel_prices_alerts.json'
        else:
            alerts_file = 'data/travel_prices_alerts.json'
    
    alerts_path = alerts_file
    if os.path.exists(alerts_path):
        try:
            with open(alerts_path, 'r', encoding='utf-8') as f:
                alerts_data = json.load(f)
                # Поддерживаем как старый формат {"alerts": [...]}, так и новый формат [...]
                if isinstance(alerts_data, dict) and 'alerts' in alerts_data:
                    alerts = alerts_data.get('alerts', [])
                elif isinstance(alerts_data, list):
                    alerts = alerts_data
                else:
                    alerts = []
        except Exception:
            alerts = []

    # Сортируем алерты по времени (новые сверху)
    def parse_iso(ts):
        try:
            dt = datetime.fromisoformat(ts)
            # Если datetime naive, делаем его UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    # Сортируем по времени создания (created_at) если есть, иначе по timestamp
    alerts.sort(key=lambda a: parse_iso(a.get('created_at') or a.get('timestamp') or a.get('time') or ''), reverse=True)
    alerts = [a for a in alerts if _should_show_alert(a)]

    _data_dir = os.path.dirname(data_file) or "data"

    def _ingest_images_source(target: dict, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                target.update(data)
        except Exception:
            pass

    # Карта изображений: сначала общий fallback, затем региональный файл фильтра, затем галереи KB.
    images_map: dict = {}
    _ingest_images_source(images_map, os.path.join('data', 'hotel_images.json'))
    _ingest_images_source(images_map, os.path.join(_data_dir, 'hotel_images.json'))
    try:
        for _h_n, _p_list in hotel_repo.galleries_kb.get("galleries", {}).items():
            if _p_list and isinstance(_p_list, list) and _p_list[0].get("url"):
                if _h_n not in images_map:
                    images_map[_h_n] = _p_list[0]["url"]
    except Exception:
        pass

    def normalize_image_url(raw_url: str) -> str:
        if raw_url is None:
            return ""
        url = str(raw_url).strip()
        if not url:
            return ""
        url = html_lib.unescape(url)

        # Приводим типичные относительные форматы.
        if url.startswith("//"):
            url = f"https:{url}"
        elif url.startswith("/"):
            url = f"https://fly.pl{url}"

        u = url.lower()

        # Отбрасываем заведомо нерабочие или "пиксельные" плейсхолдеры.
        if u.startswith("blob:"):
            return ""
        if u.startswith("data:image"):
            return ""
        if u.startswith("https://fly.pl/data:image"):
            return ""
        if "ivborw0kggoaaaansuheugaaaaeaaaab" in u and len(u) < 220:
            return ""
        if not (u.startswith("http://") or u.startswith("https://")):
            return ""
        return url

    # Имя каталога данных (filter_greece_7_10_days) — путь к JSON на Pages.
    _filter_data_id = os.path.basename(os.path.normpath(_data_dir))
    _hotel_series_dir = os.path.join(_data_dir, "hotel_series")
    _back_dashboard_href = filter_href_by_charts_subdir((charts_subdir or "").rstrip("/"))

    # Карточки отелей (визуальный режим по умолчанию)
    hotel_cards = []
    for _, hotel in all_hotels.head(200).iterrows():
        hotel_name = hotel['hotel_name']
        row_id = str(hotel.get('row_id') or hotel_name)
        duration_bucket = str(hotel.get('duration_bucket') or '')
        price = float(hotel['price'])
        dates = hotel['dates'] if pd.notna(hotel['dates']) else '—'
        duration = hotel['duration'] if pd.notna(hotel['duration']) else '—'
        offer_url = hotel.get('offer_url', '')
        image_url = ""
        for candidate in (hotel.get('image_url', ''), images_map.get(hotel_name, '')):
            normalized = normalize_image_url(candidate)
            if normalized:
                image_url = normalized
                break
        hotel_slug = slugify(hotel_name)
        chart_href = _hotel_chart_viewer_href(_filter_data_id, hotel_slug)

        delta_info = deltas_by_hotel.get(row_id)
        delta48 = f"{delta_info[1]:+.1f}%" if delta_info is not None else "—"
        avg_info = avg_baseline_delta.get(row_id)
        delta_avg = f"{avg_info[1]:+.1f}%" if avg_info is not None else "—"
        deal_info = deal_score_by_hotel.get(row_id, {'score': 0, 'confidence': 'Low'})
        deal_score = int(deal_info.get('score', 0))
        confidence = deal_info.get('confidence', 'Low')
        d48_for_badge = float(delta_info[1]) if delta_info is not None else None
        d_avg_for_badge = float(avg_info[1]) if avg_info is not None else None
        comeback_drop = deal_info.get('comeback_drop_pct')
        deal_label, deal_class, _ = classify_deal_badge(
            deal_score, confidence, d48_for_badge, d_avg_for_badge, comeback_drop
        )
        comeback = comeback_from_premium(
            price, premium_history_by_hotel.get(row_id), ceiling_val
        )
        comeback_html = (
            f'<span class="comeback-badge">{comeback["badge_html"]}</span>'
            if comeback else ''
        )
        
        forecast = determine_price_forecast(
            deal_score, confidence, d_avg_for_badge, d48_for_badge, comeback_drop,
        )

        # Альтернативные аэропорты для карточного режима
        card_cheaper_alt_html = ""
        if df_all_airports is not None and not df_all_airports.empty:
            cur_airport = hotel.get('from_airport')
            if not cur_airport or pd.isna(cur_airport) or not str(cur_airport).strip():
                cur_airport = extract_airport_from_url(hotel.get('offer_url') or hotel.get('url', ''))
            alts = find_cheaper_airport_alternatives(
                df_all_airports,
                hotel_name,
                dates,
                price,
                cur_airport,
            )
            if alts:
                best_alt = alts[0]
                alt_url = best_alt.get('url', '')
                alt_airport = html_lib.escape(str(best_alt['airport']))
                alt_price = best_alt['price']
                alt_savings = best_alt['savings']
                alt_savings_pct = best_alt['savings_percent']
                alt_title = html_lib.escape(
                    f"Вылет из {best_alt['airport']}: {alt_price:,.0f} zł (дешевле на {alt_savings:,.0f} zł / {alt_savings_pct:.1f}%)",
                    quote=True,
                )
                if alt_url:
                    card_cheaper_alt_html = f'<a href="{html_lib.escape(str(alt_url), quote=True)}" target="_blank" class="cheaper-alt-badge" title="{alt_title}">✈️ <span class="alt-label">{alt_airport}: {alt_price:,.0f} zł</span> <span class="alt-savings">(−{alt_savings:,.0f} zł)</span></a>'
                else:
                    card_cheaper_alt_html = f'<span class="cheaper-alt-badge" title="{alt_title}">✈️ <span class="alt-label">{alt_airport}: {alt_price:,.0f} zł</span> <span class="alt-savings">(−{alt_savings:,.0f} zł)</span></span>'

        # Hopper & Arbitrage метаданные
        hopper_verdict = str(hotel.get('hopper_verdict') or '')
        hopper_badge = str(hotel.get('hopper_badge') or '')
        hopper_reasoning = str(hotel.get('hopper_reasoning') or '')
        if deal_score >= 70 and hopper_verdict == "OVERPRICED":
            hopper_verdict = "BUY_NOW"
            hopper_badge = "🟢 ПОКУПАТЬ"
            hopper_reasoning = f"Отличный момент для покупки: Deal Score {deal_score}, цена на минимуме истории ({int(price)} PLN)."
        hopper_class = "buy-now" if hopper_verdict == "BUY_NOW" else ("wait" if hopper_verdict == "WAIT" else ("overpriced" if hopper_verdict == "OVERPRICED" else "neutral"))

        flash_drop_badge_html = ""
        fair_price_badge_html = ""
        booking_window_badge_html = ""
        gem_badge_html = ""
        card_dupe_html = ""

        if oracle_report and "hotel_dossiers" in oracle_report:
            h_dossier = oracle_report["hotel_dossiers"].get(hotel_name)
            if h_dossier:
                hopper_badge = h_dossier.get("badge_text", hopper_badge)
                v_raw = h_dossier.get("verdict", "")
                if v_raw in ("BUY_NOW", "GOOD_PRICE"):
                    hopper_verdict = "BUY_NOW"
                elif v_raw == "WAIT":
                    hopper_verdict = "WAIT"
                elif v_raw == "OVERPRICED":
                    hopper_verdict = "OVERPRICED"
                hopper_reasoning = f"{h_dossier.get('rationale', '')} • Риск: {h_dossier.get('risk_assessment', '')} • Совет: {h_dossier.get('action_advice', '')}"

                # 1. Optimal Booking Window
                bw_badge = h_dossier.get("booking_window_badge")
                if bw_badge:
                    bw_cls = h_dossier.get("booking_window_class", "in_window")
                    bw_tip = html_lib.escape(str(h_dossier.get("booking_window_tip", "")), quote=True)
                    booking_window_badge_html = f'<span class="booking-window-pill {bw_cls}" title="{bw_tip}">{html_lib.escape(str(bw_badge))}</span>'

                # 2. Fair Price Index
                fp_badge = h_dossier.get("fair_price_badge")
                if fp_badge:
                    fp_cls = h_dossier.get("fair_price_class", "bargain")
                    fp_tip = html_lib.escape(str(h_dossier.get("fair_price_tip", "")), quote=True)
                    fair_price_badge_html = f'<span class="fair-price-pill {fp_cls}" title="{fp_tip}">{html_lib.escape(str(fp_badge))}</span>'

                # 3. Hidden Gem Badge
                g_badge = h_dossier.get("gem_badge")
                if g_badge:
                    g_tip = html_lib.escape(str(h_dossier.get("gem_tip", "")), quote=True)
                    gem_badge_html = f'<span class="gem-pill" title="{g_tip}">{html_lib.escape(str(g_badge))}</span>'

                # 4. Flash Drop / Glitch Radar
                fd_badge = h_dossier.get("flash_drop_badge")
                if fd_badge:
                    fd_tip = html_lib.escape(str(h_dossier.get("flash_drop_tip", "")), quote=True)
                    flash_drop_badge_html = f'<span class="glitch-radar-pill" title="{fd_tip}">{html_lib.escape(str(fd_badge))}</span>'

                # 5. AI Dupe Alternative (Twin)
                dupe = h_dossier.get("dupe_suggestion")
                if dupe and isinstance(dupe, dict):
                    dupe_name = html_lib.escape(str(dupe.get("hotel_name", "")))
                    dupe_url = dupe.get("offer_url") or dupe.get("url") or "#"
                    dupe_savings = dupe.get("savings") or dupe.get("savings_pln") or 0
                    dupe_rating = dupe.get("rating", 0.0)
                    card_dupe_html = (
                        f'<div class="ai-dupe-line" title="AI Двойник: отель сравнимого класса значительно дешевле">'
                        f'💡 <strong>Двойник:</strong> <a href="{html_lib.escape(str(dupe_url), quote=True)}" target="_blank">{dupe_name}</a> '
                        f'(−{dupe_savings:,.0f} zł при {dupe_rating:g}★)</div>'
                    )

        # Guardrail: Never show positive purchase/good price badge if price is overpriced or Deal Score is bad
        d_avg_card = float(avg_info[1]) if avg_info is not None else 0.0
        d48_card = float(delta_info[1]) if delta_info is not None else 0.0
        is_overpriced_card = (deal_score <= 35 or d_avg_card >= 8.0 or d48_card >= 12.0)
        has_positive_badge_card = (
            hopper_verdict in ("BUY_NOW", "GOOD_PRICE")
            or any(k in hopper_badge for k in ("ПОКУПАТЬ", "ХОРОШАЯ", "СБРОС"))
        )
        if is_overpriced_card and has_positive_badge_card:
            hopper_verdict = "OVERPRICED"
            hopper_badge = "🔴 ДОРОГО"
            hopper_reasoning = f"Цена завышена: {d_avg_card:+.1f}% к своей средней (Deal Score {deal_score}). Лучше подождать снижения."

        # Positive guardrail: Eliminate contradictory 'WAIT' recommendation on high Deal Score, gems or underpriced hotels
        is_gem_card = bool(h_dossier.get("gem_badge")) if (oracle_report and h_dossier) else False
        is_underpriced_card = (h_dossier.get("fair_price_class") == "fair-underpriced") if (oracle_report and h_dossier) else False
        if not is_overpriced_card and (deal_score >= 75 or is_gem_card or is_underpriced_card):
            if hopper_verdict == "WAIT" or "ПОДОЖДАТЬ" in hopper_badge:
                if deal_score >= 85:
                    hopper_verdict = "BUY_NOW"
                    hopper_badge = "🟢 ПОКУПАТЬ"
                    hopper_reasoning = f"Топ-предложение (Deal Score {deal_score}/100): исключительно высокое соотношение цены и качества. Ждать снижения рискованно."
                else:
                    hopper_verdict = "GOOD_PRICE"
                    hopper_badge = "🟢 ВЫГОДНАЯ ЦЕНА"
                    hopper_reasoning = f"Выгодная сделка (Deal Score {deal_score}/100): отличное соотношение цены и уровня отеля."

        hopper_class = "buy-now" if hopper_verdict == "BUY_NOW" else ("wait" if hopper_verdict == "WAIT" else ("overpriced" if hopper_verdict == "OVERPRICED" else "neutral"))

        card_arbitrage_html = ""
        m_arb = arbitrage_by_hotel.get(hotel_name)
        if m_arb and m_arb.spread_pln > 0:
            arb_title = html_lib.escape(
                f"Вылет из Берлина ({m_arb.airport_de}): {m_arb.price_de_eur:.0f} € (~{m_arb.net_price_de_pln:.0f} PLN с дорогой). Экономия {m_arb.spread_pln:.0f} PLN ({m_arb.savings_pct:.1f}%)",
                quote=True,
            )
            arb_url = m_arb.url_de or "#"
            card_arbitrage_html = (
                f'<a href="{html_lib.escape(arb_url, quote=True)}" target="_blank" class="arbitrage-card-badge" title="{arb_title}">'
                f'🌍 <span class="arb-label">Берлин (BER): {m_arb.price_de_eur:.0f} €</span> <span class="arb-savings">(−{m_arb.spread_pln:.0f} PLN)</span></a>'
            )

        card_reputation_badges_html = ""
        if reputation_kb_data and hotel_name in reputation_kb_data:
            rep_entry = reputation_kb_data[hotel_name]
            fam = rep_entry.get("family_and_kids", {})
            wint = rep_entry.get("winter_suitability", {})
            strend = rep_entry.get("season_trend", {})

            card_rep_pills = []
            if fam.get("suitable_for_children") and float(fam.get("score", 0) or 0) >= 7.5:
                f_tip = html_lib.escape(f"Для детей ({fam.get('score', '')}/10): {fam.get('beach_entry', '')} • {fam.get('kids_facilities', '')}", quote=True)
                card_rep_pills.append(f'<span class="tbl-badge tbl-badge-kids" title="{f_tip}">👶 Дети {fam.get("score", "")}</span>')

            if wint.get("heated_pools"):
                h_tip = html_lib.escape(f"Зимний отдых: подогреваемый бассейн • {wint.get('wind_shelter', '')}", quote=True)
                card_rep_pills.append(f'<span class="tbl-badge tbl-badge-heat" title="{h_tip}">🔥 Теплый бассейн</span>')
            elif "защищена" in str(wint.get("wind_shelter", "")).lower():
                w_tip = html_lib.escape(f"Бухта {wint.get('bay', '')}: {wint.get('wind_shelter', '')}", quote=True)
                card_rep_pills.append(f'<span class="tbl-badge tbl-badge-shelter" title="{w_tip}">🛡️ Без ветра</span>')

            if strend.get("trend") == "BETTER":
                t_tip = html_lib.escape(f"Стал лучше: {strend.get('summary', '')}", quote=True)
                card_rep_pills.append(f'<span class="tbl-badge tbl-badge-better" title="{t_tip}">📈 Стал лучше</span>')
            elif strend.get("trend") == "WORSE":
                t_tip = html_lib.escape(f"Стал хуже: {strend.get('summary', '')}", quote=True)
                card_rep_pills.append(f'<span class="tbl-badge tbl-badge-worse" title="{t_tip}">📉 Стал хуже</span>')

            if card_rep_pills:
                card_reputation_badges_html = "".join(card_rep_pills)

        hotel_cards.append({
            "hotel_name": hotel_name,
            "row_id": row_id,
            "duration_bucket": duration_bucket,
            "hotel_name_html": html_lib.escape(str(hotel_name)),
            "price": price,
            "dates": str(dates),
            "duration": str(duration),
            "offer_url": str(offer_url) if offer_url and pd.notna(offer_url) else "",
            "image_url": str(image_url) if image_url and pd.notna(image_url) else "",
            "chart_href": chart_href,
            "delta48": delta48,
            "delta_avg": delta_avg,
            "deal_score": deal_score,
            "deal_label": deal_label,
            "deal_class": deal_class,
            "confidence": confidence,
            "comeback_html": comeback_html,
            "cheaper_alt_html": card_cheaper_alt_html,
            "departure_date": str(hotel.get('departure_date') or ''),
            "departure_key": str(hotel.get('departure_key') or ''),
            "forecast_text": forecast["text"],
            "forecast_class": forecast["class"],
            "forecast_icon": forecast["icon"],
            "hopper_verdict": hopper_verdict,
            "hopper_badge": hopper_badge,
            "hopper_reasoning": hopper_reasoning,
            "hopper_class": hopper_class,
            "arbitrage_badge_html": card_arbitrage_html,
            "flash_drop_badge_html": flash_drop_badge_html,
            "fair_price_badge_html": fair_price_badge_html,
            "booking_window_badge_html": booking_window_badge_html,
            "gem_badge_html": gem_badge_html,
            "dupe_html": card_dupe_html,
            "reputation_badges_html": card_reputation_badges_html,
            "ta_rating": hotel.get('ta_rating', ''),
            "ta_review_count": hotel.get('ta_review_count', ''),
            "ta_data_attr": f"{_parse_ta_rating_value(hotel.get('ta_rating', '')):.2f}" if _parse_ta_rating_value(hotel.get('ta_rating', '')) is not None else "-1",
            "region": html_lib.escape(str(arrival_hub_by_hotel.get(row_id, '')), quote=True),
        })

    hotel_meta_by_name = {c["hotel_name"]: c for c in hotel_cards}
    for hotel_name, grp in df.sort_values('scraped_at_display').groupby('hotel_name', sort=False):
        name = str(hotel_name)
        if name in hotel_meta_by_name:
            continue
        pick = grp.sort_values('scraped_at_display').iloc[-1]
        image_url = ""
        for candidate in (pick.get('image_url', ''), images_map.get(name, '')):
            normalized = normalize_image_url(candidate)
            if normalized:
                image_url = normalized
                break
        hotel_slug = slugify(name)
        chart_href = _hotel_chart_viewer_href(_filter_data_id, hotel_slug)
        offer_url = pick.get('offer_url', '')
        hotel_meta_by_name[name] = {
            "hotel_name": name,
            "hotel_name_html": html_lib.escape(name),
            "dates": str(pick['dates']) if pd.notna(pick.get('dates')) else '—',
            "duration": str(pick['duration']) if pd.notna(pick.get('duration')) else '—',
            "offer_url": str(offer_url) if offer_url and pd.notna(offer_url) else "",
            "image_url": image_url,
            "chart_href": chart_href,
        }

    for name, meta in hotel_meta_by_name.items():
        normalized = normalize_image_url(meta.get("image_url") or images_map.get(name, ""))
        if normalized:
            images_map[str(name)] = normalized
    for name, url in list(images_map.items()):
        normalized = normalize_image_url(url)
        if normalized:
            images_map[name] = normalized
        else:
            images_map.pop(name, None)

    os.makedirs(_hotel_series_dir, exist_ok=True)
    if write_legacy_hotel_html and charts_subdir:
        os.makedirs(charts_subdir, exist_ok=True)

    from price_alerts_v2 import ALERT_THRESHOLD_PERCENT

    # График отеля — JSON-серии + опционально legacy HTML
    chart_href_lookup: dict[str, str] = {}
    series_manifest = _load_hotel_series_manifest(_hotel_series_dir)
    series_written = 0
    series_skipped = 0
    chart_hotel_names = sorted(set(df_history["hotel_name"].astype(str).unique()))
    history_by_hotel = {
        str(name): grp
        for name, grp in df_history.groupby("hotel_name", sort=False)
    }
    for hotel_name in chart_hotel_names:
        hotel_ts = history_by_hotel.get(str(hotel_name), pd.DataFrame())
        if not hotel_ts.empty:
            hotel_ts = hotel_ts.dropna(subset=['scraped_at_display']).sort_values('scraped_at_display')
        x_values = [t.strftime('%Y-%m-%d %H:%M:%S') if hasattr(t, 'strftime') else str(t) for t in hotel_ts['scraped_at_display']]
        x_display = hotel_ts['scraped_at_display'].dt.strftime('%d.%m.%Y %H:%M').tolist()
        y_values = [float(p) for p in hotel_ts['price'].tolist()]
        dates_list = hotel_ts['dates'].fillna('Неизвестно').tolist()
        
        text_values = []
        for x_val, trip_dates in zip(x_display, dates_list):
            text_values.append(f"Проверка: {x_val}<br>Даты поездки: {trip_dates}")

        hotel_slug = slugify(hotel_name)
        viewer_href = _hotel_chart_viewer_href(_filter_data_id, hotel_slug)

        meta = hotel_meta_by_name.get(hotel_name, {})
        if not hotel_ts.empty:
            pick_meta = hotel_ts.iloc[-1]
            if not meta.get('hotel_name_html'):
                meta = {
                    'hotel_name_html': html_lib.escape(str(hotel_name)),
                    'dates': '—',
                    'duration': '—',
                    'offer_url': '',
                    'image_url': '',
                }
            meta = dict(meta)
            meta['dates'] = str(pick_meta['dates']) if pd.notna(pick_meta.get('dates')) else meta.get('dates', '—')
            meta['duration'] = str(pick_meta['duration']) if pd.notna(pick_meta.get('duration')) else meta.get('duration', '—')
            offer_from_full = pick_meta.get('offer_url', '')
            if offer_from_full and pd.notna(offer_from_full):
                meta['offer_url'] = str(offer_from_full)
        elif not meta.get('hotel_name_html'):
            meta = {
                'hotel_name_html': html_lib.escape(str(hotel_name)),
                'dates': '—',
                'duration': '—',
                'offer_url': '',
                'image_url': '',
            }

        delta_info = deltas_by_hotel.get(hotel_name)
        delta48_str = f"{delta_info[1]:+.1f}%" if delta_info is not None else "—"
        avg_info = avg_baseline_delta.get(hotel_name)
        delta_avg_str = f"{avg_info[1]:+.1f}%" if avg_info is not None else "—"
        deal_info = deal_score_by_hotel.get(hotel_name, {'score': 0, 'confidence': 'Low'})
        deal_score = int(deal_info.get('score', 0))
        confidence = deal_info.get('confidence', 'Low')
        d48_for_badge = float(delta_info[1]) if delta_info is not None else None
        d_avg_for_badge = float(avg_info[1]) if avg_info is not None else None
        comeback_drop_chart = deal_info.get('comeback_drop_pct')
        deal_label, deal_class, _ = classify_deal_badge(
            deal_score, confidence, d48_for_badge, d_avg_for_badge, comeback_drop_chart
        )

        if y_values:
            min_p = float(min(y_values))
            max_p = float(max(y_values))
        else:
            min_p = max_p = 0.0
        median_p = float(deal_info.get('typical_price') or deal_info.get('median') or 0.0)
        hist_grp_chart = full_history_by_group.get(str(hotel_name), pd.DataFrame())
        if median_p <= 0 and not hist_grp_chart.empty:
            median_p = _time_weighted_price_baseline(hist_grp_chart) or 0.0

        trip_dates_label = str(meta.get('dates') or (dates_list[-1] if dates_list else '—'))

        series_payload = {
            "version": 1,
            "filter_id": _filter_data_id,
            "slug": hotel_slug,
            "hotel_name": str(hotel_name),
            "x": x_values,
            "y": y_values,
            "hover": text_values,
            "meta": {
                "dates": str(meta.get("dates") or "—"),
                "duration": str(meta.get("duration") or "—"),
                "offer_url": str(meta.get("offer_url") or ""),
                "image_url": str(meta.get("image_url") or ""),
            },
            "deal_score": deal_score,
            "deal_label": deal_label,
            "deal_class": deal_class,
            "delta48": delta48_str,
            "delta_avg": delta_avg_str,
            "confidence": confidence,
            "median_p": median_p,
            "min_p": min_p,
            "max_p": max_p,
            "samples": len(y_values),
            "alert_threshold": ALERT_THRESHOLD_PERCENT,
            "trip_dates_label": trip_dates_label,
            "display_price_ceiling": ceiling_val,
            "history_price_ceiling": history_val,
            "back_href": _back_dashboard_href,
        }
        content_hash = _hotel_series_payload_hash(series_payload)
        if series_manifest.get(hotel_slug) != content_hash:
            series_path = os.path.join(_hotel_series_dir, f"{hotel_slug}.json")
            with open(series_path, "w", encoding="utf-8") as f:
                json.dump(series_payload, f, ensure_ascii=False, indent=2)
            series_manifest[hotel_slug] = content_hash
            series_written += 1
        else:
            series_skipped += 1

        if write_legacy_hotel_html and charts_subdir:
            charts_dir = charts_subdir
            hotel_html_path = os.path.join(charts_dir, f"{hotel_slug}.html")
            back_href = os.path.relpath(_back_dashboard_href, start=os.path.dirname(hotel_html_path))
            favicon_href = os.path.relpath("favicon.svg", start=os.path.dirname(hotel_html_path))
            chart_html = _render_hotel_chart_page(
                hotel_name=str(hotel_name),
                hotel_name_html=meta.get('hotel_name_html') or html_lib.escape(str(hotel_name)),
                x_values=x_values,
                y_values=y_values,
                hover_lines=text_values,
                meta=meta,
                back_href=back_href,
                deal_score=deal_score,
                deal_label=deal_label,
                deal_class=deal_class,
                delta48_str=delta48_str,
                delta_avg_str=delta_avg_str,
                confidence=confidence,
                median_p=median_p,
                min_p=min_p,
                max_p=max_p,
                samples=len(y_values),
                alert_threshold=ALERT_THRESHOLD_PERCENT,
                trip_dates_label=trip_dates_label,
                display_price_ceiling=ceiling_val,
                history_price_ceiling=history_val,
                favicon_href=favicon_href,
            )
            with open(hotel_html_path, 'w', encoding='utf-8') as f:
                f.write(chart_html)

        _register_chart_href(chart_href_lookup, hotel_name, viewer_href)

    _save_hotel_series_manifest(_hotel_series_dir, series_manifest)
    print(f"📈 Hotel series: записано {series_written}, без изменений {series_skipped} → {_hotel_series_dir}")

    for name, meta in hotel_meta_by_name.items():
        href = meta.get("chart_href")
        if href:
            _register_chart_href(chart_href_lookup, str(name), str(href))

    # Country detection for Passport & OTA cards
    filter_lower = (str(data_file) + " " + str(output_file)).lower()
    if any(k in filter_lower for k in ("turkey", "turcja")):
        default_country = "Турция"
    elif any(k in filter_lower for k in ("egypt", "egipt")):
        default_country = "Египет"
    elif any(k in filter_lower for k in ("greece", "grecja")):
        default_country = "Греция"
    elif any(k in filter_lower for k in ("cypr", "cyprus")):
        default_country = "Кипр"
    else:
        default_country = "Курорт"

    catalog_hotels_index = {}
    if os.path.exists("hotels_catalog_data.json"):
        try:
            with open("hotels_catalog_data.json", "r", encoding="utf-8") as f:
                cat_data = json.load(f)
                for h_entry in cat_data.get("hotels", []):
                    norm_k = re.sub(r"[^\w\d]+", "", h_entry.get("hotel_name", "").lower())
                    catalog_hotels_index[norm_k] = h_entry
        except Exception:
            pass

    hotel_passport_data = {}
    hotel_ai_profiles = {}

    def _parse_tour_departure_date(dates_str, dep_date_val=None, offer_url_val=None, ref_year=None):
        if ref_year is None:
            ref_year = datetime.now().year
        if dep_date_val is not None and pd.notna(dep_date_val) and dep_date_val is not pd.NaT and type(dep_date_val).__name__ != 'NaTType':
            try:
                dt_obj = pd.to_datetime(dep_date_val)
                if pd.notna(dt_obj) and dt_obj is not pd.NaT and type(dt_obj).__name__ != 'NaTType':
                    d_val = dt_obj.date()
                    if pd.notna(d_val) and d_val is not pd.NaT and type(d_val).__name__ != 'NaTType':
                        return d_val
            except Exception:
                pass
        if offer_url_val and pd.notna(offer_url_val):
            m = re.search(r'departureDate=(\d{4}-\d{2}-\d{2})', str(offer_url_val))
            if m:
                try:
                    return datetime.strptime(m.group(1), '%Y-%m-%d').date()
                except Exception:
                    pass
        if dates_str and pd.notna(dates_str):
            s = str(dates_str).strip()
            first = s.split('-')[0].strip()
            m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', first)
            if m:
                d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                try:
                    return date(y, mth, d)
                except Exception:
                    pass
            m2 = re.match(r'^(\d{1,2})\.(\d{1,2})$', first)
            if m2:
                d, mth = int(m2.group(1)), int(m2.group(2))
                try:
                    return date(ref_year, mth, d)
                except Exception:
                    pass
        return None

    today_date = datetime.now().date()

    specs_kb_norm = {}
    if isinstance(specs_kb, dict):
        for sk, sv in specs_kb.items():
            specs_kb_norm[re.sub(r"[^\w\d]+", "", sk.lower())] = sv

    rep_kb_norm = {}
    if isinstance(reputation_kb_data, dict):
        for rk, rv in reputation_kb_data.items():
            rep_kb_norm[re.sub(r"[^\w\d]+", "", rk.lower())] = rv

    for c in hotel_cards:
        h_name = c["hotel_name"]
        h_slug = slugify(h_name)
        h_pts_data = []
        h_grp = history_by_hotel.get(h_name)
        if h_grp is not None and not h_grp.empty:
            sorted_grp = h_grp.sort_values('scraped_at_display')
            for t_val, p_val in zip(sorted_grp['scraped_at_display'], sorted_grp['price']):
                if pd.notna(t_val) and pd.notna(p_val) and float(p_val) > 0:
                    h_pts_data.append({
                        "date": t_val.strftime('%d.%m %H:%M'),
                        "iso": t_val.strftime('%Y-%m-%d %H:%M:%S'),
                        "ts": int(t_val.timestamp() * 1000),
                        "price": float(p_val)
                    })
        min_p_card = min([pt['price'] for pt in h_pts_data]) if h_pts_data else float(c["price"])
        max_p_card = max([pt['price'] for pt in h_pts_data]) if h_pts_data else float(c["price"])

        drop_pct_card = 0.0
        d48_str = str(c.get("delta48", ""))
        if "-" in d48_str:
            try:
                drop_pct_card = abs(float(re.sub(r"[^\d.]", "", d48_str)))
            except (ValueError, TypeError):
                pass

        h_pkgs = []
        seen_dates = set()

        # 1. Primary guaranteed active offer from current run (card 'c')
        c_dates = c.get("dates")
        c_url = c.get("offer_url") or c.get("url") or ""
        c_price = float(c.get("price") or 0)
        c_dep_date = _parse_tour_departure_date(c_dates, c.get("departure_date"), c_url)

        c_is_future = True
        if c_dep_date is not None and pd.notna(c_dep_date) and c_dep_date is not pd.NaT and type(c_dep_date).__name__ != 'NaTType':
            try:
                c_is_future = (c_dep_date >= today_date)
            except Exception:
                c_is_future = True

        if c_is_future:
            if c_price > 0:
                c_iso = c_dep_date.isoformat() if (c_dep_date and pd.notna(c_dep_date) and c_dep_date is not pd.NaT and type(c_dep_date).__name__ != 'NaTType') else ""
                norm_d_key = c_iso if c_iso else str(c_dates).strip()
                seen_dates.add(norm_d_key)
                h_pkgs.append({
                    "dates": str(c_dates or "—"),
                    "duration": str(c.get("duration") or "—"),
                    "composition": str(c.get("duration_bucket") or "2 взр."),
                    "price": c_price,
                    "url": str(c_url),
                    "dep_date_sort": c_iso or "9999-12-31",
                })

        # 2. Collect other recent future departures for this hotel from recent runs (last 72 hours)
        if h_grp is not None and not h_grp.empty:
            latest_grp_ts = h_grp['scraped_at_display'].max()
            recent_cutoff = latest_grp_ts - pd.Timedelta(days=3) if pd.notna(latest_grp_ts) else None
            recent_grp = h_grp[h_grp['scraped_at_display'] >= recent_cutoff] if recent_cutoff is not None else h_grp

            # Sort descending by scrape time so freshest offers/urls come first
            for _, r_pkg in recent_grp.sort_values('scraped_at_display', ascending=False).iterrows():
                r_dates = r_pkg.get("dates")
                r_url = r_pkg.get("offer_url") or r_pkg.get("url") or ""
                r_price = float(r_pkg.get("price") or 0)
                if r_price <= 0:
                    continue

                r_dep_date = _parse_tour_departure_date(r_dates, r_pkg.get("departure_date"), r_url)
                # Skip past departures safely!
                if r_dep_date is not None and pd.notna(r_dep_date) and r_dep_date is not pd.NaT and type(r_dep_date).__name__ != 'NaTType':
                    try:
                        if r_dep_date < today_date:
                            continue
                    except Exception:
                        pass

                r_iso = r_dep_date.isoformat() if (r_dep_date and pd.notna(r_dep_date) and r_dep_date is not pd.NaT and type(r_dep_date).__name__ != 'NaTType') else ""
                norm_d_key = r_iso if r_iso else str(r_dates).strip()
                if norm_d_key in seen_dates:
                    continue
                seen_dates.add(norm_d_key)

                h_pkgs.append({
                    "dates": str(r_dates or "—"),
                    "duration": str(r_pkg.get("duration") or "—"),
                    "composition": str(c.get("duration_bucket") or "2 взр."),
                    "price": r_price,
                    "url": str(r_url),
                    "dep_date_sort": r_iso or "9999-12-31",
                })

        # Sort packages chronologically by departure date ascending
        h_pkgs.sort(key=lambda p: (p["dep_date_sort"], p["price"]))
        for p in h_pkgs:
            p.pop("dep_date_sort", None)

        # Cross-filter tracking lookup
        norm_k = re.sub(r"[^\w\d]+", "", h_name.lower())
        cat_entry = catalog_hotels_index.get(norm_k)
        other_filters_list = []
        if cat_entry:
            for pkg in cat_entry.get("packages", []):
                f_id = pkg.get("filter_id", "")
                if f_id and f_id.lower() not in filter_lower:
                    d_url = f"index_{f_id}.html" if f_id.startswith("filter_") else f"index_filter_{f_id}.html"
                    other_filters_list.append({
                        "filter_id": f_id,
                        "label": pkg.get("filter_name") or f_id.replace("filter_", "").replace("_", " ").title(),
                        "price": pkg.get("current_price") or pkg.get("price") or 0,
                        "duration": pkg.get("duration", "—"),
                        "dates": pkg.get("ref_dates", "—"),
                        "dashboard_url": d_url,
                    })

        # Resolve specs & reputation with exact and normalized match
        h_specs = None
        if isinstance(specs_kb, dict):
            h_specs = specs_kb.get(h_name) or specs_kb_norm.get(norm_k)
            if isinstance(h_specs, dict) and "specs" in h_specs and isinstance(h_specs["specs"], dict):
                h_specs = h_specs["specs"]

        h_rep = None
        if isinstance(reputation_kb_data, dict):
            h_rep = reputation_kb_data.get(h_name) or rep_kb_norm.get(norm_k)

        ta_r_val = _parse_ta_rating_value(c.get("ta_rating"))
        ta_rev_val = _parse_ta_review_count(c.get("ta_review_count"))

        prof = generate_hotel_ai_profile(
            hotel_name=h_name,
            country=default_country,
            destination=c.get("region", ""),
            specs=h_specs,
            rep_data=h_rep,
            current_price=float(c["price"]),
            min_price=min_p_card,
            max_price=max_p_card,
            price_drop_pct=drop_pct_card,
            packages=h_pkgs,
            main_image_url=c.get("image_url", ""),
            other_filters=other_filters_list,
            deal_score=c.get("deal_score"),
            delta_avg=c.get("delta_avg"),
            delta48=c.get("delta48"),
            hopper_verdict=c.get("hopper_verdict"),
            hopper_reasoning=c.get("hopper_reasoning"),
            forecast_text=c.get("forecast_text"),
            ta_rating_override=ta_r_val,
            ta_reviews_override=ta_rev_val,
        )
        hotel_ai_profiles[h_name] = prof

        hotel_passport_data[h_slug] = {
            "hotel_name": h_name,
            "slug": h_slug,
            "country": default_country,
            "region": c.get("region", ""),
            "stars": prof["stars"],
            "image_url": c.get("image_url", ""),
            "price": float(c["price"]),
            "min_price": min_p_card,
            "max_price": max_p_card,
            "deal_score": c.get("deal_score", 50),
            "deal_badge": prof["deal_badge"],
            "deal_sub": prof["deal_sub"],
            "deal_class": prof["deal_class"],
            "recommendation": prof["recommendation"],
            "ai_hotel_summary": prof["ai_hotel_summary"],
            "ai_price_summary": prof["ai_price_summary"],
            "ai_audience": prof["ai_audience"],
            "ai_action_signal": prof["ai_action_signal"],
            "price_diff_text": prof["price_diff_text"],
            "ta_rating": prof["ta_rating"],
            "ta_reviews": prof["ta_reviews"],
            "beach_line": prof["beach_line"],
            "beach_type": prof["beach_type"],
            "sea_entry": prof["sea_entry"],
            "has_aquapark": prof["has_aquapark"],
            "has_heated_pools": prof["has_heated_pools"],
            "food_concept": prof["food_concept"],
            "suitable_for": prof["suitable_for"],
            "verdict": prof["verdict"],
            "pros": prof["pros"],
            "cons": prof["cons"],
            "food_snippet": prof["food_snippet"],
            "beach_snippet": prof["beach_snippet"],
            "review_snippet": prof["review_snippet"],
            "tripadvisor_url": prof["tripadvisor_url"],
            "google_reviews_url": prof["google_reviews_url"],
            "youtube_search_url": prof["youtube_search_url"],
            "gallery_photos": prof["gallery_photos"],
            "infra_rich": prof["infra_rich"],
            "other_filters": prof["other_filters"],
            "history_points": h_pts_data,
            "packages": h_pkgs,
        }


    passport_css = get_hotel_passport_css()
    passport_drawer_markup = render_hotel_passport_drawer_html()
    passport_js = get_hotel_passport_js()

    # HTML шаблон
    # Готовим HTML блок изменений, выводим только если есть хотя бы один список
    changes_html = ""
    if decreases_24h or increases_24h:
        changes_html += """
        <div class=\"changes-section\">"""
        if decreases_24h:
            changes_html += """
            <div class=\"changes-block\">
                <h3>📉 Наиболее подешевевшие (24ч)</h3>"""
            for change in decreases_24h:
                changes_html += f"""
                <div class=\"change-item change-decrease\">
                    <div>
                        <div class=\"hotel-name\">{change['hotel_name']}</div>
                        <div class=\"change-percent\">{change['change']:+.0f} PLN ({change['change_percent']:+.1f}%)</div>
                    </div>
                    <div class=\"change-price\">{change['old_price']:.0f} → {change['new_price']:.0f} PLN</div>
                </div>"""
            changes_html += """
            </div>"""
        if increases_24h:
            changes_html += """
            <div class=\"changes-block\">
                <h3>📈 Наиболее подорожавшие (24ч)</h3>"""
            for change in increases_24h:
                changes_html += f"""
                <div class=\"change-item change-increase\">
                    <div>
                        <div class=\"hotel-name\">{change['hotel_name']}</div>
                        <div class=\"change-percent\">{change['change']:+.0f} PLN ({change['change_percent']:+.1f}%)</div>
                    </div>
                    <div class=\"change-price\">{change['old_price']:.0f} → {change['new_price']:.0f} PLN</div>
                </div>"""
            changes_html += """
            </div>"""
        changes_html += """
        </div>"""

    if decreases_7d or increases_7d:
        changes_html += """
        <div class=\"changes-section\">"""
        if decreases_7d:
            changes_html += """
            <div class=\"changes-block\">
                <h3>📉 Наиболее подешевевшие (7д)</h3>"""
            for change in decreases_7d:
                changes_html += f"""
                <div class=\"change-item change-decrease\">
                    <div>
                        <div class=\"hotel-name\">{change['hotel_name']}</div>
                        <div class=\"change-percent\">{change['change']:+.0f} PLN ({change['change_percent']:+.1f}%)</div>
                    </div>
                    <div class=\"change-price\">{change['old_price']:.0f} → {change['new_price']:.0f} PLN</div>
                </div>"""
            changes_html += """
            </div>"""
        if increases_7d:
            changes_html += """
            <div class=\"changes-block\">
                <h3>📈 Наиболее подорожавшие (7д)</h3>"""
            for change in increases_7d:
                changes_html += f"""
                <div class=\"change-item change-increase\">
                    <div>
                        <div class=\"hotel-name\">{change['hotel_name']}</div>
                        <div class=\"change-percent\">{change['change']:+.0f} PLN ({change['change_percent']:+.1f}%)</div>
                    </div>
                    <div class=\"change-price\">{change['old_price']:.0f} → {change['new_price']:.0f} PLN</div>
                </div>"""
            changes_html += """
            </div>"""
        changes_html += """
        </div>"""

    # Game-changer блок: сигнал раннего входа + top opportunities
    signal_class = f"entry-signal entry-{entry_signal_level}"
    signal_items_html = ""
    if entry_top:
        for item in entry_top:
            signal_items_html += f"""
            <div class="entry-item">
                <div>
                    <div class="hotel-name">{item['hotel_name']}</div>
                    <div class="change-percent">Deal Score: {item['deal_score']} ({item.get('confidence','')}) • Δ48ч {item['delta48_pct']:+.1f}%</div>
                </div>
                <div class="change-price">{item['latest']:.0f} PLN</div>
            </div>
            """
    else:
        signal_items_html = "<div class='alerts-empty'>Пока нет кандидатов под строгие критерии раннего входа.</div>"

    entry_signal_html = f"""
    <div class="{signal_class}">
        <div class="entry-title">{entry_signal_title}</div>
        <div class="entry-note">{entry_signal_note}</div>
        <div class="entry-stats">Кандидаты: {len(entry_candidates)} • Доля отелей со снижением (48ч): {market_breadth*100:.1f}%</div>
        <div class="entry-list">{signal_items_html}</div>
    </div>
    """

    # Компактный блок региональных вылетов: "самолёт" выводим через регион + даты,
    # потому что курорты одного региона прилетают в один аэропорт.
    departure_block_html = ""
    departure_history_html = ""
    departure_offers_json = "{}"
    departure_price_curves_json = "{}"
    try:
        data_dir = os.path.dirname(data_file) or "."
        current_cohorts, history_cohorts, stored_hot_history = _load_departure_cohort_frames(
            data_dir, data_file
        )

        if lo_d is not None and hi_d is not None:
            if not current_cohorts.empty and "departure_date" in current_cohorts.columns:
                c_deps = pd.to_datetime(current_cohorts["departure_date"], errors="coerce").dt.date
                current_cohorts = current_cohorts[(c_deps.isna()) | ((c_deps >= lo_d) & (c_deps <= hi_d))].copy()
            if not history_cohorts.empty and "departure_date" in history_cohorts.columns:
                h_deps = pd.to_datetime(history_cohorts["departure_date"], errors="coerce").dt.date
                history_cohorts = history_cohorts[(h_deps.isna()) | ((h_deps >= lo_d) & (h_deps <= hi_d))].copy()


        if not current_cohorts.empty or not history_cohorts.empty:
            history_source = history_cohorts if not history_cohorts.empty else current_cohorts
            current_source = current_cohorts if not current_cohorts.empty else history_cohorts
            group_by_airport = should_group_by_arrival_airport(
                current_source["country"].iloc[0] if not current_source.empty else "",
                active_filter_id(charts_subdir),
            )
            # current_work is strictly used for the latest run (latest_departures & latest_rows).
            # Slicing current_source to the latest run before aggregating eliminates aggregating
            # 100,000+ historical cohort snapshots row-by-row.
            if not current_source.empty:
                _run_ts_temp = pd.to_datetime(current_source["run_started_at"], errors="coerce", utc=True)
                latest_run_ts = _run_ts_temp.max()
                if pd.notna(latest_run_ts):
                    current_source = current_source[_run_ts_temp == latest_run_ts]
            if group_by_airport:
                current_source = aggregate_cohorts_by_arrival_airport(current_source)
            work = _prepare_departure_cohorts(history_source)
            current_work = _prepare_departure_cohorts(current_source)

            def _region_label(value):
                return str(value or 'region').replace('-', ' ').title()

            def _score_class(score):
                score = float(score or 0)
                if score >= 70:
                    return 'hot'
                if score >= 45:
                    return 'warm'
                return 'calm'

            def _days_until_label(value):
                try:
                    days = int(value)
                except (TypeError, ValueError):
                    return "вылет ?"
                if days <= 0:
                    return "вылет сегодня"
                if days == 1:
                    return "вылет завтра"
                return f"вылет через {days} дн."

            latest_dep_ts = current_work['_run_ts'].max() if not current_work.empty else None
            hot_history = (
                stored_hot_history
                if stored_hot_history is not None
                else build_hot_departure_history(work)
            )
            history_rows_html = ""
            for item in hot_history[:8]:
                region = html_lib.escape(_region_label(item.get('region')))
                dep_date = html_lib.escape(str(item.get('departure_date') or '—'))
                nights = item.get('nights')
                nights_label = f"{int(nights)}н" if str(nights) != '' else "?н"
                best_days = item.get('days_to_departure_at_best')
                best_days_label = _days_until_label(best_days)
                p10_drop = float(item.get('best_p10_change_pct') or item.get('max_p10_drop_pct') or 0)
                med_drop = float(item.get('best_median_change_pct') or item.get('max_median_drop_pct') or 0)
                prev_median = float(item.get('best_prev_median_price') or 0)
                curr_median = float(item.get('best_median_price') or 0)
                prev_p10 = float(item.get('best_prev_p10_price') or 0)
                curr_p10 = float(item.get('best_p10_price') or 0)
                median_drop_pln = curr_median - prev_median if prev_median > 0 else 0.0
                p10_drop_pln = curr_p10 - prev_p10 if prev_p10 > 0 else 0.0
                if prev_median > 0 and med_drop <= -0.5:
                    drop_text = (
                        f"Типичная цена: {prev_median:.0f} → {curr_median:.0f} PLN "
                        f"({median_drop_pln:.0f} PLN, {med_drop:+.1f}%)"
                    )
                    drop_subtext = (
                        f"Дешёвые 10%: {prev_p10:.0f} → {curr_p10:.0f} PLN "
                        f"({p10_drop_pln:.0f} PLN, {p10_drop:+.1f}%)"
                        if prev_p10 > 0 and p10_drop <= -0.5 else ''
                    )
                elif prev_p10 > 0 and p10_drop <= -0.5:
                    drop_text = (
                        f"Дешёвые 10%: {prev_p10:.0f} → {curr_p10:.0f} PLN "
                        f"({p10_drop_pln:.0f} PLN, {p10_drop:+.1f}%)"
                    )
                    drop_subtext = ''
                else:
                    drop_text = "Падение цены"
                    drop_subtext = ''
                drop_sub_html = f'<br><span>{html_lib.escape(drop_subtext)}</span>' if drop_subtext else ''
                score_cls = _score_class(item.get('max_hot_score') or 0)
                score = int(item.get('max_hot_score') or 0)
                hotels = int(item.get('max_hotel_count') or 0)
                history_rows_html += f"""
                    <tr class="departure-history-row" data-departure-key="{html_lib.escape(str(item.get('departure_key') or ''))}" role="button" tabindex="0" title="Показать отели по этому вылету">
                        <td><strong>{region}</strong><br><span>{dep_date} · {nights_label}</span></td>
                        <td><strong>{best_days_label}</strong></td>
                        <td><strong>{html_lib.escape(drop_text)}</strong>{drop_sub_html}<br><span>{html_lib.escape(str(item.get('best_seen_at') or ''))[:16]}</span></td>
                        <td><span class="departure-score mini {score_cls}">{score}</span> деш.10% <strong>{float(item.get('best_p10_price') or 0):.0f}</strong> PLN<br><span>мин. {float(item.get('best_min_price') or 0):.0f} · середина {float(item.get('best_median_price') or 0):.0f} · {hotels} отелей</span></td>
                    </tr>
                """
            if history_rows_html:
                departure_history_html = f"""
        <details class="dashboard-fold departure-history-fold" id="departureHistoryFold">
            <summary>
                <span>История горячих вылетов ({len(hot_history)})</span>
                <span class="fold-title-meta">Только прошедшие hot/late-buy кейсы</span>
                <span class="fold-chevron">⌄</span>
            </summary>
            <div class="fold-content">
                <p class="departure-history-hint">Архив уже наступивших вылетов, где за последнюю неделю до старта заметно падали цены. Нажмите на строку — график цен D-{HOT_DEPARTURE_CHART_DAYS_MAX}…D-0 и список отелей.</p>
                <div class="table-container">
                    <table class="hotels-table departure-history-table">
                        <thead>
                            <tr>
                                <th>Вылет</th>
                                <th>За сколько</th>
                                <th>Падение</th>
                                <th>Цена/сигнал</th>
                            </tr>
                        </thead>
                        <tbody>{history_rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </details>
                """
            latest_departures = current_work[current_work['_run_ts'] == latest_dep_ts].copy() if latest_dep_ts is not None else pd.DataFrame()
            latest_departures = latest_departures[latest_departures['hotel_count'].fillna(0) >= 2]
            latest_departures = latest_departures[latest_departures['days_to_departure'].fillna(9999) <= 8]
            nearby_departures_count = int(latest_departures['departure_key'].nunique()) if not latest_departures.empty else 0

            if not latest_departures.empty:
                top_departures = latest_departures.sort_values(
                    ['days_to_departure', 'hot_score', 'p10_change_pct', 'median_change_pct', 'p10_price'],
                    ascending=[True, False, True, True, True]
                )
                active_departures = int(latest_departures['departure_key'].nunique())
                hot_departures = int((latest_departures['hot_score'].fillna(0) >= 70).sum())
                active_hubs = active_departures
                active_regions = int(latest_departures['region'].fillna('').astype(str).nunique())
                best_p10 = float(latest_departures['p10_price'].min())
                hub_stats_label = "аэропортов" if group_by_airport else "регионов"
                hub_stats_value = active_hubs if group_by_airport else active_regions

                def _region_label(value):
                    return str(value or 'region').replace('-', ' ').title()

                def _score_class(score):
                    score = float(score or 0)
                    if score >= 70:
                        return 'hot'
                    if score >= 45:
                        return 'warm'
                    return 'calm'

                def _change_label(value, label):
                    try:
                        pct = float(value or 0)
                    except (TypeError, ValueError):
                        pct = 0.0
                    if abs(pct) < 0.5:
                        return ''
                    cls = 'drop' if pct < 0 else 'up'
                    arrow = '↓' if pct < 0 else '↑'
                    return f'<span class="departure-change {cls}">{label} {arrow} {pct:+.1f}%</span>'

                def _days_until_label(value):
                    try:
                        days = int(value)
                    except (TypeError, ValueError):
                        return "вылет ?"
                    if days <= 0:
                        return "вылет сегодня"
                    if days == 1:
                        return "вылет завтра"
                    return f"вылет через {days} дн."

                rows_html = ""
                for _, dep in top_departures.iterrows():
                    score = _hot_score(dep)
                    score_cls = _score_class(score)
                    card_hot_cls = ' is-hot' if score >= 70 else (' is-warm' if score >= 45 else '')
                    hot_icon = '🔥 ' if score >= 70 else ''
                    status_label = departure_status_label(dep)
                    days_left = dep.get('days_to_departure')
                    days_label = _days_until_label(days_left)
                    nights = dep.get('nights')
                    nights_label = f"{int(nights)}н" if pd.notna(nights) and str(nights) != '' else "?н"
                    region = html_lib.escape(str(dep.get("hub_label") or _region_label(dep.get("region"))))
                    hub_regions_raw = str(dep.get("hub_regions") or "")
                    hub_regions_html = ""
                    if hub_regions_raw:
                        hub_regions_html = (
                            f'<div class="departure-hub-resorts">'
                            f'{html_lib.escape(hub_regions_subtitle(hub_regions_raw.split(",")))}'
                            f'</div>'
                        )
                    departure_date = html_lib.escape(str(dep.get('departure_date') or '—'))
                    return_date = str(dep.get('return_date') or '').strip()
                    return_label = (
                        f"→ {html_lib.escape(return_date)}"
                        if return_date else ''
                    )
                    delta_bits = []
                    common_n = int(dep.get("common_hotel_count") or 0)
                    if common_n >= MIN_COMMON_HOTELS:
                        lookback_lbl = f"за {COHORT_LOOKBACK_TARGET_HOURS}ч"
                        delta_bits.extend([
                            _change_label(
                                dep.get("p10_change_pct"),
                                f"{cheap_tier_label(common_n)} ({lookback_lbl})",
                            ),
                            _change_label(
                                dep.get("median_change_pct"),
                                f"середина ({lookback_lbl})",
                            ),
                        ])
                    try:
                        mean_avg_delta = float(dep.get("mean_avg_delta_pct") or 0)
                    except (TypeError, ValueError):
                        mean_avg_delta = 0.0
                    avg_deal = int(dep.get("avg_deal_score") or 0)
                    hot_deals = int(dep.get("hot_deal_count") or 0)
                    hotel_n = int(dep.get("hotel_count") or 0)
                    if hotel_n >= MIN_DEAL_HOTELS and abs(mean_avg_delta) >= 0.5:
                        delta_bits.append(
                            _change_label(mean_avg_delta, "ниже типичной")
                        )
                    if hotel_n >= MIN_DEAL_HOTELS and avg_deal >= 65:
                        deal_cls = "drop" if avg_deal >= 75 else "warm"
                        delta_bits.append(
                            f'<span class="departure-change {deal_cls}">Deal {avg_deal}'
                            f'{f" · {hot_deals} Hot" if hot_deals else ""}</span>'
                        )
                    delta_html = ''.join(bit for bit in delta_bits if bit) or '<span class="departure-change muted">без сильного движения</span>'
                    rows_html += f"""
                    <div class="departure-card departure-card-clickable{card_hot_cls}" data-departure-key="{html_lib.escape(str(dep.get('departure_key') or ''))}" role="button" tabindex="0" title="Показать отели по этому вылету">
                        <div class="departure-card-head">
                            <div class="departure-title">{hot_icon}{region}</div>
                            <span class="departure-status {score_cls}">{status_label}</span>
                        </div>
                        {hub_regions_html}
                        <div class="departure-facts">
                            <span>{departure_date}</span>
                            {f'<span>{return_label}</span>' if return_label else ''}
                            <span>{nights_label}</span>
                            <span>{days_label}</span>
                        </div>
                        <div class="departure-delta">{delta_html}</div>
                        <div class="departure-price-line">
                            <span>типичная <strong>{float(dep.get('median_price') or 0):.0f}</strong> PLN</span>
                            <span>дешёвые 10% <strong>{float(dep.get('p10_price') or 0):.0f}</strong> PLN</span>
                        </div>
                    </div>
                    """

                departure_block_html = f"""
        <div class="departures-strip">
            <div class="departures-head">
                <div>
                    <h3>🛫 Ближайшие вылеты</h3>
                    <p>Все вылеты на ближайшие 8 дней.{' В Турции карточка = аэропорт прилёта (не отдельный курорт).' if group_by_airport else ''} Горячие, где цены реально падают, подсвечены огоньком и ярким фоном.</p>
                </div>
                <div class="departure-mini-stats">
                    <span>{active_departures} активных</span>
                    <span>{hot_departures} горячих</span>
                    <span>{hub_stats_value} {hub_stats_label}</span>
                    <span>лучшие 10% от {best_p10:.0f} PLN</span>
                </div>
            </div>
            <div class="departure-legend">{'Курорты одного аэропорта объединены: Side/Kemer/Alanya/Belek → Анталия (AYT). ' if group_by_airport else ''}«Горит» / «Снижается» — падение когорты за ~{COHORT_LOOKBACK_TARGET_HOURS}ч (≥{MIN_COMMON_HOTELS} отелей). «Выгодно» — отели ниже типичной цены (≥{MIN_DEAL_HOTELS}). В модалке те же Deal и Δ типичной.</div>
            <div class="departure-grid">{rows_html}</div>
        </div>
                """
            elif nearby_departures_count:
                departure_block_html = f"""
        <div class="departures-strip">
            <div class="departures-head">
                <div>
                    <h3>🛫 Ближайшие вылеты</h3>
                    <p>Смотрим все ближайшие вылеты до 8 дней и ждём заметного падения цен.</p>
                </div>
                <div class="departure-mini-stats">
                    <span>{nearby_departures_count} ближайших</span>
                    <span>0 горящих</span>
                </div>
            </div>
            <div class="departure-legend">Ближайших вылетов в данных сейчас нет.</div>
        </div>
                """

            departure_keys: list[str] = []
            curve_keys: list[str] = []
            preferred_runs: dict[str, str] = {}
            if latest_dep_ts is not None and not current_work.empty:
                latest_rows = current_work[current_work["_run_ts"] == latest_dep_ts]
                if not latest_rows.empty:
                    latest_run = str(latest_rows.iloc[0].get("run_started_at") or "")
                    for _, dep in latest_rows.iterrows():
                        key = str(dep.get("departure_key") or "")
                        if key:
                            departure_keys.append(key)
                            preferred_runs[key] = latest_run
            for item in hot_history:
                key = str(item.get("departure_key") or "")
                if key and key not in preferred_runs:
                    departure_keys.append(key)
                    # Archived departures: hotel table = last prices on departure day (D-0).
                    preferred_runs[key] = str(
                        item.get("departure_day_at")
                        or item.get("last_seen_at")
                        or item.get("best_seen_at")
                        or ""
                    )
                if key:
                    curve_keys.append(key)
            for _, dep in (latest_departures.iterrows() if not latest_departures.empty else []):
                key = str(dep.get("departure_key") or "")
                if key:
                    curve_keys.append(key)
            if curve_keys:
                departure_price_curves_json = json.dumps(
                    build_departure_price_curves(work, list(dict.fromkeys(curve_keys))),
                    ensure_ascii=False,
                )
            if departure_keys:
                offers_df = load_combined_departure_offers(data_dir, data_file)
                departure_offers_payload = build_departure_offers_index(
                    offers_df, departure_keys, preferred_runs
                )
                departure_hotel_histories = build_departure_hotel_histories(offers_df)
                for payload in departure_offers_payload.values():
                    for offer in payload.get("offers", []):
                        hotel_name = str(offer.get("hotel_name") or "")
                        offer["chart_href"] = _resolve_chart_href(
                            hotel_name, chart_href_lookup, charts_subdir, slugify
                        )
                        offer["slug"] = slugify(hotel_name)
                        hist = departure_hotel_histories.get(hotel_name)
                        try:
                            offer_price = float(offer.get("price"))
                        except (TypeError, ValueError):
                            offer["deal_has_data"] = False
                            offer["deal_score"] = None
                            offer["deal_label"] = ""
                            offer["deal_class"] = ""
                            offer["delta_avg"] = "—"
                            continue
                        if hist is None or len(hist) < 2:
                            offer["deal_has_data"] = False
                            offer["deal_score"] = None
                            offer["deal_label"] = ""
                            offer["deal_class"] = ""
                            offer["delta_avg"] = "—"
                            continue
                        metrics = compute_hotel_deal_metrics(
                            hist,
                            offer_price,
                            ta_rating=offer.get("ta_rating"),
                            ta_review_count=offer.get("ta_review_count"),
                        )
                        deal_score = int(metrics["deal_score"])
                        confidence = metrics["confidence"]
                        d_avg = float(metrics["avg_delta_pct"])
                        deal_label, deal_class, _ = classify_deal_badge(
                            deal_score, confidence, None, d_avg, None
                        )
                        offer["deal_has_data"] = True
                        offer["deal_score"] = deal_score
                        offer["deal_label"] = deal_label
                        offer["deal_class"] = deal_class
                        offer["delta_avg"] = f"{d_avg:+.1f}%"
                departure_offers_json = json.dumps(departure_offers_payload, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Не удалось построить блок вылетов: {e}")

    # Время последнего обновления для шапки
    meta_path = os.path.join(data_dir, ".monitor_last_run.json") if data_dir else None
    last_run_dt = None
    if meta_path and os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as _mf:
                _mdata = json.load(_mf)
                _lrun_str = _mdata.get("last_run_utc")
                if _lrun_str:
                    last_run_dt = datetime.fromisoformat(_lrun_str.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
        except Exception:
            pass

    try:
        _updated_ts = df['scraped_at_display'].max()
        updated_date = _updated_ts.strftime('%d.%m.%Y')
        updated_time = _updated_ts.strftime('%H:%M')

        # Если монитор проверял недавно, используем время последней проверки для таймера и бейджа
        _effective_ts = last_run_dt if last_run_dt else _updated_ts
        updated_iso = _effective_ts.isoformat()

        _now_ts = datetime.now(tz=_effective_ts.tzinfo) if _effective_ts.tzinfo else datetime.now()
        _age_hours = (_now_ts - _effective_ts).total_seconds() / 3600
        if _age_hours < 3:
            update_status_cls = 'update-status--ok'
            update_status_icon = '🟢'
        elif _age_hours < 12:
            update_status_cls = 'update-status--warn'
            update_status_icon = '🟡'
        else:
            update_status_cls = 'update-status--err'
            update_status_icon = '🔴'

        if last_run_dt:
            last_run_str = last_run_dt.strftime('%d.%m.%Y %H:%M')
            badge_title = f"Проверено: {last_run_str} | Свежие предложения: {updated_date} {updated_time}"
        else:
            badge_title = f"Обновлено: {updated_date} {updated_time}"
    except Exception:
        _updated_ts = datetime.now()
        updated_date = _updated_ts.strftime('%d.%m.%Y')
        updated_time = _updated_ts.strftime('%H:%M')
        updated_iso = _updated_ts.isoformat()
        update_status_cls = 'update-status--ok'
        update_status_icon = '🟢'
        badge_title = f"Обновлено: {updated_date} {updated_time}"

    # Дополнительная подпись свежести офферов, если проверка была позже, чем появление новых туров
    offers_subtext_html = ""
    try:
        if last_run_dt and _updated_ts and (_effective_ts - _updated_ts).total_seconds() > 3600:
            offers_subtext_html = (
                f'<div style="font-size:11px;color:#94a3b8;margin-top:2px;font-weight:400;" '
                f'title="{badge_title}">офферы: {updated_date} {updated_time}</div>'
            )
    except Exception:
        offers_subtext_html = ""


    filter_params_html = render_filter_params_html(
        filter_config,
        display_price_ceiling=ceiling_val,
        history_price_ceiling=history_val,
        escape=html_lib.escape,
    )
    global_duration_switch_html = (
        render_global_duration_switch_html(
            trip_buckets,
            default_bucket_id=default_trip_duration_bucket,
            escape=html_lib.escape,
        )
        if use_trip_buckets else ""
    )
    duration_views_json_embed = ""
    cfg_path = resolve_config_path(data_file, config_file)
    if filter_config and cfg_path:
        print(f"📋 Параметры фильтра из {cfg_path}")

    _current_filter = active_filter_id(charts_subdir)
    _is_current_paused = False
    for _, _f in iter_filters():
        if _f['id'] == _current_filter and is_filter_paused(_f):
            _is_current_paused = True
            break

    paused_banner_html = ""
    if _is_current_paused:
        paused_banner_html = (
            '<div class="paused-banner" style="margin-bottom:18px;padding:12px 18px;border-radius:12px;'
            'background:rgba(245,158,11,0.14);border:1px solid rgba(245,158,11,0.35);color:#b45309;'
            'font-weight:600;display:flex;align-items:center;gap:10px;font-size:0.92rem;">'
            '<span style="font-size:1.2rem;">⏸️</span>'
            '<span>Мониторинг этого направления временно приостановлен администратором. Отображаются последние сохранённые цены.</span>'
            '</div>'
        )

    _sidebar_nav_parts = [
        '<a href="index.html" class="nav-item">'
        '<span class="flag">🏠</span>'
        '<span class="country-name">Главная</span></a>',
        '<a href="hotels.html" class="nav-item" style="color:var(--primary);font-weight:700;">'
        '<span class="flag">🏨</span>'
        '<span class="country-name">Каталог отелей</span></a>',
        '<a href="create_filter.html" class="nav-item nav-item-create" style="color:var(--primary);font-weight:700;">'
        '<span class="flag">✨</span>'
        '<span class="country-name">+ Новый фильтр</span></a>',
        '<a href="admin_filters.html" class="nav-item" style="color:var(--text-secondary);font-size:0.85rem;">'
        '<span class="flag">🎛️</span>'
        '<span class="country-name">Admin Hub</span></a>',
    ]
    for group in active_filter_groups():
        _sidebar_nav_parts.append(
            f'<div class="nav-group-label"><span>{group["icon"]}</span>{group["label"]}</div>'
        )
        for flt in group['filters']:
            active = ' active' if flt['id'] == _current_filter else ''
            paused_tag = '<span style="font-size:0.75rem;margin-left:auto;color:#b45309;" title="На паузе">⏸️</span>' if is_filter_paused(flt) else ''
            _sidebar_nav_parts.append(
                f'<a href="{flt["href"]}" class="nav-item{active}">'
                f'<span class="country-name">{flt["title"]}</span>{paused_tag}</a>'
            )
    arch_group = archived_filter_group()
    if arch_group and arch_group.get('filters'):
        _sidebar_nav_parts.append(
            f'<div class="nav-group-label nav-group-archived"><span>{arch_group["icon"]}</span>{arch_group["label"]}</div>'
        )
        for flt in arch_group['filters']:
            active = ' active' if flt['id'] == _current_filter else ''
            _sidebar_nav_parts.append(
                f'<a href="{flt["href"]}" class="nav-item nav-item-archived{active}">'
                f'<span class="country-name">{flt["title"]}</span>'
                f'<span class="nav-archived-tag">архив</span></a>'
            )
    sidebar_nav_html = ''.join(_sidebar_nav_parts)
    
    # Детекция страны назначения для плашки "Куда"
    COUNTRY_MAP = {
        "egipt": "Египет",
        "egypt": "Египет",
        "grecja": "Греция",
        "greece": "Греция",
        "turcja": "Турция",
        "turkey": "Турция",
        "hiszpania": "Испания",
        "spain": "Испания",
        "cypr": "Кипр",
        "cyprus": "Кипр",
        "wlochy": "Италия",
        "italy": "Италия",
        "bulgaria": "Болгария",
        "albania": "Албания",
        "tunezja": "Тунис",
        "maroko": "Марокко",
    }
    combined_dest_str = f"{title} {output_file} {data_file} {filter_config or {}}".lower()
    dest_display_name = "Все страны"
    for k, v in COUNTRY_MAP.items():
        if k in combined_dest_str or v.lower() in combined_dest_str:
            dest_display_name = v
            break
    if dest_display_name == "Все страны" and not df_canonical.empty and 'offer_url' in df_canonical.columns:
        for url in df_canonical['offer_url'].dropna().head(30):
            path_info = parse_offer_path(str(url))
            c_key = (path_info.get('country') or '').lower()
            if c_key in COUNTRY_MAP:
                dest_display_name = COUNTRY_MAP[c_key]
                break

    entry_candidates_count = len(entry_candidates)
    market_breadth_pct_str = f"{market_breadth*100:.0f}%"
    best_deal_score_val = max((v['score'] for v in deal_score_by_hotel.values()), default=0)

    # Option 2 Humanized KPI Metrics
    if not all_hotels.empty and 'price' in all_hotels.columns:
        _valid_prices = pd.to_numeric(all_hotels['price'], errors='coerce').dropna()
        min_current_price = float(_valid_prices.min()) if not _valid_prices.empty else 0.0
    else:
        min_current_price = 0.0
    min_price_str = f"от {_format_pln(min_current_price)} zł" if min_current_price > 0 else "—"

    buy_recommended_count = 0
    if not all_hotels.empty:
        for idx, row in all_hotels.iterrows():
            rid = row.get('row_id') or row['hotel_name']
            ds = deal_score_by_hotel.get(rid, {}).get('score', 0)
            verdict = str(row.get('hopper_verdict') or '')
            if verdict in ('BUY_NOW', 'GOOD_PRICE') or ds >= 70:
                buy_recommended_count += 1

    drops_48h_count = sum(1 for d in deltas_by_hotel.values() if d is not None and d[0] < 0)

    cfg_url = resolve_config_url(filter_config)
    country_flag = COUNTRY_FLAGS.get(dest_display_name, "")
    if not country_flag:
        for c_name, flag in COUNTRY_FLAGS.items():
            if c_name.lower() in title.lower() or c_name.lower() in dest_display_name.lower():
                country_flag = flag
                break
    if not country_flag:
        country_flag = "✈️"

    if cfg_url:
        fly_button_html = (
            f'<a href="{html_lib.escape(cfg_url)}" target="_blank" rel="noopener noreferrer" class="btn-open-fly" title="Открыть этот поисковый запрос на Fly.pl">'
            f'<span>Поиск на Fly.pl</span>'
            f'<svg class="external-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>'
            f'<polyline points="15 3 21 3 21 9"></polyline>'
            f'<line x1="10" y1="14" x2="21" y2="3"></line>'
            f'</svg>'
            f'</a>'
        )
    else:
        fly_button_html = ""

    airports_parts = _airports_parts(cfg_url) if cfg_url else []
    if not airports_parts:
        airports_val = "Польша (все)"
    elif len(airports_parts) >= 10:
        airports_val = "Польша (все аэропорты)"
    else:
        airports_val = _airport_compact_label(airports_parts)

    dur_label = _duration_label(cfg_url) if cfg_url else "—"
    wf = fly_query_param(cfg_url, "whenFrom") if cfg_url else ""
    wt = fly_query_param(cfg_url, "whenTo") if cfg_url else ""
    dates_val = ""
    if wf and wt:
        try:
            d1 = datetime.strptime(wf, "%d-%m-%Y")
            d2 = datetime.strptime(wt, "%d-%m-%Y")
            if d1.year != d2.year:
                dates_part = f"{d1.strftime('%d.%m.%y')} – {d2.strftime('%d.%m.%y')}"
            else:
                dates_part = f"{d1.strftime('%d.%m')} – {d2.strftime('%d.%m')}"
            if dur_label and dur_label != "—":
                dates_val = f"{dates_part} ({dur_label} дн.)"
            else:
                dates_val = dates_part
        except Exception:
            dates_val = f"{wf} – {wt}"
    elif dur_label and dur_label != "—":
        dates_val = f"{dur_label} дней"
    else:
        dates_val = "Любые даты"

    if cfg_url:
        adults_cnt, children_cnt, child_years = _party_counts(cfg_url)
        if children_cnt > 0:
            party_val = f"{adults_cnt} взр. + {children_cnt} реб."
            if child_years is not None:
                party_val += f" (~{child_years} л.)"
        elif adults_cnt == 1:
            party_val = "1 взрослый"
        elif adults_cnt == 2:
            party_val = "2 взрослых"
        elif adults_cnt > 0:
            party_val = f"{adults_cnt} взр."
        else:
            party_val = "2 взрослых"
    else:
        party_val = "2 взрослых"

    stars_num = _stars_min(cfg_url) if cfg_url else 0
    cat_raw = fly_query_param(cfg_url, "addCatering") if cfg_url else ""
    if stars_num >= 5:
        star_part = "5★"
    elif stars_num > 0:
        star_part = f"{stars_num}★+"
    else:
        star_part = ""

    if cat_raw == "1":
        meal_part = "All Inclusive"
    elif cat_raw == "0":
        meal_part = "Любое питание"
    else:
        meal_part = ""

    if star_part and meal_part:
        hotel_val = f"{star_part} · {meal_part}"
    elif star_part:
        hotel_val = star_part
    elif meal_part:
        hotel_val = meal_part
    else:
        hotel_val = "Все отели"

    lo_p, hi_p = _price_bounds(filter_config or {}, cfg_url) if cfg_url else (None, None)
    eff_hi = ceiling_val if ceiling_val is not None else hi_p
    if lo_p is not None and eff_hi is not None:
        budget_val = f"{_format_pln(lo_p, compact=True)} – {_format_pln(eff_hi, compact=True)} PLN"
    elif eff_hi is not None:
        budget_val = f"до {_format_pln(eff_hi, compact=True)} PLN"
    elif lo_p is not None:
        budget_val = f"от {_format_pln(lo_p, compact=True)} PLN"
    else:
        budget_val = "Любой бюджет"

    html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <title>{title}</title>
    <link rel="icon" href="favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="favicon.svg">
{get_dashboard_css(passport_css)}
    <!-- Cloudflare Web Analytics --><script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='&#123;&quot;token&quot;: &quot;1b9c3c0ee6164106a1cb5eda9e61a045&quot;&#125;'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
    <div class="app-topbar">
        <button class="sidebar-toggle" id="sidebarToggle" aria-label="Меню">☰</button>
        <button class="theme-toggle" id="themeToggle" aria-label="Тема">🌙</button>
    </div>
    <!-- Sidebar Navigation -->
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h2>🌍 Travel Monitor</h2>
        </div>
        <nav class="sidebar-nav">
            {sidebar_nav_html}
        </nav>
    </div>
    
    <!-- Sidebar Overlay -->
    <div class="sidebar-overlay" id="sidebarOverlay"></div>
    
    <!-- Main Content -->
    <div class="main-content" id="mainContent">
    <div class="container">
        <div class="hero-terminal">
            {paused_banner_html}
            <div class="hero-terminal-top">
                <div class="hero-terminal-title-area">
                    <div class="hero-terminal-badge">
                        <span class="country-flag">{country_flag}</span>
                        <span class="country-name">{dest_display_name}</span>
                    </div>
                    <h1 class="hero-terminal-title">{title}</h1>
                </div>
                {fly_button_html}
            </div>

            <!-- Dynamic Metadata Chips Row -->
            <div class="hero-terminal-chips">
                <div class="terminal-chip" title="Аэропорты вылета">
                    <span class="chip-icon">🛫</span>
                    <span class="chip-label">Вылет:</span>
                    <span class="chip-val">{airports_val}</span>
                </div>
                <div class="terminal-chip" title="Даты вылета и длительность">
                    <span class="chip-icon">📅</span>
                    <span class="chip-label">Даты:</span>
                    <span class="chip-val">{dates_val}</span>
                </div>
                <div class="terminal-chip" title="Состав туристов">
                    <span class="chip-icon">👤</span>
                    <span class="chip-label">Состав:</span>
                    <span class="chip-val">{party_val}</span>
                </div>
                <div class="terminal-chip" title="Класс отеля и тип питания">
                    <span class="chip-icon">⭐</span>
                    <span class="chip-label">Отель:</span>
                    <span class="chip-val">{hotel_val}</span>
                </div>
                <div class="terminal-chip" title="Бюджет фильтра">
                    <span class="chip-icon">💰</span>
                    <span class="chip-label">Бюджет:</span>
                    <span class="chip-val">{budget_val}</span>
                </div>
            </div>

            <!-- 4 White KPI Cards (Option 2: Travel-Centric) -->
            <div class="kpi-cards-grid">
                <div class="kpi-card-white" title="Минимальная цена тура в актуальной выдаче">
                    <div class="kpi-card-icon-box kpi-icon--price">
                        <svg class="kpi-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="2" y="5" width="20" height="14" rx="2"></rect>
                            <line x1="2" y1="10" x2="22" y2="10"></line>
                        </svg>
                    </div>
                    <div class="kpi-card-info">
                        <div class="kpi-card-number" id="heroKpiMinPrice">{min_price_str}</div>
                        <div class="kpi-card-title">Мин. цена сейчас</div>
                    </div>
                </div>
                <div class="kpi-card-white" title="Отели с рекомендацией «Покупать» (Hopper AI или Deal Score ≥ 70)">
                    <div class="kpi-card-icon-box kpi-icon--buy">
                        <svg class="kpi-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                            <polyline points="22 4 12 14.01 9 11.01"></polyline>
                        </svg>
                    </div>
                    <div class="kpi-card-info">
                        <div class="kpi-card-number" id="heroKpiBuyNow">{buy_recommended_count}</div>
                        <div class="kpi-card-title">К покупке сейчас</div>
                    </div>
                </div>
                <div class="kpi-card-white" title="Отели, цена которых снизилась за последние 48 часов">
                    <div class="kpi-card-icon-box kpi-icon--drop">
                        <svg class="kpi-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="23 18 13.5 8.5 8.5 13.5 1 6"></polyline>
                            <polyline points="17 18 23 18 23 12"></polyline>
                        </svg>
                    </div>
                    <div class="kpi-card-info">
                        <div class="kpi-card-number" id="heroKpiDrops48h">{drops_48h_count}</div>
                        <div class="kpi-card-title">Подешевели за 48ч</div>
                    </div>
                </div>
                <div class="kpi-card-white">
                    <div class="kpi-card-icon-box">
                        <svg class="kpi-svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
                    </div>
                    <div class="kpi-card-info">
                        <div class="kpi-status-tag">
                            <span class="update-status {update_status_cls}" id="updateStatusBadge" title="{badge_title}" data-iso="{updated_iso}">
                                {update_status_icon} Обновлено
                            </span>
                        </div>
                        <div class="kpi-card-number kpi-card-time" id="updateAgoText">{updated_date} {updated_time}</div>
                        {offers_subtext_html}
                    </div>
                </div>
            </div>
        </div>
"""

    from price_alerts_v2 import ALERT_THRESHOLD_PERCENT

    scope_hotel_names = set(df_canonical['hotel_name'].astype(str).tolist()) if not df_canonical.empty else set()
    alert_chips_html, alerts_content_html = _build_alerts_panel_html(
        alerts=alerts,
        table_prices=table_prices,
        premium_history_by_hotel=premium_history_by_hotel,
        scope_hotel_names=scope_hotel_names,
        hotel_meta_by_name=hotel_meta_by_name,
        latest_run_ts=df_canonical['scraped_at_display'].max() if not df_canonical.empty else None,
        ceiling_val=ceiling_val,
        alert_threshold_percent=ALERT_THRESHOLD_PERCENT,
        parse_iso_fn=parse_iso,
        scope_duration_bucket=default_trip_duration_bucket if use_trip_buckets else '',
    )

    alerts_html = f"""
        <div class="alerts-section" id="alertsSection">
            <div class="alerts-header" onclick="toggleAlerts()">
                <div class="alerts-header-main">
                    <h3>📊 Заметные изменения цен</h3>
                    <p class="alerts-lead">Отели, у которых <strong>заметно изменилась цена</strong> (от {ALERT_THRESHOLD_PERCENT:.0f}% между проверками или возврат из дорогого сегмента) и <strong>эта цена всё ещё актуальна</strong> — в последнем обновлении она не менялась. Прошлые события — в «Истории».</p>
                    <div class="alerts-summary-chips" id="alertsSummaryChips">{alert_chips_html}</div>
                </div>
                <span class="expand-icon collapsed" id="alertsExpandIcon">►</span>
            </div>
            <div class="alerts-content collapsed" id="alertsContent">
{alerts_content_html}
            </div>
        </div>
"""

    # Карточки отелей (визуальный режим)
    cards_inner_html = ""
    cards_html = """
        <div class="cards-section" id="cardsSection">
            <div class="cards-grid" id="cardsGrid">
"""
    for c in hotel_cards:
        ai_prof = hotel_ai_profiles.get(c["hotel_name"], {})
        card_article = render_hotel_card_horiz(c, ai_prof)
        cards_html += card_article
        cards_inner_html += card_article

    cards_html += """
        </div>
            <div class="cards-pagination" id="cardsPagination">
                <button id="cardsPrevPage" disabled>← Предыдущая</button>
                <div class="cards-pagination-info">
                    Показано <span id="cardsShowingFrom">1</span>-<span id="cardsShowingTo">24</span> из <span id="cardsTotalItems">0</span>
                </div>
                <button id="cardsNextPage">Следующая →</button>
            </div>
        </div>
"""

    _t = timing_analysis if isinstance(timing_analysis, dict) else {}
    _conf_label = {"collecting": "Накопление", "preliminary": "Предварительно", "reliable": "Надёжно"}
    _conf_class = {"collecting": "timing-pill-collecting", "preliminary": "timing-pill-prelim", "reliable": "timing-pill-reliable"}
    _hist = _t.get("history", {}) or {}
    _reco = html_lib.escape(str(_t.get("recommendation", "") or ""))
    _dims = _t.get("dimensions", {}) or {}

    def _dim_badge(dim_key, name):
        dim = _dims.get(dim_key) or {}
        conf = dim.get("reached_confidence", "collecting")
        prog = int(round((dim.get("progress", 0) or 0) * 100))
        unit = dim.get("unit", "")
        return (
            f'<div class="timing-badge">'
            f'<span class="timing-badge-name">{html_lib.escape(name)}</span>'
            f'<span class="timing-pill {_conf_class.get(conf, "timing-pill-collecting")}">{_conf_label.get(conf, conf)}</span>'
            f'<span class="timing-badge-prog">{prog}% до надёжного ({unit})</span>'
            f'</div>'
        )

    if _t.get("available"):
        _span_txt = f'{_hist.get("first", "—")} → {_hist.get("last", "—")}'
        _days_txt = f'{_hist.get("days", 0)} дн., {_hist.get("weeks", 0)} нед.'
        _baseline_txt = f'{(_t.get("baseline_p_drop", 0) or 0) * 100:.1f}%'
        timing_inner_html = f"""
                <div class="timing-banner">
                    <div class="timing-banner-row">
                        <span class="timing-banner-label">История наблюдений</span>
                        <span class="timing-banner-value">{html_lib.escape(_span_txt)} ({html_lib.escape(_days_txt)})</span>
                    </div>
                    <div class="timing-banner-row">
                        <span class="timing-banner-label">Базовая вероятность снижения за интервал</span>
                        <span class="timing-banner-value">{_baseline_txt}</span>
                    </div>
                </div>
                <div class="timing-reco">💡 {_reco}</div>
                <div class="timing-badges">
                    {_dim_badge("hour", "Час дня")}
                    {_dim_badge("dow", "День недели")}
                    {_dim_badge("part", "Часть месяца")}
                    {_dim_badge("month", "Месяц")}
                </div>
                <div class="timing-grid">
                    <div class="timing-chart-card">
                        <h4>Вероятность снижения по часам дня (время Варшавы)</h4>
                        <div id="timingHourChart" style="height:300px;"></div>
                        <p class="timing-hint">Столбцы — доля интервалов со снижением цены; усы — 95% интервал Уилсона; пунктир — средний уровень. Бар «зажигается», только когда нижняя граница интервала выше среднего.</p>
                    </div>
                    <div class="timing-chart-card">
                        <h4>Вероятность снижения по дням недели</h4>
                        <div id="timingDowChart" style="height:300px;"></div>
                    </div>
                    <div class="timing-chart-card timing-chart-wide">
                        <h4>Интенсивность снижения: день недели × час</h4>
                        <div id="timingHeatmap" style="height:360px;"></div>
                        <p class="timing-hint">Ожидаемое снижение за интервал (вероятность × средний размер падения). Тёмные клетки — мало данных.</p>
                    </div>
                    <div class="timing-chart-card">
                        <h4>Вероятность снижения по части месяца</h4>
                        <div id="timingPartChart" style="height:280px;"></div>
                    </div>
                    <div class="timing-chart-card">
                        <h4>По месяцам <span class="timing-info-tag">справочно</span></h4>
                        <div id="timingMonthChart" style="height:280px;"></div>
                        <p class="timing-hint">Один сезон не доказывает месячную сезонность — нужны данные за несколько лет. Показано для общей картины.</p>
                    </div>
                </div>
"""
    else:
        timing_inner_html = f"""
                <div class="timing-reco">💡 {_reco or 'Накапливаем данные для анализа лучшего времени покупки.'}</div>
                <p class="timing-hint">Нужно минимум 2 последовательных замера одного и того же тура. По мере накопления ежечасной истории здесь появятся графики по часам дня, дням недели, частям месяца и месяцам.</p>
"""

    timing_section_html = f"""
        <details class="dashboard-fold" id="timingFold">
            <summary>
                <span>Когда покупать: статистика снижения цен</span>
                <span class="fold-title-meta">Время суток · день недели · часть месяца</span>
                <span class="fold-chevron">⌄</span>
            </summary>
            <div class="fold-content">
{timing_inner_html}
            </div>
        </details>
"""

    eb_analysis_res = None
    if analyze_early_booking is not None:
        try:
            eb_analysis_res = analyze_early_booking(df, filter_id=_current_filter if '_current_filter' in locals() else '')
        except Exception as _e_eb:
            print(f"⚠️ Ошибка анализа раннего бронирования: {_e_eb}")
            eb_analysis_res = None
    early_booking_section_html, eb_traj_json, eb_surv_json = render_early_booking_section_html(eb_analysis_res)

    _price_scope_tip = (
        f"Таблица и алерты — только ≤{ceiling_val:.0f} PLN. "
        f"История и графики — до {history_val:.0f} PLN "
        f"(расширенная история {ceiling_val:.0f}–{history_val:.0f} PLN — на графиках и в выпавших)."
        if ceiling_val is not None and history_val is not None and history_val > ceiling_val
        else (
            f"Учитываются только цены до {ceiling_val:.0f} PLN — по одной самой дешёвой оферте отеля за каждый запуск проверки."
            if ceiling_val is not None
            else "По одной самой дешёвой оферте каждого отеля за каждый запуск проверки."
        )
    )
    avg_deal_score = (
        int(round(sum(v['score'] for v in deal_score_by_hotel.values()) / len(deal_score_by_hotel)))
        if deal_score_by_hotel else 0
    )
    best_deal_score = max((v['score'] for v in deal_score_by_hotel.values()), default=0)
    stats_metrics_row1 = "".join([
        _metric_card(
            f"{total_offers:,}",
            "Проверок цен",
            "Сколько раз мы замерили цены: одна запись = самая дешёвая оферта отеля за один автоматический опрос.",
        ),
        _metric_card(
            str(unique_hotels),
            "Отелей отслеживали",
            "Сколько разных отелей хотя бы раз попадали в этот фильтр (даты, цена, направление).",
        ),
        _metric_card(
            str(current_table_hotels),
            "Сейчас в списке",
            "Сколько отелей видно в таблице и карточках — только последний замер, актуальные предложения.",
        ),
        _metric_card(
            f"{avg_price:.0f} PLN",
            "Средняя цена",
            f"Средняя цена по всей накопленной истории. {_price_scope_tip}",
        ),
        _metric_card(
            f"{history_min_price:.0f} PLN",
            "Самая низкая",
            f"Минимальная цена за всю историю наблюдений. {_price_scope_tip}",
        ),
        _metric_card(
            f"{history_max_price:.0f} PLN",
            "Самая высокая",
            f"Максимальная цена за всю историю наблюдений. {_price_scope_tip}",
        ),
    ])
    stats_metrics_row2 = "".join([
        _metric_card(
            str(avg_deal_score),
            "Средняя выгодность",
            "Deal Score 0–100: насколько цены выгодны относительно истории каждого отеля. ~50 — обычный уровень, выше — лучше.",
        ),
        _metric_card(
            str(best_deal_score),
            "Лучший шанс",
            "Максимальный Deal Score среди отелей — самая сильная возможность купить выгодно прямо сейчас.",
        ),
        _metric_card(
            str(len(entry_candidates)),
            "Горячие точки",
            "Отели, которые заметно подешевели за ~48 часов и сейчас в нижней четверти своей исторической цены.",
        ),
        _metric_card(
            f"{market_breadth * 100:.0f}%",
            "Подешевело за 2 дня",
            "Доля отелей, у которых цена упала за последние ~48 часов. Высокий процент — рынок в целом дешевеет.",
        ),
    ])

    hotel_meta_by_name = {}
    for _, _h_row in all_hotels.iterrows():
        _hn = str(_h_row.get("hotel_name", ""))
        if _hn and _hn not in hotel_meta_by_name:
            hotel_meta_by_name[_hn] = {
                "offer_url": str(_h_row.get("offer_url") or _h_row.get("url") or ""),
                "chart_href": f"hotel-charts/{_filter_data_id}/{slugify(_hn)}.html",
                "price": float(_h_row.get("price", 0.0) or 0.0),
                "rating": _h_row.get("ta_rating") or _h_row.get("rating"),
            }

    ai_briefing_html = render_ai_market_briefing_html(
        oracle_report,
        filter_title=title,
        hotel_meta_by_name=hotel_meta_by_name,
    )

    # 1. График ТОП-10 дешёвых предложений (всегда виден на главной странице)
    html_template += f"""
        {ai_briefing_html}
        <div class="avg-top10-section" style="margin-top:1.5rem; margin-bottom:1.5rem;">
            <h3>📉 Средняя цена ТОП‑10 дешёвых предложений</h3>
            <div id="avgTop10" style="height:300px;"></div>
        </div>

        <!-- --- Единая сворачиваемая панель расширенной аналитики (полноширинный fold) --- -->
        <details class="dashboard-fold" id="analyticsFold">
            <summary>
                <span>📊 Расширенная аналитика и тренды рынка</span>
                <span class="fold-title-meta">Вылеты · Алерты · Календарь · Тренды</span>
                <span class="fold-chevron">⌄</span>
            </summary>
            <div class="fold-content" style="padding-top: 1rem;">
                {departure_block_html}
                {departure_history_html}
                {alerts_html}
                {early_booking_section_html}
                <details class="dashboard-fold" id="calendarFold">
                    <summary>
                        <span>📅 Ценовой календарь по датам вылета</span>
                        <span class="fold-title-meta">Тепловая карта цен</span>
                        <span class="fold-chevron">⌄</span>
                    </summary>
                    <div class="fold-content">
                        <div class="calendar-section">
                            <h3>📅 Календарь минимальных цен по датам вылета</h3>
                            <p class="chart-section-note">Показывает минимальную цену предложения на каждую дату вылета. Зелёные ячейки соответствуют наиболее дешёвым датам. Нажмите на дату, чтобы отфильтровать отели ниже.</p>
                            <div id="calendarHeatmapWrapper" style="margin-top: 1rem; overflow-x: auto;"></div>
                        </div>
                    </div>
                </details>
                <details class="dashboard-fold" id="offersCountFold">
                    <summary>
                        <span>📈 Количество предложений по дням</span>
                        <span class="fold-title-meta">Доп. аналитика</span>
                        <span class="fold-chevron">⌄</span>
                    </summary>
                    <div class="fold-content">
                        <div class="avg-top10-section offers-count-section">
                            <h3>📈 Количество предложений по дням</h3>
                            <p class="chart-section-note">Одна точка в день — последний скрап за сутки{f" • видимая зона ≤{ceiling_val:.0f} PLN" if ceiling_val is not None else ""}</p>
                            <div id="offersCountChart" style="height:280px;"></div>
                        </div>
                    </div>
                </details>
                {timing_section_html}
                <details class="dashboard-fold" id="statsFold">
                    <summary>
                        <span>Статистика и сигналы</span>
                        <span class="fold-title-meta">Скрыто по умолчанию</span>
                        <span class="fold-chevron">⌄</span>
                    </summary>
                    <div class="fold-content">
                        <div class="metrics metrics-compact" id="statsMetricsRow1">
                            {stats_metrics_row1}
                        </div>
                        <div class="metrics metrics-compact" id="statsMetricsRow2">
                            {stats_metrics_row2}
                        </div>
                        <div id="durationScopedChanges">{changes_html}</div>
                        <div id="durationScopedEntry">{entry_signal_html}</div>
                    </div>
                </details>
            </div>
        </details>
"""

    # Блок выбора вида списка предложений и фильтры (всегда видны)
    top_movers_html = _render_top_movers_html(decreases_48h, increases_48h, slugify, _filter_data_id)

    # Адаптивные диапазоны фильтра по цене на основе фактических цен таблицы
    try:
        _pr = pd.to_numeric(all_hotels['price'], errors='coerce').dropna()
        _pr = _pr[_pr > 0]
    except Exception:
        _pr = pd.Series([], dtype='float64')
    arrival_hub_by_hotel = {}
    arrival_hub_labels = set()
    for _, _hotel_row in all_hotels.iterrows():
        _path = parse_offer_path(str(_hotel_row.get("offer_url") or ""))
        _hub_label = arrival_hub_label(_path.get("country"), _path.get("region"))
        _hotel_key = str(_hotel_row.get("row_id") or _hotel_row.get("hotel_name") or "")
        arrival_hub_by_hotel[_hotel_key] = _hub_label
        if _hub_label and _hub_label != "—":
            arrival_hub_labels.add(_hub_label)
    region_filter_options_html = "".join(
        f'<option value="{html_lib.escape(label)}">{html_lib.escape(label)}</option>'
        for label in sorted(arrival_hub_labels)
    )

    if len(_pr) >= 2:
        import math as _math
        _lo = float(_pr.quantile(0.02))
        _hi = float(_pr.quantile(0.98))
        if _hi - _lo < 500:
            _lo, _hi = float(_pr.min()), float(_pr.max())
        _step_base = 500
        _lo_r = int(_lo // _step_base) * _step_base
        _hi_r = int(_math.ceil(_hi / _step_base)) * _step_base
        if _hi_r <= _lo_r:
            _hi_r = _lo_r + _step_base
        _span = _hi_r - _lo_r
        _step = max(_step_base, int(round((_span / 4.0) / _step_base)) * _step_base)
        _edges = list(range(_lo_r, _hi_r + 1, _step))
        if len(_edges) < 2:
            _edges = [_lo_r, _hi_r]

        def _fmt(v):
            return f"{v:,}".replace(",", " ")

        _opts = ['<option value="">Все цены</option>']
        _opts.append(f'<option value="0-{_edges[1]}">До {_fmt(_edges[1])} PLN</option>')
        for _a, _b in zip(_edges[1:-1], _edges[2:]):
            _opts.append(f'<option value="{_a}-{_b}">{_fmt(_a)}–{_fmt(_b)} PLN</option>')
        _opts.append(f'<option value="{_edges[-1]}+">От {_fmt(_edges[-1])} PLN</option>')
        price_filter_options_html = "\n                    ".join(_opts)
    else:
        price_filter_options_html = '<option value="">Все цены</option>'

    # ── Генерация секции трансграничного арбитража ──────────────────────────
    arb_rows_html = []
    eur_rate_val = arb_engine.eur_rate if 'arb_engine' in locals() else 4.30
    default_friction_val = 250.0

    if arbitrage_matches:
        seen_arb_table_keys = set()
        for m in arbitrage_matches:
            table_row_key = (m.hotel_name_pl.lower().strip(), m.hotel_name_de.lower().strip(), m.airport_de, round(m.price_de_eur, 0))
            if table_row_key in seen_arb_table_keys:
                continue
            seen_arb_table_keys.add(table_row_key)

            hotel_h = html_lib.escape(m.hotel_name_pl)
            hotel_de_h = html_lib.escape(m.hotel_name_de)
            dates_h = html_lib.escape(m.dates_pl or m.dates_de or "—")
            spread_class = "arb-badge-win" if m.spread_pln > 0 else "arb-badge-neutral"
            sign_str = "+" if m.spread_pln > 0 else ""
            pct_str = f" (-{m.savings_pct:.1f}%)" if m.spread_pln > 0 else ""

            pl_url_final = str(m.url_pl or "").strip()
            if not pl_url_final or "/szukaj-wycieczek/" in pl_url_final:
                direct_match = all_hotels[all_hotels['hotel_name'] == m.hotel_name_pl]
                if not direct_match.empty:
                    cand = str(direct_match.iloc[0].get('offer_url') or '').strip()
                    if cand and cand not in ('—', 'None', 'nan') and '/wycieczka/' in cand:
                        pl_url_final = cand
                elif 'df_canonical' in locals() and not df_canonical.empty:
                    dm_can = df_canonical[df_canonical['hotel_name'] == m.hotel_name_pl]
                    if not dm_can.empty:
                        for cand in reversed(list(dm_can.get('offer_url', []))):
                            cand_s = str(cand or '').strip()
                            if cand_s and cand_s not in ('—', 'None', 'nan') and '/wycieczka/' in cand_s:
                                pl_url_final = cand_s
                                break
            if pl_url_final.startswith("/"):
                pl_url_final = f"https://fly.pl{pl_url_final}"

            pl_link = f'<a href="{html_lib.escape(pl_url_final, quote=True)}" target="_blank" class="card-btn primary" style="padding:4px 10px;font-size:0.75rem;">Fly.pl ↗</a>' if pl_url_final else "—"
            de_link = f'<a href="{html_lib.escape(m.url_de, quote=True)}" target="_blank" class="card-btn" style="padding:4px 10px;font-size:0.75rem;background:#10b981;color:#fff;">Check24 ↗</a>' if m.url_de else "—"

            arb_rows_html.append(f"""
                <tr class="arb-row" data-de-eur="{m.price_de_eur}" data-pl-pln="{m.price_pl_pln}" data-rate="{eur_rate_val}">
                    <td>
                        <strong>{hotel_h}</strong>
                        <div style="font-size:0.75rem;color:var(--text-muted);">{hotel_de_h} ({m.tour_operator_de})</div>
                    </td>
                    <td>{dates_h}</td>
                    <td><strong>{m.price_pl_pln:,.0f} PLN</strong> <small style="color:var(--text-muted);">({m.airport_pl})</small></td>
                    <td><strong>{m.price_de_eur:,.0f} €</strong> <small style="color:var(--text-muted);">({m.airport_de})</small></td>
                    <td class="arb-net-de"><strong>{m.net_price_de_pln:,.0f} PLN</strong></td>
                    <td><span class="arb-spread {spread_class}">{sign_str}{m.spread_pln:,.0f} PLN{pct_str}</span></td>
                    <td style="text-align:center;white-space:nowrap;">{pl_link} {de_link}</td>
                </tr>
            """.replace(",", " "))
        arb_tbody = "".join(arb_rows_html)
    else:
        arb_tbody = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-muted);">На текущий момент активных предложений с существенной выгодой в Германии не обнаружено.</td></tr>'

    arb_badge_count_html = f'<span class="arb-count-badge">{len(arb_rows_html)}</span>' if arb_rows_html else ""

    arbitrage_html = f"""
        <div class="hotels-section full-width-arbitrage-section" id="arbitrageSection" style="display:none;margin-top:1rem;">
            <div class="arbitrage-calc-bar">
                <div class="arbitrage-calc-title">
                    <span style="font-size:1.5rem;">🌍</span>
                    <div>
                        <strong style="font-size:1.05rem;">Трансграничный арбитраж: Польша (WAW/KTW) ⇄ Германия (BER/DRS)</strong>
                        <div style="font-size:0.78rem;color:var(--text-muted);font-weight:normal;">Сравнение цен на идентичные отели между польскими и немецкими туроператорами (TUI DE, DERTOUR, Alltours, Schauinsland).</div>
                    </div>
                </div>
                <div class="arbitrage-slider-group">
                    <label for="frictionSlider">Дорога до BER на семью: <strong id="frictionDisplay">{default_friction_val:.0f} PLN</strong></label>
                    <input type="range" id="frictionSlider" min="0" max="1000" step="50" value="{default_friction_val:.0f}" oninput="if(window.updateArbitrageCalculations) updateArbitrageCalculations(this.value)">
                    <span style="color:var(--text-muted);font-size:0.78rem;">Курс NBP: <strong>{eur_rate_val:.2f} zł/€</strong></span>
                </div>
            </div>
            <div class="table-container table-container--hotels" style="margin-top:1rem;">
                <table class="hotels-table arbitrage-table" id="arbitrageTable">
                    <thead>
                        <tr>
                            <th>Отель</th>
                            <th>Даты</th>
                            <th>Польша (WAW/KTW)</th>
                            <th>Германия (BER/DRS)</th>
                            <th>Net цена из BER (с дорогой)</th>
                            <th>Чистая выгода</th>
                            <th style="text-align:center;">Бронирование</th>
                        </tr>
                    </thead>
                    <tbody>
                        {arb_tbody}
                    </tbody>
                </table>
            </div>
        </div>
    """

    html_template += f"""
        <div class="table-toolbar" id="modeSwitchRow">
            <div class="table-toolbar-title">Вид</div>
            <div class="mode-switch table-mode-switch" id="modeSwitch" data-mode="cards">
                <button type="button" class="mode-btn active" data-mode="cards">Карточки</button>
                <button type="button" class="mode-btn" data-mode="table">Таблица</button>
                <button type="button" class="mode-btn" data-mode="arbitrage">🌍 Арбитраж BER {arb_badge_count_html}</button>
            </div>
        </div>

        <!-- Table & Cards Universal Filters -->
        <div class="table-filters" id="globalFilters" style="margin-bottom: 1.25rem;">
            <input type="text" class="filter-input" id="searchInput" placeholder="🔍 Поиск по отелям..." />
            <select class="filter-select" id="priceFilter">
                {price_filter_options_html}
            </select>
            <select class="filter-select" id="forecastFilter">
                <option value="">Все рекомендации</option>
                <option value="buy">🟢 Покупать</option>
                <option value="wait">🟡 Ждать</option>
                <option value="expensive">🔴 Дорого</option>
            </select>
            <select class="filter-select" id="taFilter">
                <option value="">Все рейтинги TripAdvisor</option>
                <option value="4.5">Рейтинг ≥ 4.5</option>
                <option value="4.0">Рейтинг ≥ 4.0</option>
                <option value="3.5">Рейтинг ≥ 3.5</option>
                <option value="none">Без оценки</option>
            </select>
            <select class="filter-select" id="changeFilter">
                <option value="">Все изменения</option>
                <option value="decrease">Снижение цен</option>
                <option value="increase">Рост цен</option>
                <option value="stable">Стабильные</option>
            </select>
            <select class="filter-select" id="regionFilter">
                <option value="">Все регионы</option>
                {region_filter_options_html}
            </select>
            <button class="filter-button" id="watchlistToggle" style="padding: 0.75rem 1rem; background: #cbd5e1; color: #1e293b; border: none; border-radius: var(--radius-md); cursor: pointer; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; transition: all 0.2s ease;">⭐ Избранные</button>
            <button class="filter-button" id="clearFilters" style="padding: 0.75rem 1rem; background: var(--gradient-primary); color: white; border: none; border-radius: var(--radius-md); cursor: pointer; font-weight: 600;">Очистить</button>
        </div>

        {cards_html}

        <div class="hotels-section full-width-table-section" id="tableSection" style="display:none;">
            <div class="table-header-row">
            <h3>🏨 Все отели • клик по отелю откроет график на отдельной странице</h3>
            </div>
            <div class="deal-legend">
                <strong>Как читать Deal Score:</strong>
                <span class="deal-badge-hot">🔥 Hot</span> = очень сильная возможность,
                <span class="deal-badge-good">✅ Good</span> = хороший момент,
                <span class="deal-badge-normal">↔️ Normal</span> = обычный уровень (~50),
                <span class="deal-badge-bad">📈 Bad</span> = подорожало за 48ч и vs средней,
                <span class="deal-badge-warm">⏳ Warm-up</span> = пока мало истории.
                Confidence: Low / Medium / High — степень надежности оценки.
                TripAdvisor слегка сдвигает Deal Score; без отзывов влияние минимально.
            </div>

            <div class="mobile-sort-bar" id="mobileSortBar" aria-label="Сортировка таблицы">
                <span class="mobile-sort-bar-label" id="mobileSortLabel">Сортировать по</span>
                <div class="mobile-sort-controls">
                    <select class="filter-select mobile-sort-select" id="mobileSortSelect" aria-labelledby="mobileSortLabel">
                        <option value="">Выберите поле…</option>
                        <option value="price">Цена</option>
                        <option value="deal">Deal Score</option>
                        <option value="delta48">Δ 48ч</option>
                        <option value="deltaavg">Δ к средней</option>
                        <option value="hotel">Отель</option>
                        <option value="region">Регион</option>
                        <option value="dates">Даты</option>
                        <option value="duration">Длительность</option>
                        <option value="ta">TripAdvisor</option>
                    </select>
                    <button type="button" class="mobile-sort-dir-btn" id="mobileSortDirection" disabled aria-label="Направление сортировки" title="По возрастанию">↑</button>
                </div>
            </div>
            
            <div class="table-scroll-hint">↔ Прокрутите таблицу вбок, чтобы увидеть все колонки</div>
            <div class="table-container table-container--hotels">
            <table class="hotels-table" id="hotelsTable">
                <colgroup>
                    <col class="col-w-hotel">
                    <col class="col-w-price">
                    <col class="col-w-deal">
                    <col class="col-w-forecast">
                    <col class="col-w-ta">
                    <col class="col-w-d48">
                    <col class="col-w-davg">
                    <col class="col-w-region">
                    <col class="col-w-dates">
                    <col class="col-w-dur">
                    <col class="col-w-link">
                </colgroup>
                <thead>
                    <tr>
                        <th class="sortable col-hotel" data-sort="hotel">Отель</th>
                        <th class="sortable col-tight" data-sort="price">Цена <span class="th-tip" data-tip="Стоимость тура за 2 взрослых + 1 ребёнок (PLN). Ниже — лучше.">ℹ</span></th>
                        <th class="sortable col-tight" data-sort="deal">Deal Score <span class="th-tip" data-tip="Оценка выгодности от 0 до 100. Учитывает историческую цену, тренд и рейтинг отеля. 80+ — сигнал к покупке.">ℹ</span></th>
                        <th class="sortable col-tight" data-sort="forecast">Прогноз <span class="th-tip" data-tip="Ожидаемое направление цены на ближайшие дни: рост, снижение или стабильно.">ℹ</span></th>
                        <th class="sortable col-tight th-ta col-hide-sm" data-sort="ta" title="Рейтинг на TripAdvisor">{TRIPADVISOR_HEADER_ICON_HTML}</th>
                        <th class="sortable col-tight th-col-d48" data-sort="delta48" style="text-align:center;">Δ 48ч <span class="th-tip" data-tip="Изменение цены за последние 48 часов. ↑ подорожал, ↓ подешевел, → без изменений.">ℹ</span></th>
                        <th class="sortable col-tight col-hide-sm th-col-davg" data-sort="deltaavg" style="text-align:center;" title="Отклонение от средней, взвешенной по длительности удержания каждой цены">Δ к средней <span class="th-tip" data-tip="Насколько текущая цена отличается от среднеисторической для этого отеля. Минус — дешевле обычного.">ℹ</span></th>
                        <th class="sortable col-tight" data-sort="region">Регион</th>
                        <th class="sortable col-tight col-dates" data-sort="dates">Даты</th>
                        <th class="sortable col-tight col-duration th-col-dur" data-sort="duration" style="text-align:center;">Длит.</th>
                        <th class="col-tight th-col-link" style="text-align:center;">Ссылка</th>
                    </tr>
                </thead>
                <tbody>"""

    # Добавляем строки таблицы
    table_rows_html_parts = []
    for i, (_, hotel) in enumerate(all_hotels.iterrows()):
        hotel_name = hotel['hotel_name']
        row_id = str(hotel.get('row_id') or hotel_name)
        duration_bucket = str(hotel.get('duration_bucket') or '')
        price = hotel['price']
        dates = hotel['dates'] if pd.notna(hotel['dates']) else '20-09-2025 - 04-10-2025'
        duration = hotel['duration'] if pd.notna(hotel['duration']) else '6-15 дней'
        
        # Δ 48ч
        delta_display = "—"
        delta_class = "delta flat"
        delta_info = deltas_by_hotel.get(row_id)
        if delta_info is not None:
            delta_abs, delta_pct = delta_info
            arrow = '↑' if delta_abs > 0 else ('↓' if delta_abs < 0 else '→')
            delta_class = 'delta up' if delta_abs > 0 else ('delta down' if delta_abs < 0 else 'delta flat')
            sign = '+' if delta_abs > 0 else ('' if delta_abs < 0 else '')
            delta_display = f"{arrow} {sign}{delta_pct:.1f}%"

        # Δ к time-weighted средней по полной истории отеля (без потолка показа)
        avg_display = "—"
        avg_info = avg_baseline_delta.get(row_id)
        avg_sort_value = 0
        if avg_info is not None:
            avg_abs, avg_pct = avg_info
            arrow2 = '↑' if avg_abs > 0 else ('↓' if avg_abs < 0 else '→')
            sign2 = '+' if avg_abs > 0 else ('' if avg_abs < 0 else '')
            avg_display = f"{arrow2} {sign2}{avg_pct:.1f}%"
            avg_sort_value = avg_pct

        hotel_slug = slugify(hotel_name)
        chart_href = _hotel_chart_viewer_href(_filter_data_id, hotel_slug)

        # Альтернативные аэропорты (если доступен датасет df_all_airports)
        cheaper_alt_html = ""
        if df_all_airports is not None and not df_all_airports.empty:
            cur_airport = hotel.get('from_airport')
            if not cur_airport or pd.isna(cur_airport) or not str(cur_airport).strip():
                cur_airport = extract_airport_from_url(hotel.get('offer_url') or hotel.get('url', ''))
            alts = find_cheaper_airport_alternatives(
                df_all_airports,
                hotel_name,
                dates,
                price,
                cur_airport,
            )
            if alts:
                best_alt = alts[0]
                alt_url = best_alt.get('url', '')
                alt_airport = html_lib.escape(str(best_alt['airport']))
                alt_price = best_alt['price']
                alt_savings = best_alt['savings']
                alt_savings_pct = best_alt['savings_percent']
                alt_title = html_lib.escape(
                    f"Вылет из {best_alt['airport']}: {alt_price:,.0f} zł (дешевле на {alt_savings:,.0f} zł / {alt_savings_pct:.1f}%)",
                    quote=True,
                )
                if alt_url:
                    cheaper_alt_html = f'<a href="{html_lib.escape(str(alt_url), quote=True)}" target="_blank" class="cheaper-alt-badge" title="{alt_title}">✈️ <span class="alt-label">{alt_airport}: {alt_price:,.0f} zł</span> <span class="alt-savings">(−{alt_savings:,.0f} zł)</span></a>'
                else:
                    cheaper_alt_html = f'<span class="cheaper-alt-badge" title="{alt_title}">✈️ <span class="alt-label">{alt_airport}: {alt_price:,.0f} zł</span> <span class="alt-savings">(−{alt_savings:,.0f} zł)</span></span>'

        # Ссылка на предложение
        offer_url = hotel.get('offer_url', '')
        offer_link_html = ""
        if offer_url and pd.notna(offer_url) and offer_url.strip():
            offer_link_html = f'<a href="{offer_url}" target="_blank" class="col-link-btn" title="Открыть предложение"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>'
        else:
            offer_link_html = "—"
        
        deal_info = deal_score_by_hotel.get(row_id, {'score': 0, 'confidence': 'Low', 'samples': 0})
        deal_score = int(deal_info.get('score', 0))
        confidence_level = deal_info.get('confidence', 'Low')
        d48_tbl = float(delta_info[1]) if delta_info is not None else None
        d_avg_tbl = float(avg_info[1]) if avg_info is not None else None
        comeback_drop_tbl = deal_info.get('comeback_drop_pct')
        _, _, deal_badge = classify_deal_badge(
            deal_score, confidence_level, d48_tbl, d_avg_tbl, comeback_drop_tbl
        )
        confidence_short = (
            "Low" if confidence_level == "Low"
            else ("Med" if confidence_level == "Medium" else "High")
        )
        deal_title = html_lib.escape(f"{deal_score} {deal_badge} · {confidence_level}")
        duration_display = _table_duration_compact(duration)
        duration_title = html_lib.escape(str(duration))
        comeback = comeback_from_premium(price, premium_history_by_hotel.get(row_id), ceiling_val)
        if comeback:
            peak = float(comeback["peak_price"])
            drop = float(comeback["drop_from_peak_pct"])
            comeback_title = html_lib.escape(
                f"Было до {peak:.0f} PLN (−{drop:.0f}%)", quote=True
            )
            comeback_cell = (
                f'<span class="comeback-badge" title="{comeback_title}">'
                f"↩ −{drop:.0f}%</span>"
            )
        else:
            comeback_cell = ""
        arrival_hub = arrival_hub_by_hotel.get(row_id, "—")
        hotel_name_html = html_lib.escape(str(hotel_name))
        hotel_name_attr = html_lib.escape(str(hotel_name), quote=True)
        arrival_hub_html = html_lib.escape(str(arrival_hub))
        duration_bucket_attr = html_lib.escape(duration_bucket, quote=True)
        ta_rating_html = _render_ta_rating_html(
            hotel.get('ta_rating', ''),
            hotel.get('ta_review_count', ''),
        )
        ta_sort_val = _parse_ta_rating_value(hotel.get('ta_rating', ''))
        ta_data_attr = f"{ta_sort_val:.2f}" if ta_sort_val is not None else "-1"
        
        forecast = determine_price_forecast(
            deal_score, confidence_level, d_avg_tbl, d48_tbl, comeback_drop_tbl,
        )
        hopper_badge_tbl = str(hotel.get('hopper_badge') or '')
        hopper_verdict_tbl = str(hotel.get('hopper_verdict') or '')
        hopper_reasoning_tbl = str(hotel.get('hopper_reasoning') or '')
        if deal_score >= 70 and hopper_verdict_tbl == "OVERPRICED":
            hopper_verdict_tbl = "BUY_NOW"
            hopper_badge_tbl = "🟢 ПОКУПАТЬ"
            hopper_reasoning_tbl = f"Отличный момент для покупки: Deal Score {deal_score}, цена на минимуме истории ({int(price)} PLN)."

        tbl_dupe_html = ""
        tbl_smart_badges = []
        if oracle_report and "hotel_dossiers" in oracle_report:
            h_d_tbl = oracle_report["hotel_dossiers"].get(hotel_name)
            if h_d_tbl:
                hopper_badge_tbl = h_d_tbl.get("badge_text", hopper_badge_tbl)
                v_raw_tbl = h_d_tbl.get("verdict", "")
                if v_raw_tbl in ("BUY_NOW", "GOOD_PRICE"):
                    hopper_verdict_tbl = "BUY_NOW"
                elif v_raw_tbl == "WAIT":
                    hopper_verdict_tbl = "WAIT"
                elif v_raw_tbl == "OVERPRICED":
                    hopper_verdict_tbl = "OVERPRICED"
                hopper_reasoning_tbl = f"{h_d_tbl.get('rationale', '')} • Места: {h_d_tbl.get('risk_assessment', '')} • Совет: {h_d_tbl.get('action_advice', '')}"

                # 1. Flash drop badge in table
                if h_d_tbl.get("flash_drop_badge"):
                    fd_tip = html_lib.escape(str(h_d_tbl.get("flash_drop_tip", "")), quote=True)
                    tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-flash" title="{fd_tip}">⚡ Сброс</span>')

                # 2. Gem badge in table
                if h_d_tbl.get("gem_badge"):
                    g_tip = html_lib.escape(str(h_d_tbl.get("gem_tip", "")), quote=True)
                    tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-gem" title="{g_tip}">💎 Жемчужина</span>')

                # 3. Booking window badge in table
                if h_d_tbl.get("booking_window_badge") and h_d_tbl.get("booking_window_class") == "in_window":
                    bw_tip = html_lib.escape(str(h_d_tbl.get("booking_window_tip", "")), quote=True)
                    tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-bw" title="{bw_tip}">🎯 Окно покупки</span>')

                # 4. Fair price badge in table
                if h_d_tbl.get("fair_price_badge"):
                    fp_cls = h_d_tbl.get("fair_price_class", "bargain")
                    fp_tip = html_lib.escape(str(h_d_tbl.get("fair_price_tip", "")), quote=True)
                    fp_text = h_d_tbl.get("fair_price_badge", "")
                    tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-fp {fp_cls}" title="{fp_tip}">{html_lib.escape(fp_text)}</span>')

                # 5. Dupe line in table under hotel name
                dupe = h_d_tbl.get("dupe_suggestion")
                if dupe and isinstance(dupe, dict):
                    dupe_name = html_lib.escape(str(dupe.get("hotel_name", "")))
                    dupe_url = dupe.get("offer_url") or dupe.get("url") or "#"
                    dupe_savings = dupe.get("savings") or dupe.get("savings_pln") or 0
                    tbl_smart_badges.append(
                        f'<a href="{html_lib.escape(str(dupe_url), quote=True)}" target="_blank" class="tbl-dupe-badge" title="AI Двойник: отель сравнимого класса заметно дешевле">'
                        f'💡 <span class="tbl-dupe-label">Двойник: {dupe_name}</span> <span class="tbl-dupe-savings">(−{dupe_savings:,.0f} zł)</span></a>'
                    )

        # Guardrail: Never show positive purchase/good price badge if price is overpriced or Deal Score is bad
        d_avg_tbl_val = d_avg_tbl if d_avg_tbl is not None else 0.0
        d48_tbl_val = d48_tbl if d48_tbl is not None else 0.0
        is_overpriced_tbl = (deal_score <= 35 or d_avg_tbl_val >= 8.0 or d48_tbl_val >= 12.0)
        has_positive_badge_tbl = (
            hopper_verdict_tbl in ("BUY_NOW", "GOOD_PRICE")
            or any(k in hopper_badge_tbl for k in ("ПОКУПАТЬ", "ХОРОШАЯ", "СБРОС"))
        )
        if is_overpriced_tbl and has_positive_badge_tbl:
            hopper_verdict_tbl = "OVERPRICED"
            hopper_badge_tbl = "🔴 ДОРОГО"
            hopper_reasoning_tbl = f"Цена завышена: {d_avg_tbl_val:+.1f}% к своей средней (Deal Score {deal_score}). Лучше подождать снижения."

        # Positive guardrail: Eliminate contradictory 'WAIT' recommendation on high Deal Score, gems or underpriced hotels
        is_gem_tbl = bool(h_d_tbl.get("gem_badge")) if (oracle_report and h_d_tbl) else False
        is_underpriced_tbl = (h_d_tbl.get("fair_price_class") == "fair-underpriced") if (oracle_report and h_d_tbl) else False
        if not is_overpriced_tbl and (deal_score >= 75 or is_gem_tbl or is_underpriced_tbl):
            if hopper_verdict_tbl == "WAIT" or "ПОДОЖДАТЬ" in hopper_badge_tbl:
                if deal_score >= 85:
                    hopper_verdict_tbl = "BUY_NOW"
                    hopper_badge_tbl = "🟢 ПОКУПАТЬ"
                    hopper_reasoning_tbl = f"Топ-предложение (Deal Score {deal_score}/100): исключительно высокое соотношение цены и качества. Ждать снижения рискованно."
                else:
                    hopper_verdict_tbl = "GOOD_PRICE"
                    hopper_badge_tbl = "🟢 ВЫГОДНАЯ ЦЕНА"
                    hopper_reasoning_tbl = f"Выгодная сделка (Deal Score {deal_score}/100): отличное соотношение цены и уровня отеля."

        # 6. Hotel Reputation Knowledge Base Badges
        if reputation_kb_data and hotel_name in reputation_kb_data:
            rep_entry = reputation_kb_data[hotel_name]
            fam = rep_entry.get("family_and_kids", {})
            wint = rep_entry.get("winter_suitability", {})
            strend = rep_entry.get("season_trend", {})

            # Kids badge
            if fam.get("suitable_for_children") and float(fam.get("score", 0) or 0) >= 7.5:
                f_tip = html_lib.escape(f"Для детей ({fam.get('score', '')}/10): {fam.get('beach_entry', '')} • {fam.get('kids_facilities', '')}", quote=True)
                tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-kids" title="{f_tip}">👶 Дети {fam.get("score", "")}</span>')

            # Winter heated pool / wind shelter badge
            if wint.get("heated_pools"):
                h_tip = html_lib.escape(f"Зимний отдых: подогреваемый бассейн • {wint.get('wind_shelter', '')}", quote=True)
                tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-heat" title="{h_tip}">🔥 Теплый бассейн</span>')
            elif "защищена" in str(wint.get("wind_shelter", "")).lower():
                w_tip = html_lib.escape(f"Бухта {wint.get('bay', '')}: {wint.get('wind_shelter', '')}", quote=True)
                tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-shelter" title="{w_tip}">🛡️ Без ветра</span>')

            # Season trend badge
            if strend.get("trend") == "BETTER":
                t_tip = html_lib.escape(f"Стал лучше: {strend.get('summary', '')}", quote=True)
                tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-better" title="{t_tip}">📈 Стал лучше</span>')
            elif strend.get("trend") == "WORSE":
                t_tip = html_lib.escape(f"Стал хуже: {strend.get('summary', '')}", quote=True)
                tbl_smart_badges.append(f'<span class="tbl-badge tbl-badge-worse" title="{t_tip}">📉 Стал хуже</span>')

        tbl_smart_badges_html = f'<div class="tbl-smart-badges-wrap">{"".join(tbl_smart_badges)}</div>' if tbl_smart_badges else ""

        if hopper_badge_tbl and "НЕТ ДАННЫХ" not in hopper_badge_tbl:
            hopper_cls = "buy-now" if hopper_verdict_tbl == "BUY_NOW" else ("wait" if hopper_verdict_tbl == "WAIT" else ("overpriced" if hopper_verdict_tbl == "OVERPRICED" else "neutral"))
            forecast_cell_html = f'<span class="hopper-pill {hopper_cls}" data-tip="{html_lib.escape(hopper_reasoning_tbl, quote=True)}" title="{html_lib.escape(hopper_reasoning_tbl, quote=True)}">{hopper_badge_tbl}</span>'
            forecast_sort_val = hopper_verdict_tbl
        else:
            forecast_cell_html = f'<span class="forecast-pill {forecast["class"]}">{forecast["icon"]} {forecast["text"]}</span>'
            forecast_sort_val = forecast['text']
        departure_date_attr = html_lib.escape(str(hotel.get('departure_date') or ''), quote=True)
        departure_key_attr = html_lib.escape(str(hotel.get('departure_key') or ''), quote=True)

        # Color-coded класс строки
        _d48 = float(delta_info[1]) if delta_info is not None else 0.0
        if _d48 > 8.0:
            row_color_class = ' row--rising'
        elif deal_score >= 80 and confidence_level != 'Low' and _d48 <= 0:
            row_color_class = ' row--at-min'
        else:
            row_color_class = ''

        table_rows_html_parts.append(f"""
                    <tr class="hotel-row {'row-odd' if i % 2 == 0 else 'row-even'}{row_color_class}" data-region="{arrival_hub_html}" data-ta-rating="{ta_data_attr}" data-duration-bucket="{duration_bucket_attr}" data-departure-date="{departure_date_attr}" data-departure-key="{departure_key_attr}" data-hotel-slug="{slugify(hotel_name)}" data-hotel-name="{hotel_name_attr}" title="Нажмите на строку отеля, чтобы открыть Паспорт и график цен">
                        <td class="hotel-name col-hotel" data-label="Отель"><button class="watchlist-star-btn" data-hotel-name="{hotel_name_attr}" title="Добавить в избранное">☆</button><a class="open-chart-link hotel-hover-link" href="{chart_href}" data-hotel-slug="{slugify(hotel_name)}" data-hotel-name="{hotel_name_attr}">{hotel_name_html}</a>{tbl_smart_badges_html}</td>
                        <td class="price col-tight" data-label="Цена" data-sort-value="{price}"><div class="price-cell-box"><div class="price-main-row"><span class="price-main">{price:.0f} PLN</span>{comeback_cell}</div>{cheaper_alt_html}</div></td>
                        <td class="col-tight col-w-deal-td" data-label="Deal" data-sort-value="{deal_score}" title="{deal_title}"><span class="deal-cell-inline">{deal_score} <span style="opacity:.85;">{deal_badge}</span> <span class="deal-conf-short">{confidence_short}</span></span></td>
                        <td class="col-tight col-w-forecast-td" data-label="Прогноз" data-sort-value="{forecast_sort_val}">{forecast_cell_html}</td>
                        <td class="col-tight col-w-ta-td col-hide-sm" data-label="TripAdvisor">{ta_rating_html}</td>
                        <td class="col-tight col-w-d48-td" data-label="Δ 48ч" data-sort-value="{delta_info[1] if delta_info else 0}"><span class="{delta_class}">{delta_display}</span></td>
                        <td class="col-tight col-w-davg-td col-hide-sm" data-label="Δ к средней" data-sort-value="{avg_sort_value}">{avg_display}</td>
                        <td class="arrival-hub col-tight" data-label="Регион" data-sort-value="{arrival_hub_html}">{arrival_hub_html}</td>
                        <td class="col-tight col-dates" data-label="Даты" data-sort-value="{dates}">{dates}</td>
                        <td class="col-tight col-w-dur-td col-duration" data-label="Длительность" data-sort-value="{duration}" title="{duration_title}">{duration_display}</td>
                        <td class="offer-link-cell col-tight" data-label="Ссылка">{offer_link_html}</td>
                    </tr>""")

    table_rows_html = "".join(table_rows_html_parts)
    html_template += table_rows_html

    if use_trip_buckets:
        from duration_view_bundle import (
            build_duration_view_bundle,
            duration_views_json,
        )

        duration_views_payload = {}
        for bucket in trip_buckets:
            bucket_id = str(bucket['id'])
            df_bucket = df_all_durations[
                df_all_durations['duration_bucket'].astype(str) == bucket_id
            ].copy()
            print(f"📏 Сбор представления: {bucket.get('label', bucket_id)}")
            bundle = build_duration_view_bundle(
                df_bucket,
                group_cols=['hotel_name'],
                use_trip_buckets=False,
                ceiling_val=ceiling_val,
                history_val=history_val,
                data_file=data_file,
                config_file=config_file,
                filter_data_id=_filter_data_id,
                price_scope_tip=_price_scope_tip,
                skip_ta_backfill=True,
                alerts=alerts,
                hotel_meta_by_name=hotel_meta_by_name,
                alert_threshold_percent=ALERT_THRESHOLD_PERCENT,
                parse_iso_fn=parse_iso,
                duration_bucket=bucket_id,
            )
            bundle['label'] = str(bucket.get('label') or bucket_id)
            duration_views_payload[bucket_id] = bundle

        duration_views_json_embed = (
            '<script type="application/json" id="durationViewsData">'
            + duration_views_json(duration_views_payload)
            + '</script>'
        )
        print(f"📏 Виртуальные фильтры: {len(duration_views_payload)}")

    # --- HTML секции "Выпавшие отели" ---
    def _fmt_dt(ts):
        try:
            return pd.to_datetime(ts).strftime('%d.%m.%Y %H:%M')
        except Exception:
            return '—'

    def _fmt_duration(hours):
        try:
            h = float(hours)
        except Exception:
            return '—'
        if h < 1:
            return '<1ч'
        if h < 48:
            return f'{int(round(h))}ч'
        return f'{h / 24:.1f}д'

    _reason_class = {
        'sold': 'vanished-reason-sold',
        'up': 'vanished-reason-up',
        'flat': 'vanished-reason-flat',
        'above_ceiling': 'vanished-reason-up',
    }
    vanished_rows_html = ""
    for ev in disappeared_events:
        ev_name = ev['hotel_name']
        ev_slug = slugify(ev_name)
        ev_chart_href = _hotel_chart_viewer_href(_filter_data_id, ev_slug)
        notable_badge = '<span class="vanished-badge">🔥 заметный дил</span>' if ev['notable'] else ''
        # Δ к своей средней (или к последней цене в фильтре, если отель сейчас дороже потолка)
        raw_price = ev.get('current_raw_price')
        if raw_price is not None and abs(float(raw_price) - ev['last_price']) > 1:
            raw_vs_filter = (float(raw_price) - ev['last_price']) / ev['last_price'] * 100.0 if ev['last_price'] else 0.0
            arrow = '↑' if raw_vs_filter > 0 else ('↓' if raw_vs_filter < 0 else '→')
            delta_cls = 'delta up' if raw_vs_filter > 0 else ('delta down' if raw_vs_filter < 0 else 'delta flat')
            avg_cell = f'<span class="{delta_cls}">{arrow} {raw_vs_filter:+.1f}%</span>'
            avg_cell += '<br><span style="opacity:.6;font-size:.78em;">vs последняя в фильтре</span>'
        elif ev['baseline_pct'] is not None:
            bp = ev['baseline_pct']
            arrow = '↓' if bp < 0 else ('↑' if bp > 0 else '→')
            delta_cls = 'delta down' if bp < 0 else ('delta up' if bp > 0 else 'delta flat')
            avg_cell = f'<span class="{delta_cls}">{arrow} {bp:+.1f}%</span>'
        else:
            avg_cell = '<span class="delta flat">—</span>'
        min_note = ''
        if ev['min_below_pct'] < -0.5:
            min_note = f'<br><span style="opacity:.6;font-size:.78em;">мин в фильтре: {ev["min_price"]:.0f} ({ev["min_below_pct"]:+.0f}%)</span>'
        if raw_price is not None and abs(float(raw_price) - ev['last_price']) > 1:
            raw_pct = (float(raw_price) - ev['last_price']) / ev['last_price'] * 100.0 if ev['last_price'] else 0.0
            raw_cls = 'up' if raw_pct > 0 else 'drop'
            price_cell = (
                f'<span style="opacity:.75">{ev["last_price"]:.0f}</span>'
                f' → <strong class="{raw_cls}">{float(raw_price):.0f}</strong> PLN'
                f'<br><span style="opacity:.6;font-size:.78em;">сейчас в выдаче ({raw_pct:+.0f}%)</span>'
                f'{min_note}'
            )
        else:
            price_cell = f'{ev["last_price"]:.0f} PLN{min_note}'
        airport_disp = html_lib.escape(str(ev['airport']).replace('%20', ' ')) if ev['airport'] else ''
        airport_html = f' <span style="opacity:.6;font-size:.78em;">{airport_disp}</span>' if airport_disp else ''
        first_seen_str = _fmt_dt(ev["first_seen"])
        last_seen_str = _fmt_dt(ev["last_seen"])
        visible_str = _fmt_duration(ev["visible_hours"])
        hotel_name_esc = html_lib.escape(str(ev_name))
        confidence_esc = html_lib.escape(str(ev['confidence']))
        reason_esc = html_lib.escape(str(ev['reason_text']))
        reason_cls = _reason_class.get(ev['reason_code'], 'vanished-reason-flat')
        ev_offer_url = str(ev.get('offer_url') or '').strip()
        if ev_offer_url:
            offer_url_esc = html_lib.escape(ev_offer_url, quote=True)
            offer_cell = f'<a href="{offer_url_esc}" target="_blank" rel="noopener" class="offer-link" title="Открыть оффер (может быть уже недоступен)">🔗</a>'
        else:
            offer_cell = '—'
        full_obs = ev.get('observations_full', ev['observations'])
        full_obs_suffix = f' · {full_obs} всего' if full_obs > ev['observations'] else ''
        seen_cell = (
            f'{first_seen_str} → {last_seen_str}'
            f'<br><span style="opacity:.6;font-size:.78em;">в фильтре ~{visible_str} · {ev["observations"]} набл.{full_obs_suffix}</span>'
        )
        vanished_rows_html += f"""
                    <tr>
                        <td class="hotel-name"><a class="open-chart-link" href="{ev_chart_href}" target="_blank">{hotel_name_esc}</a>{notable_badge}{airport_html}</td>
                        <td>{seen_cell}</td>
                        <td class="price">{price_cell}</td>
                        <td>{avg_cell}</td>
                        <td>{ev['deal_score']} <span style="opacity:.65;font-size:.78em;">{confidence_esc}</span></td>
                        <td><span class="vanished-reason {reason_cls}">{reason_esc}</span></td>
                        <td class="offer-link-cell">{offer_cell}</td>
                    </tr>"""

    if disappeared_events:
        if vanished_notable_count:
            vanished_summary_meta = f"заметных: {vanished_notable_count}"
        else:
            vanished_summary_meta = ""
        vanished_hint_text = (
            f"Все отели, которые хотя бы раз были в зоне отслеживания (≤{ceiling_val:.0f} PLN), но сейчас не в основной таблице. "
            f"Графики показывают полную историю до {history_val:.0f} PLN; если отель всё ещё в выдаче выше потолка — показываем актуальную цену."
            if ceiling_val is not None and history_val is not None
            else "Все отели, которые хотя бы раз были в выдаче, но сейчас не в основной таблице."
        )
        vanished_inner_html = f"""
                <p class="vanished-hint">{vanished_hint_text}</p>
                <div class="table-container">
                    <table class="hotels-table vanished-table">
                        <thead>
                            <tr>
                                <th>Отель</th>
                                <th>Был виден</th>
                                <th>Цена в фильтре → сейчас</th>
                                <th>Δ к своей средней</th>
                                <th>Deal Score</th>
                                <th>Что произошло</th>
                                <th>Оффер</th>
                            </tr>
                        </thead>
                        <tbody>{vanished_rows_html}
                        </tbody>
                    </table>
                </div>
"""
    else:
        vanished_empty_text = (
            f"Пока нет отелей вне основной таблицы: все, кто когда-либо был в зоне ≤{ceiling_val:.0f} PLN, сейчас в ней же."
            if ceiling_val is not None
            else "Пока нет отелей вне основной таблицы."
        )
        vanished_inner_html = f"""
                <p class="vanished-hint">{vanished_empty_text}</p>
"""
        vanished_summary_meta = "пусто"

    vanished_meta_html = f'<span class="fold-title-meta">{vanished_summary_meta}</span>'
    vanished_section_html = f"""
        <details class="dashboard-fold" id="vanishedFold">
            <summary>
                <span>Выпавшие отели — были в зоне, сейчас не в таблице ({len(disappeared_events)})</span>
                {vanished_meta_html}
                <span class="fold-chevron">⌄</span>
            </summary>
            <div class="fold-content">
{vanished_inner_html}
            </div>
        </details>
"""

    # Завершаем таблицу и добавляем секцию для графика
    html_template += f"""
                </tbody>
            </table>
            </div>
            
            <!-- Pagination -->
            <div class="pagination" id="pagination">
                <button id="prevPage" disabled>← Предыдущая</button>
                <div class="pagination-info">
                    Показано <span id="showingFrom">1</span>-<span id="showingTo">50</span> из <span id="totalItems">{len(all_hotels)}</span> отелей
                </div>
                <button id="nextPage">Следующая →</button>
            </div>
        </div>
{arbitrage_html}
{alerts_html}
{vanished_section_html}
{duration_views_json_embed}
        <div class="footer">
            <p>🤖 Автоматически обновляется каждый час • Powered by GitHub Actions</p>
        </div>
    </div>
    <div id="hoverThumb" class="hover-thumb"><img id="hoverImg" src="" alt="preview"/></div>
    <div id="departureOffersModal" class="departure-modal" aria-hidden="true">
        <div class="departure-modal-backdrop" id="departureModalBackdrop"></div>
        <div class="departure-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="departureModalTitle">
            <div class="departure-modal-header">
                <h3 id="departureModalTitle">Отели по вылету</h3>
                <button type="button" class="departure-modal-close" id="departureModalClose" aria-label="Закрыть">×</button>
            </div>
            <p class="departure-modal-meta" id="departureModalMeta"></p>
            <p class="departure-modal-chart-title" id="departureModalChartTitle" style="display:none;">Динамика цен по вылету (D-14 → день вылета)</p>
            <div id="departureModalChart" class="departure-modal-chart" aria-hidden="true"></div>
            <div class="departure-modal-body" id="departureModalBody"></div>
        </div>
    </div>
    {passport_drawer_markup}
"""

    # Вставляем данные и логику паспорта отеля
    html_template += """
    <script>
      window.HOTEL_PASSPORT_DATA = """ + json.dumps(hotel_passport_data, ensure_ascii=False) + """;
    </script>
    <script>
    """ + passport_js + """
    </script>
"""

    # Вставляем скрипт превью слиянием JSON вне f-строки, чтобы избежать конфликтов с фигурными скобками
    html_template += """
    <script>
      (function(){
        const X = """ + json.dumps(top10_x_values, ensure_ascii=False) + """;
        const Y = """ + json.dumps(top10_y_values, ensure_ascii=False) + """;
        const minY = """ + json.dumps(top10_min_values, ensure_ascii=False) + """;
        const maxY = """ + json.dumps(top10_max_values, ensure_ascii=False) + """;
        const detailedData = """ + json.dumps(top10_detailed_data, ensure_ascii=False, default=str) + """;
        
        if (Array.isArray(X) && Array.isArray(Y) && X.length > 0 && Y.length > 0 && window.Plotly) {
          // Подготавливаем данные для hover
          const hoverData = detailedData.map(data => data.hover_data || {});
          
          // Создаем простой текст для hover с правильными переносами строк
          const hoverTexts = detailedData.map((data, index) => {
            const hover = data.hover_data || {};
            let text = hover.title || '';
            
            // Добавляем среднюю цену и диапазон
            if (hover.avg_price) {
              const minVal = Math.round(data.min_price || hover.avg_price);
              const maxVal = Math.round(data.max_price || hover.avg_price);
              const spread = maxVal - minVal;
              text += '<br><br><b>Средняя цена ТОП-10:</b> ' + Math.round(hover.avg_price) + ' PLN';
              text += `<br><b>Диапазон (№1 — №10):</b> ${minVal} — ${maxVal} PLN <span style="opacity:.7;font-size:.88em;">(разброс ${spread} PLN)</span>`;
            }
            
            if (hover.avg_change) {
              text += '<br><br><b>Изменение средней цены:</b><br>';
              text += `${hover.avg_change.arrow} ${hover.avg_change.sign}${Math.round(hover.avg_change.change)} PLN (${hover.avg_change.sign}${hover.avg_change.change_percent.toFixed(1)}%)`;
            }
            
            if (hover.price_changes && hover.price_changes.length > 0) {
              text += '<br><br><b>🏨 Изменения цен:</b><br>';
              hover.price_changes.forEach(change => {
                text += `• ${change.name}<br>  ${Math.round(change.old_price)} → ${Math.round(change.new_price)} PLN<br>  ${change.arrow} ${change.sign}${Math.round(change.change)} PLN (${change.sign}${change.change_percent.toFixed(1)}%)<br>`;
              });
            }
            
            if (hover.new_hotels && hover.new_hotels.length > 0) {
              text += '<br><b>🆕 Новые в ТОП-10:</b><br>';
              hover.new_hotels.forEach(hotel => {
                text += `• ${hotel.name}<br>  Цена: ${Math.round(hotel.price)} PLN (позиция ${hotel.position})<br>`;
              });
            }
            
            if (hover.removed_hotels && hover.removed_hotels.length > 0) {
              text += '<br><b>❌ Покинули ТОП-10:</b><br>';
              hover.removed_hotels.forEach(hotel => {
                text += `• ${hotel.name}<br>  Цена: ${Math.round(hotel.price)} PLN (была позиция ${hotel.position})<br>`;
              });
            }
            
            if (hover.no_changes) {
              text += '<br><br><i>Нет изменений в этом ране</i>';
            }
            
            return text;
          });

          const traceMin = {
            x: X,
            y: minY.length === X.length ? minY : Y,
            type: 'scatter',
            mode: 'lines',
            line: { width: 0 },
            showlegend: false,
            hoverinfo: 'skip'
          };

          const traceMax = {
            x: X,
            y: maxY.length === X.length ? maxY : Y,
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(162, 59, 114, 0.14)',
            line: { width: 0 },
            name: 'Диапазон ТОП-10 (мин - макс)',
            hoverinfo: 'skip'
          };
          
          const traceAvg = { 
            x: X, 
            y: Y, 
            type: 'scatter', 
            mode: 'lines+markers', 
            line: { color: '#A23B72', width: 3 }, 
            marker: { size: 7, color: '#A23B72' },
            name: 'Средняя цена ТОП-10',
            text: hoverTexts,
            hovertemplate: '%{text}<extra></extra>',
            hoverinfo: 'text',
            hoverlabel: {
              bgcolor: 'rgba(248, 249, 250, 0.98)',
              bordercolor: '#A23B72',
              font: {
                family: 'Inter, sans-serif',
                size: 12,
                color: '#333'
              },
              align: 'left',
              namelength: -1
            }
          };
          
          const layout = { 
            margin: { t: 10, r: 10, b: 40, l: 50 }, 
            xaxis: { title: 'Время', type: 'date' }, 
            yaxis: { title: 'Цена (PLN)' },
            hovermode: 'closest',
            showlegend: false
          };
          
          Plotly.newPlot('avgTop10', [traceMin, traceMax, traceAvg], layout, { responsive: true, displayModeBar: false });
        }
      })();
      
      // График индекса ценовой динамики
      (function(){
        const trendIndexX = """ + json.dumps(trend_index_x_values, ensure_ascii=False) + """;
        const trendIndexY = """ + json.dumps(trend_index_y_values, ensure_ascii=False) + """;
        const trendIndexDetailedData = """ + json.dumps(trend_index_detailed_data, ensure_ascii=False, default=str) + """;
        
        if (document.getElementById('trendIndexChart') && Array.isArray(trendIndexX) && Array.isArray(trendIndexY) && trendIndexX.length > 0 && trendIndexY.length > 0 && window.Plotly) {
          // Создаем hover текст для каждой точки
          const trendIndexHoverTexts = trendIndexDetailedData.map((data, index) => {
            let text = `<b>📊 Индекс ценовой динамики</b><br>`;
            text += `<b>Время:</b> ${data.run_time}<br>`;
            text += `<b>Среднее изменение:</b> ${data.avg_change_pct.toFixed(2)}%<br>`;
            text += `<b>Отелей с изменениями:</b> ${data.hotels_with_changes}/${data.total_hotels}<br><br>`;
            
            if (data.price_changes && data.price_changes.length > 0) {
              text += `<b>Изменения по отелям:</b><br>`;
              data.price_changes.slice(0, 10).forEach(change => {
                const arrow = change.change_pct > 0 ? '↗️' : change.change_pct < 0 ? '↘️' : '➡️';
                const color = change.change_pct > 0 ? '#ef4444' : change.change_pct < 0 ? '#22c55e' : '#6b7280';
                text += `${arrow} <span style="color: ${color}">${change.hotel}: ${change.change_pct.toFixed(1)}%</span><br>`;
              });
              if (data.price_changes.length > 10) {
                text += `... и еще ${data.price_changes.length - 10} отелей`;
              }
            }
            
            return text;
          });
          
          const trendIndexTrace = {
            x: trendIndexX,
            y: trendIndexY,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Индекс ценовой динамики',
            line: { color: '#7C3AED', width: 3 },
            marker: { size: 6, color: '#7C3AED' },
            text: trendIndexHoverTexts,
            hovertemplate: '%{text}<extra></extra>',
            hoverinfo: 'text',
            hoverlabel: {
              bgcolor: 'rgba(248, 249, 250, 0.98)',
              bordercolor: '#7C3AED',
              font: { size: 12, color: '#333' },
              align: 'left',
              namelength: -1
            }
          };
          
          const trendIndexLayout = {
            title: {
              text: 'Индекс ценовой динамики (%)',
              font: { size: 16, color: '#374151' }
            },
            xaxis: {
              title: 'Время',
              type: 'date',
              gridcolor: '#e5e7eb',
              showgrid: true
            },
            yaxis: {
              title: 'Изменение цен (%)',
              gridcolor: '#e5e7eb',
              showgrid: true,
              zeroline: true,
              zerolinecolor: '#6b7280',
              zerolinewidth: 2
            },
            plot_bgcolor: 'rgba(0,0,0,0)',
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'Inter, sans-serif' },
            margin: { t: 50, b: 50, l: 60, r: 30 }
          };
          
          Plotly.newPlot('trendIndexChart', [trendIndexTrace], trendIndexLayout, { responsive: true, displayModeBar: false });
        }
      })();

        window.toggleAnalyticsDrawer = function() {
          const content = document.getElementById('analyticsDrawerContent');
          const arrow = document.getElementById('analyticsDrawerArrow');
          if (!content) return;
          if (content.style.display === 'none' || content.classList.contains('collapsed')) {
            content.style.display = 'block';
            content.classList.remove('collapsed');
            if (arrow) arrow.textContent = '▲ Скрыть аналитику';
          } else {
            content.style.display = 'none';
            content.classList.add('collapsed');
            if (arrow) arrow.textContent = '▼ Показать аналитику';
          }
        };

        (function(){
        const offersDates = """ + json.dumps(offers_count_dates, ensure_ascii=False) + """;
        const offersCounts = """ + json.dumps(offers_count_values, ensure_ascii=False) + """;
        const offersMeta = """ + json.dumps(offers_count_meta, ensure_ascii=False, default=str) + """;

        function buildOffersCountHoverTexts(meta) {
          return (meta || []).map((row) => {
            let text = '<b>' + (row.day || '') + '</b><br>';
            text += 'Предложений: <b>' + (row.count || 0) + '</b><br>';
            if (row.run_time) {
              text += 'Скрап: ' + row.run_time;
            }
            return text;
          });
        }

        window.renderOffersCountChart = function(dates, counts, meta) {
          const chartEl = document.getElementById('offersCountChart');
          if (!chartEl || !window.Plotly) return;
          const x = Array.isArray(dates) ? dates : [];
          const y = Array.isArray(counts) ? counts : [];
          if (!x.length || !y.length) {
            try { Plotly.purge(chartEl); } catch (e) {}
            chartEl.innerHTML = '<div style="padding:1rem;color:#64748b;font-size:.9rem;">Пока недостаточно истории по дням</div>';
            return;
          }
          try { Plotly.purge(chartEl); } catch (e) {}
          chartEl.innerHTML = '';

          const yNums = y.filter(function(v) { return v != null && !isNaN(v) && v > 0; });
          let yMin = yNums.length ? Math.min.apply(null, yNums) : 0;
          let yMax = yNums.length ? Math.max.apply(null, yNums) : 100;
          let ySpan = yMax - yMin;
          let yPad = Math.max(ySpan * 0.35, Math.ceil(yMax * 0.05), 3);
          const yRange = [Math.max(0, Math.floor(yMin - yPad)), Math.ceil(yMax + yPad)];

          const hoverTexts = buildOffersCountHoverTexts(meta);
          const trace = {
            x: x,
            y: y,
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: '#059669', width: 2.5 },
            marker: { size: 7, color: '#059669' },
            text: hoverTexts,
            hovertemplate: '%{text}<extra></extra>',
            hoverinfo: 'text',
          };
          const layout = {
            margin: { t: 15, r: 15, b: 45, l: 52 },
            xaxis: { title: 'День', type: 'date', tickformat: '%d.%m' },
            yaxis: { title: 'Предложений', range: yRange, gridcolor: '#e5e7eb' },
            hovermode: 'closest',
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
          };
          const config = { responsive: true, displayModeBar: false };
          Plotly.newPlot('offersCountChart', [trace], layout, config);
        };

        window.renderOffersCountChart(offersDates, offersCounts, offersMeta);
      })();

      // Секция «Анализ раннего бронирования»
      (function(){
        const ebTrajData = """ + eb_traj_json + """;
        const ebSurvData = """ + eb_surv_json + """;

        window.renderEarlyBookingCharts = function(traj, surv) {
          if (!window.Plotly) return;
          const trajEl = document.getElementById('ebTrajectoryChart');
          const survEl = document.getElementById('ebSurvivalChart');

          if (trajEl && traj && Array.isArray(traj.x) && traj.x.length) {
            try { Plotly.purge(trajEl); } catch (e) {}
            trajEl.innerHTML = '';
            const barColors = traj.y.map(function(v) { return v > 0 ? '#ef4444' : (v < 0 ? '#10b981' : '#64748b'); });
            const trajTrace = {
              x: traj.x,
              y: traj.y,
              type: 'bar',
              marker: { color: barColors },
              text: traj.y.map(function(v) { return (v > 0 ? '+' : '') + v.toFixed(1) + '%'; }),
              textposition: 'auto',
              hovertemplate: '<b>%{x}</b><br>Δ цены к First Minute: %{y:.1f}%<extra></extra>',
            };
            const trajLayout = {
              margin: { t: 20, r: 15, b: 50, l: 48 },
              yaxis: { title: 'Δ цены к FM (%)', zeroline: true, zerolinecolor: '#94a3b8', zerolinewidth: 1.5, gridcolor: '#e2e8f0' },
              xaxis: { title: 'Горизонт до вылета' },
              paper_bgcolor: 'rgba(0,0,0,0)',
              plot_bgcolor: 'rgba(0,0,0,0)',
              font: { family: 'Inter, sans-serif', size: 11 },
            };
            Plotly.newPlot('ebTrajectoryChart', [trajTrace], trajLayout, { responsive: true, displayModeBar: false });
          }

          if (survEl && surv && Array.isArray(surv.x) && surv.x.length) {
            try { Plotly.purge(survEl); } catch (e) {}
            survEl.innerHTML = '';
            const survTrace = {
              x: surv.x,
              y: surv.y,
              type: 'scatter',
              mode: 'lines+markers',
              fill: 'tozeroy',
              fillcolor: 'rgba(59, 130, 246, 0.12)',
              line: { color: '#2563eb', width: 2.5 },
              marker: { size: 6, color: '#1d4ed8' },
              hovertemplate: '<b>%{x} дн. до вылета</b><br>Доступно отелей: %{y:.1f}%<extra></extra>',
            };
            const survLayout = {
              margin: { t: 20, r: 15, b: 50, l: 48 },
              xaxis: { title: 'Дней до вылета (D)', autorange: 'reversed' },
              yaxis: { title: '% доступных отелей', range: [0, 105], gridcolor: '#e2e8f0' },
              paper_bgcolor: 'rgba(0,0,0,0)',
              plot_bgcolor: 'rgba(0,0,0,0)',
              font: { family: 'Inter, sans-serif', size: 11 },
            };
            Plotly.newPlot('ebSurvivalChart', [survTrace], survLayout, { responsive: true, displayModeBar: false });
          }
        };

        window.renderEarlyBookingCharts(ebTrajData, ebSurvData);
      })();

      // Секция «Когда покупать»: статистика снижения цен по времени
      (function(){
        const TIMING = """ + timing_json + """;
        if (!TIMING || !TIMING.available || !window.Plotly) { return; }
        const baseline = (TIMING.baseline_p_drop || 0) * 100;
        const confColor = { reliable: '#10b981', preliminary: '#f59e0b', collecting: '#94a3b8' };
        const baseLayout = {
          plot_bgcolor: 'rgba(0,0,0,0)', paper_bgcolor: 'rgba(0,0,0,0)',
          font: { family: 'Inter, sans-serif', size: 11 },
          margin: { t: 10, r: 12, b: 40, l: 48 }
        };

        function drawProbBar(elId, dim, axisTitle) {
          if (!dim || !document.getElementById(elId)) { return; }
          const b = dim.buckets || [];
          const x = b.map(d => d.label);
          const y = b.map(d => (d.p_drop || 0) * 100);
          // Усы 95% Уилсона
          const errPlus = b.map(d => Math.max(0, (d.wilson_hi - d.p_drop)) * 100);
          const errMinus = b.map(d => Math.max(0, (d.p_drop - d.wilson_lo)) * 100);
          // Значимые бакеты «зажигаются» цветом достоверности, остальные приглушены
          const colors = b.map(d => d.significant ? confColor[d.confidence] : 'rgba(148,163,184,.45)');
          const text = b.map(d => d.n > 0 ? (d.n + ' набл.') : 'нет данных');
          const trace = {
            x: x, y: y, type: 'bar', marker: { color: colors },
            error_y: { type: 'data', symmetric: false, array: errPlus, arrayminus: errMinus, color: 'rgba(71,85,105,.55)', thickness: 1, width: 2 },
            text: text, textposition: 'none',
            hovertemplate: '%{x}<br>Снижение: %{y:.1f}%<br>%{text}<extra></extra>'
          };
          const layout = Object.assign({}, baseLayout, {
            yaxis: { title: 'P(снижение), %', gridcolor: '#e5e7eb' },
            xaxis: { title: axisTitle || '', tickangle: x.length > 8 ? -45 : 0 },
            shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: baseline, y1: baseline, line: { color: '#ef4444', width: 1, dash: 'dot' } }],
            annotations: [{ xref: 'paper', x: 1, y: baseline, xanchor: 'right', yanchor: 'bottom', text: 'средн. ' + baseline.toFixed(1) + '%', showarrow: false, font: { size: 9, color: '#ef4444' } }]
          });
          Plotly.newPlot(elId, [trace], layout, { displayModeBar: false, responsive: true });
        }

        drawProbBar('timingHourChart', TIMING.dimensions.hour, 'Час (Варшава)');
        drawProbBar('timingDowChart', TIMING.dimensions.dow, 'День недели');
        drawProbBar('timingPartChart', TIMING.dimensions.part, 'Часть месяца');
        drawProbBar('timingMonthChart', TIMING.dimensions.month, 'Месяц');

        // Теплокарта: день недели × час
        const hm = TIMING.heatmap;
        if (hm && document.getElementById('timingHeatmap')) {
          const z = (hm.intensity || []).map(row => row.map(v => v === null ? null : v * 100));
          const customN = hm.n || [];
          const heat = {
            z: z, x: hm.hours.map(h => (h < 10 ? '0' + h : '' + h)), y: hm.dow_labels,
            type: 'heatmap', colorscale: 'YlGnBu', reversescale: true,
            customdata: customN,
            hovertemplate: '%{y}, %{x}:00<br>Ожид. снижение: %{z:.2f}%<br>Набл.: %{customdata}<extra></extra>',
            colorbar: { title: '%', thickness: 12 }
          };
          const layout = Object.assign({}, baseLayout, {
            margin: { t: 10, r: 12, b: 40, l: 48 },
            xaxis: { title: 'Час (Варшава)', dtick: 2 }, yaxis: { autorange: 'reversed' }
          });
          Plotly.newPlot('timingHeatmap', [heat], layout, { displayModeBar: false, responsive: true });
        }
      })();

      (function(){
        const map = """ + json.dumps(images_map, ensure_ascii=False) + """;
        try { Object.assign(map, JSON.parse(localStorage.getItem('hotel_images')||'{}')); } catch(e) {}
        const hover = document.getElementById('hoverThumb');
        const img = document.getElementById('hoverImg');
        let activeLink = null;
        function show(e, name){
          const url = map[name];
          if(!url || String(url).indexOf('data:image') === 0){ return; }
          img.src = url;
          hover.style.display = 'block';
          hover.style.left = ((e.pageX||0)+12) + 'px';
          hover.style.top = ((e.pageY||0)+12) + 'px';
        }
        function move(e){
          if(hover.style.display !== 'block'){ return; }
          hover.style.left = ((e.pageX||0)+12) + 'px';
          hover.style.top = ((e.pageY||0)+12) + 'px';
        }
        function hide(){ hover.style.display = 'none'; img.src = ''; activeLink = null; }
        document.addEventListener('mouseover', (e) => {
          const link = e.target.closest('.hotel-hover-link');
          if(!link || link === activeLink){ return; }
          activeLink = link;
          const name = link.getAttribute('data-hotel-name');
          if(name){ show(e, name); }
        });
        document.addEventListener('mouseout', (e) => {
          const link = e.target.closest('.hotel-hover-link');
          if(!link){ return; }
          const to = e.relatedTarget;
          if(to && link.contains(to)){ return; }
          hide();
        });
        document.addEventListener('mousemove', move);
        window._hoverPreview = { show, hide };
      })();
      
      function toggleAlerts() {
        const content = document.getElementById('alertsContent');
        const icon = document.getElementById('alertsExpandIcon');
        if (content.classList.contains('collapsed')) {
          content.classList.remove('collapsed');
          icon.classList.remove('collapsed');
        } else {
          content.classList.add('collapsed');
          icon.classList.add('collapsed');
        }
      }
      
      // Таблица сортировки
      let currentSort = { column: null, direction: 'asc' };
      
      function getColumnIndex(column) {
        const columnMap = { 'hotel': 0, 'price': 1, 'deal': 2, 'forecast': 3, 'ta': 4, 'delta48': 5, 'deltaavg': 6, 'region': 7, 'dates': 8, 'duration': 9, 'offer': 10 };
        return columnMap[column];
      }

      function normalizeSortValue(row, column) {
        const idx = getColumnIndex(column);
        const cell = row.cells[idx];
        const raw = (cell && (cell.dataset.sortValue || cell.textContent) || '').trim();
        if (column === 'forecast') {
          const u = raw.toUpperCase();
          if (u.includes('BUY') || u.includes('ПОКУПАТЬ')) return 3;
          if (u.includes('WAIT') || u.includes('ЖДАТЬ') || u.includes('НАБЛЮДАТЬ')) return 2;
          if (u.includes('OVERPRICED') || u.includes('ДОРОГО')) return 1;
          return 0;
        }
        if (column === 'hotel' || column === 'region') {
          return (row.cells[getColumnIndex(column)].textContent || '').trim().toLowerCase();
        }
        if (column === 'dates') {
          const m = raw.match(/(\d{2})\.(\d{2})\.(\d{4})/);
          return m ? `${m[3]}-${m[2]}-${m[1]}` : raw.toLowerCase();
        }
        if (column === 'duration') {
          const m = raw.match(/(\d+)/);
          return m ? parseFloat(m[1]) : 0;
        }
        if (column === 'ta') {
          const cellRating = cell ? cell.querySelector('.ta-rating') : null;
          const ds = cellRating ? cellRating.getAttribute('data-sort-value') : raw;
          const val = parseFloat(ds);
          return Number.isFinite(val) ? val : -1;
        }
        return parseFloat(raw) || 0;
      }

      function compareHotelRows(a, b) {
        const column = currentSort.column;
        const aVal = normalizeSortValue(a, column);
        const bVal = normalizeSortValue(b, column);
        if (column === 'ta') {
          if (aVal === -1 && bVal === -1) return 0;
          if (aVal === -1) return 1;
          if (bVal === -1) return -1;
          return currentSort.direction === 'asc' ? aVal - bVal : bVal - aVal;
        }
        let cmp;
        if (typeof aVal === 'string' || typeof bVal === 'string') {
          cmp = String(aVal).localeCompare(String(bVal));
        } else {
          cmp = aVal - bVal;
        }
        return currentSort.direction === 'asc' ? cmp : -cmp;
      }
      
      function syncMobileSortBar() {
        const sel = document.getElementById('mobileSortSelect');
        const dirBtn = document.getElementById('mobileSortDirection');
        if (!sel) return;
        sel.value = currentSort.column || '';
        if (dirBtn) {
          const asc = currentSort.direction !== 'desc';
          dirBtn.textContent = asc ? '↑' : '↓';
          dirBtn.title = asc ? 'По возрастанию — нажмите для убывания' : 'По убыванию — нажмите для возрастания';
          dirBtn.setAttribute('aria-label', asc ? 'По возрастанию' : 'По убыванию');
          dirBtn.disabled = !currentSort.column;
        }
      }

      function applyTableSort() {
        if (!currentSort.column) return;
        if (window._hotelTableSortAll) {
          window._hotelTableSortAll();
        } else {
          const table = document.getElementById('hotelsTable');
          if (!table) return;
          const tbody = table.querySelector('tbody');
          if (!tbody) return;
          const rows = Array.from(tbody.querySelectorAll('tr'));
          rows.sort(compareHotelRows);
          rows.forEach(row => tbody.appendChild(row));
        }
        updateSortIndicators();
      }

      function setTableSort(column, direction) {
        if (!column) {
          currentSort.column = null;
          currentSort.direction = 'asc';
          syncMobileSortBar();
          return;
        }
        currentSort.column = column;
        currentSort.direction = direction === 'desc' ? 'desc' : 'asc';
        applyTableSort();
        syncMobileSortBar();
      }
      
      function sortTable(column) {
        if (currentSort.column === column) {
          currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
          currentSort.direction = (column === 'ta' || column === 'deal') ? 'desc' : 'asc';
        }
        currentSort.column = column;
        applyTableSort();
      }
      
      function updateSortIndicators() {
        const headers = document.querySelectorAll('#hotelsTable th.sortable');
        headers.forEach(header => {
          header.classList.remove('sort-asc', 'sort-desc');
          if (header.dataset.sort === currentSort.column) {
            header.classList.add(currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
          }
        });
        syncMobileSortBar();
      }
      
      function bindFoldPersistence(foldId, key, defaultOpen = false) {
        const el = document.getElementById(foldId);
        if (!el) return;
        let isOpen = defaultOpen;
        try {
          const saved = localStorage.getItem(key);
          if (saved === '1') isOpen = true;
          if (saved === '0') isOpen = false;
        } catch (e) {}
        el.open = isOpen;

        function triggerChartResize() {
          [40, 150, 350].forEach(delay => {
            setTimeout(() => {
              window.dispatchEvent(new Event('resize'));
              if (window.Plotly && window.Plotly.Plots) {
                document.querySelectorAll('.js-plotly-plot, #avgTop10, #offersCountChart, #timingHourChart, #timingDowChart, #timingHeatmap, #timingPartChart, #timingMonthChart, #departurePriceChart, #ebTrajectoryChart, #ebSurvivalChart').forEach(p => {
                  try { window.Plotly.Plots.resize(p); } catch (e) {}
                });
              }
              if (typeof window.updateCalendarHeatmap === 'function') {
                window.updateCalendarHeatmap();
              }
            }, delay);
          });
        }

        if (isOpen) triggerChartResize();

        el.addEventListener('toggle', () => {
          try { localStorage.setItem(key, el.open ? '1' : '0'); } catch (e) {}
          if (el.open) {
            triggerChartResize();
          }
        });
      }

      document.addEventListener('toggle', function(event) {
        if (event.target && event.target.tagName === 'DETAILS' && event.target.open) {
          [40, 150, 350].forEach(function(delay) {
            setTimeout(function() {
              window.dispatchEvent(new Event('resize'));
              if (window.Plotly && window.Plotly.Plots) {
                document.querySelectorAll('.js-plotly-plot, #avgTop10, #offersCountChart, #timingHourChart, #timingDowChart, #timingHeatmap, #timingPartChart, #timingMonthChart, #departurePriceChart, #ebTrajectoryChart, #ebSurvivalChart').forEach(function(p) {
                  try { window.Plotly.Plots.resize(p); } catch (e) {}
                });
              }
              if (typeof window.updateCalendarHeatmap === 'function') {
                window.updateCalendarHeatmap();
              }
            }, delay);
          });
        }
      }, true);
      
      function runOnReady(fn) {
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', fn);
        } else {
          fn();
        }
      }

      // Добавляем обработчики кликов на заголовки
      runOnReady(function() {
        const headers = document.querySelectorAll('#hotelsTable th.sortable');
        headers.forEach(header => {
          header.addEventListener('click', () => sortTable(header.dataset.sort));
        });

        const mobileSortSelect = document.getElementById('mobileSortSelect');
        const mobileSortDirection = document.getElementById('mobileSortDirection');
        if (mobileSortSelect) {
          mobileSortSelect.addEventListener('change', function() {
            const col = mobileSortSelect.value;
            if (!col) {
              setTableSort(null);
              return;
            }
            const direction = currentSort.column === col ? currentSort.direction : 'asc';
            setTableSort(col, direction);
          });
        }
        if (mobileSortDirection) {
          mobileSortDirection.addEventListener('click', function() {
            if (!currentSort.column) return;
            setTableSort(
              currentSort.column,
              currentSort.direction === 'asc' ? 'desc' : 'asc'
            );
          });
        }
        syncMobileSortBar();
        
        // Sidebar functionality
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const mainContent = document.getElementById('mainContent');

        function toggleSidebar() {
          if (!sidebar || !sidebarOverlay || !mainContent) return;
          sidebar.classList.toggle('open');
          sidebarOverlay.classList.toggle('open');
          mainContent.classList.toggle('sidebar-open');
        }
        window.toggleSidebar = toggleSidebar;
        
        const sidebarToggle = document.getElementById('sidebarToggle');
        if (sidebarToggle) {
          sidebarToggle.onclick = function(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            toggleSidebar();
          };
        }
        if (sidebarOverlay) {
          sidebarOverlay.onclick = function(e) {
            if (e) { e.preventDefault(); e.stopPropagation(); }
            toggleSidebar();
          };
        }

        // Cards/Table view mode
        let refreshTableView = null;

        function setMode(mode) {
          const normalized = (mode === 'arbitrage') ? 'arbitrage' : (mode === 'table' ? 'table' : 'cards');
          const cardsEl = document.getElementById('cardsSection');
          const tableEl = document.getElementById('tableSection');
          const arbEl = document.getElementById('arbitrageSection');
          const alertsEl = document.getElementById('alertsSection');
          const globalFilters = document.getElementById('globalFilters');
          const modeSwEl = document.getElementById('modeSwitch');

          if (cardsEl) cardsEl.style.display = (normalized === 'cards') ? 'block' : 'none';
          if (tableEl) tableEl.style.display = (normalized === 'table') ? 'block' : 'none';
          if (arbEl) arbEl.style.display = (normalized === 'arbitrage') ? 'block' : 'none';
          if (globalFilters) globalFilters.style.display = (normalized === 'arbitrage') ? 'none' : 'flex';
          if (alertsEl) alertsEl.style.display = (normalized === 'arbitrage') ? 'none' : 'block';

          if (modeSwEl) {
            modeSwEl.dataset.mode = normalized;
            modeSwEl.querySelectorAll('.mode-btn').forEach((btn) => {
              btn.classList.toggle('active', btn.dataset.mode === normalized);
            });
          }
          try { localStorage.setItem('dashboard_mode', normalized); } catch(e) {}
          if (normalized === 'table' && typeof refreshTableView === 'function') {
            refreshTableView();
          }
        }
        window.setDashboardMode = setMode;

        window.updateArbitrageCalculations = function(frictionVal) {
          const f = parseFloat(frictionVal) || 0;
          const disp = document.getElementById('frictionDisplay');
          if (disp) disp.textContent = Math.round(f) + ' PLN';
          const rows = document.querySelectorAll('.arb-row');
          rows.forEach((row) => {
            const deEur = parseFloat(row.dataset.deEur) || 0;
            const plPln = parseFloat(row.dataset.plPln) || 0;
            const rate = parseFloat(row.dataset.rate) || 4.30;
            const netDe = Math.round(deEur * rate + f);
            const spread = Math.round(plPln - netDe);
            const pct = (plPln > 0) ? ((spread / plPln) * 100).toFixed(1) : 0;

            const netEl = row.querySelector('.arb-net-de');
            const spreadEl = row.querySelector('.arb-spread');
            if (netEl) netEl.innerHTML = '<strong>' + netDe.toLocaleString('ru-RU') + ' PLN</strong>';
            if (spreadEl) {
              if (spread > 0) {
                spreadEl.className = 'arb-spread arb-badge-win';
                spreadEl.textContent = '+' + spread.toLocaleString('ru-RU') + ' PLN (-' + pct + '%)';
              } else {
                spreadEl.className = 'arb-spread arb-badge-neutral';
                spreadEl.textContent = spread.toLocaleString('ru-RU') + ' PLN';
              }
            }
          });
        };

        const modeSwitch = document.getElementById('modeSwitch');
        if (modeSwitch) {
          modeSwitch.querySelectorAll('.mode-btn').forEach((btn) => {
            btn.onclick = function(e) {
              if (e) { e.preventDefault(); e.stopPropagation(); }
              setMode(btn.dataset.mode || 'cards');
            };
          });
        }
        bindFoldPersistence('aiOracleFold', 'dashboard_fold_ai_oracle', true);
        bindFoldPersistence('analyticsFold', 'dashboard_fold_analytics', false);
        bindFoldPersistence('calendarFold', 'dashboard_fold_calendar', false);
        bindFoldPersistence('offersCountFold', 'dashboard_fold_offers_count', false);
        bindFoldPersistence('trendFold', 'dashboard_fold_trend', false);
        bindFoldPersistence('timingFold', 'dashboard_fold_timing', false);
        bindFoldPersistence('earlyBookingFold', 'dashboard_fold_early_booking', false);
        bindFoldPersistence('statsFold', 'dashboard_fold_stats', false);
        bindFoldPersistence('departureHistoryFold', 'dashboard_fold_departure_history', false);
        // 'vanishedFold' (Выпавшие отели) always collapsed by default on page load
        const vFold = document.getElementById('vanishedFold');
        if (vFold) {
          vFold.open = false;
          try { localStorage.removeItem('dashboard_fold_vanished'); } catch(e) {}
        }
        
        // Theme toggle functionality
        const themeToggle = document.getElementById('themeToggle');
        const body = document.body;
        
        // Load saved theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        if (savedTheme === 'dark') {
          body.classList.add('dark-theme');
          if (themeToggle) themeToggle.textContent = '☀️';
        }
        
        if (themeToggle) themeToggle.addEventListener('click', function() {
          body.classList.toggle('dark-theme');
          const isDark = body.classList.contains('dark-theme');
          themeToggle.textContent = isDark ? '☀️' : '🌙';
          localStorage.setItem('theme', isDark ? 'dark' : 'light');
        });

        // ── Relative update time ──────────────────────────────────────────────
        function _updateRelativeTime() {
          const badge = document.getElementById('updateStatusBadge');
          const span  = document.getElementById('updateAgoText');
          if (!badge || !span) return;
          const iso = badge.getAttribute('data-iso');
          if (!iso) return;
          const diff = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
          let label;
          if (diff < 60)        label = 'только что';
          else if (diff < 3600) label = Math.floor(diff / 60) + ' мин назад';
          else if (diff < 86400) {
            const h = Math.floor(diff / 3600);
            label = h + ' ч назад';
          } else {
            const d = Math.floor(diff / 86400);
            label = d + ' д назад';
          }
          span.textContent = label;
        }
        _updateRelativeTime();
        setInterval(_updateRelativeTime, 60000);

        // Table filtering and pagination
        const searchInput = document.getElementById('searchInput');
        const priceFilter = document.getElementById('priceFilter');
        const changeFilter = document.getElementById('changeFilter');
        const regionFilter = document.getElementById('regionFilter');
        const taFilter = document.getElementById('taFilter');
        const clearFilters = document.getElementById('clearFilters');
        const table = document.getElementById('hotelsTable');
        if (!table) {
          let initialMode = 'cards';
          try { initialMode = localStorage.getItem('dashboard_mode') || 'cards'; } catch(e) {}
          setMode(initialMode);
          return;
        }
        const tbody = table.querySelector('tbody');
        if (!tbody) {
          let initialMode = 'cards';
          try { initialMode = localStorage.getItem('dashboard_mode') || 'cards'; } catch(e) {}
          setMode(initialMode);
          return;
        }
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const prevPage = document.getElementById('prevPage');
        const nextPage = document.getElementById('nextPage');
        const showingFrom = document.getElementById('showingFrom');
        const showingTo = document.getElementById('showingTo');
        const totalItems = document.getElementById('totalItems');
        
        let currentPage = 1;
        const itemsPerPage = 50;
        let filteredRows = [...rows];

        // Cards pagination
        const cardsGrid = document.querySelector('#cardsSection .cards-grid');
        const cardItems = cardsGrid ? Array.from(cardsGrid.querySelectorAll('.hotel-card')) : [];
        let filteredCards = [...cardItems];
        const cardsPrevPage = document.getElementById('cardsPrevPage');
        const cardsNextPage = document.getElementById('cardsNextPage');
        const cardsShowingFrom = document.getElementById('cardsShowingFrom');
        const cardsShowingTo = document.getElementById('cardsShowingTo');
        const cardsTotalItems = document.getElementById('cardsTotalItems');
        let cardsPage = 1;
        const cardsPerPage = 24;

        function updateCardsPagination() {
          const total = filteredCards.length;
          const totalPages = Math.max(1, Math.ceil(total / cardsPerPage));
          if (cardsPage > totalPages) cardsPage = totalPages;
          const start = (cardsPage - 1) * cardsPerPage;
          const end = start + cardsPerPage;

          cardItems.forEach((card) => {
            card.style.display = 'none';
          });
          filteredCards.slice(start, end).forEach((card) => {
            card.style.display = '';
          });

          if (cardsTotalItems) cardsTotalItems.textContent = String(total);
          if (cardsShowingFrom) cardsShowingFrom.textContent = total ? String(start + 1) : '0';
          if (cardsShowingTo) cardsShowingTo.textContent = total ? String(Math.min(end, total)) : '0';
          if (cardsPrevPage) cardsPrevPage.disabled = cardsPage <= 1;
          if (cardsNextPage) cardsNextPage.disabled = cardsPage >= totalPages;

          if (typeof window.syncWatchlistUI === 'function') {
            window.syncWatchlistUI();
          }
        }

        function cardsNextPageFunc() {
          const totalPages = Math.max(1, Math.ceil(filteredCards.length / cardsPerPage));
          if (cardsPage < totalPages) {
            cardsPage++;
            updateCardsPagination();
          }
        }

        function cardsPrevPageFunc() {
          if (cardsPage > 1) {
            cardsPage--;
            updateCardsPagination();
          }
        }
        
        function filterRows() {
          const searchTerm = searchInput.value.toLowerCase();
          const priceRange = priceFilter.value;
          const changeType = changeFilter.value;
          const regionValue = regionFilter ? regionFilter.value : '';
          const taValue = taFilter ? taFilter.value : '';
          const forecastFilter = document.getElementById('forecastFilter');
          const forecastValue = forecastFilter ? forecastFilter.value : '';
          const watchlistToggle = document.getElementById('watchlistToggle');
          const watchlistOnly = watchlistToggle ? watchlistToggle.classList.contains('active') : false;
          const watchlist = typeof window.getWatchlist === 'function' ? window.getWatchlist() : [];
          
          filteredRows = rows.filter(row => {
            const hotelName = (row.querySelector('.col-hotel a')?.textContent || row.querySelector('.col-hotel')?.textContent || row.cells[0]?.textContent || '').toLowerCase();
            const rawHotelName = (row.querySelector('.col-hotel a')?.getAttribute('data-hotel-name') || '').trim();
            const priceCell = row.querySelector('.price');
            const price = parseFloat((priceCell?.textContent || row.cells[1]?.textContent || '').replace(/[^0-9.-]/g, ''));
            const d48Cell = row.querySelector('.col-w-d48-td');
            const delta48 = (d48Cell?.textContent || row.cells[5]?.textContent || '').trim();
            const regionCell = row.querySelector('.arrival-hub');
            const rowRegion = row.dataset.region || (regionCell?.textContent || row.cells[7]?.textContent || '').trim();
            const rowTa = parseFloat(row.dataset.taRating || '-1');
            const rowDate = row.dataset.departureDate || '';
            
            if (searchTerm && !hotelName.includes(searchTerm)) {
              return false;
            }
            if (watchlistOnly && !watchlist.includes(rawHotelName)) {
              return false;
            }
            if (window.activeCalendarDate && rowDate !== window.activeCalendarDate) {
              return false;
            }
            
            // Forecast filter
            if (forecastValue) {
              const forecastCell = row.cells[3];
              const fText = (forecastCell?.textContent || '').toUpperCase();
              const fSort = (forecastCell?.dataset?.sortValue || '').toUpperCase();
              if (forecastValue === 'buy' && !fText.includes('ПОКУПАТЬ') && !fSort.includes('BUY')) return false;
              if (forecastValue === 'wait' && !fText.includes('ЖДАТЬ') && !fText.includes('НАБЛЮДАТЬ') && !fSort.includes('WAIT')) return false;
              if (forecastValue === 'expensive' && !fText.includes('ДОРОГО') && !fSort.includes('OVERPRICED')) return false;
            }
            
            // Price filter
            if (priceRange) {
              if (priceRange.endsWith('+')) {
                if (price < parseFloat(priceRange)) return false;
              } else {
                const parts = priceRange.split('-');
                const min = parseFloat(parts[0]);
                const max = parseFloat(parts[1]);
                if (price < min || price > max) return false;
              }
            }
            
            // Change filter
            if (changeType) {
              if (changeType === 'decrease' && !delta48.includes('-')) return false;
              if (changeType === 'increase' && !delta48.includes('+')) return false;
              if (changeType === 'stable' && delta48 !== '—') return false;
            }

            if (regionValue && rowRegion !== regionValue) {
              return false;
            }

            if (taValue) {
              if (taValue === 'none') {
                if (rowTa > 0) return false;
              } else {
                const minTa = parseFloat(taValue);
                if (!Number.isFinite(rowTa) || rowTa < minTa) return false;
              }
            }
            
            return true;
          });

          filteredCards = cardItems.filter((card) => {
            const title = card.querySelector('.hotel-card-title');
            const hotelName = title ? title.textContent.toLowerCase() : '';
            const rawHotelName = title ? title.textContent.trim() : '';
            const priceText = card.querySelector('.hotel-card-price')?.textContent || '';
            const price = parseFloat(priceText.replace(/[^0-9.-]/g, ''));
            const region = card.dataset.region || '';
            const cardDate = card.dataset.departureDate || '';
            const taValueAttr = card.dataset.taRating || card.dataset.ta || '-1';
            const rowTa = parseFloat(taValueAttr);
            const cardStats = card.querySelector('.hotel-card-stats');
            const delta48Text = card.dataset.delta48 || (cardStats ? cardStats.querySelector('div:first-child strong')?.textContent || '' : '');

            if (searchTerm && !hotelName.includes(searchTerm)) {
              return false;
            }
            if (watchlistOnly && !watchlist.includes(rawHotelName)) {
              return false;
            }
            if (window.activeCalendarDate && cardDate !== window.activeCalendarDate) {
              return false;
            }
            if (forecastValue) {
              const cardHopper = (card.querySelector('.hopper-pill')?.textContent || card.querySelector('.forecast-pill')?.textContent || '').toUpperCase();
              if (forecastValue === 'buy' && !cardHopper.includes('ПОКУПАТЬ') && !cardHopper.includes('BUY')) return false;
              if (forecastValue === 'wait' && !cardHopper.includes('ЖДАТЬ') && !cardHopper.includes('НАБЛЮДАТЬ') && !cardHopper.includes('WAIT')) return false;
              if (forecastValue === 'expensive' && !cardHopper.includes('ДОРОГО') && !cardHopper.includes('OVERPRICED')) return false;
            }
            if (priceRange) {
              if (priceRange.endsWith('+')) {
                if (price < parseFloat(priceRange)) return false;
              } else {
                const parts = priceRange.split('-');
                const min = parseFloat(parts[0]);
                const max = parseFloat(parts[1]);
                if (price < min || price > max) return false;
              }
            }
            if (changeType) {
              if (changeType === 'decrease' && !delta48Text.includes('-')) return false;
              if (changeType === 'increase' && !delta48Text.includes('+')) return false;
              if (changeType === 'stable' && delta48Text !== '—') return false;
            }
            if (regionValue && region !== regionValue) {
              return false;
            }
            if (taValue) {
              if (taValue === 'none') {
                if (rowTa > 0) return false;
              } else {
                const minTa = parseFloat(taValue);
                if (isNaN(rowTa) || rowTa < minTa) return false;
              }
            }
            return true;
          });

          if (currentSort.column) {
            filteredRows.sort(compareHotelRows);
          }
          
          currentPage = 1;
          cardsPage = 1;
          updateTable();
          updateCardsPagination();

          if (typeof window.updateCalendarHeatmap === 'function') {
            window.updateCalendarHeatmap();
          }
        }
        
        function updateTable() {
          const startIndex = (currentPage - 1) * itemsPerPage;
          const endIndex = startIndex + itemsPerPage;
          const pageRows = filteredRows.slice(startIndex, endIndex);
          
          // Clear current rows
          tbody.innerHTML = '';
          
          // Add filtered rows with exact zebra striping classes
          pageRows.forEach((row, idx) => {
            row.classList.remove('row-even', 'row-odd');
            row.classList.add(idx % 2 === 1 ? 'row-even' : 'row-odd');
            tbody.appendChild(row);
          });
          
          // Update pagination info
          showingFrom.textContent = filteredRows.length > 0 ? startIndex + 1 : 0;
          showingTo.textContent = Math.min(endIndex, filteredRows.length);
          totalItems.textContent = filteredRows.length;
          
          // Update pagination buttons
          prevPage.disabled = currentPage === 1;
          nextPage.disabled = endIndex >= filteredRows.length;

          if (typeof window.syncWatchlistUI === 'function') {
            window.syncWatchlistUI();
          }
        }
        
        function nextPageFunc() {
          const maxPage = Math.ceil(filteredRows.length / itemsPerPage);
          if (currentPage < maxPage) {
            currentPage++;
            updateTable();
          }
        }
        
        function prevPageFunc() {
          if (currentPage > 1) {
            currentPage--;
            updateTable();
          }
        }

        window._hotelTableSortAll = function() {
          filteredRows.sort(compareHotelRows);
          currentPage = 1;
          updateTable();
        };
        
        window._hotelTableFilterRows = filterRows;
        window._rebindHotelTableRows = function() {
          const freshRows = Array.from(tbody.querySelectorAll('tr'));
          rows.length = 0;
          freshRows.forEach((row) => rows.push(row));
          filteredRows = [...rows];
          const freshCards = cardsGrid ? Array.from(cardsGrid.querySelectorAll('.hotel-card')) : [];
          cardItems.length = 0;
          freshCards.forEach((card) => cardItems.push(card));
          filteredCards = [...cardItems];
          currentPage = 1;
          cardsPage = 1;
          filterRows();
        };

        refreshTableView = function() {
          updateTable();
        };

        // Event listeners
        const watchlistToggle = document.getElementById('watchlistToggle');
        if (watchlistToggle) {
          watchlistToggle.addEventListener('click', function(event) {
            event.preventDefault();
            watchlistToggle.classList.toggle('active');
            if (watchlistToggle.classList.contains('active')) {
              watchlistToggle.style.background = 'var(--gradient-primary)';
              watchlistToggle.style.color = 'white';
            } else {
              watchlistToggle.style.background = '#cbd5e1';
              watchlistToggle.style.color = '#1e293b';
            }
            filterRows();
          });
        }

        if (searchInput) searchInput.addEventListener('input', filterRows);
        if (priceFilter) priceFilter.addEventListener('change', filterRows);
        const forecastFilterEl = document.getElementById('forecastFilter');
        if (forecastFilterEl) forecastFilterEl.addEventListener('change', filterRows);
        if (changeFilter) changeFilter.addEventListener('change', filterRows);
        if (regionFilter) regionFilter.addEventListener('change', filterRows);
        if (taFilter) taFilter.addEventListener('change', filterRows);
        if (clearFilters) clearFilters.addEventListener('click', function() {
          if (searchInput) searchInput.value = '';
          if (priceFilter) priceFilter.value = '';
          if (forecastFilterEl) forecastFilterEl.value = '';
          if (changeFilter) changeFilter.value = '';
          if (regionFilter) regionFilter.value = '';
          if (taFilter) taFilter.value = '';
          if (watchlistToggle) {
            watchlistToggle.classList.remove('active');
            watchlistToggle.style.background = '#cbd5e1';
            watchlistToggle.style.color = '#1e293b';
          }
          window.activeCalendarDate = null;
          filterRows();
        });
        if (nextPage) nextPage.addEventListener('click', nextPageFunc);
        if (prevPage) prevPage.addEventListener('click', prevPageFunc);
        if (cardsNextPage) cardsNextPage.addEventListener('click', cardsNextPageFunc);
        if (cardsPrevPage) cardsPrevPage.addEventListener('click', cardsPrevPageFunc);
        
        // Initialize
        updateTable();
        updateCardsPagination();
        let initialMode = 'cards';
        try { initialMode = localStorage.getItem('dashboard_mode') || 'cards'; } catch(e) {}
        setMode(initialMode);
      });
    </script>
"""
    html_template += """
    <script>
      (function(){
        const departureOffers = """ + departure_offers_json + """;
        const departurePriceCurves = """ + departure_price_curves_json + """;
        window.departureOffers = departureOffers;

        // Watchlist helper functions
        function getWatchlist() {
          try {
            return JSON.parse(localStorage.getItem('watchlist_hotels') || '[]');
          } catch(e) {
            return [];
          }
        }
        function saveWatchlist(list) {
          try {
            localStorage.setItem('watchlist_hotels', JSON.stringify(list));
          } catch(e) {}
        }
        window.getWatchlist = getWatchlist;
        window.saveWatchlist = saveWatchlist;
        
        window.toggleWatchlist = function(hotelName) {
          const list = getWatchlist();
          const idx = list.indexOf(hotelName);
          if (idx > -1) {
            list.splice(idx, 1);
          } else {
            list.push(hotelName);
          }
          saveWatchlist(list);
          window.syncWatchlistUI();
          if (window._hotelTableFilterRows) {
            window._hotelTableFilterRows();
          }
        };

        window.syncWatchlistUI = function() {
          const list = getWatchlist();
          document.querySelectorAll('.watchlist-star-btn').forEach(btn => {
            const hotel = btn.getAttribute('data-hotel-name');
            if (list.includes(hotel)) {
              btn.classList.add('starred');
              btn.textContent = '★';
            } else {
              btn.classList.remove('starred');
              btn.textContent = '☆';
            }
          });
        };

        // Initialize Watchlist events
        window.initWatchlistEvents = function() {
          document.addEventListener('click', function(e) {
            const btn = e.target.closest('.watchlist-star-btn');
            if (btn) {
              e.preventDefault();
              e.stopPropagation();
              const hotel = btn.getAttribute('data-hotel-name');
              if (hotel) {
                window.toggleWatchlist(hotel);
              }
            }
          });
        };
        
        // Run once on load
        window.initWatchlistEvents();

        // Calendar Heatmap Implementation
        function getMonthName(yearMonthStr) {
          const [year, month] = yearMonthStr.split('-');
          const date = new Date(year, parseInt(month) - 1, 1);
          return date.toLocaleString('ru-RU', { month: 'long', year: 'numeric' });
        }

        window.updateCalendarHeatmap = function() {
          const wrapper = document.getElementById('calendarHeatmapWrapper');
          if (!wrapper || !window.departureOffers) return;

          const searchInput = document.getElementById('searchInput');
          const priceFilter = document.getElementById('priceFilter');
          const changeFilter = document.getElementById('changeFilter');
          const regionFilter = document.getElementById('regionFilter');
          const taFilter = document.getElementById('taFilter');
          const watchlistToggle = document.getElementById('watchlistToggle');
          
          const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
          const priceRange = priceFilter ? priceFilter.value : '';
          const changeType = changeFilter ? changeFilter.value : '';
          const regionValue = regionFilter ? regionFilter.value : '';
          const taValue = taFilter ? taFilter.value : '';
          const watchlistOnly = watchlistToggle ? watchlistToggle.classList.contains('active') : false;
          const watchlist = getWatchlist();

          const dateMinPrices = {};
          let overallMin = Infinity;
          let overallMax = -Infinity;

          for (let key in window.departureOffers) {
            const dep = window.departureOffers[key];
            const dateStr = dep.departure_date;
            if (!dateStr) continue;

            if (regionValue && dep.region !== regionValue) continue;

            dep.offers.forEach(offer => {
              if (searchTerm && !offer.hotel_name.toLowerCase().includes(searchTerm)) return;
              if (watchlistOnly && !watchlist.includes(offer.hotel_name)) return;

              const price = parseFloat(offer.price);
              if (priceRange) {
                if (priceRange.endsWith('+')) {
                  if (price < parseFloat(priceRange)) return;
                } else {
                  const parts = priceRange.split('-');
                  const min = parseFloat(parts[0]);
                  const max = parseFloat(parts[1]);
                  if (price < min || price > max) return;
                }
              }

              const rowTa = parseFloat(offer.ta_rating || '-1');
              if (taValue) {
                if (taValue === 'none') {
                  if (rowTa > 0) return;
                } else {
                  const minTa = parseFloat(taValue);
                  if (isNaN(rowTa) || rowTa < minTa) return;
                }
              }

              const delta48 = offer.delta_avg || '';
              if (changeType) {
                if (changeType === 'decrease' && !delta48.includes('-')) return;
                if (changeType === 'increase' && !delta48.includes('+')) return;
                if (changeType === 'stable' && delta48 !== '—') return;
              }

              if (!dateMinPrices[dateStr]) {
                dateMinPrices[dateStr] = { minPrice: Infinity, count: 0, best: null };
              }
              const dStats = dateMinPrices[dateStr];
              dStats.count++;
              if (price < dStats.minPrice) {
                dStats.minPrice = price;
                dStats.best = offer;
              }
            });
          }

          for (let dStr in dateMinPrices) {
            const price = dateMinPrices[dStr].minPrice;
            if (price < overallMin) overallMin = price;
            if (price > overallMax) overallMax = price;
          }

          const allDates = new Set();
          for (let key in window.departureOffers) {
            if (window.departureOffers[key].departure_date) {
              allDates.add(window.departureOffers[key].departure_date);
            }
          }
          if (allDates.size === 0) {
            wrapper.innerHTML = '<div style="color:var(--text-secondary);text-align:center;padding:1rem;">Нет доступных дат вылета</div>';
            return;
          }

          const sortedDates = Array.from(allDates).sort();
          const minDate = new Date(sortedDates[0]);
          const maxDate = new Date(sortedDates[sortedDates.length - 1]);

          const months = {};
          let curr = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
          const endLimit = new Date(maxDate.getFullYear(), maxDate.getMonth() + 1, 1);

          while (curr < endLimit) {
            const year = curr.getFullYear();
            const month = String(curr.getMonth() + 1).padStart(2, '0');
            const key = `${year}-${month}`;
            
            const firstDay = new Date(year, curr.getMonth(), 1).getDay();
            const startOffset = firstDay === 0 ? 6 : firstDay - 1;
            const totalDays = new Date(year, curr.getMonth() + 1, 0).getDate();

            months[key] = {
              title: getMonthName(key),
              startOffset: startOffset,
              totalDays: totalDays,
              year: year,
              monthIndex: curr.getMonth()
            };

            curr.setMonth(curr.getMonth() + 1);
          }

          let html = '';
          for (let mKey in months) {
            const m = months[mKey];
            html += `<div class="calendar-month-container">`;
            html += `<div class="calendar-month-title">${m.title}</div>`;
            html += `<div class="calendar-grid-container">`;
            
            ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].forEach(day => {
              html += `<div class="calendar-day-header">${day}</div>`;
            });

            for (let i = 0; i < m.startOffset; i++) {
              html += `<div class="calendar-day-cell empty"></div>`;
            }

            for (let d = 1; d <= m.totalDays; d++) {
              const dayStr = `${m.year}-${String(m.monthIndex + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
              
              if (allDates.has(dayStr)) {
                const stats = dateMinPrices[dayStr];
                if (stats && stats.minPrice !== Infinity) {
                  let hue = 140;
                  if (overallMax > overallMin) {
                    const pct = (stats.minPrice - overallMin) / (overallMax - overallMin);
                    hue = 140 - Math.round(pct * 100);
                  }
                  
                  const isSelected = window.activeCalendarDate === dayStr ? ' selected' : '';
                  const tooltipText = `Дата: ${dayStr}\\nМинимальная цена: ${Math.round(stats.minPrice)} PLN\\nЛучший отель: ${stats.best.hotel_name}\\nВсего предложений: ${stats.count}`;

                  html += `
                    <div class="calendar-day-cell${isSelected}" 
                         style="background-color: hsla(${hue}, 80%, 40%, 0.7); color: #fff;" 
                         title="${escapeHtml(tooltipText)}"
                         onclick="window.selectCalendarDate('${dayStr}')">
                      <span class="calendar-day-number">${d}</span>
                      <span class="calendar-day-price">${Math.round(stats.minPrice)}</span>
                    </div>`;
                } else {
                  html += `
                    <div class="calendar-day-cell empty" title="Нет предложений по выбранным фильтрам на эту дату">
                      <span class="calendar-day-number">${d}</span>
                      <span style="font-size:0.6rem;align-self:flex-end;">—</span>
                    </div>`;
                }
              } else {
                html += `
                  <div class="calendar-day-cell empty">
                    <span class="calendar-day-number">${d}</span>
                  </div>`;
              }
            }

            const totalCells = m.startOffset + m.totalDays;
            const remaining = (7 - (totalCells % 7)) % 7;
            for (let i = 0; i < remaining; i++) {
              html += `<div class="calendar-day-cell empty"></div>`;
            }

            html += `</div></div>`;
          }

          wrapper.innerHTML = html;
        };

        window.selectCalendarDate = function(dateStr) {
          if (window.activeCalendarDate === dateStr) {
            window.activeCalendarDate = null;
          } else {
            window.activeCalendarDate = dateStr;
          }
          if (window._hotelTableFilterRows) {
            window._hotelTableFilterRows();
          }
        };

        function regionLabel(value) {
          return String(value || 'region').replace(/-/g, ' ').replace(/\\b\\w/g, function(c) { return c.toUpperCase(); });
        }

        function escapeHtml(value) {
          return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
        }

        function renderDeparturePriceChart(key) {
          const chartEl = document.getElementById('departureModalChart');
          const chartTitleEl = document.getElementById('departureModalChartTitle');
          if (!chartEl) return;
          if (window.Plotly) {
            try { Plotly.purge(chartEl); } catch (e) {}
          }
          chartEl.innerHTML = '';
          const curve = departurePriceCurves[key];
          if (!curve || !curve.days || !curve.days.length || !window.Plotly) {
            chartEl.style.display = 'none';
            if (chartTitleEl) chartTitleEl.style.display = 'none';
            return;
          }
          chartEl.style.display = 'block';
          if (chartTitleEl) chartTitleEl.style.display = 'block';
          const x = (curve.labels && curve.labels.length)
            ? curve.labels
            : curve.days.map(function(d) { return 'D-' + d; });
          const yVals = (curve.median_price || []).concat(curve.p10_price || []).filter(function(v) {
            return v != null && !isNaN(v) && v > 0;
          });
          let yRange = null;
          if (yVals.length) {
            const yMin = Math.min.apply(null, yVals);
            const yMax = Math.max.apply(null, yVals);
            const span = Math.max(yMax - yMin, yMax * 0.05, 500);
            const pad = span * 0.1;
            yRange = [Math.max(0, yMin - pad), yMax + pad];
          }
          const traces = [
            {
              x: x,
              y: curve.median_price,
              name: 'Типичная (медиана)',
              mode: 'lines+markers',
              line: { color: '#2563eb', width: 2.5 },
              marker: { size: 6 },
            },
            {
              x: x,
              y: curve.p10_price,
              name: 'Дешёвый сегмент (~10%)',
              mode: 'lines+markers',
              line: { color: '#16a34a', width: 2, dash: 'dot' },
              marker: { size: 5 },
            },
          ];
          const chartHeight = window.innerWidth <= 480 ? 240 : 300;
          const layout = {
            height: chartHeight,
            autosize: true,
            margin: { l: 52, r: 16, t: 44, b: 52 },
            paper_bgcolor: '#f8fafc',
            plot_bgcolor: '#ffffff',
            xaxis: {
              title: 'Дней до вылета',
              tickangle: -35,
              gridcolor: '#e2e8f0',
              automargin: true,
            },
            yaxis: {
              title: 'PLN',
              gridcolor: '#e2e8f0',
              automargin: true,
              range: yRange,
            },
            legend: { orientation: 'h', y: 1.18, x: 0 },
            hovermode: 'x unified',
          };
          Plotly.newPlot(chartEl, traces, layout, { responsive: true, displayModeBar: false });
          if (window.Plotly && window.Plotly.Plots) {
            window.Plotly.Plots.resize(chartEl);
          }
        }

        function openDepartureOffers(key) {
          const modal = document.getElementById('departureOffersModal');
          const titleEl = document.getElementById('departureModalTitle');
          const metaEl = document.getElementById('departureModalMeta');
          const bodyEl = document.getElementById('departureModalBody');
          if (!modal || !titleEl || !metaEl || !bodyEl) return;

          modal.classList.add('open');
          modal.setAttribute('aria-hidden', 'false');
          renderDeparturePriceChart(key);

          const payload = departureOffers[key];
          if (!payload) {
            titleEl.textContent = 'Отели по вылету';
            metaEl.textContent = 'Для этого вылета нет сохранённых предложений в истории scrape.';
            bodyEl.innerHTML = '<div class="departure-modal-empty">Архивный вылет: офферы показываются только если они есть в travel_prices / departure_offers. Для будущих вылетов список появится после ближайших проверок.</div>';
            return;
          }

          const region = regionLabel(payload.region);
          const nights = payload.nights ? payload.nights + ' ночей' : '';
          titleEl.textContent = region + ' · ' + (payload.departure_date || '—');
          metaEl.textContent = [
            payload.hub_subtitle || '',
            nights,
            payload.offers.length + ' отелей',
            payload.run_started_at ? ('снимок ' + String(payload.run_started_at).slice(0, 16)) : ''
          ].filter(Boolean).join(' · ');

          if (!payload.offers.length) {
            bodyEl.innerHTML = '<div class="departure-modal-empty">Нет предложений для этого вылета в выбранном снимке.</div>';
          } else {
            const rows = payload.offers.map(function(offer) {
              const dealHtml = offer.deal_has_data
                ? '<span class="deal-pill ' + escapeHtml(offer.deal_class || 'normal') + '">' + offer.deal_score + ' · ' + escapeHtml(offer.deal_label || 'Normal') + '</span>'
                : '<span class="departure-modal-empty">—</span>';
              const deltaAvg = offer.delta_avg || '—';
              const deltaCls = deltaAvg.startsWith('-') ? 'delta-drop' : (deltaAvg.startsWith('+') ? 'delta-up' : 'delta-flat');
              const actions = [];
              if (offer.slug || offer.chart_href) {
                const s = offer.slug || '';
                actions.push('<a class="departure-offers-link secondary" href="' + escapeHtml(offer.chart_href || '#') + '" data-hotel-slug="' + escapeHtml(s) + '" onclick="if(window.openHotelPassport){window.openHotelPassport(this.dataset.hotelSlug); return false;}">Паспорт</a>');
              }
              if (offer.offer_url) {
                actions.push('<a class="departure-offers-link" href="' + escapeHtml(offer.offer_url) + '" target="_blank" rel="noopener">Оффер</a>');
              }
              const actionsHtml = actions.length
                ? '<div class="departure-offers-actions">' + actions.join('') + '</div>'
                : '<span class="departure-modal-empty">—</span>';
              return '<tr>'
                + '<td><strong>' + escapeHtml(offer.hotel_name) + '</strong>'
                + (offer.dates ? '<br><span style="color:#64748b;font-size:.78rem;">' + escapeHtml(offer.dates) + '</span>' : '')
                + '</td>'
                + '<td class="price">' + Math.round(Number(offer.price || 0)) + ' PLN</td>'
                + '<td>' + dealHtml + '</td>'
                + '<td class="' + deltaCls + '">' + escapeHtml(deltaAvg) + '</td>'
                + '<td>' + actionsHtml + '</td>'
                + '</tr>';
            }).join('');
            bodyEl.innerHTML = '<div class="departure-modal-table-scroll"><table class="departure-offers-table"><thead><tr><th>Отель</th><th>Цена</th><th>Deal</th><th title="Отклонение от типичной цены отеля по истории вылетов">Δ типич.</th><th>Ссылки</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
          }

          [40, 150, 350].forEach(function(delay) {
            setTimeout(function() {
              const chartEl = document.getElementById('departureModalChart');
              if (chartEl && window.Plotly && window.Plotly.Plots && chartEl.style.display !== 'none') {
                try { window.Plotly.Plots.resize(chartEl); } catch (e) {}
              }
            }, delay);
          });
        }

        function closeDepartureOffers() {
          const modal = document.getElementById('departureOffersModal');
          const chartEl = document.getElementById('departureModalChart');
          const chartTitleEl = document.getElementById('departureModalChartTitle');
          if (chartEl && window.Plotly) {
            try { Plotly.purge(chartEl); } catch (e) {}
            chartEl.innerHTML = '';
            chartEl.style.display = 'none';
          }
          if (chartTitleEl) chartTitleEl.style.display = 'none';
          if (!modal) return;
          modal.classList.remove('open');
          modal.setAttribute('aria-hidden', 'true');
        }

        function bindDepartureOfferClicks() {
          document.querySelectorAll('.departure-card-clickable, .departure-history-row').forEach(function(el) {
            el.addEventListener('click', function() {
              const key = el.getAttribute('data-departure-key');
              if (key) openDepartureOffers(key);
            });
            el.addEventListener('keydown', function(event) {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                const key = el.getAttribute('data-departure-key');
                if (key) openDepartureOffers(key);
              }
            });
          });

          const closeBtn = document.getElementById('departureModalClose');
          const backdrop = document.getElementById('departureModalBackdrop');
          if (closeBtn) closeBtn.addEventListener('click', closeDepartureOffers);
          if (backdrop) backdrop.addEventListener('click', closeDepartureOffers);
          document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') closeDepartureOffers();
          });
        }

        document.addEventListener('DOMContentLoaded', function() {
          bindDepartureOfferClicks();
          if (typeof window.updateCalendarHeatmap === 'function') window.updateCalendarHeatmap();
          if (typeof window.syncWatchlistUI === 'function') window.syncWatchlistUI();
        });
        if (document.readyState !== 'loading') {
          bindDepartureOfferClicks();
          if (typeof window.updateCalendarHeatmap === 'function') window.updateCalendarHeatmap();
          if (typeof window.syncWatchlistUI === 'function') window.syncWatchlistUI();
        }
      })();
    </script>
    <script>
      (function() {
        const dataEl = document.getElementById('durationViewsData');
        const switchRoot = document.getElementById('durationGlobalSwitch');
        if (!dataEl || !switchRoot) return;

        let views = {};
        try {
          views = JSON.parse(dataEl.textContent || '{}');
        } catch (err) {
          console.warn('duration views parse failed', err);
          return;
        }

        function buildTop10HoverTexts(detailedData) {
          return (detailedData || []).map((data) => {
            const hover = (data && data.hover_data) || {};
            let text = hover.title || '';
            if (hover.avg_price) {
              text += '<br><br><b>Средняя цена:</b><br>' + Math.round(hover.avg_price) + ' PLN';
            }
            if (hover.avg_change) {
              text += '<br><br><b>Изменение средней цены:</b><br>';
              text += hover.avg_change.arrow + ' ' + hover.avg_change.sign
                + Math.round(hover.avg_change.change) + ' PLN ('
                + hover.avg_change.sign + hover.avg_change.change_percent.toFixed(1) + '%)';
            }
            if (hover.price_changes && hover.price_changes.length) {
              text += '<br><br><b>🏨 Изменения цен:</b><br>';
              hover.price_changes.forEach((change) => {
                text += '• ' + change.name + '<br>  ' + Math.round(change.old_price)
                  + ' → ' + Math.round(change.new_price) + ' PLN<br>  '
                  + change.arrow + ' ' + change.sign + Math.round(change.change) + ' PLN ('
                  + change.sign + change.change_percent.toFixed(1) + '%)<br>';
              });
            }
            if (hover.new_hotels && hover.new_hotels.length) {
              text += '<br><b>🆕 Новые в ТОП-10:</b><br>';
              hover.new_hotels.forEach((hotel) => {
                text += '• ' + hotel.name + '<br>  Цена: ' + Math.round(hotel.price)
                  + ' PLN (позиция ' + hotel.position + ')<br>';
              });
            }
            if (hover.removed_hotels && hover.removed_hotels.length) {
              text += '<br><b>❌ Покинули ТОП-10:</b><br>';
              hover.removed_hotels.forEach((hotel) => {
                text += '• ' + hotel.name + '<br>  Цена: ' + Math.round(hotel.price)
                  + ' PLN (была позиция ' + hotel.position + ')<br>';
              });
            }
            if (hover.no_changes) {
              text += '<br><br><i>Нет изменений в этом ране</i>';
            }
            return text;
          });
        }

        function emptyChartLayout(kind) {
          const annotation = {
            text: 'Нет данных для этого фильтра',
            showarrow: false,
            xref: 'paper',
            yref: 'paper',
            x: 0.5,
            y: 0.5,
            font: { size: 14, color: '#94a3b8' },
          };
          if (kind === 'trend') {
            return {
              margin: { t: 10, r: 10, b: 40, l: 50 },
              xaxis: { title: 'Время', type: 'date' },
              yaxis: { title: 'Изменение, %' },
              hovermode: 'closest',
              annotations: [annotation],
            };
          }
          return {
            margin: { t: 10, r: 10, b: 40, l: 50 },
            xaxis: { title: 'Время', type: 'date' },
            yaxis: { title: 'Цена (PLN)' },
            hovermode: 'closest',
            annotations: [annotation],
          };
        }

        window.renderDashboardDurationCharts = function(charts) {
          if (!window.Plotly || !charts) return;
          const X = charts.top10_x || [];
          const Y = charts.top10_y || [];
          const minY = charts.top10_min || [];
          const maxY = charts.top10_max || [];
          const detailedData = charts.top10_detailed || [];
          if (X.length && Y.length) {
            const hoverTexts = buildTop10HoverTexts(detailedData);
            const traceMin = {
              x: X,
              y: minY.length === X.length ? minY : Y,
              type: 'scatter',
              mode: 'lines',
              line: { width: 0 },
              showlegend: false,
              hoverinfo: 'skip'
            };
            const traceMax = {
              x: X,
              y: maxY.length === X.length ? maxY : Y,
              type: 'scatter',
              mode: 'lines',
              fill: 'tonexty',
              fillcolor: 'rgba(162, 59, 114, 0.14)',
              line: { width: 0 },
              name: 'Диапазон ТОП-10 (мин - макс)',
              hoverinfo: 'skip'
            };
            const traceAvg = {
              x: X,
              y: Y,
              type: 'scatter',
              mode: 'lines+markers',
              line: { color: '#A23B72', width: 3 },
              marker: { size: 7, color: '#A23B72' },
              name: 'Средняя цена ТОП-10',
              text: hoverTexts,
              hovertemplate: '%{text}<extra></extra>',
              hoverinfo: 'text',
            };
            Plotly.react('avgTop10', [traceMin, traceMax, traceAvg], {
              margin: { t: 10, r: 10, b: 40, l: 50 },
              xaxis: { title: 'Время', type: 'date' },
              yaxis: { title: 'Цена (PLN)' },
              hovermode: 'closest',
              showlegend: false
            }, { responsive: true, displayModeBar: false });
          } else {
            Plotly.react('avgTop10', [], emptyChartLayout('top10'));
          }
          const trendEl = document.getElementById('trendIndexChart');
          if (trendEl && window.Plotly) {
            const trendX = charts.trend_x || [];
            const trendY = charts.trend_y || [];
            const trendDetailed = charts.trend_detailed || [];
            if (trendX.length && trendY.length) {
              const trendHoverTexts = trendDetailed.map((data) => {
                let text = '<b>' + (data.run_time || '') + '</b><br>';
                text += 'Среднее изменение: ' + (data.avg_change_pct || 0).toFixed(2) + '%<br>';
                text += 'Отелей с изменением: ' + (data.hotels_with_changes || 0)
                  + ' / ' + (data.total_hotels || 0);
                return text;
              });
              Plotly.react('trendIndexChart', [{
                x: trendX,
                y: trendY,
                type: 'scatter',
                mode: 'lines+markers',
                line: { color: '#2E86AB', width: 2 },
                marker: { size: 7 },
                text: trendHoverTexts,
                hovertemplate: '%{text}<extra></extra>',
                hoverinfo: 'text',
              }], {
                margin: { t: 10, r: 10, b: 40, l: 50 },
                xaxis: { title: 'Время', type: 'date' },
                yaxis: { title: 'Изменение, %' },
                hovermode: 'closest',
              }, { responsive: true, displayModeBar: false });
            } else {
              Plotly.react('trendIndexChart', [], emptyChartLayout('trend'));
            }
          }
          if (typeof window.renderOffersCountChart === 'function') {
            window.renderOffersCountChart(
              charts.offers_count_dates || [],
              charts.offers_count_values || [],
              charts.offers_count_meta || []
            );
          }
        };

        function formatMetricValue(kind, value) {
          if (kind === 'total_offers') return Number(value).toLocaleString('ru-RU');
          if (kind === 'avg_price' || kind === 'history_min_price' || kind === 'history_max_price') {
            return Number(value).toLocaleString('ru-RU') + ' PLN';
          }
          if (kind === 'market_breadth_pct') return Number(value).toFixed(0) + '%';
          return String(value);
        }

        const storageKey = 'tripDuration:' + window.location.pathname;
        const baseTitle = document.title;

        function resolveBucketId(preferred) {
          const candidate = String(preferred || '').trim();
          if (candidate && views[candidate]) return candidate;
          const fallback = String(switchRoot.dataset.defaultBucket || '').trim();
          if (fallback && views[fallback]) return fallback;
          const keys = Object.keys(views);
          return keys.length ? keys[0] : '';
        }

        window.applyDurationView = function(bucketId) {
          const resolvedId = resolveBucketId(bucketId);
          const view = views[resolvedId];
          if (!view) {
            console.warn('duration view missing:', resolvedId);
            switchRoot.querySelectorAll('.duration-global-btn').forEach((btn) => {
              btn.classList.toggle('active', btn.dataset.durationBucket === resolvedId);
            });
            const cardsGrid = document.getElementById('cardsGrid');
            if (cardsGrid) cardsGrid.innerHTML = '';
            const tbody = document.querySelector('#hotelsTable tbody');
            if (tbody) tbody.innerHTML = '';
            window.__activeDurationHotelNames = new Set();
            try {
              localStorage.setItem(storageKey, resolvedId);
            } catch (err) {
              /* ignore */
            }
            if (location.hash !== '#' + resolvedId) {
              history.replaceState(null, '', '#' + resolvedId);
            }
            if (typeof window._hotelTableFilterRows === 'function') {
              window._hotelTableFilterRows();
            }
            window.renderDashboardDurationCharts({});
            return;
          }

          const hero = view.hero || {};
          const stats = view.stats || {};
          const html = view.html || {};
          const minPriceEl = document.getElementById('heroKpiMinPrice');
          const buyNowEl = document.getElementById('heroKpiBuyNow');
          const dropsEl = document.getElementById('heroKpiDrops48h');
          if (minPriceEl) {
            const rawMin = hero.min_price != null ? hero.min_price : stats.history_min_price;
            minPriceEl.textContent = (rawMin != null && rawMin > 0) ? ('от ' + Math.round(rawMin).toLocaleString('ru-RU') + ' zł') : '—';
          }
          if (buyNowEl) {
            buyNowEl.textContent = String(hero.buy_recommended ?? (hero.entry_candidates ?? 0));
          }
          if (dropsEl) {
            dropsEl.textContent = String(hero.drops_48h ?? 0);
          }
          const entryEl = document.getElementById('heroKpiEntryCount');
          const breadthEl = document.getElementById('heroKpiBreadthPct');
          const bestDealEl = document.getElementById('heroKpiBestDeal');
          if (entryEl) entryEl.textContent = String(hero.entry_candidates ?? '');
          if (breadthEl) breadthEl.textContent = formatMetricValue('market_breadth_pct', hero.market_breadth_pct ?? 0);
          if (bestDealEl) bestDealEl.textContent = String(hero.best_deal_score ?? '');

          const statsRow1 = document.getElementById('statsMetricsRow1');
          const statsRow2 = document.getElementById('statsMetricsRow2');
          if (statsRow1 && view.stats_row1_html) statsRow1.innerHTML = view.stats_row1_html;
          if (statsRow2 && view.stats_row2_html) statsRow2.innerHTML = view.stats_row2_html;

          const changesEl = document.getElementById('durationScopedChanges');
          const entrySignalEl = document.getElementById('durationScopedEntry');
          if (changesEl) changesEl.innerHTML = html.changes || '';
          if (entrySignalEl) entrySignalEl.innerHTML = html.entry_signal || '';

          const alertsChipsEl = document.getElementById('alertsSummaryChips');
          const alertsContentEl = document.getElementById('alertsContent');
          if (alertsChipsEl) alertsChipsEl.innerHTML = html.alerts_chips || '';
          if (alertsContentEl) alertsContentEl.innerHTML = html.alerts_content || '';

          const cardsGrid = document.getElementById('cardsGrid');
          if (cardsGrid) cardsGrid.innerHTML = html.cards || '';

          const tbody = document.querySelector('#hotelsTable tbody');
          if (tbody) {
            tbody.innerHTML = html.table_rows || '';
            if (typeof window._rebindHotelTableRows === 'function') {
              window._rebindHotelTableRows();
            }
          }

          const priceFilter = document.getElementById('priceFilter');
          const regionFilter = document.getElementById('regionFilter');
          if (priceFilter && html.price_filter_options) {
            priceFilter.innerHTML = html.price_filter_options;
          }
          if (regionFilter && html.region_filter_options !== undefined) {
            regionFilter.innerHTML = '<option value="">Все регионы</option>' + (html.region_filter_options || '');
          }

          window.renderDashboardDurationCharts(view.charts || {});
          window.__activeDurationHotelNames = new Set((view.hotel_names || []).map(String));

          switchRoot.querySelectorAll('.duration-global-btn').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.durationBucket === resolvedId);
          });

          if (view.label) {
            const suffix = ' • ' + view.label;
            document.title = baseTitle.includes(suffix)
              ? baseTitle
              : baseTitle.replace(/ • [^•]+$/, '') + suffix;
          }

          try {
            localStorage.setItem(storageKey, resolvedId);
          } catch (err) {
            /* ignore */
          }
          if (location.hash !== '#' + resolvedId) {
            history.replaceState(null, '', '#' + resolvedId);
          }

          if (typeof window._hotelTableFilterRows === 'function') {
            window._hotelTableFilterRows();
          }
        };

        switchRoot.querySelectorAll('.duration-global-btn').forEach((btn) => {
          btn.addEventListener('click', function() {
            window.applyDurationView(btn.dataset.durationBucket || '');
          });
        });

        const hashBucket = (location.hash || '').replace(/^#/, '');
        let storedBucket = '';
        try {
          storedBucket = localStorage.getItem(storageKey) || '';
        } catch (err) {
          storedBucket = '';
        }
        const initialBucket = resolveBucketId(hashBucket || storedBucket || switchRoot.dataset.defaultBucket);
        if (initialBucket) {
          window.applyDurationView(initialBucket);
        }
      })();

      (function() {
        let resizeTimer;
        function resizeVisibleCharts() {
          if (!window.Plotly || !window.Plotly.Plots) return;
          ['avgTop10', 'trendIndexChart', 'timingHeatmap', 'timingBar', 'departureModalChart'].forEach(function(id) {
            const el = document.getElementById(id);
            if (el && el.offsetParent !== null) {
              window.Plotly.Plots.resize(el);
            }
          });
        }
        window.addEventListener('resize', function() {
          clearTimeout(resizeTimer);
          resizeTimer = setTimeout(resizeVisibleCharts, 150);
        });
        window.addEventListener('orientationchange', function() {
          setTimeout(resizeVisibleCharts, 250);
        });
      })();
    </script>
  </body>
</html>
"""

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print(f"✅ Дашборд с встроенными графиками сгенерирован: {output_file}")
    print(f"📊 Статистика: {total_offers} наблюдений, {unique_hotels} отелей в истории, {current_table_hotels} актуально в таблице")
    print(f"💰 Цены: {history_min_price:.0f} - {history_max_price:.0f} PLN (средняя: {avg_price:.0f} PLN)")
    print(f"📈 Изменения цен: {len(decreases_48h) + len(increases_48h)} отелей за 48ч")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Generate inline charts dashboard')
    parser.add_argument('--data-file', default='data/travel_prices.csv')
    parser.add_argument('--output', default='index.html')
    parser.add_argument('--title', default='Travel Price Monitor • Расширенный дашборд')
    parser.add_argument('--charts-dir', default='hotel-charts')
    parser.add_argument('--tz', default='Europe/Warsaw')
    parser.add_argument('--alerts-file', default=None)
    parser.add_argument('--all-airports-data-file', default=None, help='CSV с общим фильтром (любой аэропорт) для сравнения')
    parser.add_argument('--disappeared-after-runs', type=int, default=2, help='Сколько последних ранов подряд должен отсутствовать отель, чтобы считаться выпавшим')
    parser.add_argument('--display-price-ceiling', type=float, default=None, help='Потолок цены для ПОКАЗА в таблице/карточках (дороже — только в истории/статистике)')
    parser.add_argument('--history-price-ceiling', type=float, default=None, help='Потолок для истории/графиков/выпавших (по умолчанию 20000 при заданном display ceiling)')
    parser.add_argument('--write-legacy-hotel-html', action='store_true', help='Дополнительно писать hotel-charts/*.html (для старых ссылок)')
    parser.add_argument('--config-file', default=None, help='JSON конфиг фильтра (иначе — по data_dir из --data-file)')
    parser.add_argument('--ta-live-backfill', action='store_true', default=False, help='Включить live-скрапинг fly.pl для TripAdvisor бэкфилла')
    parser.add_argument('--force-ai', action='store_true', default=False, help='Принудительно сбросить AI-кэш и пересчитать всё заново')
    args = parser.parse_args()
    generate_inline_charts_dashboard(
        data_file=args.data_file,
        output_file=args.output,
        title=args.title,
        charts_subdir=args.charts_dir,
        tz=args.tz,
        alerts_file=args.alerts_file,
        all_airports_data_file=args.all_airports_data_file,
        disappeared_after_runs=args.disappeared_after_runs,
        display_price_ceiling=args.display_price_ceiling,
        history_price_ceiling=args.history_price_ceiling,
        write_legacy_hotel_html=args.write_legacy_hotel_html,
        config_file=args.config_file,
        enable_ta_live_backfill=args.ta_live_backfill,
        force_ai=args.force_ai,
    )
