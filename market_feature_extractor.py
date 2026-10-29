#!/usr/bin/env python3
"""
Market Feature Extractor for AI Market Intelligence.

Distills raw filter scrapes, historical Market DNA, and cross-border arbitrage data
into a dense, highly structured JSON context (~2 KB) optimized for LLM synthesis.

Extracts:
1. Macro Filter Snapshot (Phase, Days-to-Departure distribution, 24h price trend).
2. Floor Breakers (Hotels currently trading at or near historical season minimum).
3. Top Price Movers (Highest 24h drops and spikes).
4. Cross-Border Arbitrage Highlights (Poland vs Germany Check24 price delta).
5. Curated Top Candidates for deep individual AI Booking Dossiers.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from build_market_dna import parse_departure_date, parse_scraped_date, get_d_bucket, extract_operator_from_url

try:
    from early_booking_analyzer import analyze_dataframe as analyze_early_booking
except ImportError:
    analyze_early_booking = None

logger = logging.getLogger("feature_extractor")
DEFAULT_DNA_FILE = "market_dna_profile.json"
DEFAULT_REPUTATION_KB_FILE = "hotel_reputation_kb.json"

BUCKET_CONFIG: Dict[str, Tuple[str, int, int]] = {
    "last_minute": ("D-1…D-3", 1, 3),
    "panic_dump": ("D-4…D-7", 4, 7),
    "first_markdown": ("D-8…D-14", 8, 14),
    "mid_term": ("D-15…D-30", 15, 30),
    "early_bird": ("D-30+", 31, 180),
    # Display label aliases
    "D-1…D-3": ("D-1…D-3", 1, 3),
    "D-1...D-3": ("D-1…D-3", 1, 3),
    "D-4…D-7": ("D-4…D-7", 4, 7),
    "D-4...D-7": ("D-4…D-7", 4, 7),
    "D-8…D-14": ("D-8…D-14", 8, 14),
    "D-8...D-14": ("D-8…D-14", 8, 14),
    "D-15…D-30": ("D-15…D-30", 15, 30),
    "D-15...D-30": ("D-15…D-30", 15, 30),
    "D-30+": ("D-30+", 31, 180),
}


def infer_stars(hotel_name: str, row: pd.Series, dna: Optional[Dict[str, Any]] = None) -> int:
    """Infers hotel star rating (3, 4, 5). Defaults to 5 if luxury brand, else 4."""
    for col in ("stars", "hotel_stars", "star_rating"):
        if col in row and pd.notna(row[col]):
            try:
                s = int(float(row[col]))
                if s in (3, 4, 5):
                    return s
            except (ValueError, TypeError):
                pass
    h_lower = hotel_name.lower()
    m = re.search(r"(\d)\s*(?:\*|★|star)", h_lower)
    if m:
        s = int(m.group(1))
        if s in (3, 4, 5):
            return s
    if dna and "stars" in dna:
        try:
            return int(dna["stars"])
        except (ValueError, TypeError):
            pass
    luxury_chains = [
        "rixos", "baron", "four seasons", "kempinski", "albatros", "steigenberger",
        "hilton", "marriott", "sheraton", "movenpick", "jaz", "concorde", "sentido",
        "delphin", "voyage", "maxx royal", "titanic", "gural", "crystal"
    ]
    if any(c in h_lower for c in luxury_chains):
        return 5
    return 4


def infer_meal_plan(row: pd.Series) -> str:
    """Infers meal plan / board type (all_inclusive, half_board, breakfast)."""
    for col in ("catering", "board", "meal_plan", "meal"):
        if col in row and pd.notna(row[col]):
            val = str(row[col]).lower().strip()
            if any(k in val for k in ("all", "ai", "все включено", "wszystko")):
                return "all_inclusive"
            if any(k in val for k in ("hb", "half", "полупансион", "dwa posiłki")):
                return "half_board"
            if any(k in val for k in ("bb", "bed", "завтрак", "śniadani")):
                return "breakfast"
    url_str = (str(row.get("offer_url") or "") + " " + str(row.get("url") or "")).lower()
    if "catering=all_inclusive" in url_str:
        return "all_inclusive"
    if "catering=half_board" in url_str or "catering=hb" in url_str:
        return "half_board"
    if "catering=breakfast" in url_str or "catering=bb" in url_str:
        return "breakfast"
    return "all_inclusive"


def resolve_booking_window(
    h_dna: Optional[Dict[str, Any]],
    d_days: Optional[int],
    cur_p: Optional[float] = None,
) -> Dict[str, str]:
    """Computes hotel-specific optimal booking window based on historical D-Minus yield curve."""
    default_res = {
        "optimal_window": "D-14…D-21",
        "window_status": "unknown",
        "window_badge": "",
        "window_class": "early",
        "window_tip": "Историческое окно максимальной выгоды для этого типа отелей наступает за 14–21 день до вылета.",
    }
    hist_med = float(h_dna.get("median_price", 0.0)) if h_dna else 0.0
    best_bucket = None
    if h_dna:
        if h_dna.get("sweet_spot_d_bucket") in BUCKET_CONFIG:
            best_bucket = h_dna.get("sweet_spot_d_bucket")
        elif "d_bucket_medians" in h_dna:
            b_medians = {k: v for k, v in h_dna.get("d_bucket_medians", {}).items() if v > 0 and k in BUCKET_CONFIG}
            if b_medians:
                best_bucket = min(b_medians.items(), key=lambda x: x[1])[0]

    if d_days is not None and d_days <= 3:
        if cur_p is not None and hist_med > 0 and cur_p > (hist_med * 1.02):
            pass
        else:
            lbl = f"вылет через {d_days} дн.!" if d_days > 0 else "вылет сегодня!"
            return {
                "optimal_window": "D-0…D-3",
                "window_status": "panic",
                "window_badge": f"🔥 Горящий тур: {lbl}",
                "window_class": "panic",
                "window_tip": f"Срочный вылет ({d_days} дн.), туроператор сбрасывает оставшиеся места на рейсе.",
            }

    if not best_bucket or best_bucket not in BUCKET_CONFIG:
        return default_res

    w_label, w_min, w_max = BUCKET_CONFIG[best_bucket]

    if d_days is None:
        return {
            "optimal_window": w_label,
            "window_status": "unknown",
            "window_badge": "",
            "window_class": "early",
            "window_tip": f"Исторический минимум цены для этого отеля достигается за {w_label}.",
        }

    if w_min <= d_days <= w_max:
        # Rule of Silence: Only award "🎯 Окно покупки" if the price is actually good (not overpriced or ordinary!)
        # The price must be noticeably below historical median (at least 2% below median)
        if cur_p is not None and hist_med > 0 and cur_p > (hist_med * 0.98):
            return {
                "optimal_window": w_label,
                "window_status": "in_window_normal",
                "window_badge": "",
                "window_class": "in_window",
                "window_tip": f"Период {w_label} исторически благоприятен для покупки, но сейчас отель продаётся по обычной цене ({cur_p:,.0f} zł при норме {hist_med:,.0f} zł).",
            }
        return {
            "optimal_window": w_label,
            "window_status": "in_window",
            "window_badge": f"🎯 Окно покупки: {w_label} (сейчас!)",
            "window_class": "in_window",
            "window_tip": f"Текущий момент (D-{d_days}) совпадает со скидочным окном ({w_label}), и цена снижена относительно нормы ({cur_p:,.0f} zł при медиане {hist_med:,.0f} zł).",
        }
    elif d_days > w_max:
        return {
            "optimal_window": w_label,
            "window_status": "early",
            "window_badge": "",
            "window_class": "early",
            "window_tip": f"Историческое дно цены наступает за {w_label}. Сейчас D-{d_days} (рано).",
        }
    else:
        return {
            "optimal_window": w_label,
            "window_status": "late",
            "window_badge": "",
            "window_class": "late",
            "window_tip": f"Окно максимальных скидок ({w_label}) уже прошло. Текущий день: D-{d_days}.",
        }


OPERATOR_NAME_MAP: Dict[str, str] = {
    "CORAL": "Coral Travel",
    "ITAKA": "Itaka",
    "EXIM": "Exim Tours",
    "OREX": "Orex Travel",
    "JOIN": "Join UP!",
    "ANEX": "Anex Tour",
    "WEZY": "Coral Travel (Wezyr)",
    "BVBE": "Best Reisen",
    "TUI": "TUI Poland",
    "SUNF": "Sun & Fun",
    "REIS": "Reisebureau",
}


def get_hotel_reputation_metadata(
    hotel_name: str,
    destination_hint: str = "",
    kb_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extracts contextual reputation intelligence, geography/bay profile,
    and suitability (family, winter shelter, aquapark, reef quality).
    Merges deep AI intelligence from hotel_reputation_kb.json if available.
    """
    h_lower = hotel_name.lower()
    dest_hint_lower = (destination_hint or "").lower()

    # Determine target destination from filter or context
    is_target_turkey = any(k in dest_hint_lower for k in ("турци", "turkey", "turcja", "анталья", "сиде", "кемер", "белек", "аланья", "мармарис", "бодрум", "фетхие"))
    is_target_cyprus = any(k in dest_hint_lower for k in ("кипр", "cypr", "cyprus", "пафос", "айя-напа", "айя напа", "протарас", "ларнака", "лимассол"))
    is_target_greece = any(k in dest_hint_lower for k in ("грец", "greece", "grecja", "крит", "родос", "корфу", "кос", "закинф"))
    is_target_spain = any(k in dest_hint_lower for k in ("испан", "spain", "hiszpania", "майорка", "тенерифе", "барселона", "коста"))
    is_target_egypt = any(k in dest_hint_lower for k in ("египет", "egypt", "красное море", "шарм", "хургада", "марса", "эль гуна", "сахл хашиш"))

    # If destination_hint was ambiguous or generic, infer from hotel name
    if not (is_target_turkey or is_target_cyprus or is_target_greece or is_target_spain or is_target_egypt):
        if any(k in h_lower for k in ("sharm", "hurghada", "makadi", "el gouna", "gouna", "marsa alam", "sahl hasheesh", "ras um sid", "naama", "nabq")):
            is_target_egypt = True
        elif any(k in h_lower for k in ("side", "alanya", "kemer", "belek", "antalya", "lara", "kundu", "avsallar", "konakli", "manavgat", "marmaris", "bodrum", "fethiye")):
            is_target_turkey = True
        elif any(k in h_lower for k in ("cyprus", "paphos", "ayia napa", "protaras", "larnaca", "limassol")):
            is_target_cyprus = True
        elif any(k in h_lower for k in ("crete", "rhodes", "corfu", "kos", "greece")):
            is_target_greece = True
        elif any(k in h_lower for k in ("spain", "mallorca", "tenerife", "murcia", "costa")):
            is_target_spain = True

    bay_or_area = ""
    wind_shelter = ""
    beach_profile = ""
    winter_comfort = ""

    if is_target_turkey:
        if any(k in h_lower for k in ("side", "kumkoy", "evrenseki", "colakli", "titreyengol", "manavgat", "sorgun", "kizilot", "kizilagac", "sueno", "kamelya", "club side coast", "mira meridia", "verbena")):
            bay_or_area = "Сиде / Манавгат (Side)"
            wind_shelter = "Широкая береговая линия, пологий заход"
            beach_profile = "Широкий пологий песчаный вход в море, идеален для детей"
            winter_comfort = "Живой курорт с красивым променадом вдоль античного города"
        elif any(k in h_lower for k in ("alanya", "konakli", "avsallar", "okurcalar", "mahmutlar", "incekum", "eftalia", "xoria", "arancia", "kaila", "rubi", "long beach", "numa", "numa bay", "gypsophila")):
            bay_or_area = "Аланья / Конаклы / Авсаллар"
            wind_shelter = "Самый теплый регион Анталийского побережья"
            beach_profile = "Песчано-галечный пляж, в Авсалларе (Инжекум) мягкий песок"
            winter_comfort = "Мягкий климат, море дольше всего сохраняет тепло осенью"
        elif any(k in h_lower for k in ("kemer", "beldibi", "goynuk", "kiris", "camyuva", "tekirova", "meder", "sungate", "alva donna world", "royal diwa")):
            bay_or_area = "Кемер (Kemer)"
            wind_shelter = "Окружен хвойными Таврскими горами"
            beach_profile = "Кристально чистая прозрачная вода, галька и пирсы"
            winter_comfort = "Хвойный воздух и горы, в межсезонье приятный прохладный бриз"
        elif any(k in h_lower for k in ("belek", "kadriye", "bogazkent", "land of legends", "selectum", "papillon", "gural premier", "pine beach", "maritim pine")):
            bay_or_area = "Белек (Belek)"
            wind_shelter = "Элитный курорт среди хвойных и эвкалиптовых рощ"
            beach_profile = "Широкий песчаный пляж с мелкой галькой у кромки воды"
            winter_comfort = "Премиальные отели с круглогодичными теплыми бассейнами и спа"
        elif any(k in h_lower for k in ("lara", "kundu", "barut lara", "delphin imperial", "delphin be grand", "delphin diva", "titanic mardan", "concorde de luxe")):
            bay_or_area = "Анталья / Лара (Lara Beach)"
            wind_shelter = "Быстрый трансфер из аэропорта (15–20 мин)"
            beach_profile = "Широкий золотой песчаный пляж"
            winter_comfort = "Отели-дворцы с круглогодичной инфраструктурой и теплыми бассейнами"
        else:
            bay_or_area = "Анталийское побережье"
            wind_shelter = "Средиземноморское побережье"
            beach_profile = "Песчано-галечный пляж с удобным входом в море"
            winter_comfort = "Мягкий климат, развитая инфраструктура"

    elif is_target_cyprus:
        if any(k in h_lower for k in ("ayia napa", "nissi", "ая напа", "айя-напа")):
            bay_or_area = "Айя-Напа (Ayia Napa)"
            wind_shelter = "Песчаные бухты, защищенные от волн"
            beach_profile = "Белоснежный песок и лазурная прозрачная вода"
            winter_comfort = "Живописные прогулки вдоль побережья и мыса Греко"
        elif any(k in h_lower for k in ("protaras", "fig tree", "протарас")):
            bay_or_area = "Протарас (Protaras)"
            wind_shelter = "Уютные закрытые бухты"
            beach_profile = "Золотистый песок и плавный пологий вход в воду"
            winter_comfort = "Спокойный курортный отдых у моря"
        elif any(k in h_lower for k in ("paphos", "пафос")):
            bay_or_area = "Пафос (Paphos)"
            wind_shelter = "Западное побережье Кипра"
            beach_profile = "Скалистые и песчано-галечные бухты"
            winter_comfort = "Богатая античная история, живописная набережная"
        elif any(k in h_lower for k in ("limassol", "лимассол")):
            bay_or_area = "Лимассол (Limassol)"
            wind_shelter = "Южное побережье Кипра"
            beach_profile = "Темный вулканический песок, пологий вход"
            winter_comfort = "Круглогодичный активный город с красивым променадом Молос"
        elif any(k in h_lower for k in ("larnaca", "ларнака")):
            bay_or_area = "Ларнака (Larnaca)"
            wind_shelter = "Спокойное мелкое море"
            beach_profile = "Широкий песчано-галечный пляж Финикудес"
            winter_comfort = "Быстрый трансфер, знаменитая пальмовая аллея"
        else:
            bay_or_area = "Кипр"
            wind_shelter = "Средиземноморское побережье"
            beach_profile = "Бирюзовые лагуны и золотистый песок"
            winter_comfort = "Мягкая теплая средиземноморская зима"

    elif is_target_greece:
        bay_or_area = "Греческие острова"
        wind_shelter = "Средиземное и Эгейское моря"
        beach_profile = "Живописные песчаные и галечные бухты"
        winter_comfort = "Мягкий климат, экскурсионный сезон"

    elif is_target_spain:
        bay_or_area = "Испания"
        wind_shelter = "Средиземноморское побережье"
        beach_profile = "Широкие благоустроенные пляжи"
        winter_comfort = "Приятный климат, богатая экскурсионная программа"

    elif is_target_egypt:
        # Sharm El Sheikh Bays
        if any(k in h_lower for k in ("naama", "promenade")) or (any(k in h_lower for k in ("sharm", "шарм")) and any(k in h_lower for k in ("novotel", "maritim", "tropitel", "movenpick"))):
            bay_or_area = "Бухта Наама Бэй (Naama Bay)"
            wind_shelter = "Защищена от ветра (комфортна зимой)"
            beach_profile = "Песчаный пологий вход в море, без обязательного понтона"
            winter_comfort = "Высокий: защищена горами от зимних ветров, море спокойное"
        elif any(k in h_lower for k in ("hadaba", "ras um sid", "faraana", "jaz fanara", "reef oasis")) or (any(k in h_lower for k in ("sharm", "шарм")) and any(k in h_lower for k in ("renaissance", "sentido"))):
            bay_or_area = "Бухта Рас Ум Сид / Хадаба"
            wind_shelter = "Защищена от ветра высокими скалами"
            beach_profile = "Один из лучших живых коралловых рифов Шарма"
            winter_comfort = "Высокий: безветренная бухта, идеальна для плавания зимой"
        elif any(k in h_lower for k in ("shark", "sultan gardens", "grand rotana", "white knight")):
            bay_or_area = "Бухта Шаркс Бэй (Shark's Bay)"
            wind_shelter = "Умеренный ветер, открытый вид на остров Тиран"
            beach_profile = "Красивый коралловый риф, заход с понтона"
            winter_comfort = "Средний: при сильном ветре возможны волны"
        elif any(k in h_lower for k in ("nabq", "rehana", "rixos premium seagate", "albatros laguna")) or (any(k in h_lower for k in ("sharm", "шарм")) and any(k in h_lower for k in ("amwaj", "cleopatra", "parrotel", "barcelo"))):
            bay_or_area = "Бухта Набк (Nabq Bay)"
            wind_shelter = "Открытая бухта, подвержена зимним ветрам"
            beach_profile = "Длинный понтон (до 500-800 м) через мелководный коралловый риф"
            winter_comfort = "Низкий зимой: частые ветра, возможен красный флаг на понтоне"
        # Hurghada Areas
        elif any(k in h_lower for k in ("makadi", "tia heights", "jaz makadi", "cleopatra makadi")):
            bay_or_area = "Бухта Макади Бэй (Makadi Bay)"
            wind_shelter = "Умеренно защищенная бухта"
            beach_profile = "Песчаный пляж с участками рифа"
            winter_comfort = "Хороший: песчаный заход и красивый подводный мир"
        elif any(k in h_lower for k in ("sahl hasheesh", "baron palace", "gravity", "old palace", "citadel azur")):
            bay_or_area = "Сахл Хашиш (Sahl Hasheesh)"
            wind_shelter = "Премиальная курортная зона с длинным променадом"
            beach_profile = "Широкий песчаный пляж"
            winter_comfort = "Высокий: красивый променад и качественный сервис"
        elif any(k in h_lower for k in ("el gouna", "gouna", "mangroovy", "creek hotel")):
            bay_or_area = "Эль Гуна (El Gouna)"
            wind_shelter = "Египетская Венеция с лагунами и каналами"
            beach_profile = "Лагуны и песчаные отмели"
            winter_comfort = "Европейский сервис, идеально для кайтинга и спокойного отдыха"
        elif any(k in h_lower for k in ("marsa alam", "port ghalib", "brayka", "sataya", "lazuli", "akassia")):
            bay_or_area = "Марса Алам / Порт Галиб"
            wind_shelter = "Открытое побережье Красного моря"
            beach_profile = "Нетронутые коралловые рифы с морскими черепахами и дюгонями"
            winter_comfort = "Для дайвинга и снорклинга; зимой возможны волны"
        else:
            bay_or_area = "Красное море"
            wind_shelter = "Побережье Красного моря"
            beach_profile = "Песчаный пляж с коралловым рифом"
            winter_comfort = "Теплое море круглый год"
    else:
        bay_or_area = "Курортный регион"
        wind_shelter = "Побережье"
        beach_profile = "Песчано-галечный пляж с удобным входом в море"
        winter_comfort = "Мягкий климат"

    # Family & Aquapark profiling
    has_aquapark = any(k in h_lower for k in (
        "aqua", "park", "water", "splash", "slide", "аквапарк",
        "eftalia", "land of legends", "titanic", "ali bey", "delphin",
        "granada", "long beach", "vonresort", "voyage", "paloma", "kamelya", "pegasos"
    ))
    is_adults_only = any(k in h_lower for k in ("adults", "16+", "18+", "только для взрослых"))
    family_friendly = not is_adults_only and (
        has_aquapark or any(k in h_lower for k in ("family", "kids", "albatros", "pickalbatros", "jaz", "sunrise", "eftalia", "delphin", "voyage", "barut"))
    )

    # Winter amenities (heated pools)
    has_heated_pool = any(k in h_lower for k in (
        "albatros", "pickalbatros", "rixos", "jaz", "baron", "sunrise", "steigenberger",
        "four seasons", "promenade", "maritim", "delphin", "voyage", "maxx royal", "titanic",
        "barut", "akra", "concorde", "alva donna", "dobedan", "gural", "kaya", "cullinan", "regnum"
    ))

    # Merge deep intelligence from KB if available
    kb_hotels = {}
    if isinstance(kb_data, dict):
        if "hotels" in kb_data and isinstance(kb_data["hotels"], dict):
            kb_hotels = kb_data["hotels"]
        else:
            kb_hotels = kb_data

    season_trend_dict: Dict[str, Any] = {}
    sentiment_scores_dict: Dict[str, Any] = {}
    family_and_kids_dict: Dict[str, Any] = {}
    pros_list: List[str] = []
    cons_list: List[str] = []
    verdict_text = ""

    if hotel_name in kb_hotels:
        kb_h = kb_hotels[hotel_name]
        fam = kb_h.get("family_and_kids", {})
        wint = kb_h.get("winter_suitability", {})
        strend = kb_h.get("season_trend", {})

        kb_bay = wint.get("bay", "")
        kb_wind = wint.get("wind_shelter", "")
        kb_beach = fam.get("beach_entry", "")

        is_non_egypt = is_target_turkey or is_target_cyprus or is_target_greece or is_target_spain
        egypt_tokens = ("наама", "рас ум сид", "хадаба", "шаркс", "набк", "макади", "сахл хашиш", "эль гуна", "марса алам", "красное море", "тиран")

        if is_non_egypt:
            # Drop any Red Sea / Egyptian bay metadata from KB
            if kb_bay and not any(et in kb_bay.lower() for et in egypt_tokens):
                bay_or_area = kb_bay
            if kb_wind and not any(et in kb_wind.lower() for et in egypt_tokens) and "скалист" not in kb_wind.lower():
                wind_shelter = kb_wind
            if kb_beach and not any(et in kb_beach.lower() for et in ("риф", "понтон", "коралл")):
                beach_profile = kb_beach
        else:
            if kb_bay:
                bay_or_area = kb_bay
            if kb_wind:
                wind_shelter = kb_wind
            if kb_beach:
                beach_profile = kb_beach

        if fam.get("suitable_for_children") or float(fam.get("score", 0) or 0) >= 7.5:
            family_friendly = True

        if wint.get("heated_pools"):
            has_heated_pool = True

        kids_fac = str(fam.get("kids_facilities", "")).lower()
        if "аквапарк" in kids_fac or "горк" in kids_fac:
            has_aquapark = True

        season_trend_dict = strend
        sentiment_scores_dict = kb_h.get("sentiment_scores", {})
        family_and_kids_dict = fam
        pros_list = kb_h.get("pros", [])
        cons_list = kb_h.get("cons_and_red_flags", [])
        verdict_text = kb_h.get("verdict", "")

        # Geographic sanity check: Coral reefs and Red Sea bays only belong to Egypt
        dest_val = f"{kb_h.get('destination', '')} {destination_hint}".lower()
        is_egypt_loc = not is_non_egypt and any(k in dest_val for k in ("египет", "egypt", "красное море", "шарм", "хургада", "марса"))
        if not is_egypt_loc:
            pros_list = [p for p in pros_list if not any(k in p.lower() for k in ("кораллов", "снорклин", "риф", "безветренная бухта", "тиран"))]
            if not pros_list:
                pros_list = [
                    "Удобное расположение относительно моря и курортной инфраструктуры",
                    "Чистое море и благоустроенная пляжная зона"
                ]
            if any(k in beach_profile.lower() for k in ("риф", "понтон", "коралл")):
                beach_profile = "Песчано-галечный пляж с удобным входом в море"
            if any(k in wind_shelter.lower() for k in ("риф", "скалист", "тиран", "северного ветра", "горами от зимних")):
                wind_shelter = "Средиземноморское побережье"
            if any(k in winter_comfort.lower() for k in ("безветренная бухта", "купания в декабре-феврале", "красного моря")):
                winter_comfort = "Мягкий средиземноморский климат"

    highlights_list = []
    if bay_or_area:
        highlights_list.append(bay_or_area)
    if beach_profile and beach_profile != "Курортный комплекс":
        highlights_list.append(beach_profile)
    if has_aquapark:
        highlights_list.append("Аквапарк / водные горки")
    if has_heated_pool:
        highlights_list.append("Подогреваемый бассейн")
    if is_adults_only:
        highlights_list.append("Только для взрослых (16+)")
    elif family_friendly:
        highlights_list.append("Подходит для семей с детьми")

    base_res = {
        "bay_or_area": bay_or_area,
        "wind_shelter_winter": wind_shelter,
        "beach_profile": beach_profile,
        "winter_comfort": winter_comfort,
        "has_aquapark": has_aquapark,
        "has_heated_pool": has_heated_pool,
        "family_friendly": family_friendly,
        "is_adults_only": is_adults_only,
        "season_trend": season_trend_dict,
        "sentiment_scores": sentiment_scores_dict,
        "family_and_kids": family_and_kids_dict,
        "pros": pros_list,
        "cons_and_red_flags": cons_list,
        "verdict": verdict_text,
        "highlights": ", ".join(highlights_list) if highlights_list else "Курортный комплекс",
    }

    return base_res


def calculate_market_trends(df: pd.DataFrame) -> Dict[str, Any]:
    """Computes historical market trend (7-day and 14-day median price movement)."""
    if "scraped_at" not in df.columns or "price" not in df.columns:
        return {}
    df_clean = df.dropna(subset=["price", "scraped_at"]).copy()
    if df_clean.empty:
        return {}
    df_clean["scraped_dt"] = pd.to_datetime(df_clean["scraped_at"], errors="coerce", utc=True)
    df_clean = df_clean.dropna(subset=["scraped_dt"])
    if df_clean.empty:
        return {}

    now_max = df_clean["scraped_dt"].max()
    p_current = df_clean[df_clean["scraped_dt"] >= (now_max - pd.Timedelta(days=1))]["price"]
    med_current = float(p_current.median()) if len(p_current) > 0 else float(df_clean["price"].median())

    p_7d = df_clean[(df_clean["scraped_dt"] >= (now_max - pd.Timedelta(days=8))) & (df_clean["scraped_dt"] <= (now_max - pd.Timedelta(days=6)))]["price"]
    med_7d = float(p_7d.median()) if len(p_7d) > 0 else None

    p_14d = df_clean[(df_clean["scraped_dt"] >= (now_max - pd.Timedelta(days=16))) & (df_clean["scraped_dt"] <= (now_max - pd.Timedelta(days=13)))]["price"]
    med_14d = float(p_14d.median()) if len(p_14d) > 0 else None

    res: Dict[str, Any] = {
        "current_median": round(med_current, 0),
        "sample_records_analyzed": len(df_clean),
    }
    if med_7d and med_7d > 0:
        res["trend_7d_pct"] = round(((med_current - med_7d) / med_7d) * 100.0, 1)
        res["median_7d_ago"] = round(med_7d, 0)
        res["delta_7d_pln"] = round(med_current - med_7d, 0)
    else:
        res["trend_7d_pct"] = 0.0
        res["median_7d_ago"] = round(med_current, 0)
        res["delta_7d_pln"] = 0.0

    if med_14d and med_14d > 0:
        res["trend_14d_pct"] = round(((med_current - med_14d) / med_14d) * 100.0, 1)
        res["median_14d_ago"] = round(med_14d, 0)
    else:
        res["trend_14d_pct"] = None

    t_pct = res.get("trend_7d_pct", 0.0)
    if t_pct <= -2.5:
        res["market_direction"] = "FALLING"
        res["direction_label"] = f"Рынок падает ({t_pct:+.1f}% за неделю)"
    elif t_pct >= 2.5:
        res["market_direction"] = "RISING"
        res["direction_label"] = f"Рынок растет ({t_pct:+.1f}% за неделю)"
    else:
        res["market_direction"] = "STABLE"
        res["direction_label"] = "Цены стабильны (без резких колебаний за 7 дней)"

    return res


def calculate_airports_comparison(df: pd.DataFrame, latest_per_hotel: pd.DataFrame) -> Dict[str, Any]:
    """Compares departure airports from latest scrape."""
    if "departure_airport" not in df.columns or "price" not in df.columns:
        return {}
    recent_df = df.dropna(subset=["price", "departure_airport"]).copy()
    if recent_df.empty:
        return {}

    airport_stats: Dict[str, Dict[str, Any]] = {}
    for apt, grp in recent_df.groupby("departure_airport"):
        code = str(apt).strip()
        if not code or code.lower() in ("nan", "none", "unknown"):
            continue
        plist = grp["price"].dropna().astype(float).values
        if len(plist) > 0:
            airport_stats[code] = {
                "min_price": round(float(np.min(plist)), 0),
                "median_price": round(float(np.median(plist)), 0),
                "offer_count": int(len(plist)),
            }

    if len(airport_stats) <= 1:
        return {"multi_airport": False, "airports": airport_stats}

    sorted_apts = sorted(airport_stats.items(), key=lambda x: x[1]["median_price"])
    cheapest_code, cheapest_data = sorted_apts[0]
    expensive_code, expensive_data = sorted_apts[-1]
    spread = round(expensive_data["median_price"] - cheapest_data["median_price"], 0)

    return {
        "multi_airport": True,
        "cheapest_hub": cheapest_code,
        "cheapest_median": cheapest_data["median_price"],
        "expensive_hub": expensive_code,
        "expensive_median": expensive_data["median_price"],
        "spread_pln": spread,
        "insight": f"Вылет из {cheapest_code} в среднем на {spread:,.0f} zł дешевле, чем из {expensive_code}",
        "all_hubs": airport_stats,
    }


def calculate_duration_comparison(df: pd.DataFrame) -> Dict[str, Any]:
    """Compares price differences between stay lengths (e.g., 7 days vs 10 days)."""
    if "duration" not in df.columns or "price" not in df.columns:
        return {}

    dur_df = df.dropna(subset=["price", "duration"]).copy()
    if dur_df.empty:
        return {}

    def _extract_days(val: Any) -> Optional[int]:
        m = re.search(r"(\d+)\s*(?:d|n|дн|ноч)", str(val).lower())
        if m:
            return int(m.group(1))
        m2 = re.search(r"^(\d+)$", str(val).strip())
        if m2:
            return int(m2.group(1))
        return None

    dur_df["days"] = dur_df["duration"].apply(_extract_days)
    dur_df = dur_df.dropna(subset=["days"])
    if dur_df.empty:
        return {}

    duration_stats: Dict[int, Dict[str, Any]] = {}
    for d_int, grp in dur_df.groupby("days"):
        plist = grp["price"].dropna().astype(float).values
        if len(plist) >= 2:
            duration_stats[int(d_int)] = {
                "days": int(d_int),
                "min_price": round(float(np.min(plist)), 0),
                "median_price": round(float(np.median(plist)), 0),
                "count": len(plist),
            }

    if len(duration_stats) <= 1:
        return {"multi_duration": False, "durations": duration_stats}

    sorted_durations = sorted(duration_stats.items(), key=lambda x: x[0])
    short_days, short_data = sorted_durations[0]
    long_days, long_data = sorted_durations[-1]

    day_diff = long_days - short_days
    price_diff = round(long_data["median_price"] - short_data["median_price"], 0)
    cost_per_extra_day = round(price_diff / max(1, day_diff), 0)

    insight = f"Доплата за отдых {long_days} дн. вместо {short_days} дн. составляет {price_diff:,.0f} zł ({cost_per_extra_day:,.0f} zł в день)"

    return {
        "multi_duration": True,
        "shorter_duration_days": short_days,
        "shorter_median": short_data["median_price"],
        "longer_duration_days": long_days,
        "longer_median": long_data["median_price"],
        "delta_days": day_diff,
        "delta_pln": price_diff,
        "cost_per_extra_day_pln": cost_per_extra_day,
        "insight": insight,
        "all_durations": {f"{k}d": v for k, v in duration_stats.items()},
    }


def extract_stay_days(val: Any) -> Optional[int]:
    """Extracts integer stay duration in days/nights (e.g. '14 dni' -> 14)."""
    if val is None:
        return None
    s = str(val).lower()
    m = re.search(r"(\d+)\s*(?:d|n|дн|ноч)", s)
    if m:
        return int(m.group(1))
    m2 = re.search(r"^(\d+)$", s.strip())
    if m2:
        return int(m2.group(1))
    return None


def extract_filter_features(
    prices_csv_path: str,
    dna_profile_path: str = DEFAULT_DNA_FILE,
    filter_id: Optional[str] = None,
    filter_title: Optional[str] = None,
    arbitrage_matches: Optional[List[Dict[str, Any]]] = None,
    reputation_kb_path: str = DEFAULT_REPUTATION_KB_FILE,
) -> Dict[str, Any]:
    """
    Extracts structured market features from a filter's travel_prices.csv.
    """
    if not os.path.exists(prices_csv_path):
        raise FileNotFoundError(f"Prices CSV not found: {prices_csv_path}")

    df = pd.read_csv(prices_csv_path)
    if "hotel_name" not in df.columns or "price" not in df.columns:
        raise ValueError(f"Invalid prices CSV structure in {prices_csv_path}")

    # Load DNA profile if present
    dna_hotels: Dict[str, Any] = {}
    macro_dna: Dict[str, Any] = {}
    if os.path.exists(dna_profile_path):
        try:
            with open(dna_profile_path, "r", encoding="utf-8") as f:
                dna_data = json.load(f)
                dna_hotels = dna_data.get("hotel_profiles", {})
                macro_dna = dna_data.get("macro_profile", {})
        except Exception as e:
            logger.warning(f"Could not load DNA profile from {dna_profile_path}: {e}")

    # Load Hotel Reputation Knowledge Base if present
    reputation_kb: Dict[str, Any] = {}
    kb_candidates = [
        reputation_kb_path,
        os.path.join(os.path.dirname(prices_csv_path), "hotel_reputation_kb.json"),
        "hotel_reputation_kb.json",
        os.path.join(os.path.dirname(__file__), "hotel_reputation_kb.json"),
    ]
    for p in kb_candidates:
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    reputation_kb = json.load(f)
                break
            except Exception as e:
                logger.warning(f"Could not load Reputation KB from {p}: {e}")

    # Filter out invalid / domestic outlier rows (< 1000 PLN)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price", "hotel_name"])
    df = df[df["price"] >= 1000.0]

    if df.empty:
        return {"error": "No valid package tour rows found."}

    # Dedup by hotel_name keeping latest
    latest_per_hotel = df.sort_values(by="scraped_at", ascending=True).groupby("hotel_name").last().reset_index()

    prices = latest_per_hotel["price"].values
    med_price = float(np.median(prices))
    min_price = float(np.min(prices))
    max_price = float(np.max(prices))
    p10_price = float(np.percentile(prices, 10))
    p90_price = float(np.percentile(prices, 90))

    # Stay duration profiling (e.g. 7-10 nights vs long 13-16 nights / 2 weeks)
    trip_days_list: List[int] = []
    latest_ts = df["scraped_at"].max() if "scraped_at" in df.columns else None
    active_slice = df[df["scraped_at"] == latest_ts] if latest_ts is not None else latest_per_hotel
    source_df = active_slice if "duration" in active_slice.columns else latest_per_hotel
    if "duration" in source_df.columns:
        for val in source_df["duration"].dropna():
            d_len = extract_stay_days(val)
            if d_len and 2 <= d_len <= 35:
                trip_days_list.append(d_len)

    if trip_days_list:
        min_trip_days = int(min(trip_days_list))
        max_trip_days = int(max(trip_days_list))
        med_trip_days = int(np.median(trip_days_list))
    else:
        # Fallback from filter_title, filter_id, or path (e.g. 13_16 or 7_10)
        m_span = re.search(r"(\d+)[\-_–:](\d+)", f"{filter_id or ''} {filter_title or ''} {prices_csv_path}")
        if m_span:
            min_trip_days = int(m_span.group(1))
            max_trip_days = int(m_span.group(2))
            med_trip_days = int(round((min_trip_days + max_trip_days) / 2))
        else:
            min_trip_days, max_trip_days, med_trip_days = 7, 10, 8

    if min_trip_days == max_trip_days:
        trip_duration_label = f"{min_trip_days} ночей"
    else:
        trip_duration_label = f"{min_trip_days}–{max_trip_days} ночей"

    if med_trip_days >= 12:
        duration_category = "длинный двухнедельный тур (2 недели)"
        is_long_trip = True
    elif med_trip_days <= 6:
        duration_category = "короткий тур"
        is_long_trip = False
    else:
        duration_category = "стандартная неделя (7–10 ночей)"
        is_long_trip = False

    cost_per_day_median = round(med_price / max(1, med_trip_days), 0)
    cost_per_day_min = round(min_price / max(1, med_trip_days), 0)

    # Calculate Days-to-Departure (D-Minus) timeline & horizon
    d_values: List[int] = []
    dep_dates: List[date] = []
    d_buckets_count: Dict[str, int] = {}
    today = date.today()

    for _, row in latest_per_hotel.iterrows():
        dep_d = parse_departure_date(str(row.get("dates", "")))
        if dep_d:
            d = (dep_d - today).days
            if d >= 0:
                d_values.append(d)
                dep_dates.append(dep_d)
                b = get_d_bucket(d)
                d_buckets_count[b] = d_buckets_count.get(b, 0) + 1

    min_d = int(np.min(d_values)) if d_values else 14
    max_d = int(np.max(d_values)) if d_values else 14
    avg_d = int(np.median(d_values)) if d_values else 14
    span_d = max(0, max_d - min_d)
    is_wide_window = span_d >= 7

    nearest_dep = min(dep_dates).strftime("%d.%m") if dep_dates else ""
    furthest_dep = max(dep_dates).strftime("%d.%m") if dep_dates else ""

    dominant_phase = max(d_buckets_count.items(), key=lambda x: x[1])[0] if d_buckets_count else "mid_term"

    # Today departure check & next realistic flight
    has_today_departures = (min_d == 0)
    today_departures_count = sum(1 for d in d_values if d == 0)
    future_pairs = [(d, dt) for d, dt in zip(d_values, dep_dates) if d >= 1]
    if future_pairs:
        next_realistic_days = int(min(p[0] for p in future_pairs))
        next_realistic_dep = min(p[1] for p in future_pairs).strftime("%d.%m")
    else:
        next_realistic_days = min_d
        next_realistic_dep = nearest_dep

    # Destination detection & seasonal weather intelligence
    filter_search_text = f"{filter_id or ''} {filter_title or ''} {prices_csv_path}".lower()
    sample_hotels_text = " ".join(latest_per_hotel["hotel_name"].astype(str).tolist()).lower()

    # 0. Primary ground truth: Check filter configuration file if available
    detected_country = ""
    try:
        from filter_params import load_filter_config, _country_label
        f_cfg = load_filter_config(prices_csv_path)
        if f_cfg:
            c_from_cfg = _country_label(f_cfg, f_cfg.get("url", ""))
            if c_from_cfg and c_from_cfg not in ("—", ""):
                detected_country = c_from_cfg
    except Exception:
        pass

    # 1. Fallback check: Explicit destination in filter_id, title, or directory path
    if not detected_country:
        if any(k in filter_search_text for k in ("greece", "grecja", "греци", "athens", "crete", "rhodes", "corfu", "kos", "santorini", "zakynthos")):
            detected_country = "Греция"
        elif any(k in filter_search_text for k in ("cyprus", "cypr", "кипр")):
            detected_country = "Кипр"
        elif any(k in filter_search_text for k in ("turkey", "turcja", "турци", "antalya", "alanya", "kemer", "belek")):
            detected_country = "Турция"
        elif any(k in filter_search_text for k in ("egypt", "egipt", "египет", "sharm", "hurghada", "marsa_alam")):
            detected_country = "Египет"
        elif any(k in filter_search_text for k in ("spain", "hiszpania", "испани", "mallorca", "tenerife", "canaria")):
            detected_country = "Испания"
        elif any(k in filter_search_text for k in ("tunisia", "tunezja", "тунис")):
            detected_country = "Тунис"
        elif any(k in filter_search_text for k in ("italy", "italia", "wlochy", "итали")):
            detected_country = "Италия"
        elif any(k in filter_search_text for k in ("bulgaria", "bułgaria", "болгари")):
            detected_country = "Болгария"
        elif any(k in filter_search_text for k in ("uae", "emirates", "emiraty", "оаэ", "dubai")):
            detected_country = "ОАЭ"
        elif any(k in filter_search_text for k in ("malta", "мальт")):
            detected_country = "Мальта"

    # 2. Secondary check: Word-boundary regex on hotel names (prevents 'side' inside 'residence' from triggering Turkey!)
    if not detected_country:
        if re.search(r"\b(athens|attica|attyka|crete|kreta|rhodes|rodos|corfu|korfu|kos|zakynthos|santorini)\b", sample_hotels_text):
            detected_country = "Греция"
        elif re.search(r"\b(ayia napa|napa|paphos|protaras|limassol|larnaca)\b", sample_hotels_text):
            detected_country = "Кипр"
        elif re.search(r"\b(antalya|alanya|kemer|belek|side|manavgat|eftalia|xoria)\b", sample_hotels_text):
            detected_country = "Турция"
        elif re.search(r"\b(sharm|hurghada|marsa alam|makadi|gouna|naama|hadaba|nabq)\b", sample_hotels_text):
            detected_country = "Египет"
        elif re.search(r"\b(mallorca|tenerife|canaria|ibiza|costa)\b", sample_hotels_text):
            detected_country = "Испания"
        else:
            detected_country = "Египет"

    # Region determination based on country and specific local tokens
    combined_geo = f"{filter_search_text} {sample_hotels_text}"
    if detected_country == "Греция":
        if any(k in combined_geo for k in ("athens", "attica", "attyka", "афин", "аттик")):
            detected_region = "Афины и Аттика"
        elif any(k in combined_geo for k in ("crete", "kreta", "крит")):
            detected_region = "Остров Крит"
        elif any(k in combined_geo for k in ("rhodes", "rodos", "родос")):
            detected_region = "Остров Родос"
        elif any(k in combined_geo for k in ("corfu", "korfu", "корфу")):
            detected_region = "Остров Корфу"
        else:
            detected_region = "Греческие курорты и острова"
    elif detected_country == "Кипр":
        detected_region = "Айя-Напа / Протарас / Пафос / Лимассол"
    elif detected_country == "Турция":
        detected_region = "Анталийское побережье (Сиде / Аланья / Кемер / Белек)"
    elif detected_country == "Испания":
        detected_region = "Канарские / Балеарские острова"
    elif detected_country == "Египет":
        detected_region = "Шарм-эль-Шейх / Хургада / Марса Алам"
    else:
        detected_region = f"Курорты ({detected_country})"

    dep_month = min(dep_dates).month if dep_dates else today.month
    if detected_country == "Турция":
        if dep_month in (11, 12, 1, 2, 3):
            season_phase = "Закрытие пляжного сезона / переход на зимнюю концепцию"
            weather_advice = "Днем тепло (+20..+24°C), море остывает до +21..+22°C в ноябре, вечера прохладные (+12..+15°C). Выбирайте отели с подогреваемыми бассейнами и спа. Не для жаркого пляжа, а для комфортного отдыха и релакса."
        elif dep_month in (4, 5):
            season_phase = "Открытие летнего сезона"
            weather_advice = "Воздух комфортно теплый (+24..+27°C), море бодрящее (+19..+21°C). Отличные цены перед летним пиком."
        elif dep_month in (6, 7, 8, 9):
            season_phase = "Высокий пляжный сезон"
            weather_advice = "Жаркое средиземноморское лето (+32..+38°C), очень теплое море (+27..+29°C), максимальная загрузка."
        else:
            season_phase = "Бархатный сезон"
            weather_advice = "Мягкая приятная погода (+27..+29°C), очень теплое море (+25..+26°C), отличный период для пляжного отдыха."
    elif detected_country == "Греция":
        if dep_month in (11, 12, 1, 2, 3):
            season_phase = "Экскурсионный сезон / средиземноморская зима"
            weather_advice = "Мягкая приятная зима (+15..+18°C днем), море прохладное (+17..+18°C). Идеальное время для неспешных прогулок по Афинам, музеям и античным памятникам без толп и летней жары."
        elif dep_month in (4, 5):
            season_phase = "Весеннее пробуждение"
            weather_advice = "Комфортное тепло (+20..+24°C), цветущие острова, море освежающее (+18..+20°C). Отлично для автопутешествий и первого загара."
        elif dep_month in (6, 7, 8, 9):
            season_phase = "Высокий пляжный сезон"
            weather_advice = "Жаркое солнце (+30..+35°C), лазурное теплое море (+25..+27°C), чистейшие пляжи и таверны у воды."
        else:
            season_phase = "Бархатный сезон"
            weather_advice = "Идеальное мягкое солнце (+24..+27°C), прогретое за лето море (+23..+25°C), комфортный отдых без изнуряющего зноя."
    elif detected_country == "Кипр":
        if dep_month in (11, 12, 1, 2, 3):
            season_phase = "Мягкая теплая зима"
            weather_advice = "Самый теплый климат в Европе: днем +19..+23°C, солнце, море остывает медленно (+20..+21°C в ноябре). Отлично для прогулок, хайкинга и отдыха в качественных отелях."
        elif dep_month in (6, 7, 8, 9):
            season_phase = "Жаркий пляжный сезон"
            weather_advice = "Жаркое сухое лето (+32..+37°C), очень теплое море (+27..+29°C), кристально чистые пляжи Айя-Напы и Протараса."
        else:
            season_phase = "Бархатный сезон"
            weather_advice = "Золотое время: комфортное тепло (+26..+29°C), теплое море (+25..+26°C), прекрасный пляжный отдых."
    elif detected_country == "Египет":
        if dep_month in (11, 12, 1, 2, 3):
            season_phase = "Зимний сезон Красного моря"
            weather_advice = "Теплое море (+23..+26°C), воздух днем +24..+28°C. Ключевой фактор комфорта — закрытая от зимних ветров бухта (Наама Бэй, Рас Ум Сид) и подогреваемый бассейн."
        else:
            season_phase = "Круглогодичный курорт"
            weather_advice = "Теплое море и солнце, отличный снорклинг и дайвинг."
    else:
        season_phase = "Средиземноморский сезон"
        weather_advice = "Мягкий климат, европейский сервис и экскурсионные возможности."

    destination_context = {
        "country": detected_country,
        "region": detected_region,
        "season_phase": season_phase,
        "climate_and_weather_advice": weather_advice,
    }

    # 1. Pre-calculate star clusters, price tiers, and ratings (Peer Group Benchmarking)
    hotel_stars_map: Dict[str, int] = {}
    hotel_ratings_map: Dict[str, float] = {}
    hotel_reviews_map: Dict[str, int] = {}
    hotel_meal_map: Dict[str, str] = {}
    hotel_tier_map: Dict[str, str] = {}
    star_prices_map: Dict[int, List[float]] = {4: [], 5: []}
    peer_cohort_prices: Dict[Tuple[int, str], List[float]] = {}

    if len(prices) >= 6:
        tier_p33 = float(np.percentile(prices, 33.3))
        tier_p67 = float(np.percentile(prices, 66.7))
    elif len(prices) > 0:
        tier_p33 = float(np.percentile(prices, 50.0))
        tier_p67 = float(np.percentile(prices, 50.0))
    else:
        tier_p33 = 0.0
        tier_p67 = 0.0

    for _, row in latest_per_hotel.iterrows():
        hn = str(row["hotel_name"])
        p = float(row["price"])
        st = infer_stars(hn, row, dna_hotels.get(hn))
        hotel_stars_map[hn] = st
        star_prices_map.setdefault(st, []).append(p)
        hotel_meal_map[hn] = infer_meal_plan(row)

        # Classify hotel into comparable price tier
        if p <= tier_p33:
            tier_name = "эконом"
        elif p <= tier_p67:
            tier_name = "комфорт"
        else:
            tier_name = "премиум"
        hotel_tier_map[hn] = tier_name
        peer_cohort_prices.setdefault((st, tier_name), []).append(p)

        r_val = 0.0
        for r_col in ("ta_rating", "rating", "hotel_rating"):
            if r_col in row and pd.notna(row[r_col]):
                try:
                    r_val = float(str(row[r_col]).replace(",", "."))
                    if r_val > 5.0:  # normalize 10-scale to 5
                        r_val = round(r_val / 2.0, 1)
                    break
                except (ValueError, TypeError):
                    pass
        hotel_ratings_map[hn] = r_val

        rev_val = 0
        for rev_col in ("ta_review_count", "review_count", "reviews", "ta_reviews"):
            if rev_col in row and pd.notna(row[rev_col]):
                try:
                    c_rev = re.sub(r"[^\d]", "", str(row[rev_col]))
                    if c_rev:
                        rev_val = int(c_rev)
                        break
                except (ValueError, TypeError):
                    pass
        hotel_reviews_map[hn] = rev_val

    # Ensure complete rating and review count coverage from all historical rows of df
    for r_col in ("ta_rating", "rating", "hotel_rating"):
        if r_col in df.columns:
            for hn, val in df.dropna(subset=[r_col]).groupby("hotel_name")[r_col].last().items():
                if hn not in hotel_ratings_map or hotel_ratings_map[hn] <= 0:
                    try:
                        v = float(str(val).replace(",", "."))
                        if v > 5.0:
                            v = round(v / 2.0, 1)
                        hotel_ratings_map[hn] = v
                    except (ValueError, TypeError):
                        pass

    for rev_col in ("ta_review_count", "review_count", "reviews", "ta_reviews"):
        if rev_col in df.columns:
            for hn, val in df.dropna(subset=[rev_col]).groupby("hotel_name")[rev_col].last().items():
                if hn not in hotel_reviews_map or hotel_reviews_map[hn] <= 0:
                    try:
                        c_rev = re.sub(r"[^\d]", "", str(val))
                        if c_rev:
                            hotel_reviews_map[hn] = int(c_rev)
                    except (ValueError, TypeError):
                        pass

    # Fallback to Reputation KB for complete rating and review count coverage
    kb_hotels = reputation_kb.get("hotels", {}) if isinstance(reputation_kb, dict) and "hotels" in reputation_kb else (reputation_kb if isinstance(reputation_kb, dict) else {})
    for hn in latest_per_hotel["hotel_name"].unique():
        if hotel_ratings_map.get(hn, 0.0) <= 0 and hn in kb_hotels:
            kb_entry = kb_hotels[hn]
            kb_r = kb_entry.get("ta_rating")
            if kb_r and float(kb_r) > 0:
                hotel_ratings_map[hn] = float(kb_r)
            kb_rev = kb_entry.get("ta_review_count")
            if kb_rev and int(kb_rev) > 0 and hotel_reviews_map.get(hn, 0) <= 0:
                hotel_reviews_map[hn] = int(kb_rev)

    # Peer cohort medians (comparing only with roughly equal hotels)
    peer_medians: Dict[Tuple[int, str], float] = {
        k: float(np.median(plist)) for k, plist in peer_cohort_prices.items() if plist
    }
    cluster_medians: Dict[int, float] = {
        st: float(np.median(plist)) if plist else med_price
        for st, plist in star_prices_map.items()
    }

    # 2. Identify Floor Breakers, Flash Drops, Gems, Dupes & Hotel Intelligence
    floor_breakers: List[Dict[str, Any]] = []
    flash_drops: List[Dict[str, Any]] = []
    gems: List[Dict[str, Any]] = []
    active_candidates: List[Dict[str, Any]] = []
    all_hotel_intelligence: Dict[str, Dict[str, Any]] = {}

    # Temporary storage for second-pass dupe finding
    hotel_records_list: List[Dict[str, Any]] = []

    # Pre-calculate local price history per hotel from df
    hotel_hist_stats: Dict[str, Dict[str, float]] = {}
    for hn, grp in df.groupby("hotel_name"):
        plist = grp["price"].dropna().astype(float).tolist()
        if plist:
            hotel_hist_stats[hn] = {
                "min": float(min(plist)),
                "med": float(np.median(plist)),
                "max": float(max(plist)),
            }

    for _, row in latest_per_hotel.iterrows():
        h_name = str(row["hotel_name"])
        cur_p = float(row["price"])
        r_val = hotel_ratings_map.get(h_name, 0.0)
        h_dna = dna_hotels.get(h_name)
        l_stats = hotel_hist_stats.get(h_name, {"min": cur_p, "med": cur_p, "max": cur_p})

        if h_dna:
            hist_min = float(h_dna.get("min_price", l_stats["min"]))
            hist_med = float(h_dna.get("median_price", l_stats["med"]))
            hist_max = float(h_dna.get("max_price", l_stats["max"]))
            archetype = h_dna.get("archetype", "BALANCED")
        else:
            hist_min = l_stats["min"]
            hist_med = l_stats["med"]
            hist_max = l_stats["max"]
            archetype = "BALANCED"

        # Is current price within 2.5% of historical minimum?
        # Sanity check: must have real historical variation (hist_max > hist_min * 1.03)
        # to avoid falsely marking 100% of newly-tracked hotels as "season floor drops".
        has_real_history = (hist_max > hist_min * 1.03)
        is_floor = has_real_history and (cur_p <= (hist_min * 1.025))
        # Quantile relative to current filter
        cur_rank = float(np.sum(prices < cur_p)) / max(1, len(prices))

        # Departure days for this hotel
        h_dep_d = parse_departure_date(str(row.get("dates", "")))
        h_d_days = (h_dep_d - today).days if h_dep_d else None

        # Feature 1: Optimal Booking Window
        bw_res = resolve_booking_window(h_dna, h_d_days, cur_p)

        # Feature 2: Fair Price Index & Peer Cohort Benchmarking
        st = hotel_stars_map.get(h_name, 4)
        tier_name = hotel_tier_map.get(h_name, "комфорт")

        # Benchmark strictly against comparable peer cohort (same stars AND same price tier)
        peer_med = peer_medians.get((st, tier_name))
        if not peer_med:
            plist = star_prices_map.get(st, prices)
            peer_med = float(np.median(plist)) if len(plist) > 0 else med_price

        fair_delta_pct = ((cur_p - peer_med) / max(1.0, peer_med)) * 100.0

        # Self-benchmarking sanity checks:
        # A hotel can ONLY be considered underpriced/bargain if:
        # 1. It is below peer cohort median (fair_delta_pct <= -10.0%)
        # 2. AND it is NOT selling above its own historical median (cur_p <= hist_med * 1.02)
        # 3. AND it has a decent rating (r_val >= 3.8 or unrated)
        is_truly_underpriced = (
            fair_delta_pct <= -10.0
            and cur_p <= (hist_med * 1.02)
            and (r_val >= 3.8 or r_val == 0.0)
        )

        is_overpriced = (
            fair_delta_pct >= 20.0
            or cur_p >= (hist_med * 1.15)
        )

        if is_truly_underpriced:
            fair_badge = f"🔥 −{abs(fair_delta_pct):.0f}% к равным {tier_name} {st}★"
            fair_class = "fair-underpriced"
            fair_tip = (
                f"Цена на {abs(fair_delta_pct):.0f}% ниже медианы равных отелей сегмента "
                f"{tier_name} {st}★ ({peer_med:,.0f} zł) и не превышает обычную цену отеля ({hist_med:,.0f} zł)."
            )
        elif is_overpriced:
            fair_badge = f"⚠️ +{fair_delta_pct:.0f}% к {tier_name} {st}★" if fair_delta_pct >= 15.0 else "⚠️ Дороже обычного"
            fair_class = "fair-overpriced"
            fair_tip = (
                f"Цена на {fair_delta_pct:+.0f}% отличается от сопоставимых отелей сегмента "
                f"{tier_name} {st}★ ({peer_med:,.0f} zł) или превышает историческую норму отеля ({hist_med:,.0f} zł)."
            )
        else:
            fair_badge, fair_class, fair_tip = "", "", ""

        # Feature 3: Hidden Gem
        # A true gem is a high quality hotel (rating >= 4.4) with confirmed reviews (>=30) priced in economy/comfort tier
        rev_count = hotel_reviews_map.get(h_name, 0)
        has_adequate_reviews = (rev_count >= 30 or rev_count == 0)
        meal_type = hotel_meal_map.get(h_name, "all_inclusive")

        is_gem = (
            r_val >= 4.4
            and has_adequate_reviews
            and cur_p <= (tier_p33 * 1.08)
            and cur_p <= (hist_med * 1.03)
        )
        gem_badge = "💎 Скрытая жемчужина" if is_gem else ""
        gem_tip = f"Высокий рейтинг ({r_val:g}★{f', {rev_count} отз.' if rev_count else ''}) при цене в бюджетном сегменте {st}★ ({cur_p:,.0f} zł)." if is_gem else ""

        if is_gem:
            gems.append({
                "hotel_name": h_name,
                "price": cur_p,
                "rating": r_val,
                "stars": st,
                "review_count": rev_count,
                "meal_plan": meal_type,
            })

        # Feature 4: Glitch & Flash Drop Radar
        is_flash = False
        flash_badge = ""
        flash_tip = ""
        if hist_min > 0 and cur_p <= (hist_min * 0.85):
            drop_below = ((hist_min - cur_p) / hist_min) * 100.0
            is_flash = True
            flash_badge = f"⚡ FLASH DROP (−{drop_below:.0f}%)"
            flash_tip = f"Аномалия: цена пробила исторический минимум на {drop_below:.0f}% ({hist_min:,.0f} zł → {cur_p:,.0f} zł)!"
            flash_drops.append({
                "hotel_name": h_name,
                "current_price": cur_p,
                "historical_min": hist_min,
                "drop_pct": round(drop_below, 1),
            })

        op_code = extract_operator_from_url(str(row.get("offer_url") or row.get("url") or ""))
        op_name = OPERATOR_NAME_MAP.get(op_code, op_code) if op_code else "Туроператор (Польша)"

        cand_info = {
            "hotel_name": h_name,
            "current_price": cur_p,
            "historical_min": hist_min,
            "historical_median": hist_med,
            "historical_max": hist_max,
            "quantile_in_filter": round(cur_rank, 2),
            "archetype": archetype,
            "stars": st,
            "rating": r_val,
            "review_count": hotel_reviews_map.get(h_name, 0),
            "dates": str(row.get("dates", "")),
            "duration": str(row.get("duration", "")),
            "departure_airport": str(row.get("departure_airport") or "").strip(),
            "meal_plan": hotel_meal_map.get(h_name, "all_inclusive"),
            "tour_operator": op_name,
            "offer_url": str(row.get("offer_url") or row.get("url") or ""),
            "booking_window": bw_res,
            "fair_price": {
                "delta_pct": round(fair_delta_pct, 1),
                "badge": fair_badge,
                "class": fair_class,
                "tip": fair_tip,
                "tier": tier_name,
                "cluster_median": round(peer_med, 0),
            },
            "gem": {
                "is_gem": is_gem,
                "badge": gem_badge,
                "tip": gem_tip,
            },
            "flash_drop": {
                "is_flash": is_flash,
                "badge": flash_badge,
                "tip": flash_tip,
            },
            "reputation": get_hotel_reputation_metadata(h_name, filter_title or "", kb_data=reputation_kb),
            "dupe_suggestion": None,
        }

        # Exclude expired departures (dates in the past) only if dataset contains active/future departures
        h_dep_d = parse_departure_date(str(row.get("dates", "")))
        h_d_days = (h_dep_d - today).days if h_dep_d else None
        is_past_departure = (h_d_days is not None and h_d_days < 0) if d_values else False

        if is_floor and not is_past_departure:
            floor_breakers.append(cand_info)

        has_buy_catalyst = (
            (is_floor and cur_p <= hist_med * 0.98)
            or is_flash
            or is_gem
            or (is_truly_underpriced and r_val >= 4.2)
        )
        # Low rating (< 4.0) or unrated (0.0) hotels, as well as past departures, should NEVER be candidates for buy recommendations
        if has_buy_catalyst and r_val >= 4.0 and not is_past_departure:
            active_candidates.append(cand_info)

        if not is_past_departure:
            hotel_records_list.append(cand_info)

    # 3. Second pass: AI Dupe (Двойник / Альтернатива) Matching for expensive hotels
    for cand in hotel_records_list:
        cur_p = cand["current_price"]
        st = cand["stars"]
        tier_name = cand["fair_price"].get("tier", "комфорт")
        peer_med = peer_medians.get((st, tier_name), med_price)
        r_val = cand["rating"]

        # Only search dupes for hotels with premium pricing or elevated prices
        if cur_p >= 5000.0 and (cur_p >= (peer_med * 1.20) or cur_p >= (cand["historical_median"] * 1.15)):
            dupe_candidates = [
                other for other in hotel_records_list
                if other["hotel_name"] != cand["hotel_name"]
                and other["current_price"] <= (cur_p - 1000.0)
                and other["rating"] >= max(4.3, r_val - 0.2)
            ]
            if dupe_candidates:
                # Pick dupe with same star tier if possible, then highest rating, then lowest price
                dupe_candidates.sort(key=lambda x: (abs(x["stars"] - st), -x["rating"], x["current_price"]))
                best_dupe = dupe_candidates[0]
                cand["dupe_suggestion"] = {
                    "hotel_name": best_dupe["hotel_name"],
                    "price": best_dupe["current_price"],
                    "savings": round(cur_p - best_dupe["current_price"], 0),
                    "savings_pln": round(cur_p - best_dupe["current_price"], 0),
                    "rating": best_dupe["rating"],
                    "offer_url": best_dupe["offer_url"],
                }

        all_hotel_intelligence[cand["hotel_name"]] = cand

    # Build complete catalog of ALL hotels in the filter for AI analysis (zero artificial truncation!)
    all_hotels_catalog = []
    for cand in hotel_records_list:
        cur_p = cand["current_price"]
        h_med = cand["historical_median"]
        diff_h = round(((cur_p - h_med) / max(1.0, h_med)) * 100.0, 1) if h_med > 0 else 0.0
        all_hotels_catalog.append({
            "hotel_name": cand["hotel_name"],
            "price": cur_p,
            "stars": cand["stars"],
            "rating": cand["rating"],
            "tier": cand["fair_price"].get("tier", "комфорт"),
            "historical_median": h_med,
            "diff_from_history_pct": diff_h,
            "diff_from_tier_pct": cand["fair_price"].get("delta_pct", 0.0),
            "is_floor": cur_p <= (cand["historical_min"] * 1.01),
            "is_flash": cand["flash_drop"]["is_flash"],
            "is_gem": cand["gem"]["is_gem"],
            "booking_window": cand["booking_window"].get("optimal_window", ""),
        })

    # Sort catalog: premium first, then comfort, then economy, ordered by highest rating and best discount
    tier_order = {"премиум": 0, "комфорт": 1, "эконом": 2}
    all_hotels_catalog.sort(key=lambda x: (tier_order.get(x["tier"], 1), -x["rating"], x["diff_from_history_pct"]))

    # Process cross-border arbitrage highlights if available
    arbitrage_summary: List[Dict[str, Any]] = []
    if arbitrage_matches:
        for m in arbitrage_matches[:5]:
            arbitrage_summary.append({
                "hotel_name": m.get("hotel_name"),
                "best_deal": m.get("best_deal"),
                "savings_pct": m.get("savings_pct"),
                "spread_pln": m.get("spread_pln"),
                "price_pl": m.get("price_pl"),
                "price_de_pln": m.get("price_de_pln"),
                "airport_de": m.get("airport_de"),
            })

    # 4. Filter candidates for Executive LLM Briefing
    is_deep = os.getenv("AI_ANALYSIS_MODE", "standard").lower() == "full_deep"
    if is_deep:
        selected_cands = active_candidates if active_candidates else hotel_records_list
    else:
        selected_cands = list(active_candidates)
        if len(selected_cands) < 6:
            seen = {c["hotel_name"] for c in selected_cands}
            # Backfill with highest-rated and best-value hotels from catalog (rating >= 4.0 first)
            rated_first = [c for c in hotel_records_list if c["rating"] >= 4.0]
            unrated = [c for c in hotel_records_list if c["rating"] < 4.0]
            sorted_by_quality = sorted(rated_first, key=lambda x: (-x["rating"], x["current_price"])) + sorted(unrated, key=lambda x: x["current_price"])
            for cand in sorted_by_quality:
                if cand["hotel_name"] not in seen:
                    selected_cands.append(cand)
                    seen.add(cand["hotel_name"])
                    if len(selected_cands) >= 8:
                        break

    top_candidates = []
    arch_desc_map = {
        "LATE_DUMPER": "Сбрасывает до 25% цены за 3–5 дней до вылета",
        "EARLY_SURGER": "Дорожает ближе к вылету, выгоднее брать заранее",
        "ROCK_SOLID": "Держит цену стабильно без резких сбросов",
        "VOLATILE": "Цена совершает частые колебания вверх-вниз",
        "BALANCED": "Умеренная динамика",
    }

    for cand in selected_cands:
        cand_dep_d = parse_departure_date(str(cand.get("dates", "")))
        cand_d_days = (cand_dep_d - today).days if cand_dep_d else None
        if d_values and cand_d_days is not None and cand_d_days < 0:
            continue
        cur_p = cand["current_price"]
        h_med = cand["historical_median"]
        h_min = cand["historical_min"]
        h_max = cand["historical_max"]
        st = cand["stars"]
        r_val = cand["rating"]
        rev_count = cand.get("review_count", 0)
        arch = cand.get("archetype", "BALANCED")
        arch_desc = arch_desc_map.get(arch, "Умеренная динамика")

        diff_med = round(((cur_p - h_med) / max(1.0, h_med)) * 100.0, 1) if h_med > 0 else 0.0
        diff_min = round(((cur_p - h_min) / max(1.0, h_min)) * 100.0, 1) if h_min > 0 else 0.0
        discount_pct = round(((h_med - cur_p) / max(1.0, h_med)) * 100.0, 1) if h_med > 0 else 0.0

        op_name = cand.get("tour_operator") or "Туроператор (Польша)"
        rep_meta = cand.get("reputation") or get_hotel_reputation_metadata(cand["hotel_name"], filter_title or "", kb_data=reputation_kb)
        is_today_cand = (cand_d_days == 0)

        cand_dur_days = extract_stay_days(cand.get("duration", "")) or med_trip_days
        cand_cost_per_day = round(cur_p / max(1, cand_dur_days), 0)

        cand_dossier = {
            "hotel_name": cand["hotel_name"],
            "stars": st,
            "tier": cand["fair_price"].get("tier", "комфорт"),
            "price": cur_p,
            "duration_days": cand_dur_days,
            "cost_per_day_pln": cand_cost_per_day,
            "rating": r_val,
            "review_count": rev_count,
            "meal_plan": cand.get("meal_plan", "all_inclusive"),
            "tripadvisor": {
                "rating": r_val,
                "review_count": rev_count,
                "summary": f"{r_val:g}★ ({rev_count:,} отзывов)" if r_val > 0 else "Без подтвержденных отзывов",
            },
            "price_history": {
                "historical_min": h_min,
                "historical_median": h_med,
                "historical_max": h_max,
                "diff_from_median_pct": diff_med,
                "diff_from_min_pct": diff_min,
                "is_at_season_floor": (h_max > h_min * 1.03) and (cur_p <= (h_min * 1.025)),
            },
            "behavioral_archetype": {
                "type": arch,
                "description": arch_desc,
            },
            "trip_details": {
                "dates": cand.get("dates", ""),
                "duration": cand.get("duration", ""),
                "duration_days": cand_dur_days,
                "cost_per_day_pln": cand_cost_per_day,
                "departure_airport": cand.get("departure_airport", ""),
                "meal_plan": cand.get("meal_plan", "all_inclusive"),
                "tour_operator": op_name,
            },
            "booking_window": {
                "optimal_window": cand["booking_window"].get("optimal_window", ""),
                "status": cand["booking_window"].get("window_status", ""),
                "tip": cand["booking_window"].get("window_tip", ""),
            },
            "discount_from_median_pct": discount_pct,
            "peer_cohort_median": cand["fair_price"].get("cluster_median", 0.0),
            "fair_price_badge": cand["fair_price"].get("badge", ""),
            "flash_drop_badge": cand["flash_drop"].get("badge", ""),
            "gem_badge": cand["gem"].get("badge", ""),
            "cheaper_alternative": cand.get("dupe_suggestion"),
            "hotel_reputation": rep_meta,
            "is_departing_today": is_today_cand,
            "days_to_departure": cand_d_days,
            "departure_warning": "⚡ ВЫЛЕТ СЕГОДНЯ! Подходит только тем, кто сидит на чемоданах." if is_today_cand else "",
        }
        top_candidates.append(cand_dossier)

    # Compute comprehensive temporal, airport, and duration trends
    market_trends = calculate_market_trends(df)
    airports_comp = calculate_airports_comparison(df, latest_per_hotel)
    duration_comp = calculate_duration_comparison(df)

    trend_7d = market_trends.get("trend_7d_pct") or 0.0
    floor_pct = round((len(floor_breakers) / max(1, len(latest_per_hotel))) * 100.0, 1)

    # Determine human-friendly and accurate dominant phase
    if dominant_phase == "panic_dump":
        if trend_7d <= -2.5 or floor_pct >= 40.0:
            display_phase = "panic_dump"
            dominant_phase_label = "Сброс цен перед вылетом (D-4…D-7, цены падают)"
        else:
            display_phase = "close_in_stable"
            dominant_phase_label = "Срочные вылеты за 4–7 дн. (цены стабильны)"
    elif dominant_phase == "last_minute":
        display_phase = "last_minute"
        dominant_phase_label = "Горящие туры за 1–3 дн."
    elif dominant_phase == "first_markdown":
        display_phase = "first_markdown"
        dominant_phase_label = "Вылеты через 8–14 дн."
    elif dominant_phase == "mid_term":
        display_phase = "mid_term"
        dominant_phase_label = "Обычный период за 15–30 дн."
    else:
        display_phase = "early_bird"
        dominant_phase_label = f"Раннее бронирование за {min_d}+ дн."

    # Assemble compacted market context
    market_context = {
        "filter_id": filter_id or os.path.basename(os.path.dirname(prices_csv_path)),
        "filter_title": filter_title or "",
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "market_stats": {
            "hotel_count": len(latest_per_hotel),
            "min_price": min_price,
            "p10_price": p10_price,
            "median_price": med_price,
            "p90_price": p90_price,
            "max_price": max_price,
            "trip_duration": {
                "min_days": min_trip_days,
                "max_days": max_trip_days,
                "median_days": med_trip_days,
                "label": trip_duration_label,
                "category": duration_category,
                "is_long_trip": is_long_trip,
                "cost_per_day_median_pln": cost_per_day_median,
                "cost_per_day_min_pln": cost_per_day_min,
                "context_note": (
                    f"ВНИМАНИЕ: Это {duration_category} на {trip_duration_label}. "
                    f"Цены указаны за ДВЕ НЕДЕЛИ ({med_trip_days} дн.), а не за 7 дней! "
                    f"В пересчете это ~{cost_per_day_median:,.0f} zł/сутки (от ~{cost_per_day_min:,.0f} zł/сутки за двоих на 'всё включено'). "
                    f"Оценивай бюджет с учетом {med_trip_days} дней отдыха, подчеркивая выгоду долгого отпуска."
                    if is_long_trip else
                    f"Тур на {trip_duration_label} (~{cost_per_day_median:,.0f} zł/сутки за двоих)."
                ),
            },
            "median_days_to_departure": avg_d,
            "min_days_to_departure": min_d,
            "max_days_to_departure": max_d,
            "departure_span_days": span_d,
            "is_wide_window": is_wide_window,
            "nearest_departure_date": nearest_dep,
            "furthest_departure_date": furthest_dep,
            "dominant_yield_phase": display_phase,
            "dominant_phase_label": dominant_phase_label,
            "phase_distribution": d_buckets_count,
            "near_term_count": len([d for d in d_values if d <= 7]),
            "mid_term_count": len([d for d in d_values if 8 <= d <= 21]),
            "far_term_count": len([d for d in d_values if d >= 22]),
            "has_today_departures": has_today_departures,
            "today_departures_count": today_departures_count,
            "next_realistic_departure_date": next_realistic_dep,
            "next_realistic_days_to_departure": next_realistic_days,
            "destination_context": destination_context,
        },
        "market_trends": market_trends,
        "airports_comparison": airports_comp,
        "duration_comparison": duration_comp,
        "floor_saturation": {
            "floor_breaker_count": len(floor_breakers),
            "floor_breaker_pct": floor_pct,
            "sample_floor_hotels": [f["hotel_name"] for f in floor_breakers[:6]],
            "has_meaningful_history": any((l.get("max", 0) > l.get("min", 0) * 1.03) for l in hotel_hist_stats.values()),
        },
        "top_candidates": top_candidates,
        "arbitrage_highlights": arbitrage_summary,
        "all_hotels_catalog": all_hotels_catalog,
        "selected_hotel_dossiers": all_hotels_catalog,
        "all_hotel_intelligence": all_hotel_intelligence,
        "gems": gems,
        "flash_drops": flash_drops,
        "cluster_medians": cluster_medians,
    }

    if analyze_early_booking is not None:
        try:
            eb_res = analyze_early_booking(df, filter_id=filter_id or "")
            if not eb_res.get("error") and eb_res.get("summary", {}).get("verdict") != "INSUFFICIENT_DATA":
                surv_14 = next((item["survival_rate"] for item in eb_res.get("survival_curve", []) if item["d"] == 14), None)
                market_context["early_booking"] = {
                    "ebas_score": eb_res["summary"].get("ebas_score"),
                    "verdict": eb_res["summary"].get("verdict"),
                    "best_d_bucket": eb_res["summary"].get("best_price_d_bucket"),
                    "paired_trajectory": eb_res.get("paired_price_trajectory"),
                    "survival_rate_at_14d": surv_14,
                    "sold_out_rate_at_14d": round(1.0 - surv_14, 3) if surv_14 is not None else None,
                }
        except Exception as e_eb:
            logger.debug(f"Early booking extraction skipped: {e_eb}")

    return market_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract compact market features for AI context.")
    parser.add_argument("--csv", required=True, help="Path to travel_prices.csv")
    parser.add_argument("--dna", default=DEFAULT_DNA_FILE, help="Path to market_dna_profile.json")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    feats = extract_filter_features(args.csv, dna_profile_path=args.dna)
    out_json = json.dumps(feats, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"Features saved to {args.output}")
    else:
        print(out_json)


if __name__ == "__main__":
    main()
