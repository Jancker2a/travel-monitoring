#!/usr/bin/env python3
"""
Hotel Passport Drawer & Horizontal OTA Card Component.

Provides:
- generate_hotel_ai_profile: OTA-grade AI overview, TripAdvisor rating & links,
  infrastructure features, compact YouTube review banner, photo gallery, and cross-filter intelligence.
- get_hotel_passport_css: Sleek CSS for horizontal OTA cards, table passport buttons, 780px slide-over drawer,
  photo gallery carousel, compact YouTube banner, rich infrastructure cards, and dark theme support.
- render_hotel_card_horiz: 3-column aggregator card with media, AI verdict, YouTube/TripAdvisor badges,
  and Price Intelligence CTA.
- render_hotel_passport_drawer_html: 780px slide-over modal markup with 4 rich tabs:
  (1) AI-Обзор, Отзывы и компактный YouTube баннер
  (2) Анализ и график цен Plotly + отель в других фильтрах
  (3) Расширенная детальная Инфраструктура (пляж, бассейны, питание, дети, спа, связь)
  (4) Все доступные вылеты и пакеты
- get_hotel_passport_js: Client-side JS for drawer open/close, photo gallery switching, tabs, Plotly rendering, and other filters navigation.
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

_HOTEL_GALLERIES_CACHE: Optional[Dict[str, Any]] = None


def _get_galleries_kb() -> Dict[str, Any]:
    """Loads and caches hotel_galleries_kb.json for instant multi-photo lookup."""
    global _HOTEL_GALLERIES_CACHE
    if _HOTEL_GALLERIES_CACHE is None:
        _HOTEL_GALLERIES_CACHE = {}
        for path in ("hotel_galleries_kb.json", os.path.join(os.path.dirname(__file__), "hotel_galleries_kb.json")):
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            _HOTEL_GALLERIES_CACHE = data.get("galleries", {})
                        break
                except Exception:
                    pass
    return _HOTEL_GALLERIES_CACHE


def _compute_price_intelligence(
    current_price: float,
    min_price: float,
    max_price: float,
    price_drop_pct: float,
    deal_score: Optional[int] = None,
    delta_avg: Optional[str] = None,
    delta48: Optional[str] = None,
    hopper_verdict: Optional[str] = None,
    hopper_reasoning: Optional[str] = None,
    forecast_text: Optional[str] = None,
):
    if price_drop_pct >= 8.0:
        deal_badge = f"🟢 Рекордное дно! ↓ -{price_drop_pct:.0f}%"
        deal_sub = "Цена на минимуме за последние 30 дней"
        deal_class = "drop"
        recommendation = "Идеальный момент для покупки: зафиксировано рекордное падение цены относительно пика сезона."
    elif min_price > 0 and current_price <= (min_price + (max_price - min_price) * 0.25):
        deal_badge = "🟢 Выгодная цена"
        deal_sub = "В нижней четверти ценового диапазона"
        deal_class = "good"
        recommendation = "Хороший момент для бронирования: цена близка к историческому минимуму."
    else:
        deal_badge = "🟡 Стабильная цена"
        deal_sub = "В пределах среднерыночной нормы"
        deal_class = "fair"
        recommendation = "Цена стабильна. Резких ценовых скачков не зафиксировано."

    diff_text = ""
    if delta_avg:
        diff_text = f"{delta_avg} к средней"
    elif min_price > 0 and current_price <= min_price:
        diff_text = "Исторический минимум"
    elif max_price > min_price:
        pct_from_min = ((current_price - min_price) / max_price) * 100
        diff_text = f"+{pct_from_min:.0f}% от минимума"
    else:
        diff_text = "Стабильная цена"

    if deal_score is not None and deal_score >= 70:
        price_signal = "🟢 ПОКУПАТЬ СЕЙЧАС"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł — исключительно выгодный момент. "
            f"Deal Score {deal_score}/100 фиксирует сильную ценовую аномалию. "
            f"{hopper_reasoning or recommendation} "
            f"Вероятность дальнейшего снижения цены минимальна."
        )
    elif price_drop_pct >= 6.0:
        price_signal = "🟢 ПОКУПАТЬ (ЦЕНА УПАЛА)"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł упала на -{price_drop_pct:.0f}% за последние 48 часов. "
            f"{deal_sub}. Рекомендуется фиксировать тур, пока есть доступные места."
        )
    elif min_price > 0 and current_price <= (min_price + (max_price - min_price) * 0.25):
        price_signal = "🟢 ВЫГОДНАЯ ЦЕНА"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł находится в нижней четверти исторического диапазона ({int(min_price):,} – {int(max_price):,} zł). "
            f"Сигнал Hopper: «{hopper_verdict or 'Покупать'}». Отличное соотношение цены и качества."
        )
    else:
        price_signal = "🟡 ЦЕНА СТАБИЛЬНА"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł соответствует сезонной норме для этого отеля. "
            f"{forecast_text or 'Резких ценовых колебаний не зафиксировано'}. Можно бронировать при совпадении дат."
        )

    return deal_badge, deal_sub, deal_class, recommendation, price_signal, ai_price_summary, diff_text


def generate_hotel_ai_profile(
    hotel_name: str,
    country: str = "",
    destination: str = "",
    specs: Optional[Dict[str, Any]] = None,
    rep_data: Optional[Dict[str, Any]] = None,
    current_price: float = 0.0,
    min_price: float = 0.0,
    max_price: float = 0.0,
    price_drop_pct: float = 0.0,
    packages: Optional[List[Dict[str, Any]]] = None,
    main_image_url: str = "",
    other_filters: Optional[List[Dict[str, Any]]] = None,
    deal_score: Optional[int] = None,
    delta_avg: Optional[str] = None,
    delta48: Optional[str] = None,
    hopper_verdict: Optional[str] = None,
    hopper_reasoning: Optional[str] = None,
    forecast_text: Optional[str] = None,
    ta_rating_override: Optional[float] = None,
    ta_reviews_override: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Synthesizes rich profile for hotel:
    - Stars classification (3, 4, 5★)
    - TripAdvisor rating & review count
    - YouTube review search link & compact banner
    - Interactive 4-photo gallery model
    - Rich 6-block Infrastructure attributes
    - Cross-filter monitoring presence
    - Structured AI Verdict, Pros, Cons, and Review quotes
    - Price intelligence status and advice
    """
    # 0. Specs unwrap if nested & safe dict initialization
    if specs and isinstance(specs, dict) and "specs" in specs and isinstance(specs["specs"], dict):
        specs = specs["specs"]
    if not isinstance(specs, dict):
        specs = {}
    if not isinstance(rep_data, dict):
        rep_data = {}

    # 1. Use verified, pre-compiled Passport if present in Knowledge Base (Zero runtime heuristics)
    if specs and "passport" in specs and isinstance(specs["passport"], dict):
        p = specs["passport"]
        deal_badge, deal_sub, deal_class, recommendation, price_signal, ai_price_summary, diff_text = _compute_price_intelligence(
            current_price=current_price,
            min_price=min_price,
            max_price=max_price,
            price_drop_pct=price_drop_pct,
            deal_score=deal_score,
            delta_avg=delta_avg,
            delta48=delta48,
            hopper_verdict=hopper_verdict,
            hopper_reasoning=hopper_reasoning,
            forecast_text=forecast_text,
        )

        encoded_name = urllib.parse.quote(hotel_name)
        encoded_query = urllib.parse.quote(f"{hotel_name} {destination or country} reviews")
        tripadvisor_url = f"https://www.tripadvisor.com/Search?q={encoded_name}"
        google_reviews_url = f"https://www.google.com/search?q={encoded_query}"
        yt_main_query = urllib.parse.quote(f"обзор отеля {hotel_name}")
        youtube_search_url = f"https://www.youtube.com/results?search_query={yt_main_query}"

        gallery_photos = []
        if specs.get("gallery_photos"):
            gallery_photos = list(specs["gallery_photos"])
        else:
            g_kb = _get_galleries_kb()
            if hotel_name in g_kb:
                gallery_photos = list(g_kb[hotel_name])
            elif main_image_url:
                gallery_photos.append({"label": "Территория и отель", "url": main_image_url})
            else:
                gallery_photos.append({"label": "Территория и отель", "url": ""})

        ta_rating_final = ta_rating_override if (ta_rating_override is not None and ta_rating_override > 0) else p.get("ta_rating", 4.2)
        ta_reviews_final = ta_reviews_override if (ta_reviews_override is not None and ta_reviews_override > 0) else int(p.get("ta_reviews", 0))

        ai_summary_safe = p.get("ai_hotel_summary", "")
        verdict_safe = p.get("verdict", "")
        cur_geo = destination or country
        if cur_geo and any(dg in cur_geo for dg in ("Кипр", "Греция", "Турция", "Египет", "Испания")):
            target_country = "Кипр" if "Кипр" in cur_geo else ("Греция" if "Греция" in cur_geo else ("Турция" if "Турция" in cur_geo else ("Египет" if "Египет" in cur_geo else "Испания")))
            from scripts.hotel_passport_compiler import format_region_prepositional
            expected_prep = format_region_prepositional(target_country)
            for bad_prep in ("в регионе Египет", "в Египте", "в регионе Греция", "в Греции", "в регионе Турция", "в Турции", "в регионе Кипр", "на Кипре", "в регионе Испания", "в Испании"):
                if bad_prep in ai_summary_safe and bad_prep != expected_prep:
                    ai_summary_safe = ai_summary_safe.replace(bad_prep, expected_prep)
                if bad_prep in verdict_safe and bad_prep != expected_prep:
                    verdict_safe = verdict_safe.replace(bad_prep, expected_prep)

        return {
            "stars": p.get("stars", 4),
            "ta_rating": ta_rating_final,
            "ta_reviews": int(ta_reviews_final or 0),
            "beach_line": p.get("beach_line", 1),
            "beach_type": p.get("beach_type", "Песчаный пляж"),
            "sea_entry": p.get("sea_entry", "Пологий песчаный вход"),
            "has_aquapark": p.get("has_aquapark", False),
            "has_heated_pools": p.get("has_heated_pools", False),
            "food_concept": p.get("food_concept", "All Inclusive"),
            "suitable_for": p.get("suitable_for", "Отдых и релакс"),
            "verdict": verdict_safe,
            "ai_hotel_summary": ai_summary_safe,
            "ai_price_summary": ai_price_summary,
            "ai_audience": p.get("ai_audience", ""),
            "ai_action_signal": price_signal,
            "price_diff_text": diff_text,
            "pros": list(p.get("pros", []))[:3],
            "cons": list(p.get("cons", []))[:2],
            "food_snippet": p.get("food_snippet", ""),
            "beach_snippet": p.get("beach_snippet", ""),
            "review_snippet": p.get("review_snippet", ""),
            "deal_badge": deal_badge,
            "deal_sub": deal_sub,
            "deal_class": deal_class,
            "recommendation": recommendation,
            "tripadvisor_url": tripadvisor_url,
            "google_reviews_url": google_reviews_url,
            "youtube_search_url": youtube_search_url,
            "gallery_photos": gallery_photos,
            "infra_rich": p.get("infra_rich", {}),
            "other_filters": other_filters or [],
        }

    # Fallback generation for non-indexed/new hotels
    stars = None
    if specs and specs.get("stars"):
        try:
            stars = int(specs["stars"])
        except (ValueError, TypeError):
            pass
    if not stars:
        if re.search(r"5\s*(?:\*|★)|5-star|luxury|palace|resort & spa|premium|deluxe", hotel_name, re.I):
            stars = 5
        elif re.search(r"3\s*(?:\*|★)|3-star", hotel_name, re.I):
            stars = 3
        elif current_price >= 6500:
            stars = 5
        else:
            stars = 4

    # 2. TripAdvisor Rating & Reviews
    ta_rating = ta_rating_override if (ta_rating_override is not None and ta_rating_override > 0) else None
    ta_reviews = ta_reviews_override if (ta_reviews_override is not None and ta_reviews_override > 0) else 0
    if not ta_rating and specs and specs.get("tripadvisor_rating"):
        try:
            r_val = float(specs["tripadvisor_rating"])
            if r_val > 0:
                ta_rating = r_val
                ta_reviews = int(specs.get("tripadvisor_reviews") or 0)
        except (ValueError, TypeError):
            pass
    elif rep_data and rep_data.get("ta_rating"):
        try:
            r_val = float(rep_data["ta_rating"])
            if r_val > 0:
                ta_rating = r_val
                ta_reviews = int(rep_data.get("ta_review_count") or 0)
        except (ValueError, TypeError):
            pass
    elif rep_data and rep_data.get("sentiment_scores"):
        scores = rep_data["sentiment_scores"]
        valid = [v for v in scores.values() if isinstance(v, (int, float)) and v > 0]
        if valid:
            ta_rating = round(sum(valid) / len(valid) / 2, 1)

    if not ta_rating or ta_rating < 3.0:
        ta_rating = 4.5 if stars == 5 else (4.1 if stars == 4 else 3.8)
        ta_reviews = 0

    # 3. Infrastructure traits
    has_aquapark = False
    if specs and "aquapark" in specs:
        has_aquapark = bool(specs["aquapark"])
    elif re.search(r"aqua\s*park|water\s*park|аквапарк", hotel_name, re.I):
        has_aquapark = True

    has_heated_pools = False
    cons_text = " ".join((rep_data.get("cons_and_red_flags") or []) if rep_data else []).lower()
    if "отсутствие гарантированного подогрева" in cons_text or "без подогрева" in cons_text or "нет подогрева" in cons_text:
        has_heated_pools = False
    elif specs and "heated_pools_winter" in specs:
        has_heated_pools = bool(specs["heated_pools_winter"])
    elif rep_data and "winter_suitability" in rep_data and "heated_pools" in rep_data["winter_suitability"]:
        has_heated_pools = bool(rep_data["winter_suitability"]["heated_pools"])
    elif country in ("Египет", "egipt") and stars >= 5:
        has_heated_pools = True

    beach_line = 2
    if specs and specs.get("beach_line"):
        try:
            beach_line = int(specs["beach_line"])
        except (ValueError, TypeError):
            beach_line = 2
    elif re.search(r"\b(beach\s*resort|seafront|beachfront|on the beach|plage|strand)\b", hotel_name, re.I):
        beach_line = 1
    elif re.search(r"\b(city|inn|suites|apartments|gardens?|hills?|residence|village)\b", hotel_name, re.I):
        beach_line = 2
    else:
        beach_line = 2

    # Beach type & entry
    c_lower = country.lower()
    dest_lower = destination.lower()
    if "египет" in c_lower or "egipt" in c_lower:
        if "marsa" in dest_lower or "шарм" in dest_lower:
            beach_type = "Песчаный с коралловым рифом"
            sea_entry = "Песчаный заход + понтон к рифу"
        else:
            beach_type = "Собственный песчаный"
            sea_entry = "Пологий песчаный вход"
    elif "кипр" in c_lower or "cypr" in c_lower:
        beach_type = "Песчаный пляж с Голубым флагом"
        sea_entry = "Плавный вход в кристальное море"
    elif "турция" in c_lower or "turcja" in c_lower or "turkey" in c_lower:
        beach_type = "Собственный песчано-галечный"
        sea_entry = "Удобный пологий заход"
    elif "греция" in c_lower or "grecja" in c_lower:
        beach_type = "Живописная песчано-галечная бухта"
        sea_entry = "Плавный вход в бирюзовое море"
    else:
        beach_type = "Песчаный пляж"
        sea_entry = "Пологий вход в море"

    # Food concept
    food_concept = "Ultra All Inclusive" if stars == 5 else "All Inclusive"
    if packages and any("hb" in p.get("filter_id", "").lower() for p in packages):
        food_concept = "Half Board (Завтрак + Ужин)"

    # 4. Rich Infrastructure Dictionary (6 categories)
    if specs and "infrastructure" in specs and isinstance(specs["infrastructure"], dict):
        infra_rich = specs["infrastructure"]
    else:
        # Truthful dynamic fallback based on actual specs and hotel tier
        beach_line_str = f"{beach_line}-я линия (собственный оборудованный пляж)" if beach_line == 1 else (f"{beach_line}-я линия (через променад/дорогу, 200–600м)" if beach_line == 2 else f"{beach_line}-я линия (в глубине курорта, шаттл на пляж)")
        reef_desc = "Живой коралловый риф, удобный спуск с понтона для снорклинга" if ("риф" in beach_type.lower() or (specs and specs.get("reef_presence") == "live_house_reef")) else "Чистое пологое дно, подходит для купания без спецобуви"
        if specs and specs.get("pontoon_length_m"):
            reef_desc += f" (длина понтона: {specs['pontoon_length_m']} м)"

        pool_cnt = specs.get('pool_count') if specs else None
        if pool_cnt == 1:
            pools_count_str = "1 открытый бассейн с пресной водой"
        elif pool_cnt and 2 <= pool_cnt <= 4:
            pools_count_str = f"{pool_cnt} открытых бассейна с пресной водой"
        elif pool_cnt and pool_cnt >= 5:
            pools_count_str = f"{pool_cnt} открытых бассейнов с пресной водой"
        else:
            pools_count_str = "Открытый плавательный бассейн"

        if has_heated_pools:
            heated_desc = (specs.get("heated_pools_details") if specs else None) or "Бассейн с постоянным зимним подогревом (+28°C)"
        else:
            heated_desc = "Открытый бассейн, терраса для загара (зимний подогрев отсутствует)" if pool_cnt == 1 else "Открытые бассейны, терраса для загара (зимний подогрев отсутствует)"

        slides_cnt = specs.get("slides_total", 0) if specs else 0
        if has_aquapark and slides_cnt > 0:
            aqua_desc = f"Собственный аквапарк ({slides_cnt} водных горок)"
        elif has_aquapark:
            aqua_desc = "Собственный аквапарк с водными горками для взрослых и детей"
        elif slides_cnt > 0:
            aqua_desc = f"{slides_cnt} водные горки при бассейне (не является аквапарком)"
        else:
            aqua_desc = "Водные горки и аквапарк отсутствуют"

        if stars >= 5:
            main_b = "Главный ресторан: богатый шведский стол, тематические ужины, гриль-станция и свежая выпечка"
            alac = "2–4 ресторана a la carte (итальянская, восточная, рыбная кухни) по предварительной записи"
            bars_desc = "Круглосуточный лобби-бар, бар у бассейна, пляжный снек-бар с закусками и мороженым"
            spa_desc = "Спа-комплекс: турецкий хаммам, финская сауна, паровая комната и массажные кабинеты"
            fit_desc = "Современный тренажерный зал с кардио- и силовыми тренажерами"
            wifi_desc = "Бесплатный высокоскоростной Wi-Fi на территории и в лобби отеля"
        elif stars == 4:
            main_b = "Главный ресторан: разнообразный шведский стол, блюда местной и международной кухни"
            if beach_line >= 3:
                alac = "Рестораны a la carte отсутствуют. Работают основной ресторан и бар у бассейна"
                spa_desc = "Спа-комплекс отсутствует (массаж по запросу за доплату)"
                fit_desc = "Тренажерный зал отсутствует либо базовая фитнес-комната"
            else:
                alac = "1–2 ресторана a la carte (по предварительной записи) и лобби-бар"
                spa_desc = "Спа-зона: сауна, парная и массажные кабинеты (процедуры платно)"
                fit_desc = "Тренажерный зал с базовыми кардио- и силовыми тренажерами"
            bars_desc = "Лобби-бар, бар у бассейна и дневной снек-бар"
            wifi_desc = "Бесплатный Wi-Fi в лобби и общественных зонах"
        else: # 3 stars and below
            main_b = "Главный ресторан: базовый шведский стол с блюдами местной кухни"
            alac = "Рестораны a la carte отсутствуют. Доступны основной ресторан и бар у бассейна"
            bars_desc = "Бар у бассейна и напитки в ресторане во время питания"
            spa_desc = "Спа-комплекс отсутствует (массажные услуги по запросу за доплату)"
            fit_desc = "Тренажерный зал отсутствует"
            wifi_desc = "Бесплатный базовый Wi-Fi в зоне лобби (в номерах отсутствует)"

        if beach_line >= 3:
            beach_equip = "Шезлонги и зонты на арендованном пляже (бесплатно). Напитки в пляжном баре за доплату"
            watersp = "Снорклинг и водные виды спорта доступны на общественном пляже платно"
        elif beach_line == 2:
            beach_equip = "Бесплатные шезлонги и зонты на выделенной пляжной зоне, пляжные полотенца"
            watersp = "Водные виды спорта и снорклинг на пляже (платно)"
        else:
            beach_equip = "Бесплатные шезлонги, солнцезащитные зонты, пляжные полотенца, бар на пляже"
            watersp = "Дайвинг-центр, прокат оборудования для снорклинга и водные виды спорта"

        infra_rich = {
            "beach": {
                "line": beach_line_str,
                "type": beach_type,
                "entry": sea_entry,
                "equipment": beach_equip,
                "reef": reef_desc,
            },
            "pools": {
                "pools_count": pools_count_str,
                "heated": heated_desc,
                "aquapark": aqua_desc,
                "indoor": "Крытый бассейн в спа-центре" if stars >= 5 else "Крытый бассейн отсутствует",
            },
            "food": {
                "concept": food_concept,
                "main_buffet": main_b,
                "alacarte": alac,
                "bars": bars_desc,
            },
            "kids": {
                "club": "Мини-клуб для детей от 4 до 12 лет с анимационной программой" if stars >= 4 and beach_line <= 2 else "Мини-клуб отсутствует (эконом-формат без специализированной детской анимации)",
                "pool": "Мелкий детский бассейн с навесом от прямого солнца" if stars >= 4 else "Интегрированная мелкая секция в общем бассейне",
                "playground": "Оборудованная игровая площадка на свежем воздухе" if stars >= 4 else "Компактная игровая зона на территории",
                "menu": "Детские стульчики в ресторане",
            },
            "sport_spa": {
                "spa": spa_desc,
                "fitness": fit_desc,
                "sport": "Настольный теннис, дартс, утренняя гимнастика",
                "watersports": watersp,
            },
            "comfort": {
                "wifi": wifi_desc,
                "room_amenities": f"Индивидуальный кондиционер, сейф, балкон/терраса, мини-бар. Реновация: {specs.get('last_renovation_year')} г." if (specs and specs.get('last_renovation_year')) else "Индивидуальный кондиционер, сейф, балкон/терраса, мини-бар, спутниковое ТВ",
                "distance": f"Трансфер из аэропорта ({specs.get('nearest_airport') or 'а/п'}): ~{specs['transfer_minutes']} мин (регион {destination or country})" if (specs and specs.get('transfer_minutes')) else f"Трансфер из аэропорта: ~20–35 минут (регион {destination or country})",
                "service": "Круглосуточная стойка регистрации, камера хранения багажа",
            },
        }

    # 5. AI Verdict & Pros/Cons
    verdict = ""
    pros = []
    cons = []
    if specs and specs.get("highlights"):
        pros = [p for p in specs["highlights"] if len(p) > 8][:3]
    elif rep_data and rep_data.get("pros"):
        pros = [p for p in rep_data["pros"] if len(p) > 10][:3]

    if specs and specs.get("caution_notes"):
        cons = [c for c in specs["caution_notes"] if len(c) > 8][:2]
    elif rep_data and rep_data.get("cons_and_red_flags"):
        cons = [c for c in rep_data["cons_and_red_flags"] if len(c) > 10][:2]

    if rep_data and rep_data.get("verdict") and len(rep_data["verdict"]) > 25:
        verdict = rep_data["verdict"]

    if not verdict:
        if has_aquapark and has_heated_pools:
            verdict = f"Отличный семейный отель категории {stars}★ с собственным аквапарком, бассейнами с зимним подогревом и разнообразным питанием."
        elif stars == 5:
            verdict = f"Премиальный курортный комплекс {stars}★ на {beach_line}-й линии с высоким уровнем сервиса, просторными номерами и концепцией {food_concept}."
        else:
            verdict = f"Качественный отель {stars}★ в регионе {destination or country} с ухоженной зеленой территорией и комфортным пляжным отдыхом."

    if not pros:
        pros = [
            f"{beach_line}-я линия: собственный оборудованный пляж ({beach_type})",
            "Бассейны с подогревом в зимний период" if has_heated_pools else "Большая зеленая территория и несколько открытых бассейнов",
            f"Питание «{food_concept}»: разнообразный шведский стол, блюда на гриле и свежие фрукты",
        ]
        if has_aquapark:
            pros.insert(1, "Собственный аквапарк с водными горками для взрослых и детей")

    if not cons:
        if has_aquapark:
            cons = ["Высокая популярность отеля: в пиковый сезон возможна повышенная активность у бассейнов"]
        elif beach_line == 2:
            cons = ["Вторая линия: до пляжа курсирует бесплатный шаттл-бас (3–5 минут)"]
        else:
            cons = ["Во время отлива глубина у берега снижается, для плавания рекомендуется понтон"]

    suitable_for = "Семьи с детьми и пары" if (has_aquapark or has_heated_pools) else "Пары и спокойный отдых"
    if stars == 5:
        suitable_for = "Премиальный отдых и семьи"

    food_snippet = f"Концепция «{food_concept}»: гости хвалят свежевыжатые соки, блюда на гриле, свежую выпечку и разнообразие десертов. Доступны a la carte рестораны."
    dist_val = specs.get("beach_distance_meters") if specs else None
    if beach_line >= 2:
        dist_text = f" (~{dist_val} м)" if dist_val else ""
        beach_snippet = f"{beach_line}-я линия{dist_text} ({beach_type}). Курсирует бесплатный шаттл-бас на пляж. {sea_entry}."
    else:
        beach_snippet = f"1-я линия ({beach_type}): собственный оборудованный пляж. {sea_entry}."
    review_snippet = ""
    canned_phrases = (
        "стабильное качество обслуживания",
        "на уровне категории отеля",
        "отдыхали здесь в этом сезоне",
        "удобное расположение относительно",
        "качественный отель категории",
    )
    if rep_data and isinstance(rep_data, dict):
        if rep_data.get("review_snippet"):
            cand = str(rep_data["review_snippet"]).strip()
            if cand and not any(cp in cand.lower() for cp in canned_phrases):
                review_snippet = cand
        elif rep_data.get("season_trend", {}).get("summary"):
            s_sum = str(rep_data["season_trend"]["summary"]).strip()
            if s_sum and len(s_sum) > 15 and not any(cp in s_sum.lower() for cp in canned_phrases):
                review_snippet = f"«{s_sum}» (Сводка отзывов туристов)"

    # 6. Price Intelligence status
    if price_drop_pct >= 8.0:
        deal_badge = f"🟢 Рекордное дно! ↓ -{price_drop_pct:.0f}%"
        deal_sub = "Цена на минимуме за последние 30 дней"
        deal_class = "drop"
        recommendation = "Идеальный момент для покупки: зафиксировано рекордное падение цены относительно пика сезона."
    elif min_price > 0 and current_price <= (min_price + (max_price - min_price) * 0.25):
        deal_badge = "🟢 Выгодная цена"
        deal_sub = "В нижней четверти ценового диапазона"
        deal_class = "good"
        recommendation = "Хороший момент для бронирования: цена близка к историческому минимуму."
    else:
        deal_badge = "🟡 Стабильная цена"
        deal_sub = "В пределах среднерыночной нормы"
        deal_class = "fair"
        recommendation = "Цена стабильна. Резких ценовых скачков не зафиксировано."

    # 7. AI Executive Dossier: Hotel & Live Price Summaries
    ai_hotel_summary = (
        f"{hotel_name} — современный курортный комплекс категории {stars}★ в регионе {destination or country}. "
        f"Расположен на {beach_line}-й линии ({beach_type.lower()}). "
        f"Ключевые преимущества: концепция питания «{food_concept}», {pros[0].lower() if pros else 'чистая территория'}, "
        f"{'собственный аквапарк с горками' if has_aquapark else 'несколько открытых бассейнов'}"
        f"{' и бассейны с подогревом в зимний период' if has_heated_pools else ''}."
    )

    diff_text = ""
    if delta_avg:
        diff_text = f"{delta_avg} к средней"
    elif min_price > 0 and current_price <= min_price:
        diff_text = "Исторический минимум"
    elif max_price > min_price:
        pct_from_min = ((current_price - min_price) / max_price) * 100
        diff_text = f"+{pct_from_min:.0f}% от минимума"
    else:
        diff_text = "Стабильная цена"

    if deal_score is not None and deal_score >= 70:
        price_signal = "🟢 ПОКУПАТЬ СЕЙЧАС"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł — исключительно выгодный момент. "
            f"Deal Score {deal_score}/100 фиксирует сильную ценовую аномалию. "
            f"{hopper_reasoning or recommendation} "
            f"Вероятность дальнейшего снижения цены минимальна."
        )
    elif price_drop_pct >= 6.0:
        price_signal = "🟢 ПОКУПАТЬ (ЦЕНА УПАЛА)"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł упала на -{price_drop_pct:.0f}% за последние 48 часов. "
            f"{deal_sub}. Рекомендуется фиксировать тур, пока есть доступные места."
        )
    elif min_price > 0 and current_price <= (min_price + (max_price - min_price) * 0.25):
        price_signal = "🟢 ВЫГОДНАЯ ЦЕНА"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł находится в нижней четверти исторического диапазона ({int(min_price):,} – {int(max_price):,} zł). "
            f"Сигнал Hopper: «{hopper_verdict or 'Покупать'}». Отличное соотношение цены и качества."
        )
    else:
        price_signal = "🟡 ЦЕНА СТАБИЛЬНА"
        ai_price_summary = (
            f"Текущая цена {int(current_price):,} zł соответствует сезонной норме для этого отеля. "
            f"{forecast_text or 'Резких ценовых колебаний не зафиксировано'}. Можно бронировать при совпадении дат."
        )

    ai_audience = f"{suitable_for}. Рекомендуется тем, кому важны {'аквапарк и активная семейная анимация' if has_aquapark else 'спокойный качественный пляжный отдых'} и сервис уровня {stars}★."

    # 8. Direct external URLs & Compact YouTube Link
    encoded_name = urllib.parse.quote(hotel_name)
    encoded_query = urllib.parse.quote(f"{hotel_name} {destination or country} reviews")
    tripadvisor_url = f"https://www.tripadvisor.com/Search?q={encoded_name}"
    google_reviews_url = f"https://www.google.com/search?q={encoded_query}"

    yt_main_query = urllib.parse.quote(f"обзор отеля {hotel_name}")
    youtube_search_url = f"https://www.youtube.com/results?search_query={yt_main_query}"

    # 9. Interactive Photo Gallery List
    gallery_photos = []
    if specs and isinstance(specs, dict) and specs.get("gallery_photos"):
        gallery_photos = list(specs.get("gallery_photos"))
    else:
        g_kb = _get_galleries_kb()
        if hotel_name in g_kb:
            gallery_photos = list(g_kb[hotel_name])
        elif main_image_url:
            gallery_photos.append({"label": "Территория и отель", "url": main_image_url})
        else:
            gallery_photos.append({"label": "Территория и отель", "url": ""})

    return {
        "stars": stars,
        "ta_rating": ta_rating,
        "ta_reviews": int(ta_reviews or 0),
        "beach_line": beach_line,
        "beach_type": beach_type,
        "sea_entry": sea_entry,
        "has_aquapark": has_aquapark,
        "has_heated_pools": has_heated_pools,
        "food_concept": food_concept,
        "suitable_for": suitable_for,
        "verdict": verdict,
        "ai_hotel_summary": ai_hotel_summary,
        "ai_price_summary": ai_price_summary,
        "ai_audience": ai_audience,
        "ai_action_signal": price_signal,
        "price_diff_text": diff_text,
        "pros": pros[:3],
        "cons": cons[:2],
        "food_snippet": food_snippet,
        "beach_snippet": beach_snippet,
        "review_snippet": review_snippet,
        "deal_badge": deal_badge,
        "deal_sub": deal_sub,
        "deal_class": deal_class,
        "recommendation": recommendation,
        "tripadvisor_url": tripadvisor_url,
        "google_reviews_url": google_reviews_url,
        "youtube_search_url": youtube_search_url,
        "gallery_photos": gallery_photos,
        "infra_rich": infra_rich,
        "other_filters": other_filters or [],
    }


def get_hotel_passport_css() -> str:
    """Returns CSS styles for horizontal OTA cards, table passport buttons, 780px slide-over drawer, and gallery carousel."""
    return """
    /* ══════════════════════════════════════════════════════════════
       TABLE VIEW: FULL ROW CLICKABLE INTERACTION
       ══════════════════════════════════════════════════════════════ */
    .hotels-table tbody tr.hotel-row {
      cursor: pointer !important;
      transition: background-color 0.15s ease, transform 0.12s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.15s ease;
    }

    .hotels-table tbody tr.hotel-row:hover td {
      background: #f0f7ff !important;
      border-top-color: #38bdf8 !important;
      border-bottom-color: #38bdf8 !important;
    }

    .hotels-table tbody tr.hotel-row:hover td:first-child {
      border-left-color: #38bdf8 !important;
    }

    .hotels-table tbody tr.hotel-row:hover td:last-child {
      border-right-color: #38bdf8 !important;
    }

    .dark-theme .hotels-table tbody tr.hotel-row:hover td {
      background: #1e293b !important;
      border-top-color: #6366f1 !important;
      border-bottom-color: #6366f1 !important;
    }

    .dark-theme .hotels-table tbody tr.hotel-row:hover td:first-child {
      border-left-color: #6366f1 !important;
    }

    .dark-theme .hotels-table tbody tr.hotel-row:hover td:last-child {
      border-right-color: #6366f1 !important;
    }

    .hotels-table tbody tr.hotel-row .hotel-hover-link {
      cursor: pointer;
      color: #0f172a;
      text-decoration: none;
      font-weight: 700;
    }

    .hotels-table tbody tr.hotel-row:hover .hotel-hover-link {
      color: #0284c7;
      text-decoration: underline;
    }

    .dark-theme .hotels-table tbody tr.hotel-row .hotel-hover-link {
      color: #f1f5f9;
    }

    .dark-theme .hotels-table tbody tr.hotel-row:hover .hotel-hover-link {
      color: #38bdf8;
    }

    /* Isolated controls inside row */
    .hotels-table tbody tr.hotel-row .watchlist-star-btn,
    .hotels-table tbody tr.hotel-row .offer-link-cell a,
    .hotels-table tbody tr.hotel-row .cheaper-alt-badge {
      cursor: pointer;
      position: relative;
      z-index: 2;
    }

    /* ══════════════════════════════════════════════════════════════
       HORIZONTAL OTA AGGREGATOR CARDS
       ══════════════════════════════════════════════════════════════ */
    .cards-grid {
      display: flex;
      flex-direction: column;
      gap: 16px;
      margin-bottom: 2rem;
    }

    .hotel-card-horiz {
      display: grid;
      grid-template-columns: 280px 1fr 260px;
      gap: 0;
      background: #ffffff;
      border: 1px solid rgba(226, 232, 240, 0.9);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
      transition: all 0.22s ease-in-out;
      cursor: pointer;
      position: relative;
    }

    .hotel-card-horiz:hover {
      transform: translateY(-3px);
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.12);
      border-color: rgba(99, 102, 241, 0.4);
    }

    .dark-theme .hotel-card-horiz {
      background: #1e293b;
      border-color: #334155;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
    }

    .dark-theme .hotel-card-horiz:hover {
      border-color: rgba(129, 140, 248, 0.45);
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.5);
    }

    /* Col 1: Media Column */
    .card-media-col {
      position: relative;
      background: #f1f5f9;
      min-height: 220px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
    }

    .dark-theme .card-media-col {
      background: #0f172a;
    }

    .card-photo {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: transform 0.4s ease;
    }

    .hotel-card-horiz:hover .card-photo {
      transform: scale(1.04);
    }

    .card-photo-placeholder {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
      color: #64748b;
      gap: 6px;
      z-index: 1;
    }

    .dark-theme .card-photo-placeholder {
      background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
      color: #94a3b8;
    }

    .card-photo-placeholder-icon {
      font-size: 2.2rem;
      line-height: 1;
      filter: drop-shadow(0 2px 4px rgba(0,0,0,0.06));
    }

    .card-photo-placeholder-text {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      opacity: 0.8;
      text-transform: uppercase;
    }

    .card-media-badges {
      position: relative;
      z-index: 2;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 10px;
      pointer-events: none;
    }

    .badge-country {
      background: rgba(15, 23, 42, 0.78);
      color: #ffffff;
      font-size: 0.72rem;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 6px;
      backdrop-filter: blur(4px);
    }

    .badge-drop {
      background: #ef4444;
      color: #ffffff;
      font-size: 0.75rem;
      font-weight: 800;
      padding: 4px 8px;
      border-radius: 6px;
      box-shadow: 0 2px 6px rgba(239, 68, 68, 0.4);
    }

    .card-media-footer {
      position: relative;
      z-index: 2;
      padding: 8px 10px;
      background: linear-gradient(to top, rgba(15, 23, 42, 0.92) 0%, rgba(15, 23, 42, 0.4) 70%, transparent 100%);
      display: flex;
      flex-direction: column;
      gap: 5px;
    }

    .media-footer-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
    }

    .ta-score-pill {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: rgba(255, 255, 255, 0.92);
      color: #0f172a;
      padding: 2px 7px;
      border-radius: 6px;
      font-size: 0.72rem;
      font-weight: 700;
    }

    .dark-theme .ta-score-pill {
      background: rgba(30, 41, 59, 0.92);
      color: #f8fafc;
    }

    .ta-link-sm {
      color: #38bdf8;
      font-size: 0.72rem;
      font-weight: 600;
      text-decoration: none;
      transition: color 0.15s ease;
    }

    .ta-link-sm:hover {
      color: #bae6fd;
      text-decoration: underline;
    }

    .yt-badge-sm {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: rgba(239, 68, 68, 0.18);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #fca5a5;
      padding: 2px 7px;
      border-radius: 6px;
      font-size: 0.7rem;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.15s ease;
    }

    .yt-badge-sm:hover {
      background: rgba(239, 68, 68, 0.35);
      color: #ffffff;
    }

    .yt-svg-inline {
      width: 14px;
      height: 14px;
      fill: currentColor;
    }

    /* Col 2: Content Column */
    .card-content-col {
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      border-right: 1px solid rgba(226, 232, 240, 0.7);
    }

    .dark-theme .card-content-col {
      border-right-color: #334155;
    }

    .card-title-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 4px;
    }

    .card-hotel-title {
      font-size: 1.15rem;
      font-weight: 800;
      color: #0f172a;
      margin: 0;
      line-height: 1.3;
    }

    .dark-theme .card-hotel-title {
      color: #f8fafc;
    }

    .hotel-stars {
      color: #f59e0b;
      font-size: 0.95rem;
      letter-spacing: 1px;
      white-space: nowrap;
    }

    .card-geo-line {
      font-size: 0.82rem;
      color: #64748b;
      margin-bottom: 10px;
    }

    .dark-theme .card-geo-line {
      color: #94a3b8;
    }

    .card-infra-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }

    .infra-pill {
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: #f1f5f9;
      color: #334155;
      border: 1px solid #e2e8f0;
    }

    .dark-theme .infra-pill {
      background: #0f172a;
      color: #cbd5e1;
      border-color: #334155;
    }

    .infra-pill.warm {
      background: #fff7ed;
      color: #c2410c;
      border-color: #fed7aa;
    }

    .dark-theme .infra-pill.warm {
      background: rgba(194, 65, 12, 0.15);
      color: #fdba74;
      border-color: rgba(194, 65, 12, 0.35);
    }

    .infra-pill.aqua {
      background: #f0fdf4;
      color: #15803d;
      border-color: #bbf7d0;
    }

    .dark-theme .infra-pill.aqua {
      background: rgba(21, 128, 61, 0.15);
      color: #86efac;
      border-color: rgba(21, 128, 61, 0.35);
    }

    .card-ai-box {
      background: #f8fafc;
      border-left: 3px solid #6366f1;
      padding: 8px 12px;
      border-radius: 0 8px 8px 0;
      margin-bottom: 8px;
    }

    .dark-theme .card-ai-box {
      background: #0f172a;
      border-left-color: #818cf8;
    }

    .ai-box-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 3px;
    }

    .ai-badge-lbl {
      font-size: 0.72rem;
      font-weight: 800;
      color: #4f46e5;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    .dark-theme .ai-badge-lbl {
      color: #a5b4fc;
    }

    .ai-suitable {
      font-size: 0.72rem;
      font-weight: 600;
      color: #059669;
    }

    .dark-theme .ai-suitable {
      color: #34d399;
    }

    .ai-verdict-text {
      font-size: 0.8rem;
      line-height: 1.35;
      color: #334155;
      margin: 0;
    }

    .dark-theme .ai-verdict-text {
      color: #cbd5e1;
    }

    .card-review-snippet {
      font-size: 0.75rem;
      font-style: italic;
      color: #64748b;
      line-height: 1.3;
      padding-top: 4px;
      border-top: 1px dashed rgba(226, 232, 240, 0.8);
    }

    .dark-theme .card-review-snippet {
      color: #94a3b8;
      border-top-color: #334155;
    }

    /* Col 3: Price Column */
    .card-price-col {
      padding: 16px 18px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      background: #fafaf9;
    }

    .dark-theme .card-price-col {
      background: #182234;
    }

    .deal-status-box {
      padding: 6px 10px;
      border-radius: 8px;
      margin-bottom: 8px;
      border: 1px solid transparent;
    }

    .deal-status-box.drop {
      background: #f0fdf4;
      border-color: #bbf7d0;
      color: #166534;
    }

    .dark-theme .deal-status-box.drop {
      background: rgba(22, 101, 52, 0.2);
      border-color: rgba(34, 197, 94, 0.3);
      color: #86efac;
    }

    .deal-status-box.good {
      background: #eff6ff;
      border-color: #bfdbfe;
      color: #1e40af;
    }

    .dark-theme .deal-status-box.good {
      background: rgba(30, 64, 175, 0.2);
      border-color: rgba(59, 130, 246, 0.3);
      color: #93c5fd;
    }

    .deal-status-box.fair {
      background: #fefce8;
      border-color: #fef08a;
      color: #854d0e;
    }

    .dark-theme .deal-status-box.fair {
      background: rgba(133, 77, 14, 0.2);
      border-color: rgba(234, 179, 8, 0.3);
      color: #fde047;
    }

    .deal-badge-title {
      font-size: 0.78rem;
      font-weight: 800;
      line-height: 1.2;
    }

    .deal-badge-sub {
      font-size: 0.7rem;
      opacity: 0.85;
      margin-top: 2px;
    }

    .price-box-main {
      margin: 4px 0 8px;
    }

    .price-val {
      font-size: 1.55rem;
      font-weight: 900;
      color: #0f172a;
      letter-spacing: -0.5px;
      line-height: 1.1;
    }

    .dark-theme .price-val {
      color: #f8fafc;
    }

    .price-pkg-desc {
      font-size: 0.76rem;
      color: #64748b;
      margin-top: 3px;
    }

    .dark-theme .price-pkg-desc {
      color: #94a3b8;
    }

    .price-flight-dates {
      font-size: 0.74rem;
      color: #475569;
      margin-top: 2px;
    }

    .dark-theme .price-flight-dates {
      color: #cbd5e1;
    }

    .price-spread-box {
      font-size: 0.72rem;
      color: #64748b;
      background: rgba(241, 245, 249, 0.8);
      padding: 6px 8px;
      border-radius: 6px;
      margin-bottom: 12px;
    }

    .dark-theme .price-spread-box {
      background: #0f172a;
      color: #94a3b8;
    }

    .spread-lbl {
      font-size: 0.68rem;
      opacity: 0.8;
      margin-bottom: 2px;
    }

    .spread-vals {
      font-weight: 600;
      color: #334155;
    }

    .dark-theme .spread-vals {
      color: #cbd5e1;
    }

    .card-action-btns {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .btn-book-main {
      display: block;
      text-align: center;
      background: #4f46e5;
      color: #ffffff !important;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 0.82rem;
      font-weight: 700;
      text-decoration: none;
      transition: background 0.16s ease;
    }

    .btn-book-main:hover {
      background: #4338ca;
    }

    .btn-inspect-passport {
      display: block;
      width: 100%;
      text-align: center;
      background: #ffffff;
      color: #334155;
      border: 1px solid #cbd5e1;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.16s ease;
    }

    .btn-inspect-passport:hover {
      background: #f1f5f9;
      border-color: #94a3b8;
      color: #0f172a;
    }

    .dark-theme .btn-inspect-passport {
      background: #1e293b;
      color: #e2e8f0;
      border-color: #475569;
    }

    .dark-theme .btn-inspect-passport:hover {
      background: #334155;
      color: #ffffff;
    }

    /* ══════════════════════════════════════════════════════════════
       PASSPORT DRAWER (780px SLIDE-OVER MODAL)
       ══════════════════════════════════════════════════════════════ */
    .drawer-overlay {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(4px);
      z-index: 10000;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.25s ease, visibility 0.25s ease;
    }

    .drawer-overlay.open {
      opacity: 1;
      visibility: visible;
    }

    .passport-drawer {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 780px;
      max-width: 95vw;
      background: #ffffff;
      box-shadow: -10px 0 35px rgba(0, 0, 0, 0.35);
      z-index: 10001;
      transform: translateX(100%);
      transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .dark-theme .passport-drawer {
      background: #0f172a;
      box-shadow: -10px 0 45px rgba(0, 0, 0, 0.7);
    }

    .passport-drawer.open {
      transform: translateX(0);
    }

    .drawer-header {
      padding: 16px 22px;
      border-bottom: 1px solid #e2e8f0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      background: #ffffff;
      z-index: 5;
    }

    .dark-theme .drawer-header {
      background: #0f172a;
      border-bottom-color: #334155;
    }

    .drawer-title-box {
      flex: 1;
      min-width: 0;
    }

    .drawer-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .drawer-title-box h2 {
      font-size: 1.25rem;
      font-weight: 800;
      color: #0f172a;
      margin: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .dark-theme .drawer-title-box h2 {
      color: #f8fafc;
    }

    .drawer-title-box p {
      font-size: 0.82rem;
      color: #64748b;
      margin: 2px 0 0;
    }

    .dark-theme .drawer-title-box p {
      color: #94a3b8;
    }

    .drawer-header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .btn-drawer-header-ta {
      background: #059669;
      color: #ffffff !important;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 700;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 0.15s ease;
    }

    .btn-drawer-header-ta:hover {
      background: #047857;
    }

    .btn-drawer-header-yt {
      background: #ef4444;
      color: #ffffff !important;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 700;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: background 0.15s ease;
    }

    .btn-drawer-header-yt:hover {
      background: #dc2626;
    }

    .drawer-close-btn {
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      color: #334155;
      font-size: 1.15rem;
      line-height: 1;
      width: 34px;
      height: 34px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .drawer-close-btn:hover {
      background: #e2e8f0;
      color: #0f172a;
    }

    .dark-theme .drawer-close-btn {
      background: #1e293b;
      border-color: #334155;
      color: #cbd5e1;
    }

    .dark-theme .drawer-close-btn:hover {
      background: #334155;
      color: #ffffff;
    }

    /* Tabs Bar */
    .drawer-tabs-bar {
      display: flex;
      border-bottom: 1px solid #e2e8f0;
      background: #f8fafc;
      padding: 0 16px;
      gap: 6px;
      position: sticky;
      top: 0;
      z-index: 4;
    }

    .dark-theme .drawer-tabs-bar {
      background: #1e293b;
      border-bottom-color: #334155;
    }

    .drawer-tab-btn {
      padding: 11px 14px;
      font-size: 0.82rem;
      font-weight: 700;
      color: #64748b;
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.16s ease;
    }

    .drawer-tab-btn:hover {
      color: #0f172a;
    }

    .dark-theme .drawer-tab-btn:hover {
      color: #f8fafc;
    }

    .drawer-tab-btn.active {
      color: #4f46e5;
      border-bottom-color: #4f46e5;
    }

    .dark-theme .drawer-tab-btn.active {
      color: #818cf8;
      border-bottom-color: #818cf8;
    }

    /* Drawer Scrollable Content */
    .drawer-content {
      flex: 1;
      overflow-y: auto;
      padding: 20px 24px 40px;
    }

    .drawer-tab-panel {
      display: none;
    }

    .drawer-tab-panel.active {
      display: block;
    }

    /* ══════════════════════════════════════════════════════════════
       PHOTO GALLERY CAROUSEL
       ══════════════════════════════════════════════════════════════ */
    .drawer-gallery-box {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      overflow: hidden;
      margin-bottom: 18px;
    }

    .dark-theme .drawer-gallery-box {
      background: #1e293b;
      border-color: #334155;
    }

    .gallery-stage {
      position: relative;
      width: 100%;
      height: 240px;
      background: #0f172a;
      overflow: hidden;
    }

    .gallery-main-img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: opacity 0.22s ease;
    }

    .gallery-nav-btn {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      width: 36px;
      height: 36px;
      background: rgba(15, 23, 42, 0.7);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.3);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
      cursor: pointer;
      transition: all 0.16s ease;
      z-index: 3;
    }

    .gallery-nav-btn:hover {
      background: rgba(15, 23, 42, 0.95);
      transform: translateY(-50%) scale(1.08);
    }

    .gallery-nav-btn.prev { left: 12px; }
    .gallery-nav-btn.next { right: 12px; }

    .gallery-counter-pill {
      position: absolute;
      bottom: 12px;
      right: 12px;
      background: rgba(15, 23, 42, 0.78);
      color: #ffffff;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.72rem;
      font-weight: 700;
      z-index: 3;
      backdrop-filter: blur(4px);
    }

    .gallery-thumbs-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      padding: 8px;
      background: #ffffff;
      border-top: 1px solid #e2e8f0;
    }

    .dark-theme .gallery-thumbs-row {
      background: #1e293b;
      border-top-color: #334155;
    }

    .gallery-thumb-item {
      height: 48px;
      border-radius: 6px;
      overflow: hidden;
      cursor: pointer;
      border: 2px solid transparent;
      opacity: 0.65;
      transition: all 0.16s ease;
      position: relative;
    }

    .gallery-thumb-item img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .gallery-thumb-item.active {
      opacity: 1;
      border-color: #4f46e5;
    }

    .gallery-thumb-item:hover {
      opacity: 0.95;
    }

    /* ══════════════════════════════════════════════════════════════
       AI EXECUTIVE DOSSIER & LIVE PRICE ORACLE CARD
       ══════════════════════════════════════════════════════════════ */
    .drawer-ai-oracle-card {
      background: linear-gradient(135deg, #f8fafc 0%, #f0fdf4 50%, #eff6ff 100%);
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 14px 16px;
      margin: 14px 0 16px;
      box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
      position: relative;
      overflow: hidden;
    }

    .dark-theme .drawer-ai-oracle-card {
      background: linear-gradient(135deg, #1e293b 0%, #064e3b 40%, #1e1b4b 100%);
      border-color: #334155;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    }

    .oracle-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding-bottom: 10px;
      margin-bottom: 12px;
      border-bottom: 1px solid rgba(203, 213, 225, 0.7);
    }

    .dark-theme .oracle-header {
      border-bottom-color: rgba(51, 65, 85, 0.8);
    }

    .oracle-title-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .oracle-robot-icon {
      font-size: 1.4rem;
      background: #ffffff;
      padding: 4px 6px;
      border-radius: 8px;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
    }

    .dark-theme .oracle-robot-icon {
      background: #0f172a;
    }

    .oracle-title {
      font-size: 0.92rem;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.01em;
    }

    .dark-theme .oracle-title {
      color: #f8fafc;
    }

    .oracle-subtitle {
      font-size: 0.72rem;
      color: #64748b;
    }

    .dark-theme .oracle-subtitle {
      color: #94a3b8;
    }

    .oracle-deal-pill {
      font-size: 0.72rem;
      font-weight: 800;
      padding: 4px 10px;
      border-radius: 20px;
      background: #dcfce7;
      color: #166534;
      border: 1px solid #bbf7d0;
      white-space: nowrap;
    }

    .dark-theme .oracle-deal-pill {
      background: #064e3b;
      color: #6ee7b7;
      border-color: #047857;
    }

    .oracle-grid {
      display: grid;
      grid-template-columns: 1.15fr 1fr;
      gap: 14px;
    }

    @media (max-width: 680px) {
      .oracle-grid {
        grid-template-columns: 1fr;
      }
    }

    .oracle-col {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .oracle-col-title {
      font-size: 0.75rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #2563eb;
      display: flex;
      align-items: center;
      gap: 5px;
    }

    .dark-theme .oracle-col-title {
      color: #60a5fa;
    }

    .oracle-body-text {
      margin: 0;
      font-size: 0.81rem;
      line-height: 1.45;
      color: #334155;
    }

    .dark-theme .oracle-body-text {
      color: #cbd5e1;
    }

    .oracle-meta-line {
      margin-top: auto;
      font-size: 0.75rem;
      line-height: 1.35;
      background: rgba(255, 255, 255, 0.75);
      border: 1px solid rgba(226, 232, 240, 0.9);
      border-radius: 6px;
      padding: 6px 8px;
    }

    .dark-theme .oracle-meta-line {
      background: rgba(15, 23, 42, 0.65);
      border-color: rgba(51, 65, 85, 0.85);
    }

    .oracle-meta-lbl {
      font-weight: 700;
      color: #475569;
      margin-right: 4px;
    }

    .dark-theme .oracle-meta-lbl {
      color: #94a3b8;
    }

    .oracle-meta-val {
      font-weight: 600;
      color: #0f172a;
    }

    .dark-theme .oracle-meta-val {
      color: #f1f5f9;
    }

    .oracle-price-row {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin-bottom: 2px;
    }

    .oracle-price-val {
      font-size: 1.28rem;
      font-weight: 900;
      color: #15803d;
      letter-spacing: -0.02em;
    }

    .dark-theme .oracle-price-val {
      color: #4ade80;
    }

    .oracle-diff-pill {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 12px;
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
    }

    .dark-theme .oracle-diff-pill {
      background: #1e3a8a;
      color: #93c5fd;
      border-color: #3b82f6;
    }

    /* ══════════════════════════════════════════════════════════════
       COMPACT YOUTUBE BANNER
       ══════════════════════════════════════════════════════════════ */
    .yt-compact-banner {
      background: linear-gradient(135deg, #fef2f2 0%, #fff1f2 100%);
      border: 1px solid #fecaca;
      border-radius: 12px;
      padding: 12px 16px;
      margin: 16px 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .dark-theme .yt-compact-banner {
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(225, 29, 72, 0.08) 100%);
      border-color: rgba(239, 68, 68, 0.28);
    }

    .yt-banner-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .yt-svg-lg {
      width: 32px;
      height: 32px;
      flex-shrink: 0;
    }

    .yt-banner-left h4 {
      font-size: 0.92rem;
      font-weight: 800;
      color: #991b1b;
      margin: 0;
    }

    .dark-theme .yt-banner-left h4 {
      color: #fca5a5;
    }

    .yt-banner-left p {
      font-size: 0.76rem;
      color: #7f1d1d;
      margin: 2px 0 0;
    }

    .dark-theme .yt-banner-left p {
      color: #f87171;
    }

    .btn-yt-main {
      background: #ef4444;
      color: #ffffff !important;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 700;
      text-decoration: none;
      transition: background 0.15s ease;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .btn-yt-main:hover {
      background: #dc2626;
      box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35);
    }

    /* External Reviews Row */
    .drawer-reviews-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 18px;
    }

    .ext-review-card {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 12px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-decoration: none;
      transition: all 0.16s ease;
    }

    .ext-review-card:hover {
      border-color: #cbd5e1;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
    }

    .dark-theme .ext-review-card {
      background: #1e293b;
      border-color: #334155;
    }

    .dark-theme .ext-review-card:hover {
      border-color: #475569;
    }

    .ext-review-info h5 {
      font-size: 0.82rem;
      font-weight: 800;
      color: #0f172a;
      margin: 0;
    }

    .dark-theme .ext-review-info h5 {
      color: #f8fafc;
    }

    .ext-review-info p {
      font-size: 0.74rem;
      color: #64748b;
      margin: 2px 0 0;
    }

    .dark-theme .ext-review-info p {
      color: #94a3b8;
    }

    .ext-review-score {
      font-size: 1.15rem;
      font-weight: 900;
      color: #059669;
    }

    /* Pros & Cons */
    .pros-cons-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 18px;
    }

    .pros-card, .cons-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 12px 14px;
    }

    .dark-theme .pros-card, .dark-theme .cons-card {
      background: #1e293b;
      border-color: #334155;
    }

    .pros-card h5 {
      color: #059669;
      font-size: 0.84rem;
      font-weight: 800;
      margin: 0 0 8px;
    }

    .cons-card h5 {
      color: #d97706;
      font-size: 0.84rem;
      font-weight: 800;
      margin: 0 0 8px;
    }

    .pros-list, .cons-list {
      margin: 0;
      padding-left: 18px;
      font-size: 0.78rem;
      line-height: 1.4;
      color: #334155;
    }

    .dark-theme .pros-list, .dark-theme .cons-list {
      color: #cbd5e1;
    }

    /* ══════════════════════════════════════════════════════════════
       RICH INFRASTRUCTURE 6-BLOCK GRID
       ══════════════════════════════════════════════════════════════ */
    .infra-rich-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .infra-cat-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 14px;
    }

    .dark-theme .infra-cat-card {
      background: #1e293b;
      border-color: #334155;
    }

    .infra-cat-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid #e2e8f0;
    }

    .dark-theme .infra-cat-header {
      border-bottom-color: #334155;
    }

    .infra-cat-header h4 {
      font-size: 0.88rem;
      font-weight: 800;
      color: #0f172a;
      margin: 0;
    }

    .dark-theme .infra-cat-header h4 {
      color: #f8fafc;
    }

    .infra-item-line {
      display: flex;
      flex-direction: column;
      margin-bottom: 6px;
    }

    .infra-item-lbl {
      font-size: 0.68rem;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .dark-theme .infra-item-lbl {
      color: #94a3b8;
    }

    .infra-item-val {
      font-size: 0.78rem;
      color: #334155;
      line-height: 1.35;
    }

    .dark-theme .infra-item-val {
      color: #cbd5e1;
    }

    /* ══════════════════════════════════════════════════════════════
       CROSS-FILTER SECTION ("Отель в других фильтрах")
       ══════════════════════════════════════════════════════════════ */
    .cross-filter-section {
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      border-radius: 12px;
      padding: 14px 16px;
      margin-top: 18px;
    }

    .dark-theme .cross-filter-section {
      background: rgba(16, 185, 129, 0.08);
      border-color: rgba(16, 185, 129, 0.28);
    }

    .cross-filter-title {
      font-size: 0.88rem;
      font-weight: 800;
      color: #166534;
      margin: 0 0 10px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .dark-theme .cross-filter-title {
      color: #86efac;
    }

    .cross-filters-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .cross-filter-card {
      background: #ffffff;
      border: 1px solid #bbf7d0;
      border-radius: 8px;
      padding: 10px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      text-decoration: none;
      transition: all 0.16s ease;
    }

    .cross-filter-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.15);
      border-color: #86efac;
    }

    .dark-theme .cross-filter-card {
      background: #1e293b;
      border-color: #334155;
    }

    .dark-theme .cross-filter-card:hover {
      border-color: #34d399;
    }

    .cross-filter-name {
      font-size: 0.82rem;
      font-weight: 700;
      color: #0f172a;
    }

    .dark-theme .cross-filter-name {
      color: #f8fafc;
    }

    .cross-filter-meta {
      font-size: 0.72rem;
      color: #64748b;
      margin-top: 2px;
    }

    .dark-theme .cross-filter-meta {
      color: #94a3b8;
    }

    .cross-filter-price {
      font-size: 0.95rem;
      font-weight: 800;
      color: #059669;
      text-align: right;
    }

    /* History & Plotly Chart Tab */
    .chart-controls-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }

    .timeframe-group {
      display: inline-flex;
      background: #f1f5f9;
      border-radius: 8px;
      padding: 2px;
    }

    .dark-theme .timeframe-group {
      background: #1e293b;
    }

    .tf-btn {
      border: none;
      background: transparent;
      padding: 5px 12px;
      font-size: 0.76rem;
      font-weight: 700;
      color: #64748b;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.14s ease;
    }

    .tf-btn.active {
      background: #ffffff;
      color: #0f172a;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }

    .dark-theme .tf-btn.active {
      background: #334155;
      color: #ffffff;
    }

    .chart-container-box {
      min-height: 340px;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 8px;
      margin-bottom: 16px;
    }

    .dark-theme .chart-container-box {
      background: #1e293b;
      border-color: #334155;
    }

    .benchmarks-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }

    .benchmark-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px;
      text-align: center;
    }

    .dark-theme .benchmark-card {
      background: #1e293b;
      border-color: #334155;
    }

    .benchmark-card .lbl {
      font-size: 0.68rem;
      color: #64748b;
      margin-bottom: 2px;
    }

    .dark-theme .benchmark-card .lbl {
      color: #94a3b8;
    }

    .benchmark-card .val {
      font-size: 1.05rem;
      font-weight: 800;
      color: #0f172a;
    }

    .dark-theme .benchmark-card .val {
      color: #f8fafc;
    }

    /* Packages Table */
    .packages-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78rem;
    }

    .packages-table th {
      text-align: left;
      padding: 8px 10px;
      background: #f1f5f9;
      color: #475569;
      font-weight: 700;
      border-bottom: 1px solid #e2e8f0;
    }

    .dark-theme .packages-table th {
      background: #1e293b;
      color: #94a3b8;
      border-bottom-color: #334155;
    }

    .packages-table td {
      padding: 8px 10px;
      border-bottom: 1px solid #f1f5f9;
      color: #334155;
    }

    .dark-theme .packages-table td {
      border-bottom-color: #1e293b;
      color: #cbd5e1;
    }

    /* Responsive */
    @media (max-width: 900px) {
      .hotel-card-horiz {
        grid-template-columns: 1fr;
      }
      .card-media-col {
        min-height: 180px;
      }
      .card-content-col {
        border-right: none;
        border-bottom: 1px solid rgba(226, 232, 240, 0.7);
      }
      .passport-drawer {
        width: 100vw;
      }
      .drawer-reviews-row, .pros-cons-grid, .benchmarks-grid, .infra-rich-grid {
        grid-template-columns: 1fr;
      }
      .yt-compact-banner {
        flex-direction: column;
        align-items: flex-start;
      }
      .btn-yt-main {
        width: 100%;
        justify-content: center;
      }
    }
    """


def render_hotel_card_horiz(c: Dict[str, Any], ai_profile: Dict[str, Any]) -> str:
    """Renders single horizontal OTA card with complete attributes for filtering/sorting."""
    hotel_name = c["hotel_name"]
    hotel_name_html = c["hotel_name_html"]
    price = c["price"]
    image_url = c.get("image_url", "")
    offer_url = c.get("offer_url", "")
    chart_href = c.get("chart_href", "#")
    slug = re.sub(r"[^\w\d]+", "-", hotel_name.lower()).strip("-")

    # Star rating
    stars_count = ai_profile.get("stars", 4)
    stars_html = "★" * stars_count

    # Image block with reliable graceful fallback
    placeholder_text = "★" * stars_count if stars_count else "Отель"
    placeholder_html = (
        f'<div class="card-photo-placeholder" style="{"display:none;" if image_url else ""}">'
        f'<span class="card-photo-placeholder-icon">🏨</span>'
        f'<span class="card-photo-placeholder-text">{html.escape(placeholder_text)}</span>'
        f'</div>'
    )
    if image_url:
        img_html = (
            f'<img class="card-photo" src="{html.escape(image_url, quote=True)}" '
            f'alt="{html.escape(hotel_name, quote=True)}" loading="lazy" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
            f'{placeholder_html}'
        )
    else:
        img_html = placeholder_html

    # Tags
    heated_pill = '<span class="infra-pill warm">♨️ Подогрев зимой</span>' if ai_profile.get("has_heated_pools") else ''
    aqua_pill = '<span class="infra-pill aqua">🎢 Аквапарк</span>' if ai_profile.get("has_aquapark") else ''

    # Drop badge
    drop_pct = 0.0
    delta48_str = str(c.get("delta48", ""))
    if "-" in delta48_str:
        try:
            drop_pct = abs(float(re.sub(r"[^\d.]", "", delta48_str)))
        except (ValueError, TypeError):
            pass
    drop_badge_html = f'<span class="badge-drop">↓ -{drop_pct:.0f}%</span>' if drop_pct >= 5 else ''

    # YouTube snippet button
    yt_url = ai_profile.get("youtube_search_url", "#")
    yt_badge_html = f"""
    <a href="{html.escape(yt_url, quote=True)}" target="_blank" rel="noopener" class="yt-badge-sm" onclick="event.stopPropagation();" title="Смотреть видеообзоры отеля на YouTube">
      <svg class="yt-svg-inline" viewBox="0 0 24 24"><path d="M23.5 6.2c-.3-1-.9-1.8-1.9-2.1C19.9 3.5 12 3.5 12 3.5s-7.9 0-9.6.6c-1 .3-1.6 1.1-1.9 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8c.3 1 .9 1.8 1.9 2.1 1.7.6 9.6.6 9.6.6s7.9 0 9.6-.6c1-.3 1.6-1.1 1.9-2.1.5-1.9.5-5.8.5-5.8s0-3.9-.5-5.8z"/><polygon fill="#FFF" points="9.6,15.6 15.8,12 9.6,8.4"/></svg>
      <span>Видеообзоры YT ↗</span>
    </a>
    """

    # Price section
    deal_class = ai_profile.get("deal_class", "fair")
    deal_badge = ai_profile.get("deal_badge", "🟢 Выгодная цена")
    deal_sub = ai_profile.get("deal_sub", "В пределах нормы")

    dates_label = c.get("dates", "—")
    duration_label = c.get("duration", "—")
    flight_dates = f'<div class="price-flight-dates">✈️ {dates_label} • {duration_label}</div>' if dates_label != "—" else ''

    # Actions
    book_btn = f'<a href="{html.escape(offer_url, quote=True)}" target="_blank" rel="noopener" class="btn-book-main" onclick="event.stopPropagation()">Забронировать тур ↗</a>' if offer_url else ''

    return f"""
    <article class="hotel-card hotel-card-horiz"
      data-hotel-name="{html.escape(hotel_name, quote=True)}"
      data-hotel-slug="{slug}"
      data-delta48="{html.escape(str(c.get('delta48', '—')), quote=True)}"
      data-duration-bucket="{html.escape(c.get('duration_bucket', ''), quote=True)}"
      data-departure-date="{html.escape(c.get('departure_date', ''), quote=True)}"
      data-departure-key="{html.escape(c.get('departure_key', ''), quote=True)}"
      data-ta-rating="{c.get('ta_data_attr', '-1')}"
      data-region="{c.get('region', '')}"
      onclick="openHotelPassport('{slug}')">

      <!-- Col 1: Media -->
      <div class="card-media-col">
        {img_html}
        <div class="card-media-badges">
          <span class="badge-country">{html.escape(c.get('region', 'Курорт'))}</span>
          {drop_badge_html}
        </div>
        <div class="card-media-footer">
          <div class="media-footer-row">
            <div class="ta-score-pill">
              <span>🦉</span>
              <strong>★ {ai_profile.get('ta_rating', 4.3):.1f}</strong>
              <span style="opacity:0.75;">({ai_profile.get('ta_reviews', 1200):,})</span>
            </div>
            <a href="{html.escape(ai_profile.get('tripadvisor_url', '#'), quote=True)}" target="_blank" rel="noopener" class="ta-link-sm" onclick="event.stopPropagation()">TripAdvisor ↗</a>
          </div>
          <div class="media-footer-row">
            {yt_badge_html}
          </div>
        </div>
      </div>

      <!-- Col 2: Content & AI Overview -->
      <div class="card-content-col">
        <div>
          <div class="card-title-row">
            <h4 class="hotel-card-title card-hotel-title">{hotel_name_html}</h4>
            <span class="hotel-stars">{stars_html}</span>
          </div>
          <div class="card-geo-line">
            📍 <strong>{html.escape(c.get('region', 'Курорт'))}</strong> • 🏖️ {ai_profile.get('beach_line', 1)}-я линия ({html.escape(ai_profile.get('beach_type', 'Песчаный'))})
          </div>

          <div class="card-infra-tags">
            <span class="infra-pill">🏖️ {html.escape(ai_profile.get('sea_entry', 'Пологий вход'))}</span>
            <span class="infra-pill">🍽️ {html.escape(ai_profile.get('food_concept', 'All Inclusive'))}</span>
            {heated_pill}
            {aqua_pill}
            {c.get('flash_drop_badge_html', '')}
            {c.get('booking_window_badge_html', '')}
            {c.get('arbitrage_badge_html', '')}
          </div>

          <div class="card-ai-box">
            <div class="ai-box-header">
              <span class="ai-badge-lbl">🤖 AI-Вердикт</span>
              <span class="ai-suitable">{html.escape(ai_profile.get('suitable_for', 'Семьи и пары'))}</span>
            </div>
            <p class="ai-verdict-text">{html.escape(ai_profile.get('verdict', ''))}</p>
          </div>
        </div>

        <div class="card-review-snippet">
          {html.escape(ai_profile.get('review_snippet', ''))}
        </div>
      </div>

      <!-- Col 3: Price Intelligence & Action -->
      <div class="card-price-col">
        <div>
          <div class="deal-status-box {deal_class}">
            <div class="deal-badge-title">{html.escape(deal_badge)}</div>
            <div class="deal-badge-sub">{html.escape(deal_sub)}</div>
          </div>

          <div class="price-box-main">
            <div class="hotel-card-price price-val">{price:.0f} zł</div>
            <div class="price-pkg-desc">Deal Score {c.get('deal_score', 50)} • {c.get('deal_label', 'Normal')}</div>
            {flight_dates}
          </div>

          <div class="price-spread-box">
            <div class="spread-lbl">Динамика цен за 48ч:</div>
            <div class="spread-vals">
              <span>Δ48ч: <strong>{c.get('delta48', '—')}</strong></span> • 
              <span>Δср: <strong>{c.get('delta_avg', '—')}</strong></span>
            </div>
          </div>
        </div>

        <div class="card-action-btns">
          {book_btn}
          <button type="button" class="btn-inspect-passport" onclick="event.stopPropagation(); openHotelPassport('{slug}');">Паспорт и график цен 📈</button>
        </div>
      </div>
    </article>
    """


def render_hotel_passport_drawer_html() -> str:
    """Renders 780px slide-over drawer modal markup with 4 tabs, gallery carousel, compact YouTube banner, and rich infra."""
    return """
    <!-- Deep Hotel Passport Drawer (780px Wide Slide-Over Modal) -->
    <div class="drawer-overlay" id="passportDrawerOverlay" onclick="closeHotelPassport()"></div>
    <aside class="passport-drawer" id="passportDrawer" aria-hidden="true" role="dialog" aria-labelledby="drawerHotelTitle">
      <!-- Header -->
      <div class="drawer-header">
        <div class="drawer-title-box">
          <div class="drawer-title-row">
            <h2 id="drawerHotelTitle">Название отеля</h2>
            <span id="drawerStarsRow" class="hotel-stars">★★★★★</span>
          </div>
          <p id="drawerHotelSubtitle">Страна • Курорт</p>
        </div>
        <div class="drawer-header-actions">
          <a id="drawerHeaderTaLink" href="#" target="_blank" rel="noopener" class="btn-drawer-header-ta" title="Открыть отзывы на TripAdvisor">🦉 TripAdvisor ↗</a>
          <a id="drawerHeaderYtLink" href="#" target="_blank" rel="noopener" class="btn-drawer-header-yt" title="Смотреть обзоры на YouTube">▶ YouTube ↗</a>
          <button type="button" class="drawer-close-btn" id="drawerCloseBtn" onclick="closeHotelPassport()" title="Закрыть">✕</button>
        </div>
      </div>

      <!-- Sticky Tabs Bar -->
      <nav class="drawer-tabs-bar" id="drawerTabsBar">
        <button type="button" class="drawer-tab-btn active" data-tab="ai" onclick="switchDrawerTab('ai')">🤖 AI-Обзор и Отзывы</button>
        <button type="button" class="drawer-tab-btn" data-tab="history" onclick="switchDrawerTab('history')">📈 Анализ и график цен</button>
        <button type="button" class="drawer-tab-btn" data-tab="infra" onclick="switchDrawerTab('infra')">🏖 Инфраструктура</button>
        <button type="button" class="drawer-tab-btn" data-tab="packages" onclick="switchDrawerTab('packages')">📦 Все вылеты и фильтры</button>
      </nav>

      <!-- Scrollable Content -->
      <div class="drawer-content" id="drawerScrollContent">
        <!-- Tab 1: AI-Обзор & Отзывы & YouTube -->
        <div class="drawer-tab-panel active" id="tabPanel-ai">
          <!-- Interactive Photo Gallery Carousel -->
          <div class="drawer-gallery-box" id="drawerGalleryBox">
            <div class="gallery-stage">
              <img id="galleryMainImg" class="gallery-main-img" src="" alt="Фото отеля" onerror="this.style.display='none';">
              <button type="button" class="gallery-nav-btn prev" onclick="prevGalleryPhoto()" aria-label="Предыдущее фото">‹</button>
              <button type="button" class="gallery-nav-btn next" onclick="nextGalleryPhoto()" aria-label="Следующее фото">›</button>
              <div class="gallery-counter-pill" id="galleryCounterPill" style="display:none;"></div>
            </div>
            <div class="gallery-thumbs-row" id="galleryThumbsRow"></div>
          </div>

          <!-- Badges -->
          <div class="drawer-hero-badges" id="drawerHeroBadges" style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px;"></div>

          <!-- AI Executive Dossier & Live Price Oracle Card -->
          <div class="drawer-ai-oracle-card">
            <div class="oracle-header">
              <div class="oracle-title-wrap">
                <span class="oracle-robot-icon">🤖</span>
                <div>
                  <div class="oracle-title">AI-Саммари и Ценовой Анализ</div>
                  <div class="oracle-subtitle">Анализ отеля, инфраструктуры и текущей точки входа</div>
                </div>
              </div>
              <div id="drawerOraclePriceBadge" class="oracle-deal-pill">🟢 Выгодно брать</div>
            </div>

            <div class="oracle-grid">
              <!-- Left: Hotel Dossier -->
              <div class="oracle-col hotel-col">
                <div class="oracle-col-title">🏨 Об отеле и отдыхе</div>
                <p id="drawerAiHotelSummaryText" class="oracle-body-text"></p>
                <div class="oracle-meta-line">
                  <span class="oracle-meta-lbl">🎯 Для кого:</span>
                  <span id="drawerAiAudienceText" class="oracle-meta-val"></span>
                </div>
              </div>

              <!-- Right: Price Intelligence & Live Action Signal -->
              <div class="oracle-col price-col">
                <div class="oracle-col-title">💰 Текущая цена и выгода</div>
                <div class="oracle-price-row">
                  <span id="drawerOracleCurPrice" class="oracle-price-val">—</span>
                  <span id="drawerOraclePriceDiff" class="oracle-diff-pill">—</span>
                </div>
                <p id="drawerAiPriceVerdictText" class="oracle-body-text"></p>
                <div class="oracle-meta-line">
                  <span class="oracle-meta-lbl">🔮 Сигнал Hopper:</span>
                  <span id="drawerAiActionSignal" class="oracle-meta-val"></span>
                </div>
              </div>
            </div>
          </div>

          <!-- Compact YouTube Video Review Banner -->
          <div class="yt-compact-banner">
            <div class="yt-banner-left">
              <svg class="yt-svg-lg" viewBox="0 0 24 24"><path fill="#FF0000" d="M23.5 6.2c-.3-1-.9-1.8-1.9-2.1C19.9 3.5 12 3.5 12 3.5s-7.9 0-9.6.6c-1 .3-1.6 1.1-1.9 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8c.3 1 .9 1.8 1.9 2.1 1.7.6 9.6.6 9.6.6s7.9 0 9.6-.6c1-.3 1.6-1.1 1.9-2.1.5-1.9.5-5.8.5-5.8s0-3.9-.5-5.8z"/><polygon fill="#FFFFFF" points="9.6,15.6 15.8,12 9.6,8.4"/></svg>
              <div>
                <h4>Видеообзоры туристов на YouTube</h4>
                <p>Смотрите живые рум-туры, обзоры территории и пляжа перед покупкой</p>
              </div>
            </div>
            <a id="drawerYtAllBtn" href="#" target="_blank" rel="noopener" class="btn-yt-main">▶ Все видео на YouTube ↗</a>
          </div>

          <!-- External Ratings -->
          <div class="drawer-reviews-row">
            <a id="drawerTripadvisorLink" href="#" target="_blank" rel="noopener" class="ext-review-card">
              <div class="ext-review-info">
                <h5>🦉 TripAdvisor Рейтинг</h5>
                <p id="drawerTaReviewsCount">на основе отзывов</p>
              </div>
              <div class="ext-review-score" id="drawerTaScore">★ 4.5</div>
            </a>
            <a id="drawerGoogleLink" href="#" target="_blank" rel="noopener" class="ext-review-card">
              <div class="ext-review-info">
                <h5>🔍 Отзывы в Google</h5>
                <p>Поиск свежих впечатлений</p>
              </div>
              <div class="ext-review-score">↗</div>
            </a>
          </div>

          <!-- Pros & Cons -->
          <div class="pros-cons-grid">
            <div class="pros-card">
              <h5>✅ Ключевые преимущества</h5>
              <ul class="pros-list" id="drawerProsList"></ul>
            </div>
            <div class="cons-card">
              <h5>⚠️ На что обратить внимание</h5>
              <ul class="cons-list" id="drawerConsList"></ul>
            </div>
          </div>

          <!-- Real Quotes / Reviews Summary (hidden when no real quote) -->
          <div id="drawerQuoteBox" style="background:#fffbeb; border:1px solid #fef3c7; border-radius:10px; padding:12px 14px; display:none;" class="drawer-quote-box">
            <h5 style="margin:0 0 4px; font-size:0.82rem; font-weight:800; color:#92400e;">💬 Резюме отзывов туристов</h5>
            <p id="drawerQuoteDetail" style="margin:0; font-size:0.78rem; font-style:italic; line-height:1.35; color:#78350f;"></p>
          </div>
        </div>

        <!-- Tab 2: График Plotly и Аналитика -->
        <div class="drawer-tab-panel" id="tabPanel-history">
          <div class="chart-controls-bar">
            <div class="timeframe-group">
              <button type="button" class="tf-btn" data-days="7" onclick="setPlotlyTimeframe(7)">7 дней</button>
              <button type="button" class="tf-btn active" data-days="30" onclick="setPlotlyTimeframe(30)">30 дней</button>
              <button type="button" class="tf-btn" data-days="90" onclick="setPlotlyTimeframe(90)">Все время</button>
            </div>
            <div id="drawerPriceStatusBadge" class="stat-pill">🟢 Выгодная цена</div>
          </div>

          <div class="chart-container-box">
            <div id="drawerPlotlyChart" style="width:100%; height:320px;"></div>
          </div>

          <div class="benchmarks-grid">
            <div class="benchmark-card">
              <div class="lbl">Текущая цена</div>
              <div class="val" id="bmCurrentPrice">—</div>
            </div>
            <div class="benchmark-card">
              <div class="lbl">Минимум истории</div>
              <div class="val" id="bmMinPrice">—</div>
            </div>
            <div class="benchmark-card">
              <div class="lbl">Максимум цен</div>
              <div class="val" id="bmMaxPrice">—</div>
            </div>
            <div class="benchmark-card">
              <div class="lbl">Экономия от пика</div>
              <div class="val" id="bmSavingsVal">—</div>
            </div>
          </div>

          <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; padding:12px 14px;" class="drawer-ai-advice-box">
            <h5 style="margin:0 0 4px; font-size:0.82rem; font-weight:800; color:#166534;">💡 Рекомендация монитора</h5>
            <p id="drawerAiAdvice" style="margin:0; font-size:0.78rem; line-height:1.35; color:#14532d;"></p>
          </div>
        </div>

        <!-- Tab 3: Расширенная Инфраструктура -->
        <div class="drawer-tab-panel" id="tabPanel-infra">
          <div class="infra-rich-grid" id="drawerInfraGrid">
            <!-- 6 structured categories populated dynamically -->
          </div>
        </div>

        <!-- Tab 4: Все пакеты и Отель в других фильтрах -->
        <div class="drawer-tab-panel" id="tabPanel-packages">
          <!-- Current Filter Packages -->
          <div style="margin-bottom:10px; font-size:0.84rem; font-weight:700; color:#0f172a;" id="drawerPackagesCount">Вылеты в текущем фильтре:</div>
          <div style="overflow-x:auto; margin-bottom:20px;">
            <table class="packages-table">
              <thead>
                <tr>
                  <th>Даты поездки</th>
                  <th>Длит.</th>
                  <th>Состав</th>
                  <th>Цена</th>
                  <th>Бронь</th>
                </tr>
              </thead>
              <tbody id="drawerPackagesTbody"></tbody>
            </table>
          </div>

          <!-- Cross-Filter Tracking Block -->
          <div class="cross-filter-section" id="drawerCrossFilterSection">
            <div class="cross-filter-title">🌐 Отель в других фильтрах мониторинга</div>
            <div class="cross-filters-list" id="drawerCrossFiltersList"></div>
          </div>
        </div>
      </div>
    </aside>
    """


def get_hotel_passport_js() -> str:
    """Returns client-side JavaScript for handling the slide-over drawer, gallery carousel, tabs, Plotly charts, and cross-filters."""
    return """
    // ══════════════════════════════════════════════════════════════
    // HOTEL PASSPORT DRAWER & GALLERY CONTROLLER
    // ══════════════════════════════════════════════════════════════
    let activePassportHotel = null;
    let activeTimeframeDays = 30;
    let currentGalleryIdx = 0;
    let currentGalleryPhotos = [];

    window.openHotelPassport = function(slug) {
      if (!window.HOTEL_PASSPORT_DATA) return;
      const h = window.HOTEL_PASSPORT_DATA[slug];
      if (!h) {
        console.warn('Hotel passport data not found for slug:', slug);
        return;
      }
      activePassportHotel = h;

      // 1. Populate Header
      document.getElementById('drawerHotelTitle').textContent = h.hotel_name;
      document.getElementById('drawerHotelSubtitle').textContent = `${h.region || 'Курорт'} • ${h.country || ''}`;
      document.getElementById('drawerStarsRow').textContent = '★'.repeat(h.stars || 4);

      const taHeaderBtn = document.getElementById('drawerHeaderTaLink');
      if (taHeaderBtn) taHeaderBtn.href = h.tripadvisor_url || '#';

      const ytHeaderBtn = document.getElementById('drawerHeaderYtLink');
      if (ytHeaderBtn) ytHeaderBtn.href = h.youtube_search_url || '#';

      // 2. Photo Gallery Setup
      currentGalleryPhotos = (h.gallery_photos && h.gallery_photos.length) ? h.gallery_photos : [
        { label: 'Территория отеля', url: h.image_url }
      ];
      currentGalleryIdx = 0;
      updateGalleryView();

      // 3. Badges & AI Short Verdict
      const badgesRow = document.getElementById('drawerHeroBadges');
      if (badgesRow) {
        let bHtml = '';
        if (h.ta_reviews && h.ta_reviews > 0) {
          bHtml += `<span class="stat-pill" style="color:#059669; font-weight:700;">★ ${h.ta_rating ? h.ta_rating.toFixed(1) : '4.3'} (${h.ta_reviews.toLocaleString('ru-RU')} отзывов)</span>`;
        } else if (h.ta_rating) {
          bHtml += `<span class="stat-pill" style="color:#059669; font-weight:700;">★ ${h.ta_rating.toFixed(1)} на TripAdvisor</span>`;
        }
        bHtml += `<span class="stat-pill" style="color:#0284c7; font-weight:700;">🏖️ ${h.beach_line || 2}-я линия</span>`;
        if (h.has_aquapark) bHtml += `<span class="stat-pill" style="color:#16a34a; font-weight:700;">🎢 Аквапарк</span>`;
        if (h.has_heated_pools) bHtml += `<span class="stat-pill" style="color:#ea580c; font-weight:700;">♨️ Подогрев зимой</span>`;
        bHtml += `<span class="stat-pill" style="color:#4f46e5; font-weight:700;">🍽️ ${h.food_concept || 'All Inclusive'}</span>`;
        badgesRow.innerHTML = bHtml;
      }

      // 3. AI Executive Dossier & Live Price Oracle Card
      const oracleBadge = document.getElementById('drawerOraclePriceBadge');
      if (oracleBadge) {
        oracleBadge.textContent = h.deal_badge || '🟢 Выгодная цена';
        if (h.deal_class === 'drop') {
          oracleBadge.style.background = '#dcfce7';
          oracleBadge.style.color = '#15803d';
        } else if (h.deal_class === 'good') {
          oracleBadge.style.background = '#e0f2fe';
          oracleBadge.style.color = '#0369a1';
        } else {
          oracleBadge.style.background = '#fef3c7';
          oracleBadge.style.color = '#92400e';
        }
      }

      const hotelSummaryEl = document.getElementById('drawerAiHotelSummaryText');
      if (hotelSummaryEl) {
        hotelSummaryEl.textContent = h.ai_hotel_summary || h.verdict || '';
      }

      const audEl = document.getElementById('drawerAiAudienceText');
      if (audEl) {
        audEl.textContent = h.ai_audience || h.suitable_for || 'Семьи и пары';
      }

      const curPriceEl = document.getElementById('drawerOracleCurPrice');
      if (curPriceEl) {
        curPriceEl.textContent = `${Math.round(h.price || 0).toLocaleString('ru-RU')} zł`;
      }

      const diffEl = document.getElementById('drawerOraclePriceDiff');
      if (diffEl) {
        diffEl.textContent = h.price_diff_text || 'Норма сезона';
      }

      const priceVerdictEl = document.getElementById('drawerAiPriceVerdictText');
      if (priceVerdictEl) {
        priceVerdictEl.textContent = h.ai_price_summary || h.recommendation || '';
      }

      const signalEl = document.getElementById('drawerAiActionSignal');
      if (signalEl) {
        signalEl.textContent = h.ai_action_signal || '🟢 ПОКУПАТЬ СЕЙЧАС';
      }

      // 4. Compact YouTube Banner Button
      const ytAllBtn = document.getElementById('drawerYtAllBtn');
      if (ytAllBtn) ytAllBtn.href = h.youtube_search_url || '#';

      // 5. External Ratings
      const taLink = document.getElementById('drawerTripadvisorLink');
      if (taLink) taLink.href = h.tripadvisor_url || '#';
      const taScore = document.getElementById('drawerTaScore');
      if (taScore) taScore.textContent = `★ ${h.ta_rating ? h.ta_rating.toFixed(1) : '4.3'}`;
      const taRev = document.getElementById('drawerTaReviewsCount');
      if (taRev) {
        taRev.textContent = (h.ta_reviews && h.ta_reviews > 0)
          ? `на основе ${h.ta_reviews.toLocaleString('ru-RU')} отзывов`
          : 'Смотреть отзывы на TripAdvisor';
      }

      const gglLink = document.getElementById('drawerGoogleLink');
      if (gglLink) gglLink.href = h.google_reviews_url || '#';

      // 6. Pros & Cons
      const prosList = document.getElementById('drawerProsList');
      if (prosList) {
        prosList.innerHTML = (h.pros || []).map(p => `<li>${p}</li>`).join('');
      }
      const consList = document.getElementById('drawerConsList');
      if (consList) {
        consList.innerHTML = (h.cons || []).map(c => `<li>${c}</li>`).join('');
      }

      // 7. Quote / Reviews Summary
      const quoteBox = document.getElementById('drawerQuoteBox');
      const quoteDet = document.getElementById('drawerQuoteDetail');
      if (quoteBox && quoteDet) {
        if (h.review_snippet && h.review_snippet.trim()) {
          quoteBox.style.display = 'block';
          quoteDet.textContent = h.review_snippet;
        } else {
          quoteBox.style.display = 'none';
        }
      }

      // 8. Benchmarks & Price Tab
      const bmCurr = document.getElementById('bmCurrentPrice');
      if (bmCurr) bmCurr.textContent = `${Math.round(h.price || 0).toLocaleString('ru-RU')} zł`;
      const bmMin = document.getElementById('bmMinPrice');
      if (bmMin) bmMin.textContent = `${Math.round(h.min_price || h.price || 0).toLocaleString('ru-RU')} zł`;
      const bmMax = document.getElementById('bmMaxPrice');
      if (bmMax) bmMax.textContent = `${Math.round(h.max_price || h.price || 0).toLocaleString('ru-RU')} zł`;
      const bmSav = document.getElementById('bmSavingsVal');
      if (bmSav) {
        const diff = (h.max_price || h.price) - (h.price || 0);
        bmSav.textContent = diff > 0 ? `-${Math.round(diff).toLocaleString('ru-RU')} zł` : 'Лучшая цена';
      }
      const adviceEl = document.getElementById('drawerAiAdvice');
      if (adviceEl) adviceEl.textContent = h.recommendation || '';

      // 9. Rich 6-block Infrastructure
      const infraGrid = document.getElementById('drawerInfraGrid');
      if (infraGrid) {
        const ir = h.infra_rich || {};
        const b = ir.beach || {};
        const p = ir.pools || {};
        const f = ir.food || {};
        const k = ir.kids || {};
        const s = ir.sport_spa || {};
        const c = ir.comfort || {};

        infraGrid.innerHTML = `
          <!-- 1. Beach -->
          <div class="infra-cat-card">
            <div class="infra-cat-header">
              <span>🏖️</span>
              <h4>Пляж и море</h4>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Линия и берег</span>
              <span class="infra-item-val">${b.line || '1-я линия'}, ${b.type || 'Собственный песчаный'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Заход в море</span>
              <span class="infra-item-val">${b.entry || 'Пологий песчаный вход'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Оснащение пляжа</span>
              <span class="infra-item-val">${b.equipment || 'Шезлонги, зонтики и бар на пляже'}</span>
            </div>
          </div>

          <!-- 2. Pools -->
          <div class="infra-cat-card">
            <div class="infra-cat-header">
              <span>🏊</span>
              <h4>Бассейны и водные горки</h4>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Открытые бассейны</span>
              <span class="infra-item-val">${p.pools_count || 'Несколько открытых бассейнов с пресной водой'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Подогрев зимой</span>
              <span class="infra-item-val">${p.heated || 'Подогреваемый бассейн'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Аквапарк</span>
              <span class="infra-item-val">${p.aquapark || 'Водные горки для всей семьи'}</span>
            </div>
          </div>

          <!-- 3. Food -->
          <div class="infra-cat-card">
            <div class="infra-cat-header">
              <span>🍽️</span>
              <h4>Питание и рестораны</h4>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Концепция</span>
              <span class="infra-item-val"><strong>${f.concept || 'All Inclusive'}</strong></span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Главный ресторан</span>
              <span class="infra-item-val">${f.main_buffet || 'Шведский стол, гриль, свежая выпечка'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">A la Carte и бары</span>
              <span class="infra-item-val">${f.alacarte || 'Рестораны a la carte, лобби-бар и бар у бассейна'}</span>
            </div>
          </div>

          <!-- 4. Kids -->
          <div class="infra-cat-card">
            <div class="infra-cat-header">
              <span>👶</span>
              <h4>Для детей и семей</h4>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Мини-клуб</span>
              <span class="infra-item-val">${k.club || 'Детский клуб от 4 до 12 лет с аниматорами'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Детский бассейн</span>
              <span class="infra-item-val">${k.pool || 'Мелкий детский бассейн с навесом от солнца'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Площадка и меню</span>
              <span class="infra-item-val">${k.playground || 'Игровая площадка, стульчики и детское меню'}</span>
            </div>
          </div>

          <!-- 5. Sport & Spa -->
          <div class="infra-cat-card">
            <div class="infra-cat-header">
              <span>💆</span>
              <h4>Спа, спорт и активности</h4>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Спа-центр</span>
              <span class="infra-item-val">${s.spa || 'Сауна, хаммам, джакузи и массаж'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Фитнес и спорт</span>
              <span class="infra-item-val">${s.fitness || 'Тренажерный зал, пляжный волейбол, аэробика'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Дайвинг и риф</span>
              <span class="infra-item-val">${s.watersports || 'Снорклинг, прокат масок, водные виды спорта'}</span>
            </div>
          </div>

          <!-- 6. Comfort & Service -->
          <div class="infra-cat-card">
            <div class="infra-cat-header">
              <span>🌐</span>
              <h4>Удобства и сервис</h4>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Интернет Wi-Fi</span>
              <span class="infra-item-val">${c.wifi || 'Бесплатный Wi-Fi на территории и в лобби'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Номера</span>
              <span class="infra-item-val">${c.room_amenities || 'Кондиционер, сейф, балкон/терраса, мини-бар'}</span>
            </div>
            <div class="infra-item-line">
              <span class="infra-item-lbl">Трансфер</span>
              <span class="infra-item-val">${c.distance || 'Быстрый трансфер из аэропорта'}</span>
            </div>
          </div>
        `;
      }

      // 10. Packages in Current Filter
      const pkgCount = document.getElementById('drawerPackagesCount');
      const pkgTbody = document.getElementById('drawerPackagesTbody');
      if (pkgTbody) {
        const pkgs = (h.packages || []).filter(p => p && p.price > 0);
        if (pkgCount) {
          pkgCount.textContent = pkgs.length > 0
            ? `Доступно предложений в текущем фильтре: ${pkgs.length}`
            : `В текущем фильтре нет активных вылетов`;
        }
        if (pkgs.length === 0) {
          pkgTbody.innerHTML = `
            <tr>
              <td colspan="5" style="text-align:center; padding:18px; color:#64748b; font-size:0.82rem;">
                Нет активных туров на будущие даты в этом фильтре. Проверьте отель в других фильтрах ниже.
              </td>
            </tr>
          `;
        } else {
          pkgTbody.innerHTML = pkgs.map(p => `
            <tr>
              <td><strong>${p.dates || '—'}</strong></td>
              <td>${p.duration || '—'}</td>
              <td>${p.composition || '2 взр.'}</td>
              <td><strong style="color:#059669;">${Math.round(p.price).toLocaleString('ru-RU')} zł</strong></td>
              <td>
                ${p.url ? `<a href="${p.url}" target="_blank" rel="noopener" class="btn-book-main" style="padding:4px 8px; font-size:0.72rem; display:inline-block;">Купить ↗</a>` : '—'}
              </td>
            </tr>
          `).join('');
        }
      }

      // 11. Cross-Filter Presence Block
      const crossList = document.getElementById('drawerCrossFiltersList');
      const crossSection = document.getElementById('drawerCrossFilterSection');
      if (crossList && crossSection) {
        const ofs = h.other_filters || [];
        if (ofs.length > 0) {
          crossSection.style.display = 'block';
          crossList.innerHTML = ofs.map(of => `
            <a href="${of.dashboard_url}" class="cross-filter-card" title="Открыть этот отель в фильтре ${of.label}">
              <div>
                <div class="cross-filter-name">${of.label}</div>
                <div class="cross-filter-meta">📅 ${of.dates || 'Доступные даты'} • ⏱️ ${of.duration || 'Длительность'}</div>
              </div>
              <div>
                <div class="cross-filter-price">от ${Math.round(of.price || 0).toLocaleString('ru-RU')} zł</div>
                <span style="font-size:0.72rem; color:#4f46e5; font-weight:600;">Перейти ↗</span>
              </div>
            </a>
          `).join('');
        } else {
          crossSection.style.display = 'block';
          crossList.innerHTML = '<div style="font-size:0.78rem; color:#64748b; font-style:italic;">Отель отслеживается только в текущем фильтре.</div>';
        }
      }

      // Open drawer modal
      const overlay = document.getElementById('passportDrawerOverlay');
      const drawer = document.getElementById('passportDrawer');
      if (overlay) overlay.classList.add('open');
      if (drawer) {
        drawer.classList.add('open');
        drawer.setAttribute('aria-hidden', 'false');
      }

      // Trigger Plotly chart rendering
      renderPassportPlotlyChart(h, activeTimeframeDays);
    };

    function updateGalleryView() {
      const mainImg = document.getElementById('galleryMainImg');
      const counter = document.getElementById('galleryCounterPill');
      const thumbsRow = document.getElementById('galleryThumbsRow');
      const prevBtn = document.querySelector('.gallery-nav-btn.prev');
      const nextBtn = document.querySelector('.gallery-nav-btn.next');

      if (!currentGalleryPhotos || currentGalleryPhotos.length === 0) return;
      const cur = currentGalleryPhotos[currentGalleryIdx] || currentGalleryPhotos[0];

      if (mainImg) {
        if (cur.url) {
          mainImg.src = cur.url;
          mainImg.style.display = 'block';
        } else {
          mainImg.style.display = 'none';
        }
      }

      const totalPhotos = currentGalleryPhotos.length;
      if (counter) {
        if (totalPhotos <= 1) {
          counter.style.display = cur.url ? 'block' : 'none';
          counter.textContent = `📷 ${cur.label || 'Фото отеля'}`;
        } else {
          counter.style.display = 'block';
          counter.textContent = `📷 ${currentGalleryIdx + 1} / ${totalPhotos} • ${cur.label || 'Фото'}`;
        }
      }

      // Hide navigation arrows and thumbnails row if only 1 photo exists
      if (prevBtn) prevBtn.style.display = totalPhotos > 1 ? 'flex' : 'none';
      if (nextBtn) nextBtn.style.display = totalPhotos > 1 ? 'flex' : 'none';

      if (thumbsRow) {
        if (totalPhotos <= 1) {
          thumbsRow.style.display = 'none';
        } else {
          thumbsRow.style.display = 'flex';
          thumbsRow.innerHTML = currentGalleryPhotos.map((p, idx) => `
            <div class="gallery-thumb-item ${idx === currentGalleryIdx ? 'active' : ''}" onclick="selectGalleryPhoto(${idx})">
              ${p.url ? `<img src="${p.url}" alt="${p.label}">` : '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:0.7rem;color:#94a3b8;">🏨</div>'}
            </div>
          `).join('');
        }
      }
    }

    window.selectGalleryPhoto = function(idx) {
      if (!currentGalleryPhotos || idx < 0 || idx >= currentGalleryPhotos.length) return;
      currentGalleryIdx = idx;
      updateGalleryView();
    };

    window.nextGalleryPhoto = function() {
      if (!currentGalleryPhotos || currentGalleryPhotos.length <= 1) return;
      currentGalleryIdx = (currentGalleryIdx + 1) % currentGalleryPhotos.length;
      updateGalleryView();
    };

    window.prevGalleryPhoto = function() {
      if (!currentGalleryPhotos || currentGalleryPhotos.length <= 1) return;
      currentGalleryIdx = (currentGalleryIdx - 1 + currentGalleryPhotos.length) % currentGalleryPhotos.length;
      updateGalleryView();
    };

    window.closeHotelPassport = function() {
      const overlay = document.getElementById('passportDrawerOverlay');
      const drawer = document.getElementById('passportDrawer');
      if (overlay) overlay.classList.remove('open');
      if (drawer) {
        drawer.classList.remove('open');
        drawer.setAttribute('aria-hidden', 'true');
      }
    };

    window.switchDrawerTab = function(tabId) {
      document.querySelectorAll('.drawer-tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === tabId);
      });
      document.querySelectorAll('.drawer-tab-panel').forEach(p => {
        p.classList.toggle('active', p.id === `tabPanel-${tabId}`);
      });

      if (tabId === 'history' && activePassportHotel) {
        // Multi-phase resize to satisfy AGENTS.md rules
        [40, 150, 350].forEach(delay => {
          setTimeout(() => {
            renderPassportPlotlyChart(activePassportHotel, activeTimeframeDays);
          }, delay);
        });
      }
    };

    window.setPlotlyTimeframe = function(days) {
      activeTimeframeDays = days;
      document.querySelectorAll('.tf-btn').forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.days, 10) === days);
      });
      if (activePassportHotel) {
        renderPassportPlotlyChart(activePassportHotel, days);
      }
    };

    function renderPassportPlotlyChart(hotel, days) {
      const chartEl = document.getElementById('drawerPlotlyChart');
      if (!chartEl || !window.Plotly) return;

      let pts = (hotel.history_points || []).filter(p => p && p.price > 0);
      if (pts.length === 0) {
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-size:0.85rem;">Недостаточно исторических точек для отображения</div>';
        return;
      }

      // Filter by timeframe: 7 days, 30 days, or 90+ (all time)
      if (days && days < 90 && pts.length > 0) {
        const lastPt = pts[pts.length - 1];
        const lastTs = lastPt.ts || (lastPt.iso ? new Date(lastPt.iso).getTime() : Date.now());
        const cutoffTs = lastTs - (days * 24 * 3600 * 1000);
        const filtered = pts.filter(p => {
          const ptTs = p.ts || (p.iso ? new Date(p.iso).getTime() : 0);
          return ptTs >= cutoffTs;
        });
        if (filtered.length >= 2) {
          pts = filtered;
        }
      }

      const isDark = document.body.classList.contains('dark-theme') || document.documentElement.getAttribute('data-theme') === 'dark';
      const bgColor = isDark ? '#1e293b' : '#ffffff';
      const fontColor = isDark ? '#cbd5e1' : '#334155';
      const gridColor = isDark ? 'rgba(51, 65, 85, 0.5)' : '#f1f5f9';

      const xVals = pts.map(p => p.ts ? new Date(p.ts).toISOString() : (p.iso ? p.iso.replace(' ', 'T') : p.date));
      const yVals = pts.map(p => p.price);
      const hoverTexts = pts.map(p => `${p.date || p.iso}<br><b>${Math.round(p.price).toLocaleString('ru-RU')} zł</b>`);

      const trace = {
        x: xVals,
        y: yVals,
        text: hoverTexts,
        hoverinfo: 'text',
        mode: 'lines+markers',
        type: 'scatter',
        line: { color: '#6366f1', width: 3, shape: pts.length > 2 ? 'spline' : 'linear' },
        marker: { color: '#4f46e5', size: 6 },
        fill: 'tozeroy',
        fillcolor: isDark ? 'rgba(99, 102, 241, 0.12)' : 'rgba(99, 102, 241, 0.08)',
      };

      const layout = {
        autosize: true,
        height: 320,
        margin: { l: 55, r: 25, t: 15, b: 40 },
        paper_bgcolor: bgColor,
        plot_bgcolor: bgColor,
        font: { family: 'inherit', color: fontColor, size: 11 },
        xaxis: {
          gridcolor: gridColor,
          linecolor: gridColor,
          tickfont: { color: fontColor },
          type: 'date',
          tickformat: '%d.%m',
        },
        yaxis: {
          gridcolor: gridColor,
          linecolor: gridColor,
          tickfont: { color: fontColor },
          tickformat: ',.0f',
          ticksuffix: ' zł',
        },
      };

      const config = { responsive: true, displayModeBar: false };
      if (window.Plotly && window.Plotly.purge) {
        Plotly.purge(chartEl);
      }
      Plotly.newPlot('drawerPlotlyChart', [trace], layout, config).then(() => {
        Plotly.Plots.resize(chartEl);
      });
    }

    // Table click listener: Clicking anywhere on a hotel row opens drawer
    // (excluding direct clicks on watchlist star, operator link, or airport alt badge)
    document.addEventListener('click', function(e) {
      // 1. Direct interactive exclusions (stars, external tour operator links, etc.)
      if (e.target.closest('.watchlist-star-btn, .col-link-btn, .cheaper-alt-badge, .offer-link-cell a')) {
        return;
      }

      // 2. Check if clicked on a hotel table row
      const row = e.target.closest('tr.hotel-row');
      if (row && !e.ctrlKey && !e.metaKey) {
        const slug = row.getAttribute('data-hotel-slug');
        const hotelName = row.getAttribute('data-hotel-name') || (row.querySelector('.hotel-hover-link') ? row.querySelector('.hotel-hover-link').textContent.trim() : '');

        if (slug && window.HOTEL_PASSPORT_DATA && window.HOTEL_PASSPORT_DATA[slug]) {
          e.preventDefault();
          window.openHotelPassport(slug);
          return;
        }

        if (hotelName && window.HOTEL_PASSPORT_DATA) {
          const found = Object.values(window.HOTEL_PASSPORT_DATA).find(
            h => h.hotel_name.toLowerCase() === hotelName.toLowerCase()
          );
          if (found) {
            e.preventDefault();
            window.openHotelPassport(found.slug);
            return;
          }
        }
      }

      // 3. Fallback for standalone links if rendered elsewhere
      const link = e.target.closest('.open-chart-link, .hotel-hover-link');
      if (link && !e.ctrlKey && !e.metaKey) {
        const slug = link.getAttribute('data-hotel-slug');
        const hotelName = link.getAttribute('data-hotel-name') || link.textContent.trim();
        if (slug && window.HOTEL_PASSPORT_DATA && window.HOTEL_PASSPORT_DATA[slug]) {
          e.preventDefault();
          e.stopPropagation();
          window.openHotelPassport(slug);
        } else if (hotelName && window.HOTEL_PASSPORT_DATA) {
          const found = Object.values(window.HOTEL_PASSPORT_DATA).find(
            h => h.hotel_name.toLowerCase() === hotelName.toLowerCase()
          );
          if (found) {
            e.preventDefault();
            e.stopPropagation();
            window.openHotelPassport(found.slug);
          }
        }
      }
    });

    // Keyboard listener (Escape closes drawer)
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        window.closeHotelPassport();
      }
    });
    """
