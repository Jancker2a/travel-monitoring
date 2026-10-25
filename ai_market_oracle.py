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
4. ЕСЛИ В ПОДБОРКЕ РАЗНЫЕ ДАТЫ ВЫЛЕТА (например, на месяц вперед):
   - Разделяй ближайшие и дальние даты: на ближайшие дни туроператоры уже «горят» и отдают туры дешевле, а на дальние даты цены пока обычные, можно спокойно выбирать.
   - Поясни, что подборка «живая» и обновляется каждый день по мере приближения вылетов.
5. РЕКОМЕНДАЦИЯ «ЕСЛИ ПОКУПАТЬ СЕЙЧАС» (поле buy_now_recommendation):
   - Если на рынке есть 1-2 реально выгодных предложения (сброс цены, дно сезона, жемчужина) — укажи has_worthy_deals: true, заголовок «Стоит выбрать из этих вариантов:» и перечисли их с понятным объяснением, почему брать.
   - Если же на рынке ВСЕ варианты средние, плохие или переоценены — укажи has_worthy_deals: false, заголовок «Лучше ничего не покупать — подождите», и объясни, почему сейчас не время для покупки.
6. ФОРМАТ ОТВЕТА: строго валидный JSON без markdown-разметки.
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

    # Human-friendly phase descriptions and advice
    if is_wide_window:
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

    dossiers: Dict[str, Dict[str, Any]] = {}
    hotels_to_process = market_context.get("all_hotel_intelligence") or {
        h["hotel_name"]: h for h in market_context.get("selected_hotel_dossiers", [])
    }

    for h_name, h in hotels_to_process.items():
        cur_p = h.get("current_price", 0.0)
        hist_min = h.get("historical_min", cur_p)
        quantile = h.get("quantile_in_filter", 0.5)
        flash = h.get("flash_drop", {})

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
        elif quantile <= 0.25:
            verdict = "GOOD_PRICE"
            verdict_badge = "🔵 ХОРОШАЯ ЦЕНА"
            rationale = f"Цена {cur_p:,.0f} zł заметно ниже средней по рынку на эти даты."
            risk = "Цена может слегка колебаться, но предложение уже достаточно выгодное."
            advice = "Можно брать, если даты и отель полностью вас устраивают."
        else:
            verdict = "WAIT"
            verdict_badge = "🟡 ПОДОЖДАТЬ"
            rationale = f"Отель сейчас стоит {cur_p:,.0f} zł — это обычная средняя цена. По опыту, перед вылетом туроператор часто делает скидки."
            risk = "Если купить сейчас, есть риск переплатить 300–600 zł."
            advice = "Если вылет не горит — добавьте в Избранное (☆) и подождите снижения цены ближе к вылету."

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
            h["hotel_name"]: h for h in market_context.get("selected_hotel_dossiers", [])
        }

    scored_candidates = []
    for h_name, h_info in all_intel.items():
        cur_p = float(h_info.get("current_price", 0.0) or 0.0)
        if cur_p <= 0:
            continue

        hist_min = float(h_info.get("historical_min", cur_p) or cur_p)
        flash = h_info.get("flash_drop", {})
        gem = h_info.get("gem", {})
        bw = h_info.get("booking_window", {})
        fp = h_info.get("fair_price", {})
        dossier = dossiers.get(h_name, {})
        verdict = dossier.get("verdict", "")

        # Исключаем заведомо переоценённые варианты
        if verdict == "OVERPRICED" or fp.get("class") == "expensive":
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

        # 3. Скидка к рыночной медиане (Fair Price Index)
        diff_pct = fp.get("diff_pct", 0)
        if diff_pct <= -12:
            score += abs(diff_pct) * 2.5
            if not best_badge:
                st = fp.get("stars", 4)
                best_badge = f"💎 {diff_pct:.0f}% к рынку {st}★"
            reasons.append(f"на {abs(diff_pct):.0f}% дешевле похожих отелей")
            has_real_catalyst = True

        # 4. Идеальное окно покупки по истории
        if bw.get("window_class") in ("panic", "last"):
            score += 60
            if not best_badge:
                best_badge = f"🎯 {bw.get('window_label', 'Окно покупки')}"
            reasons.append(f"идеальное окно покупки ({bw.get('window_label', '')})")
            has_real_catalyst = True

        # 5. Реальное дно сезона (только если есть подтвержденная история и заметный спад)
        hist_max = float(h_info.get("historical_max", cur_p) or cur_p)
        if cur_p <= hist_min * 1.01 and hist_max >= cur_p * 1.08:
            score += 50
            reasons.append(f"цена на дне сезона (−{((hist_max - cur_p)/hist_max)*100:.0f}% от пика)")
            has_real_catalyst = True

        rating = float(h_info.get("rating", 0.0) or 0.0)
        if rating >= 4.0:
            score += (rating - 4.0) * 15

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
        return {
            "has_worthy_deals": False,
            "headline": "Лучше ничего не покупать — подождите",
            "status_badge": "✋ ВЫГОДНЫХ СДЕЛОК НЕТ",
            "advice": "Сейчас на рынке нет действительно выгодных предложений: отели продаются по базовым или завышенным ценам. Спешить с бронированием нет смысла — сохраните отели в «Избранное» (☆) и подождите приближения вылета (за 7–10 дней туроператоры обычно начинают снижать цены).",
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
        cur_d = dossiers.setdefault(h_name, {
            "verdict": "GOOD_PRICE",
            "badge_text": "🔵 ХОРОШАЯ ЦЕНА",
            "rationale": f"Цена {h_info.get('current_price', 0):,.0f} zł на актуальные даты.",
            "risk_assessment": "Места доступны для бронирования.",
            "action_advice": "Ориентируйтесь на ваши планы поездки.",
        })

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
            existing_anomalies.append({
                "type": "gem",
                "title": f"💎 Скрытая жемчужина: {g['hotel_name']}",
                "text": f"Высокий рейтинг {g.get('rating', 4.5):g}★ в категории {g.get('stars', 5)}★ всего за {g['price']:,.0f} zł (намного дешевле похожих отелей)."
            })

    # 6. Buy Now Recommendation
    if "buy_now_recommendation" not in macro or not macro["buy_now_recommendation"].get("top_picks"):
        macro["buy_now_recommendation"] = compute_buy_now_recommendation(market_context, dossiers)

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

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров и выдай понятное экспертное заключение простым языком для обычного туриста в формате JSON:

ВХОДНЫЕ ДАННЫЕ РЫНКА:
{json.dumps(market_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Короткий живой заголовок ситуации (СТРОГО БЕЗ названий файлов, slug или filter_id. Пример: 'На ближайшие даты цены падают, на дальние — стабильны')",
    "market_phase": "Понятная фаза (например: Горящие туры через 6 дн. или Спокойный выбор за месяц до вылета)",
    "charter_dynamics": "2-3 простых понятных предложения с цифрами о ценах и рейсах",
    "floor_status": "Сколько отелей сейчас на самом дне цены",
    "strategic_directive": "Простой четкий совет: кому брать тур прямо сейчас, а кому лучше подождать",
    "buy_now_recommendation": {{
      "has_worthy_deals": true,
      "headline": "Стоит выбрать из этих вариантов: (или: 'Лучше ничего не покупать — подождите')",
      "advice": "Короткий живой совет туристу",
      "top_picks": [
        {{ "hotel_name": "...", "badge": "⚡ Сброс цены / 💎 Жемчужина", "why_buy": "..." }}
      ]
    }},
    "key_anomalies": [
      {{ "type": "drop|arbitrage|overprice", "title": "...", "text": "..." }}
    ]
  }},
  "hotel_dossiers": {{
    "<ИМЯ_ОТЕЛЯ>": {{
      "verdict": "BUY_NOW | GOOD_PRICE | WAIT | OVERPRICED",
      "badge_text": "🟢 ПОКУПАТЬ | 🔵 ХОРОШАЯ ЦЕНА | 🟡 ПОДОЖДАТЬ | 🔴 ДОРОГО",
      "rationale": "Простое понятное объяснение с цифрами",
      "risk_assessment": "Понятный риск: быстро ли разбирают номера",
      "action_advice": "Четкий совет: брать сейчас или подождать"
    }}
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
            "responseMimeType": "application/json",
        }
    }

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
                if result and "macro_briefing" in result and "hotel_dossiers" in result:
                    result["macro_briefing"]["synthesized_by"] = f"Google Gemini ({m_name})"
                    logger.info(f"✓ Gemini ({m_name}) successfully generated AI market analysis.")
                    return enrich_oracle_report_with_smart_features(result, market_context)
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")[:180]
            logger.warning(f"Gemini call with {m_name} failed: HTTP {he.code} - {err_body}. Trying next model/fallback...")
        except Exception as e:
            logger.warning(f"Gemini call with {m_name} failed: {e}. Trying next model/fallback...")

    return None


def call_openai_oracle(
    market_context: Dict[str, Any],
    api_key: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Invokes OpenAI Chat Completions API (e.g. gpt-4o-mini, gpt-4o) with JSON mode.
    """
    import re

    candidates = [
        model,
        os.getenv("OPENAI_MODEL"),
        "gpt-5.6-luna",
        "gpt-5-luna",
        "gpt-6-luna",
        "gpt-4o-mini",
        "gpt-6.1-sol",
        "gpt-4o",
    ]
    target_models = []
    for c in candidates:
        if c and c not in target_models:
            target_models.append(c)

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров и выдай понятное экспертное заключение простым языком для обычного туриста в формате JSON:

ВХОДНЫЕ ДАННЫЕ РЫНКА:
{json.dumps(market_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Короткий живой заголовок ситуации (СТРОГО БЕЗ названий файлов, slug или filter_id. Пример: 'На ближайшие даты цены падают, на дальние — стабильны')",
    "market_phase": "Понятная фаза (например: Горящие туры через 6 дн. или Спокойный выбор за месяц до вылета)",
    "charter_dynamics": "2-3 простых понятных предложения с цифрами о ценах и рейсах",
    "floor_status": "Сколько отелей сейчас на самом дне цены",
    "strategic_directive": "Простой четкий совет: кому брать тур прямо сейчас, а кому лучше подождать",
    "buy_now_recommendation": {{
      "has_worthy_deals": true,
      "headline": "Стоит выбрать из этих вариантов: (или: 'Лучше ничего не покупать — подождите')",
      "advice": "Короткий живой совет туристу",
      "top_picks": [
        {{ "hotel_name": "...", "badge": "⚡ Сброс цены / 💎 Жемчужина", "why_buy": "..." }}
      ]
    }},
    "key_anomalies": [
      {{ "type": "drop|arbitrage|overprice", "title": "...", "text": "..." }}
    ]
  }},
  "hotel_dossiers": {{
    "<ИМЯ_ОТЕЛЯ>": {{
      "verdict": "BUY_NOW | GOOD_PRICE | WAIT | OVERPRICED",
      "badge_text": "🟢 ПОКУПАТЬ | 🔵 ХОРОШАЯ ЦЕНА | 🟡 ПОДОЖДАТЬ | 🔴 ДОРОГО",
      "rationale": "Простое понятное объяснение с цифрами",
      "risk_assessment": "Понятный риск: быстро ли разбирают номера",
      "action_advice": "Четкий совет: брать сейчас или подождать"
    }}
  }}
}}
Ответь ТОЛЬКО валидным JSON без markdown-оберток.
"""

    for target_model in target_models:
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

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
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["choices"][0]["message"]["content"].strip()
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                result = json.loads(raw_text)
                if result and "macro_briefing" in result and "hotel_dossiers" in result:
                    result["macro_briefing"]["synthesized_by"] = f"OpenAI ({target_model})"
                    logger.info(f"✓ OpenAI ({target_model}) successfully generated AI market analysis.")
                    return enrich_oracle_report_with_smart_features(result, market_context)
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")[:180]
            logger.warning(f"OpenAI call with {target_model} failed: HTTP {he.code} - {err_body}. Trying next model/fallback...")
        except Exception as e:
            logger.warning(f"OpenAI call with {target_model} failed: {e}. Trying next model/fallback...")

    return None


def synthesize_market_oracle(
    prices_csv_path: str,
    dna_profile_path: str = "market_dna_profile.json",
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    api_key: Optional[str] = None,
    filter_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main orchestration function: extracts features and generates two-tier AI intelligence.
    Supports OpenAI (gpt-5.6-luna / gpt-4o-mini), Google Gemini (gemini-2.0-flash / gemini-1.5-flash),
    and deterministic Rule-Based Fallback.
    """
    market_context = extract_filter_features(
        prices_csv_path,
        dna_profile_path=dna_profile_path,
        filter_title=filter_title,
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

