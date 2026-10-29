#!/usr/bin/env python3
"""
AI Market Oracle: Two-Tier Market Intelligence Synthesizer.

Consumes compacted market features from `market_feature_extractor.py` and produces:
1. Macro Layer: Executive Market Briefing (Headline, Charter yield status, Arbitrage verdict,
   Key anomalies, Strategic booking directive).
2. Micro Layer: Hotel Booking Dossiers (Specific risk-reward rationale, wait potential,
   sold-out risk, and concrete booking trigger).

Supports:
- Gemini 1.5 Flash API with temperature control and structured JSON schema output.
- Deterministic Rule-Based Fallback when API keys are absent or rate-limited.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from market_feature_extractor import extract_filter_features

logger = logging.getLogger("ai_oracle")

SYSTEM_INSTRUCTION = """
Ты — умный и опытный консультант по путешествиям. Твоя задача — простым, живым и понятным обывателю языком объяснить ситуацию с ценами на туры и дать ясный совет: брать путевку прямо сейчас или подождать.

ПРАВИЛА И СТИЛЬ ОБЩЕНИЯ:
1. ПИШИ ПРОСТО И ПО-ЧЕЛОВЕЧЕСКИ, как опытный друг-турист. Никаких сложных финансовых и брокерских терминов вроде «квантиль», «волатильность», «асимметрия риска», «чартерная зачистка» или «доходность оператора».
2. ОБЪЯСНЯЙ НА ПАЛЬЦАХ:
   - Вместо «цена в 1-м квартиле» пиши: «цена на самом дне / одна из самых выгодных за сезон».
   - Вместо «чартерный демпинг» пиши: «туроператоры распродают оставшиеся билеты на рейсы со скидками».
   - Вместо «плато раннего бронирования» пиши: «до вылета еще много времени, цены спокойные и спешить не нужно».
   - Вместо «риск sold-out» пиши: «хорошие номера в этом отеле быстро разбирают».
3. ПРИВОДИ КОНКРЕТНЫЕ ЦИФРЫ: цены в злотых (zł), сколько дней осталось до вылета, сколько можно сэкономить.
4. УЧИТЫВАЙ РЕАЛЬНЫЕ ДАТЫ ВЫЛЕТА И ВЫЛЕТЫ «СЕГОДНЯ» (market_stats):
   - Обязательно смотри на min_days_to_departure, nearest_departure_date, has_today_departures, is_wide_window и dominant_yield_phase!
   - ВЫЛЕТЫ СЕГОДНЯ (min_days_to_departure = 0 или has_today_departures = true):
     * Помни: рейс улетает СЕГОДНЯ. Это экстремально горящий тур ТОЛЬКО для тех, кто уже сидит на собранных чемоданах и готов выехать в аэропорт через пару часов!
     * В совете (strategic_directive) обязательно предупреждай об этом и ДЛЯ СПОКОЙНОЙ ПОЕЗДКИ указывай следующую реалистичную дату вылета (next_realistic_departure_date через next_realistic_days_to_departure дн.).
     * КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать «Горящие туры за 0 дн.» — пиши «Срочные вылеты сегодня» (или «Срочные вылеты сегодня и даты до {furthest_departure_date}» при широком окне)!
   - ЕСЛИ is_wide_window=true (даты вылетов охватывают разные недели, например от 0/2 до 23 дней):
     * КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО называть ВЕСЬ рынок «Горящими турами» или писать, что все билеты закончатся через 24–48 часов!
     * В заголовке (headline) и фазе (market_phase) обязательно укажи весь диапазон: «Вылеты {nearest_departure_date}–{furthest_departure_date}: на ближайшие даты цены падают, на дальние — стабильны».
     * В совете (strategic_directive) четко раздели туристов на две группы:
       1) Тем, кто готов лететь сегодня/на днях ({nearest_departure_date}) — брать сейчас, билетов на рейсы мало.
       2) Тем, кто планирует поездку позже (до {furthest_departure_date}) — не спешить, добавить в «Избранное» (☆) и ждать: ближе к вылету туроператоры часто снижают цены.
   - Если is_wide_window=false (все даты в пределах 2-3 дней): НЕ дели даты на «ближайшие» и «дальние», вылет один!
   - Если до вылета больше 20 дней (например, 56 дней в декабре): это РАННЕЕ БРОНИРОВАНИЕ (early_bird / mid_term). Цены спокойные, спешить с покупкой не нужно. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать «Горящие туры», «вылет через 6 дн.» или советовать брать тур прямо сейчас!
   - Термин «Горящие туры» и совет «брать срочно» допустимы ТОЛЬКО если до вылета РЕАЛЬНО осталось от 1 до 7 дней при отсутствии широкого окна (или строго для ближайшей группы в широком окне)!
5. БЛОК «ЕСЛИ ПОКУПАТЬ СЕЙЧАС» (buy_now_recommendation):
   - Изучи переданные flash_drops, gems, arbitrage_highlights и top_candidates.
   - СТРОГИЙ АЛГОРИТМ ОТБОРА ДЛЯ TOP_PICKS (СТРОГО ПО ШАГАМ):
     1) ШАГ 1 (ЖЕСТКИЙ ФИЛЬТР КАЧЕСТВА): Рассматривай ТОЛЬКО отели с подтвержденным высоким рейтингом rating >= 4.0 и реальными отзывами (review_count > 0).
        Отели с rating = 0 (без отзывов) или rating < 4.0 ИСКЛЮЧАЮТСЯ ИЗ TOP_PICKS БЕЗУСЛОВНО, какая бы супер-скидка или низкая цена там ни была! КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО называть отели с 0 отзывов «проверенными с высоким рейтингом»!
     2) ШАГ 2 (КАТАЛИЗАТОР ВЫГОДЫ): Среди прошедших фильтр качественных отелей выбери 1–2 лучших с реальным сбросом цены (flash drop), статусом скрытой жемчужины (gem), историческим минимумом сезона или скидкой от 7% к медиане. Обязательно указывай точную цену отеля в поле "price".
     3) ШАГ 3 (ЕСЛИ КАЧЕСТВЕННЫХ ВЫГОДНЫХ СДЕЛОК НЕТ): Верни has_worthy_deals: false, headline: «Лучше ничего не покупать — подождите» (или «Срочные вылеты: нет выраженных супер-скидок в 4–5★» если вылет на днях), advice: «Честное объяснение...», top_picks: [].
6. СТРОГАЯ ТОЧНОСТЬ РЕЙТИНГОВ И ЦЕН (АНТИ-ГАЛЛЮЦИНАЦИЯ):
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО придумывать рейтинг отеля или писать «рейтинг 4.5★», если в данных указан другой рейтинг или rating=0!
   - Указывай ТОЛЬКО реальный рейтинг из поля rating отеля (например: «рейтинг 4.2★»). Если рейтинг равен 0 или отсутствует — вообще не упоминай рейтинг.
   - Отели с рейтингом ниже 4.0 КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО называть «Жемчужиной» или рекомендовать в блоке «Стоит выбрать»!
7. СРАВНЕНИЕ ТОЛЬКО С ПРИМЕРНО РАВНЫМИ:
   - Не сравнивай бюджетный отель со средней ценой по всему рынку. Сравнивай отель только с его собственной историей или равными отелями его категории.
8. СТРОГИЙ ЗАПРЕТ БРЕДОВЫХ ФРАЗ И ФАЛЬШИВЫХ СБРОСОВ ЦЕНЫ:
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать бейдж «⚡ Сброс цены», если скидка меньше 15%!
   - Скидка 1–6% — это НЕ скидка и НЕ сброс цены, это обычные суточные колебания. Запрещено называть это выгодной ценой или скидкой!
   - Скидка 7–14% — умеренная скидка («🔵 Скидка −X%»).
   - Скидка 15%+ или подтвержденный flash drop — реальный обвал цены («⚡ Сброс цены (−X%)»).
   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать «на 0% ниже» или «на 0% выше»!
9. ИСПОЛЬЗУЙ РЫНОЧНЫЙ ТРЕНД (market_trends):
   - Если trend_7d_pct <= -2.5% (рынок падает): отметь это в charter_dynamics как позитивный сигнал для выжидания (туроператоры снижают планку).
   - Если trend_7d_pct >= +2.5% (рынок растет): предупреди туриста, что цены начали подниматься.
10. АРБИТРАЖ АЭРОПОРТОВ (airports_comparison):
   - Если вылет из одного города заметно дешевле другого (spread_pln >= 300 zł): обязательно дай этот практический совет (например: «Вылет из Катовице на 650 zł выгоднее Варшавы на те же отели»).
11. АРБИТРАЖ ПО ДЛИТЕЛЬНОСТИ (duration_comparison):
   - Если multi_duration=true и доплата за дополнительные дни минимальна (cost_per_extra_day_pln <= 250 zł или delta_pln до 350-400 zł):
     ОБЯЗАТЕЛЬНО добавь это как аномалию в key_anomalies (type: "duration" или "arbitrage") и подскажи туристу: «10 дней брать намного выгоднее — доплата всего X zł за дополнительные дни на море».
12. ПОВЕДЕНЧЕСКИЙ АРХЕТИП ОТЕЛЯ (behavioral_archetype):
   - LATE_DUMPER: если до вылета еще много дней (D-30+), советуй ждать — отель регулярно сбрасывает цену в последние дни. Если вылет через 2–4 дня и цена упала — время брать.
   - ROCK_SOLID: держит стабильную цену весь сезон, ждать скидок перед вылетом бессмысленно.
   - EARLY_SURGER: дорожает ближе к дате, выгодно брать заранее.
13. НАПРАВЛЕНИЕ, СЕЗОННОСТЬ И РЕПУТАЦИЯ (destination_context & hotel_reputation):
   - Обязательно смотри на destination_context (страна, регион, климат и сезонность):
     * Турция в ноябре/зимой: закрытие сезона, море +20..+22°C, вечера прохладные (+12..+15°C). Отели переходят на зимнюю концепцию. Советуй отели с подогреваемыми бассейнами и спа. Не позиционируй это как жаркий пляжный отдых, а как комфортный релакс.
     * Египет зимой: море теплое (+23..+26°C), но важна защита бухты от ветра (Наама Бэй, Рас Ум Сид) и подогреваемый бассейн. В ветреных бухтах (Набк) предупреждай о волнах.
     * Кипр / Греция / Испания: обращай внимание на сезон и особенности пляжей.
   - Используй реальные данные из hotel_reputation:
     * Для семей с детьми отмечай beach_profile (пологий песчаный заход) и has_aquapark / family_and_kids.
     * Проверяй pros, cons_and_red_flags и season_trend (стал лучше / стал хуже) из базы отзывов!
     * Если отель дорогой, используй cheaper_alternative — предложи качественного двойника.
14. ДЛИТЕЛЬНОСТЬ ТУРА И СУТОЧНАЯ СТОИМОСТЬ (market_stats.trip_duration & cost_per_day_pln):
   - ВСЕГДА обращай внимание на длительность тура (trip_duration):
     * ДЛИННЫЙ ДВУХНЕДЕЛЬНЫЙ ТУР (13–16 дней / 2 недели, is_long_trip=true):
       - Помни: общая цена (например, 11 000 – 14 000 zł) — это цена за ДВЕ ПОЛНЫЕ НЕДЕЛИ отдыха, а не за 7 дней!
       - Не называй тур за 11 000 zł дорогим, если он на 14–16 ночей. Обязательно пересчитывай в стоимость за сутки (cost_per_day_pln): например, 11 400 zł за 14 ночей — это всего ~810 zł/сутки за двоих на «всё включено» в хорошем 5★ отеле (очень выгодная цена за долгий 2-недельный отдых!).
       - В тексте обязательно явно подчеркивай длительность: «для двухнедельного отдыха (13–16 ночей) цена очень комфортная» или «всего ~X zł в сутки за двоих».
     * СТАНДАРТНЫЙ ТУР (7–10 ночей / 1 неделя): средний бюджет 4 000 – 7 000 zł.
     * КОРОТКИЙ ТУР (3–5 ночей): общая цена ниже, но стоимость суток выше.
   - СТРОГО УКАЗЫВАЙ ПРАВИЛЬНУЮ СТРАНУ НАПРАВЛЕНИЯ из destination_context (например: Египет, а не Турция!).
15. ФОРМАТ ОТВЕТА: строго валидный JSON без markdown-разметки.

ЭТАЛОННЫЕ ПРИМЕРЫ (FEW-SHOT):

ПРИМЕР 1 (Раннее бронирование, вылет через 56 дней, спокойный рынок):
Вход: min_days=56, nearest_date="20.12", median_price=6800 zł, floor_pct=10%, top_candidates=[]
Ответ:
{
  "macro_briefing": {
    "headline": "Раннее бронирование: до вылета 56 дней, рынок спокойный",
    "market_phase": "Раннее бронирование за 56 дн.",
    "charter_dynamics": "До рейсов почти два месяца, туроператоры держат базовые цены без резких колебаний. Средний тур стоит около 6 800 zł.",
    "floor_status": "Только 10% отелей сейчас на локальном минимуме, рынок в спящем режиме.",
    "strategic_directive": "Покупать тур срочно не нужно. Добавьте понравившиеся отели в «Избранное» (☆) и наблюдайте за динамикой.",
    "buy_now_recommendation": {
      "has_worthy_deals": false,
      "headline": "Лучше ничего не покупать — подождите",
      "advice": "До вылета еще много времени. Глубоких скидок нет, отели продаются по стандартным базовым тарифам.",
      "top_picks": []
    },
    "key_anomalies": []
  }
}

ПРИМЕР 2 (Срочный вылет СЕГОДНЯ + широкий диапазон дат, отель без рейтинга отсеян):
Вход: min_days=0, has_today_departures=true, nearest_date="29.10", next_realistic_date="31.10", next_realistic_days=2, is_wide_window=true, furthest_date="21.11", median_price=7900 zł, floor_pct=4%, duration_comparison={cost_per_extra_day_pln: 98, delta_days: 2, delta_pln: 197}, top_candidates=[{"hotel_name": "Titanic Pearl", "price": 6915, "rating": 0.0, "review_count": 0, "discount_from_median_pct": 36.7}, {"hotel_name": "Albatros Makadi Resort", "price": 8206, "rating": 4.5, "review_count": 2800, "discount_from_median_pct": 20.1, "is_departing_today": true}, {"hotel_name": "Jaz Royal Palmariva", "price": 7644, "rating": 4.5, "review_count": 2800, "discount_from_median_pct": 42.4, "is_departing_today": false, "days_to_departure": 21}]
Ответ:
{
  "macro_briefing": {
    "headline": "Египет: стабильный рынок за 2–3 недели до вылета со срочными билетами на сегодня",
    "market_phase": "Срочные вылеты (29.10) и даты до 21.11",
    "charter_dynamics": "Базовые цены на стандартную неделю (8–9 ночей) стабильны и держатся около 7 900 zł за двоих. На сегодня есть срочные места со сбросом цен, но следующий спокойный вылет — 31.10 (через 2 дн.).",
    "floor_status": "Только 4% отелей находятся на историческом дне цены, массового сброса нет.",
    "strategic_directive": "Если готовы выехать в аэропорт через пару часов — берите проверенный Albatros на сегодня. Для спокойной поездки планируйте вылет на 31.10 или выбирайте Jaz Royal на вторую половину ноября по цене исторического дна.",
    "buy_now_recommendation": {
      "has_worthy_deals": true,
      "headline": "Стоит выбрать из этих вариантов:",
      "advice": "Для вылета сегодня подходит проверенный Albatros, а для планового отдыха в ноябре — Jaz Royal на абсолютном минимуме цены.",
      "top_picks": [
        {
          "hotel_name": "Albatros Makadi Resort (ex Royal Pharaohs Makadi)",
          "price": 8206.0,
          "badge": "⚡ Горящий вылет сегодня (−20%)",
          "why_buy": "Отличный рейтинг 4.5★ и подогреваемый бассейн. Цена ниже сезонной медианы на 20% (вылет сегодня, только на собранных чемоданах)."
        },
        {
          "hotel_name": "Jaz Royal Palmariva",
          "price": 7644.0,
          "badge": "💎 Историческое дно цены",
          "why_buy": "Вылет 19.11 на 9 ночей. Цена пробила абсолютный минимум сезона (−42% от нормы), отличный риф и высокий рейтинг 4.5★."
        }
      ]
    },
    "key_anomalies": [
      {
        "type": "duration",
        "title": "⏳ Выгодная доплата за 10 дней",
        "text": "Отдых на 10 ночей стоит всего на 197 zł дороже 8 ночей (доплата 98 zł в день за двоих). Имеет смысл брать более длинный тур."
      }
    ]
  }
}

ПРИМЕР 3 (Широкое окно дат 2–23 дня, спокойный рынок без супер-скидок):
Вход: is_wide_window=true, min_days=2, max_days=23, nearest_date="30.10", furthest_date="20.11", median_price=8000 zł, dominant_yield_phase="mid_term", gems=[], flash_drops=[], top_candidates=[{"hotel_name": "NLH Fix", "price": 6677, "rating": 0.0, "discount_from_median_pct": 4.0}]
Ответ:
{
  "macro_briefing": {
    "headline": "Вылеты 30.10–20.11: на ближайшие даты цены падают, на дальние — стабильны",
    "market_phase": "Ближайшие вылеты (30.10) и даты до 20.11",
    "charter_dynamics": "Подборка охватывает вылеты от ближайших дней (30.10, через 2 дн.) до конца ноября (20.11). На ближайшие рейсы туроператоры закрывают остатки мест, а на ноябрьские даты цены держатся на стабильном уровне около 8 000 zł.",
    "floor_status": "Только 12% отелей сейчас на локальном минимуме, рынок в спокойном режиме.",
    "strategic_directive": "Если планируете лететь на днях (30.10) — лучше брать сейчас, билетов на рейсы мало. Если поездка планируется позже (20.11) — можно не спешить, добавьте отели в «Избранное» (☆) и следите за ценой: ближе к вылету она часто снижается.",
    "buy_now_recommendation": {
      "has_worthy_deals": false,
      "headline": "Срочные вылеты: нет выраженных супер-скидок в 4–5★",
      "advice": "Ближайший вылет уже через 2 дня, но среди отелей с подтвержденным высоким рейтингом (4.0+★) глубоких скидок сейчас нет. Спешить с покупкой на ноябрь не стоит.",
      "top_picks": []
    },
    "key_anomalies": []
  }
}
"""


def generate_rule_based_briefing(market_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback deterministic synthesizer for offline or zero-key environments.
    Produces high-quality, friendly, data-grounded insights using simple human language.
    """
    stats = market_context.get("market_stats", {})
    floor = market_context.get("floor_saturation", {})
    hotel_count = stats.get("hotel_count", 0)
    med_price = stats.get("median_price", 0.0)
    min_price = stats.get("min_price", 0.0)
    p10_price = stats.get("p10_price", 0.0)
    avg_d = stats.get("median_days_to_departure", 14)
    floor_pct = floor.get("floor_breaker_pct", 0.0)
    floor_count = floor.get("floor_breaker_count", 0)

    min_d = stats.get("min_days_to_departure", avg_d)
    max_d = stats.get("max_days_to_departure", avg_d)
    is_wide_window = stats.get("is_wide_window", False)
    nearest_dep = stats.get("nearest_departure_date", "")
    furthest_dep = stats.get("furthest_departure_date", "")
    dep_label = f" ({nearest_dep})" if nearest_dep else ""

    has_today = stats.get("has_today_departures", min_d == 0)
    today_cnt = stats.get("today_departures_count", 0)
    next_real_d = stats.get("next_realistic_days_to_departure", min_d)
    next_real_dep = stats.get("next_realistic_departure_date", nearest_dep)
    dest_ctx = stats.get("destination_context", {})
    country_name = dest_ctx.get("country", "")
    weather_note = dest_ctx.get("climate_and_weather_advice", "")

    # Human-friendly phase descriptions and advice
    if has_today:
        if is_wide_window:
            phase_title = f"Срочные рейсы ({nearest_dep}) и вылеты до {furthest_dep}"
            phase_desc = (
                f"В подборке есть вылеты СЕГОДНЯ ({nearest_dep}) — они актуальны только для тех, кто сидит на собранных чемоданах. "
                f"Ближайший рейс для спокойного бронирования — {next_real_dep} (через {next_real_d} дн.). "
                f"На дальние даты (до {furthest_dep}) цены пока держатся на среднем уровне (~{med_price:,.0f} zł)."
            )
            directive = (
                f"Если готовы лететь сегодня ({nearest_dep}) — бронируйте срочно, билеты сгорают. "
                f"Для спокойной поездки планируйте вылет на {next_real_dep} или добавьте отели в «Избранное» (☆) на дальние даты."
            )
            headline = f"Вылеты {nearest_dep}–{furthest_dep}: срочные рейсы на сегодня и стабильные даты на {next_real_dep}"
        else:
            phase_title = f"Вылет СЕГОДНЯ ({nearest_dep})"
            phase_desc = f"Рейс улетает сегодня{dep_label}. Туроператоры отдают последние места с максимальными скидками. Подходит только туристам, готовым сразу ехать в аэропорт."
            directive = "Бронируйте немедленно, если успеваете на рейс: регистрация закроется в ближайшие часы."
            headline = f"Срочный вылет СЕГОДНЯ: туроператоры распродают последние кресла"
    elif is_wide_window:
        if min_d <= 7:
            phase_title = f"Ближайшие вылеты через {min_d} дн."
            phase_desc = (
                f"На рейсы в ближайшие дни ({nearest_dep}, через {min_d} дн.) туроператоры уже распродают последние места со скидками. "
                f"На более дальние даты (до {furthest_dep}) цены пока держатся на среднем уровне (~{med_price:,.0f} zł). "
                f"По мере приближения вылетов окно скидок будет постепенно смещаться и на следующие недели."
            )
            directive = (
                f"Если планируете лететь на днях ({nearest_dep}) — лучше брать сейчас, билетов на рейсы осталось мало. "
                f"Если поездка планируется позже ({furthest_dep}) — можно не спешить, добавьте отели в «Избранное» (☆) и следите за ценой: ближе к вылету она часто снижается."
            )
            headline = f"Вылеты {nearest_dep}–{furthest_dep}: на ближайшие даты цены падают, на дальние — стабильны"
        else:
            phase_title = f"Спокойные цены ({nearest_dep}–{furthest_dep})"
            phase_desc = (
                f"Ближайшие вылеты стартуют через {min_d} дн. ({nearest_dep}), а дальний край охватывает даты до {furthest_dep} ({max_d} дн.). "
                f"Вся подборка находится на стабильном уровне без резких скачков, средняя цена около {med_price:,.0f} zł. "
                f"Подборка живая и регулярно обновляется."
            )
            directive = (
                f"Спешить некуда, времени достаточно. За 10–14 дней до вылета на {nearest_dep} начнут появляться первые скидки. "
                f"Для дальних дат ({furthest_dep}) сейчас имеет смысл бронировать только самые популярные отели, где быстро кончаются номера."
            )
            headline = f"Вылеты {nearest_dep}–{furthest_dep}: цены стабильные, спешить с покупкой не нужно"
    else:
        if min_d <= 3:
            phase_title = f"Горящие туры (вылет через {min_d} дн.)"
            phase_desc = f"До вылета осталось всего {min_d} дн.{dep_label}. Самолеты почти заполнены, поэтому отели либо отдают последние номера с максимальной скидкой, либо места просто заканчиваются."
            directive = "Бронируйте сразу, если отель вам подходит: места на рейсах тают на глазах, через пару часов тура может уже не быть."
            headline = f"Горящие туры: вылет через {min_d} дн., туроператоры отдают последние места"
        elif min_d <= 7:
            phase_title = f"Время скидок (вылет через {min_d} дн.)"
            phase_desc = f"До вылета {min_d} дн.{dep_label} — это самое активное время распродаж. Туроператоры снижают цены на оставшиеся места в самолетах. Средняя цена сейчас около {med_price:,.0f} zł."
            directive = f"Отличный момент для покупки отелей со значком «ПОКУПАТЬ» — цена на минимуме. Если отель обычный, можно понаблюдать еще пару дней."
            headline = f"Время выгодных покупок: вылет через {min_d} дн., цены активно падают"
        elif min_d <= 14:
            phase_title = f"Первые скидки (вылет через {min_d} дн.)"
            phase_desc = f"До вылета {min_d} дн.{dep_label}. Началась первая волна снижения цен перед вылетом. Хорошие варианты начинаются от {p10_price:,.0f} zł."
            directive = "Удачное время для выбора хороших отелей: и скидки уже есть, и популярные номера еще не раскуплены."
            headline = f"Вылет через {min_d} дн.: отличный баланс цены и выбора отелей"
        else:
            phase_title = f"Ранний выбор (вылет через {min_d} дн.)"
            phase_desc = f"До вылета {min_d} дн.{dep_label}. Рынок спокойный, средняя цена держится на уровне {med_price:,.0f} zł. Резких сбросов цен пока нет."
            directive = "Спешить не нужно. Сохраняйте понравившиеся отели в Избранное (☆) и ждите: за 10–14 дней до вылета часто начинаются первые скидки."
            headline = f"До вылета {min_d} дн.: цены стабильные, можно спокойно выбирать отель"

    if weather_note:
        phase_desc = f"{phase_desc} Погода ({country_name}): {weather_note}"

    trip_dur = stats.get("trip_duration", {})
    dur_label = trip_dur.get("label", "")
    is_long_trip = trip_dur.get("is_long_trip", False)
    cost_per_day = trip_dur.get("cost_per_day_median_pln", 0)
    if is_long_trip and dur_label and cost_per_day > 0:
        phase_desc = f"{phase_desc} Тур рассчитан на {dur_label} (две недели), средняя стоимость суток — ~{cost_per_day:,.0f} zł за двоих на «всё включено»."

    # Top anomalies in everyday language
    anomalies: List[Dict[str, str]] = []
    if floor_count > 0:
        anomalies.append({
            "type": "floor",
            "title": f"Ценовое дно: {floor_count} отелей ({floor_pct}%)",
            "text": f"Зафиксирована самая низкая цена за весь сезон. Цены начинаются от {min_price:,.0f} zł."
        })

    for fd in market_context.get("flash_drops", [])[:2]:
        anomalies.append({
            "type": "drop",
            "title": f"⚡ Резкий сброс: {fd['hotel_name']}",
            "text": f"Цена упала на {fd['drop_pct']:.0f}% ниже обычного минимума (сейчас {fd['current_price']:,.0f} zł). Туроператор может закрыть скидку в любой момент."
        })

    top_gems = market_context.get("gems", [])
    if top_gems:
        g = top_gems[0]
        anomalies.append({
            "type": "gem",
            "title": f"💎 Скрытая жемчужина: {g['hotel_name']}",
            "text": f"Высокий рейтинг {g.get('rating', 4.5):g}★ в категории {g.get('stars', 5)}★ всего за {g['price']:,.0f} zł (намного дешевле похожих отелей)."
        })

    apt_comp = market_context.get("airports_comparison", {})
    if apt_comp.get("multi_airport") and apt_comp.get("spread_pln", 0) >= 300:
        anomalies.append({
            "type": "arbitrage",
            "title": f"✈️ Разница вылетов: {apt_comp.get('cheapest_hub')} vs {apt_comp.get('expensive_hub')}",
            "text": apt_comp.get("insight", f"Экономия {apt_comp.get('spread_pln', 0):,.0f} zł при смене аэропорта."),
        })

    dur_comp = market_context.get("duration_comparison", {})
    if dur_comp.get("multi_duration") and dur_comp.get("cost_per_extra_day_pln", 9999) <= 250:
        anomalies.append({
            "type": "duration",
            "title": f"⏳ Выгодная длительность: {dur_comp.get('longer_duration_days')} дн.",
            "text": dur_comp.get("insight", "Доплата за дополнительные дни минимальна."),
        })

    m_trends = market_context.get("market_trends", {})
    t7 = m_trends.get("trend_7d_pct")
    if t7 is not None and abs(t7) >= 3.0:
        if t7 <= -3.0:
            anomalies.append({
                "type": "trend",
                "title": f"📉 Недельный спад рынка: {t7:+.1f}%",
                "text": f"За последние 7 дней средняя цена на направлении снизилась на {abs(t7):.1f}% ({abs(m_trends.get('delta_7d_pln', 0)):,.0f} zł).",
            })
        else:
            anomalies.append({
                "type": "trend",
                "title": f"📈 Цены растут: {t7:+.1f}% за неделю",
                "text": f"Средняя цена за последние 7 дней поднялась на {t7:.1f}% ({m_trends.get('delta_7d_pln', 0):,.0f} zł).",
            })

    eb_ctx = market_context.get("early_booking", {})
    if eb_ctx:
        eb_verdict = eb_ctx.get("verdict")
        eb_sold_out = eb_ctx.get("sold_out_rate_at_14d")
        if eb_verdict == "EARLY_BOOKING_HIGHLY_FAVORABLE":
            anomalies.append({
                "type": "early_booking",
                "title": "🏷️ Раннее бронирование выгодно",
                "text": f"По нашей когортной статистике отели этого направления дорожают к вылету, а ~{int((eb_sold_out or 0.44)*100)}% номеров распродаются до горящих туров. Бронирование заранее надёжнее.",
            })
        elif eb_verdict == "WAIT_FOR_LAST_MINUTE":
            anomalies.append({
                "type": "early_booking",
                "title": "⚡ Выгоднее ждать Last Minute",
                "text": "По исторической динамике туроператоры снижают цены ближе к вылету. Ожидание горящих предложений здесь статистически оправдано.",
            })

    dossiers: Dict[str, Dict[str, Any]] = {}
    hotels_to_process = market_context.get("all_hotel_intelligence") or {
        h["hotel_name"]: h for h in market_context.get("selected_hotel_dossiers", [])
    }

    for h_name, h in hotels_to_process.items():
        cur_p = h.get("current_price", 0.0)
        hist_min = h.get("historical_min", cur_p)
        quantile = h.get("quantile_in_filter", 0.5)
        flash = h.get("flash_drop", {})

        hist_med = h.get("historical_median", cur_p)
        fp = h.get("fair_price", {})
        diff_from_med = ((cur_p - hist_med) / max(1.0, hist_med)) * 100.0 if hist_med > 0 else 0.0

        if flash.get("is_flash"):
            verdict = "BUY_NOW"
            verdict_badge = "⚡ СБРОС ЦЕНЫ"
            rationale = f"Резкий обвал цены до {cur_p:,.0f} zł (на {flash.get('drop_pct', 0):.0f}% ниже минимума сезона)."
            risk = "Билеты по этой цене туроператор может распродать за считанные часы."
            advice = "Если отель вам подходит — бронируйте прямо сейчас."
        elif cur_p <= hist_min * 1.02:
            verdict = "BUY_NOW"
            verdict_badge = "🟢 ПОКУПАТЬ"
            rationale = f"Цена {cur_p:,.0f} zł — на самом дне за всё время наблюдений (обычно этот отель дороже). Самый удачный момент для покупки."
            risk = "Номера в этом отеле популярны, к дате вылета мест может не остаться."
            advice = "Если отель нравится — фиксируйте бронь прямо сегодня, дешевле уже вряд ли будет."
        elif diff_from_med >= 10.0 or fp.get("class") == "expensive":
            verdict = "OVERPRICED"
            verdict_badge = "🔴 ДОРОГО"
            diff_val = max(1.0, abs(diff_from_med))
            rationale = f"Цена {cur_p:,.0f} zł на {diff_val:.0f}% выше обычной средней цены этого отеля ({hist_med:,.0f} zł)."
            risk = "Высокий риск переплаты. Туроператор держит завышенную цену."
            advice = "Покупать сейчас крайне невыгодно. Добавьте в Избранное (☆) и ждите снижения."
        elif diff_from_med <= -7.0:
            verdict = "GOOD_PRICE"
            verdict_badge = "🔵 ХОРОШАЯ ЦЕНА"
            rationale = f"Цена {cur_p:,.0f} zł на {abs(diff_from_med):.0f}% ниже обычной средней цены отеля ({hist_med:,.0f} zł)."
            risk = "Цена может слегка колебаться, но предложение уже достаточно выгодное."
            advice = "Хорошая цена со скидкой, можно бронировать."
        else:
            verdict = "WAIT"
            verdict_badge = "🟡 ПОДОЖДАТЬ"
            rationale = f"Отель сейчас стоит {cur_p:,.0f} zł — это обычная базовая цена за сезон (медиана {hist_med:,.0f} zł)."
            risk = "Цена не снижена, туроператор пока не давал скидок на эти даты."
            advice = "Спешить не нужно: добавьте в Избранное (☆) и подождите приближения вылета."

        dossiers[h_name] = {
            "verdict": verdict,
            "badge_text": verdict_badge,
            "rationale": rationale,
            "risk_assessment": risk,
            "action_advice": advice,
        }

    clean_filter_title = market_context.get("filter_title") or ""

    res = {
        "macro_briefing": {
            "headline": headline,
            "market_phase": phase_title,
            "filter_title": clean_filter_title,
            "charter_dynamics": phase_desc,
            "floor_status": f"{floor_count} отелей ({floor_pct}%) сейчас отдают по минимальной цене за сезон.",
            "strategic_directive": directive,
            "key_anomalies": anomalies,
            "synthesized_by": "Rule-Based Deterministic Engine (Offline)",
        },
        "hotel_dossiers": dossiers,
    }
    return enrich_oracle_report_with_smart_features(res, market_context)


def compute_buy_now_recommendation(
    market_context: Dict[str, Any],
    dossiers: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Формирует рекомендацию «Если покупать сейчас»:
    - 1-2 лучших варианта на текущий момент, если есть реальная выгода (сброс цены, жемчужина, идеальное окно, супер Deal Score).
    - Либо «Лучше ничего не покупать — подождите», если все отели на рынке обычные или переоценены.
    """
    all_intel = market_context.get("all_hotel_intelligence", {})
    if not all_intel:
        all_intel = {
            c["hotel_name"]: c for c in market_context.get("top_candidates", []) if isinstance(c, dict) and c.get("hotel_name")
        } or {
            h["hotel_name"]: h for h in market_context.get("selected_hotel_dossiers", []) if isinstance(h, dict) and h.get("hotel_name")
        }

    scored_candidates = []
    for h_name, h_info in all_intel.items():
        cur_p = float(h_info.get("current_price") or h_info.get("price") or 0.0)
        if cur_p <= 0:
            continue

        hist_min = float(h_info.get("historical_min") or h_info.get("price_history", {}).get("historical_min") or cur_p or 0.0)
        flash = h_info.get("flash_drop", {})
        gem = h_info.get("gem", {})
        bw = h_info.get("booking_window", {})
        fp = h_info.get("fair_price", {})
        dossier = dossiers.get(h_name, {})
        verdict = dossier.get("verdict", "")

        hist_med = float(h_info.get("historical_median") or h_info.get("price_history", {}).get("historical_median") or cur_p or 0.0)

        # Исключаем заведомо переоценённые варианты или варианты выше собственной нормы
        if verdict == "OVERPRICED" or fp.get("class") == "fair-overpriced" or (hist_med > 0 and cur_p > hist_med * 1.03):
            continue

        score = 0
        reasons = []
        best_badge = ""
        has_real_catalyst = False

        # 1. Резкий сброс цены (Flash Drop / сброс чартера)
        if flash.get("is_flash"):
            score += 120
            drop_pct = flash.get("drop_pct", 0)
            best_badge = f"⚡ Сброс цены (−{drop_pct:.0f}%)"
            reasons.append(f"цена рухнула на {drop_pct:.0f}% ниже минимума сезона")
            has_real_catalyst = True

        # 2. Скрытая жемчужина
        if gem.get("is_gem"):
            score += 100
            r_val = gem.get("rating", 4.5)
            if not best_badge:
                best_badge = f"💎 Жемчужина {r_val:g}★"
            reasons.append(f"высокий рейтинг {r_val:g}★ по цене эконом-сегмента")
            has_real_catalyst = True

        # 3. Скидка к сопоставимым отелям своего сегмента (Fair Price Index)
        diff_pct = fp.get("delta_pct", 0)
        tier_lbl = fp.get("tier", "")
        if diff_pct <= -10 and (hist_med <= 0 or cur_p <= hist_med * 0.98):
            score += abs(diff_pct) * 2.5
            if not best_badge:
                st = fp.get("stars", 4)
                best_badge = f"🔥 {diff_pct:.0f}% в {tier_lbl} {st}★"
            reasons.append(f"на {abs(diff_pct):.0f}% дешевле равных отелей сегмента {tier_lbl}")
            has_real_catalyst = True

        # 4. Идеальное окно покупки по истории (только если цена реально снижена)
        if bw.get("window_class") in ("panic", "last", "in_window") and bw.get("window_badge"):
            score += 60
            if not best_badge:
                best_badge = bw.get("window_badge", "🎯 Окно покупки")
            reasons.append(f"выгодный момент покупки ({bw.get('optimal_window', 'сейчас')})")
            has_real_catalyst = True

        # 5. Реальное дно сезона (только если цена на минимуме и была выше)
        hist_max = float(h_info.get("historical_max") or h_info.get("price_history", {}).get("historical_max") or cur_p or 0.0)
        if cur_p <= hist_min * 1.01 and (hist_max >= cur_p * 1.05 or hist_med >= cur_p * 1.03):
            score += 50
            if hist_max > cur_p:
                reasons.append(f"цена на дне сезона (−{((hist_max - cur_p)/hist_max)*100:.0f}% от пика)")
            else:
                reasons.append("цена на историческом минимуме")
            has_real_catalyst = True
            if not best_badge:
                best_badge = "⚡ Дно цены"

        rating = float(h_info.get("rating") or h_info.get("ta_rating") or 0.0)
        # Quality Guard: unrated (0.0) or low-rated (< 4.0) hotels should not be recommended in top picks
        if rating < 4.0:
            continue

        if rating >= 4.5:
            score += 40
            reasons.append(f"высокий рейтинг {rating:g}★")
        elif rating >= 4.0:
            score += 20
            reasons.append(f"хороший рейтинг {rating:g}★")

        if has_real_catalyst and score >= 80:
            scored_candidates.append({
                "hotel_name": h_name,
                "price": cur_p,
                "score": score,
                "badge": best_badge or "🟢 Выгодная цена",
                "why_buy": ", ".join(reasons).capitalize() + f" ({cur_p:,.0f} zł).",
                "offer_url": h_info.get("offer_url", ""),
            })

    scored_candidates.sort(key=lambda x: -x["score"])

    if scored_candidates:
        top_picks = scored_candidates[:2]
        headline = "Стоит выбрать из этих вариантов:" if len(top_picks) > 1 else "Стоит присмотреться к этому варианту:"
        return {
            "has_worthy_deals": True,
            "headline": headline,
            "status_badge": "🟢 ЕСТЬ ВЫГОДНЫЕ ВАРИАНТЫ",
            "advice": "Если вы планируете поездку на ближайшее время — это самые удачные предложения по соотношению цена/качество прямо сейчас.",
            "top_picks": top_picks,
        }
    else:
        stats = market_context.get("market_stats", {})
        min_d = stats.get("min_days_to_departure", 14)
        if min_d <= 3:
            headline = "Срочные вылеты: нет выраженных супер-скидок в 4–5★"
            advice = (
                f"Ближайший вылет уже через {min_d} дн., однако среди отелей с высоким подтвержденным рейтингом (4.0+★) "
                "глубоких аномальных скидок сейчас нет. Если лететь нужно срочно — выбирайте варианты в таблице ниже, обязательно проверяя отзывы."
            )
        else:
            headline = "Лучше ничего не покупать — подождите"
            advice = (
                "Сейчас на рынке нет действительно выгодных предложений: отели продаются по базовым или завышенным ценам. "
                "Спешить с бронированием нет смысла — сохраните отели в «Избранное» (⭐) и подождите приближения вылета (за 7–10 дней туроператоры обычно начинают снижать цены)."
            )
        return {
            "has_worthy_deals": False,
            "headline": headline,
            "status_badge": "✋ ВЫГОДНЫХ СДЕЛОК НЕТ",
            "advice": advice,
            "top_picks": [],
        }


def enrich_oracle_report_with_smart_features(
    report: Dict[str, Any],
    market_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Enriches AI or rule-based reports with quantitative smart feature badges:
    - Optimal Booking Window Matrix
    - Fair Price Index
    - Hidden Gems
    - Glitch & Flash Drop Radar
    - AI Dupe & Twin suggestions
    - Buy Now Recommendation (Top 1-2 picks or "better not buy")
    Ensures EVERY hotel in filter has a complete dossier with badges.
    """
    if not report or not isinstance(report, dict):
        report = {}

    dossiers = report.setdefault("hotel_dossiers", {})
    all_intel = market_context.get("all_hotel_intelligence", {})
    for h_name, h_info in all_intel.items():
        if h_name not in dossiers:
            cur_p = float(h_info.get("current_price", 0.0) or 0.0)
            hist_min = float(h_info.get("historical_min", cur_p) or cur_p)
            hist_med = float(h_info.get("historical_median", cur_p) or cur_p)
            fp = h_info.get("fair_price", {})
            diff_from_med = ((cur_p - hist_med) / max(1.0, hist_med)) * 100.0 if hist_med > 0 else 0.0
            flash = h_info.get("flash_drop", {})
            quantile = float(h_info.get("quantile_in_filter", 0.5))

            if flash.get("is_flash"):
                v = "BUY_NOW"
                b_text = "⚡ СБРОС ЦЕНЫ"
                rat = f"Резкий обвал цены до {cur_p:,.0f} zł (на {flash.get('drop_pct', 0):.0f}% ниже минимума сезона)."
                adv = "Если отель вам подходит — бронируйте прямо сейчас."
            elif cur_p <= hist_min * 1.02:
                v = "BUY_NOW"
                b_text = "🟢 ПОКУПАТЬ"
                rat = f"Цена {cur_p:,.0f} zł — на самом дне за всё время наблюдений ({hist_min:,.0f} zł)."
                adv = "Отличный момент для покупки, дешевле уже вряд ли будет."
            elif diff_from_med >= 10.0 or fp.get("class") == "expensive":
                v = "OVERPRICED"
                b_text = "🔴 ДОРОГО"
                diff_val = max(1.0, abs(diff_from_med))
                rat = f"Цена {cur_p:,.0f} zł на {diff_val:.0f}% выше обычной средней этого отеля ({hist_med:,.0f} zł)."
                adv = "Покупать сейчас невыгодно: цена завышена, лучше подождать снижения."
            elif diff_from_med <= -7.0:
                v = "GOOD_PRICE"
                b_text = "🔵 ХОРОШАЯ ЦЕНА"
                rat = f"Цена {cur_p:,.0f} zł на {abs(diff_from_med):.0f}% ниже обычной средней цены отеля ({hist_med:,.0f} zł)."
                adv = "Хорошая цена со скидкой, можно бронировать."
            else:
                v = "WAIT"
                b_text = "🟡 ПОДОЖДАТЬ"
                rat = f"Отель сейчас стоит {cur_p:,.0f} zł — это обычная базовая цена за сезон (медиана {hist_med:,.0f} zł)."
                adv = "Спешить не нужно, добавьте в «Избранное» (☆) и подождите."

            dossiers[h_name] = {
                "verdict": v,
                "badge_text": b_text,
                "rationale": rat,
                "risk_assessment": "Следите за доступностью номеров перед вылетом.",
                "action_advice": adv,
            }
        cur_d = dossiers[h_name]

        # 1. Booking Window
        bw = h_info.get("booking_window", {})
        cur_d["booking_window_badge"] = bw.get("window_badge", "")
        cur_d["booking_window_class"] = bw.get("window_class", "early")
        cur_d["booking_window_tip"] = bw.get("window_tip", "")

        # 2. Fair Price Index
        fp = h_info.get("fair_price", {})
        cur_d["fair_price_badge"] = fp.get("badge", "")
        cur_d["fair_price_class"] = fp.get("class", "")
        cur_d["fair_price_tip"] = fp.get("tip", "")

        # 3. Hidden Gem
        gem = h_info.get("gem", {})
        cur_d["gem_badge"] = gem.get("badge", "")
        cur_d["gem_tip"] = gem.get("tip", "")

        # 4. Flash Drop
        flash = h_info.get("flash_drop", {})
        cur_d["flash_drop_badge"] = flash.get("badge", "")
        cur_d["flash_drop_tip"] = flash.get("tip", "")

        # 5. AI Dupe Alternative
        cur_d["dupe_suggestion"] = h_info.get("dupe_suggestion")

    # Ensure anomalies list contains active flash drops & gems if missing
    macro = report.setdefault("macro_briefing", {})
    existing_anomalies = macro.setdefault("key_anomalies", [])
    existing_texts = " ".join(str(a.get("title", "")) for a in existing_anomalies)

    for fd in market_context.get("flash_drops", [])[:2]:
        if fd["hotel_name"] not in existing_texts:
            existing_anomalies.append({
                "type": "drop",
                "title": f"⚡ Резкий сброс: {fd['hotel_name']}",
                "text": f"Цена упала на {fd['drop_pct']:.0f}% ниже обычного минимума (сейчас {fd['current_price']:,.0f} zł). Туроператор может закрыть скидку в любой момент."
            })

    for g in market_context.get("gems", [])[:1]:
        if g["hotel_name"] not in existing_texts:
            r_str = f"Рейтинг {g['rating']:g}★" if g.get("rating", 0) > 0 else "Популярный отель"
            existing_anomalies.append({
                "type": "gem",
                "title": f"💎 Скрытая жемчужина: {g['hotel_name']}",
                "text": f"{r_str} в категории {g.get('stars', 4)}★ всего за {g['price']:,.0f} zł (дешевле аналогов)."
            })

    # Duration arbitrage auto-injection
    dur_comp = market_context.get("duration_comparison", {})
    if dur_comp.get("multi_duration") and dur_comp.get("cost_per_extra_day_pln", 9999) <= 250:
        if not any(a.get("type") in ("duration", "arbitrage") and ("дн" in str(a.get("title", "")).lower() or "длительн" in str(a.get("title", "")).lower()) for a in existing_anomalies):
            existing_anomalies.append({
                "type": "duration",
                "title": f"⏳ Выгодная длительность: {dur_comp.get('longer_duration_days')} дн.",
                "text": dur_comp.get("insight", "Доплата за дополнительные дни минимальна."),
            })

    # Airport arbitrage auto-injection
    apt_comp = market_context.get("airports_comparison", {})
    if apt_comp.get("multi_airport") and apt_comp.get("spread_pln", 0) >= 300:
        if not any(a.get("type") == "arbitrage" and "вылет" in str(a.get("title", "")).lower() for a in existing_anomalies):
            existing_anomalies.append({
                "type": "arbitrage",
                "title": f"✈️ Разница вылетов: {apt_comp.get('cheapest_hub')} vs {apt_comp.get('expensive_hub')}",
                "text": apt_comp.get("insight", f"Экономия {apt_comp.get('spread_pln', 0):,.0f} zł при смене аэропорта."),
            })

    # 6. Buy Now Recommendation validation & ground-truth enrichment
    buy_rec = macro.get("buy_now_recommendation")
    all_intel = market_context.get("all_hotel_intelligence", {})
    if not buy_rec or not buy_rec.get("top_picks"):
        macro["buy_now_recommendation"] = compute_buy_now_recommendation(market_context, dossiers)
    else:
        verified_picks = []
        for pick in buy_rec.get("top_picks", []):
            hn = str(pick.get("hotel_name", ""))
            intel = all_intel.get(hn)
            if intel:
                cur_p = float(intel.get("current_price", 0.0) or 0.0)
                real_r = float(intel.get("rating", 0.0) or 0.0)

                # Overwrite price with verified ground truth (fixes 0 zł bug!)
                pick["price"] = cur_p
                pick["rating"] = real_r

                # Disqualify hotels with unrated or poor ratings (< 4.0) from buy recommendations
                if real_r < 4.0 or (intel.get("review_count", 0) == 0 and real_r == 0.0):
                    logger.info(f"Disqualifying {hn} from top picks due to unrated or low TripAdvisor rating ({real_r}★)")
                    continue

                # Fix hallucinated ratings in why_buy (fixes 'Ложь про рейтинг 4.5' bug!)
                why_text = str(pick.get("why_buy", ""))
                if "4.5" in why_text and abs(real_r - 4.5) > 0.1:
                    if real_r > 0:
                        why_text = why_text.replace("4.5", f"{real_r:g}")
                    else:
                        why_text = re.sub(r",?\s*(?:а\s*)?рейтинг\s*4\.5[★\*]?", "", why_text)
                pick["why_buy"] = why_text
                verified_picks.append(pick)
            else:
                if hn in dossiers:
                    d_r = float(dossiers[hn].get("rating") or dossiers[hn].get("ta_rating") or 0.0)
                    if d_r >= 4.0:
                        verified_picks.append(pick)

        buy_rec["top_picks"] = verified_picks
        if not verified_picks:
            macro["buy_now_recommendation"] = compute_buy_now_recommendation(market_context, dossiers)

    # 7. Ground-truth sanity check for market_phase, headline, and strategic_directive
    stats = market_context.get("market_stats", {})
    min_d = stats.get("min_days_to_departure", 14)
    nearest_dep = stats.get("nearest_departure_date", "")
    furthest_dep = stats.get("furthest_departure_date", "")
    is_wide = stats.get("is_wide_window", False)
    phase_str = str(macro.get("market_phase", ""))
    has_today = stats.get("has_today_departures", min_d == 0)

    # Sanitize clumsy '0 дн.' phrasing in market_phase
    if has_today or min_d == 0:
        if any(token in phase_str.lower() for token in ("0 дн", "0 дней", "через 0", "за 0")):
            if is_wide and furthest_dep:
                macro["market_phase"] = f"Срочные вылеты ({nearest_dep}) и даты до {furthest_dep}"
            else:
                macro["market_phase"] = f"Срочный вылет СЕГОДНЯ ({nearest_dep})" if nearest_dep else "Срочный вылет СЕГОДНЯ"
            logger.info(f"Sanitized '0 дн.' phrasing in market_phase from '{phase_str}' to '{macro['market_phase']}'")

    # If departure is > 20 days away, but AI hallucinated "Горящие туры" or "через X дн."
    if min_d >= 20 and ("горящ" in phase_str.lower() or re.search(r"через\s*[1-9]\s*дн", phase_str, re.I)):
        dep_suffix = f" ({nearest_dep})" if nearest_dep else ""
        macro["market_phase"] = f"Ранний выбор (вылет через {min_d} дн.{dep_suffix})"
        logger.info(f"Corrected hallucinated market_phase from '{phase_str}' to '{macro['market_phase']}' (min_d={min_d})")

    head_str = str(macro.get("headline", ""))
    if not is_wide and ("дальние" in head_str.lower() or "ближайшие даты цены падают" in head_str.lower()):
        if min_d >= 20:
            macro["headline"] = f"Вылеты {nearest_dep} (через {min_d} дн.): цены стабильные, спешить с покупкой не нужно"
        else:
            macro["headline"] = f"Вылеты {nearest_dep} (через {min_d} дн.): туроператоры обновляют цены"
        logger.info(f"Corrected wide-window hallucination in headline to '{macro['headline']}'")

    directive_str = str(macro.get("strategic_directive", ""))
    if min_d >= 20 and ("на ближайшие даты, стоит брать" in directive_str.lower() or "брать прямо сейчас" in directive_str.lower() or "стоит брать туры сейчас" in directive_str.lower()):
        macro["strategic_directive"] = f"До вылета еще много времени ({min_d} дн.). Цены находятся на обычном уровне. Спешить с бронированием не нужно: добавьте отели в «Избранное» (☆) и наблюдайте за ценой за 10–14 дней до вылета."
        logger.info("Corrected rushed buy directive for distant departure (>20 days).")
    elif has_today:
        next_real_dep = stats.get("next_realistic_departure_date", "")
        next_real_d = stats.get("next_realistic_days_to_departure", 0)
        charter_str = str(macro.get("charter_dynamics", ""))
        if next_real_dep and next_real_d > 0 and next_real_dep not in directive_str and next_real_dep not in charter_str:
            macro["strategic_directive"] = directive_str.rstrip() + f" Для спокойного вылета ближайшая дата — {next_real_dep} (через {next_real_d} дн.)."
            logger.info("Appended next realistic departure date for today's flight.")

    if market_context.get("filter_title"):
        macro["filter_title"] = market_context["filter_title"]

    return report


def call_gemini_oracle(
    market_context: Dict[str, Any],
    api_key: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Invokes Google Gemini API with strict JSON schema and robust fallback chain.
    """
    import re

    candidates = [model, os.getenv("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    target_models = []
    for c in candidates:
        if c and c not in target_models:
            target_models.append(c)

    llm_context = {
        "filter_id": market_context.get("filter_id"),
        "filter_title": market_context.get("filter_title"),
        "analyzed_at": market_context.get("analyzed_at"),
        "market_stats": market_context.get("market_stats"),
        "market_trends": market_context.get("market_trends", {}),
        "airports_comparison": market_context.get("airports_comparison", {}),
        "duration_comparison": market_context.get("duration_comparison", {}),
        "floor_saturation": market_context.get("floor_saturation"),
        "top_candidates": market_context.get("top_candidates", []),
        "arbitrage_highlights": market_context.get("arbitrage_highlights", []),
        "gems": market_context.get("gems", []),
        "flash_drops": market_context.get("flash_drops", []),
    }
    if market_context.get("early_booking"):
        llm_context["early_booking"] = market_context.get("early_booking")

    is_deep = os.getenv("AI_ANALYSIS_MODE", "standard").lower() == "full_deep"
    if is_deep:
        if market_context.get("all_hotels_catalog"):
            llm_context["all_hotels_catalog"] = market_context.get("all_hotels_catalog", [])
        deep_note = "\nРЕЖИМ: FULL DEEP (полный глубокий прогон через AI). Тебе переданы ВСЕ отели и кандидаты данного направления. Проведи полный всесторонний разбор рынка и отбери лучших кандидатов для покупки из всего каталога."
    else:
        deep_note = ""

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров направления "{market_context.get('filter_title', '')}" и выдай краткое экспертное резюме в формате JSON:{deep_note}

ВХОДНЫЕ ДАННЫЕ РЫНКА (МАКРО-СТАТИСТИКА И ТОП-КАНДИДАТЫ):
{json.dumps(llm_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Честный краткий заголовок ситуации строго по реальным данным min_days_to_departure и nearest_departure_date (СТРОГО БЕЗ названий файлов, slug или filter_id)",
    "market_phase": "Фаза рынка: если вылет сегодня (0 дн.) — 'Срочные вылеты сегодня' (при широком окне: 'Срочные вылеты сегодня и даты до DD.MM'); если вылет нескоро — 'Раннее бронирование за X дн.'; если через 1–7 дн. — 'Горящие туры за X дн.'",
    "charter_dynamics": "2-3 простых понятных предложения с цифрами о ценах и рейсах, обязательно с точной страной из destination_context и длительностью (например: туры на 8–9 ночей в Египет...). При вылетах сегодня обязательно укажи дату следующего спокойного рейса (next_realistic_departure_date)",
    "floor_status": "Сколько отелей сейчас на самом дне цены (например: 'Лишь 4% отелей на минимуме...')",
    "strategic_directive": "Простой четкий совет: кому брать тур прямо сейчас (если вылет сегодня — только на чемоданах; для остальных указать next_realistic_departure_date), а кому лучше подождать",
    "buy_now_recommendation": {{
      "has_worthy_deals": true,
      "headline": "Стоит выбрать из этих вариантов: (или: 'Лучше ничего не покупать — подождите')",
      "advice": "Короткий живой совет туристу (никогда не называй непроверенные отели с 0 отзывов проверенными!)",
      "top_picks": [
        {{ "hotel_name": "Точное имя отеля из top_candidates СТРОГО с rating >= 4.0", "price": 1234.0, "badge": "⚡ Сброс цены / 💎 Жемчужина", "why_buy": "Краткое обоснование с цифрами" }}
      ]
    }},
    "key_anomalies": [
      {{ "type": "drop|arbitrage|overprice|duration", "title": "...", "text": "..." }}
    ]
  }}
}}
Ответь ТОЛЬКО валидным JSON без markdown-оберток.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_INSTRUCTION}\n\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        }
    }

    valid_result = None
    for m_name in target_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={api_key}"
        try:
            logger.info(f"Invoking Gemini model: {m_name}...")
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                result = json.loads(raw_text)
                if result and "macro_briefing" in result:
                    result.setdefault("hotel_dossiers", result.get("dossiers", {}))
                    result["macro_briefing"]["synthesized_by"] = f"Google Gemini ({m_name})"
                    logger.info(f"✓ Gemini ({m_name}) successfully generated AI market analysis.")
                    valid_result = result
                    break
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")[:180]
            logger.warning(f"Gemini call with {m_name} failed: HTTP {he.code} - {err_body}. Trying next model/fallback...")
        except Exception as e:
            logger.warning(f"Gemini call with {m_name} failed: {e}. Trying next model/fallback...")

    if not valid_result:
        return None

    try:
        return enrich_oracle_report_with_smart_features(valid_result, market_context)
    except Exception as e:
        logger.error(f"Error enriching oracle report with smart features: {e}")
        return valid_result


def fetch_available_openai_models(api_key: str) -> List[str]:
    """Queries GET https://api.openai.com/v1/models to discover exact model IDs available to this API key."""
    try:
        url = "https://api.openai.com/v1/models"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "TravelPriceMonitor/1.0",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_ids = [m["id"] for m in data.get("data", []) if "id" in m]
            chat_models = [m for m in raw_ids if any(m.startswith(p) for p in ("gpt-4o", "gpt-4", "o1", "o3", "chatgpt"))]
            if chat_models:
                logger.info(f"OpenAI account models discovered ({len(chat_models)}): {', '.join(chat_models[:6])}")
            return chat_models
    except Exception as e:
        logger.debug(f"Could not auto-discover OpenAI models via /v1/models: {e}")
        return []


def call_openai_oracle(
    market_context: Dict[str, Any],
    api_key: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Invokes OpenAI Chat Completions API with dynamic model discovery and JSON mode.
    """
    target_models = []
    explicit_model = model or os.getenv("OPENAI_MODEL")
    if explicit_model:
        target_models.append(explicit_model)
        # At most 1 fallback if explicit model fails with HTTP error
        fallback = "gpt-4o-mini"
        if explicit_model != fallback and fallback not in target_models:
            target_models.append(fallback)
    else:
        target_models = ["gpt-4o-mini"]

    llm_context = {
        "filter_id": market_context.get("filter_id"),
        "filter_title": market_context.get("filter_title"),
        "analyzed_at": market_context.get("analyzed_at"),
        "market_stats": market_context.get("market_stats"),
        "market_trends": market_context.get("market_trends", {}),
        "airports_comparison": market_context.get("airports_comparison", {}),
        "duration_comparison": market_context.get("duration_comparison", {}),
        "floor_saturation": market_context.get("floor_saturation"),
        "top_candidates": market_context.get("top_candidates", []),
        "arbitrage_highlights": market_context.get("arbitrage_highlights", []),
        "gems": market_context.get("gems", []),
        "flash_drops": market_context.get("flash_drops", []),
    }
    if market_context.get("early_booking"):
        llm_context["early_booking"] = market_context.get("early_booking")

    is_deep = os.getenv("AI_ANALYSIS_MODE", "standard").lower() == "full_deep"
    if is_deep:
        if market_context.get("all_hotels_catalog"):
            llm_context["all_hotels_catalog"] = market_context.get("all_hotels_catalog", [])
        deep_note = "\nРЕЖИМ: FULL DEEP (полный глубокий прогон через AI). Тебе переданы ВСЕ отели и кандидаты данного направления. Проведи полный всесторонний разбор рынка и отбери лучших кандидатов для покупки из всего каталога."
    else:
        deep_note = ""

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров направления "{market_context.get('filter_title', '')}" и выдай краткое экспертное резюме в формате JSON:{deep_note}

ВХОДНЫЕ ДАННЫЕ РЫНКА (МАКРО-СТАТИСТИКА И ТОП-КАНДИДАТЫ):
{json.dumps(llm_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Честный краткий заголовок ситуации строго по реальным данным min_days_to_departure и nearest_departure_date (СТРОГО БЕЗ названий файлов, slug или filter_id)",
    "market_phase": "Фаза рынка: если вылет сегодня (0 дн.) — 'Срочные вылеты сегодня' (при широком окне: 'Срочные вылеты сегодня и даты до DD.MM'); если вылет нескоро — 'Раннее бронирование за X дн.'; если через 1–7 дн. — 'Горящие туры за X дн.'",
    "charter_dynamics": "2-3 простых понятных предложения с цифрами о ценах и рейсах, обязательно с точной страной из destination_context и длительностью (например: туры на 8–9 ночей в Египет...). При вылетах сегодня обязательно укажи дату следующего спокойного рейса (next_realistic_departure_date)",
    "floor_status": "Сколько отелей сейчас на самом дне цены (например: 'Лишь 4% отелей на минимуме...')",
    "strategic_directive": "Простой четкий совет: кому брать тур прямо сейчас (если вылет сегодня — только на чемоданах; для остальных указать next_realistic_departure_date), а кому лучше подождать",
    "buy_now_recommendation": {{
      "has_worthy_deals": true,
      "headline": "Стоит выбрать из этих вариантов: (или: 'Лучше ничего не покупать — подождите')",
      "advice": "Короткий живой совет туристу (никогда не называй непроверенные отели с 0 отзывов проверенными!)",
      "top_picks": [
        {{ "hotel_name": "Точное имя отеля из top_candidates СТРОГО с rating >= 4.0", "price": 1234.0, "badge": "⚡ Сброс цены / 💎 Жемчужина", "why_buy": "Краткое обоснование с цифрами" }}
      ]
    }},
    "key_anomalies": [
      {{ "type": "drop|arbitrage|overprice|duration", "title": "...", "text": "..." }}
    ]
  }}
}}
Ответь ТОЛЬКО валидным JSON без markdown-оберток.
"""

    valid_result = None
    for target_model in target_models:
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        # Newer reasoning and next-gen models (gpt-5*, gpt-6*, o1, o3) only support default temperature (1.0).
        # Supplying temperature=0.2 causes OpenAI HTTP 400 invalid_request_error: unsupported_value.
        if not any(target_model.startswith(p) for p in ("gpt-5", "gpt-6", "o1", "o3")):
            payload["temperature"] = 0.2

        try:
            url = "https://api.openai.com/v1/chat/completions"
            logger.info(f"Invoking OpenAI model: {target_model}...")
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["choices"][0]["message"]["content"].strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                result = json.loads(raw_text)
                if result and "macro_briefing" in result:
                    result.setdefault("hotel_dossiers", result.get("dossiers", {}))
                    result["macro_briefing"]["synthesized_by"] = f"OpenAI ({target_model})"
                    logger.info(f"✓ OpenAI ({target_model}) successfully generated AI market analysis.")
                    valid_result = result
                    break
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")[:180]
            logger.warning(f"OpenAI call with {target_model} failed: HTTP {he.code} - {err_body}.")
        except Exception as e:
            logger.warning(f"OpenAI call with {target_model} failed: {e}.")

    if not valid_result:
        return None

    # Post-processing runs strictly OUTSIDE the LLM loop
    try:
        return enrich_oracle_report_with_smart_features(valid_result, market_context)
    except Exception as e:
        logger.error(f"Error enriching oracle report with smart features: {e}")
        return valid_result


def synthesize_market_oracle(
    prices_csv_path: str,
    dna_profile_path: str = "market_dna_profile.json",
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    api_key: Optional[str] = None,
    filter_title: Optional[str] = None,
    filter_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main orchestration function: extracts features and generates two-tier AI intelligence.
    Supports OpenAI (gpt-5.4-mini / gpt-5.6-luna / gpt-4o-mini), Google Gemini (gemini-2.0-flash / gemini-1.5-flash),
    and deterministic Rule-Based Fallback.
    """
    market_context = extract_filter_features(
        prices_csv_path,
        dna_profile_path=dna_profile_path,
        filter_title=filter_title,
        filter_id=filter_id,
    )
    if "error" in market_context:
        return market_context

    provider_pref = os.getenv("LLM_PROVIDER", "").lower()

    # Resolve keys and backwards-compatible api_key alias
    if api_key:
        if api_key.startswith("sk-"):
            openai_api_key = openai_api_key or api_key
        else:
            gemini_api_key = gemini_api_key or api_key

    # 1. Check OpenAI
    oai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    gem_key = gemini_api_key or os.getenv("GEMINI_API_KEY")


    if provider_pref == "openai" and oai_key:
        logger.info("Invoking OpenAI API as preferred provider...")
        res = call_openai_oracle(market_context, oai_key)
        if res:
            return res

    # 2. Check Gemini
    if gem_key:
        logger.info("Invoking Gemini API for market intelligence...")
        res = call_gemini_oracle(market_context, gem_key)
        if res:
            return res

    # 3. Fallback to OpenAI if Gemini was not preferred or failed
    if oai_key:
        logger.info("Invoking OpenAI API for market intelligence...")
        res = call_openai_oracle(market_context, oai_key)
        if res:
            return res

    logger.info("Using Rule-Based Intelligence Engine fallback.")
    return generate_rule_based_briefing(market_context)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI Market Oracle intelligence report.")
    parser.add_argument("--csv", required=True, help="Path to travel_prices.csv")
    parser.add_argument("--dna", default="market_dna_profile.json", help="Path to market_dna_profile.json")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    oracle_report = synthesize_market_oracle(args.csv, dna_profile_path=args.dna)
    out_json = json.dumps(oracle_report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"Report saved to {args.output}")
    else:
        print(out_json)


if __name__ == "__main__":
    main()

