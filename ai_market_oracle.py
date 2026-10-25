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
Ты — старший тревел-брокер и количественный аналитик пакетного туризма с 10-летним опытом.
Твоя задача — проанализировать предоставленные данные по рынку туров и составить жесткий,
практичный и полезный аналитический отчет.

ПРАВИЛА И СТИЛЬ:
1. НИКАКОЙ ВОДЫ И ОБЩИХ ФРАЗ. Запрещено писать "Турция - прекрасная страна" или "цены могут измениться".
2. КАЖДЫЙ ТЕЗИС ОБЯЗАН ОПИРАТЬСЯ НА ЦИФРЫ: дни до вылета, цены в злотых (zł), проценты (%), конкретные отели.
3. ОЦЕНИВАЙ АСИММЕТРИЮ РИСКА: ожидание сброса чартера имеет смысл ТОЛЬКО если потенциал экономии превышает риск ухода отеля в Stop-Sale.
4. Отвечай на русском языке строго в формате валидного JSON.
5. АНАЛИЗ ВЫЛЕТОВ И СКОЛЬЗЯЩИХ ОКОН:
   Если в фильтре широкий диапазон вылетов (например, на месяц вперёд, is_wide_window=True), КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО усреднять "вылеты через X дней" на весь пул!
   Обязательно разделяй:
   - Ближайшие вылеты (стартуют через min_days_to_departure дней): оценивай горящий сброс чартеров и риск Stop-Sale для первых дат.
   - Дальние вылеты окна (через max_days_to_departure дней): объясняй, что они на ценовом плато и спешить не нужно.
   - Учитывай, что окно фильтра скользящее: по мере прохождения ближайших дат окно автоматически смещается дальше.
"""


def generate_rule_based_briefing(market_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback deterministic synthesizer for offline or zero-key environments.
    Produces high-quality, data-grounded insights using structured rule heuristics.
    """
    stats = market_context.get("market_stats", {})
    floor = market_context.get("floor_saturation", {})
    hotel_count = stats.get("hotel_count", 0)
    med_price = stats.get("median_price", 0.0)
    min_price = stats.get("min_price", 0.0)
    p10_price = stats.get("p10_price", 0.0)
    avg_d = stats.get("median_days_to_departure", 14)
    phase = stats.get("dominant_yield_phase", "mid_term")
    floor_pct = floor.get("floor_breaker_pct", 0.0)
    floor_count = floor.get("floor_breaker_count", 0)

    min_d = stats.get("min_days_to_departure", avg_d)
    max_d = stats.get("max_days_to_departure", avg_d)
    span_d = stats.get("departure_span_days", 0)
    is_wide_window = stats.get("is_wide_window", False)
    nearest_dep = stats.get("nearest_departure_date", "")
    furthest_dep = stats.get("furthest_departure_date", "")
    dep_label = f" ({nearest_dep})" if nearest_dep else ""

    # Determine phase narrative based on departure window
    if is_wide_window:
        if min_d <= 7:
            phase_title = f"Скользящее окно: ближайшие через {min_d} дн."
            phase_desc = (
                f"Ближайшие вылеты стартуют уже через {min_d} дн. ({nearest_dep}), а дальний край окна охватывает даты до {furthest_dep} ({max_d} дн.). "
                f"По ближайшим рейсам туроператоры уже ведут сброс остатков кресел, тогда как основной массив на дальние даты находится на стабильном плато (медиана {med_price:,.0f} zł). "
                f"Когда рейсы на {nearest_dep} вылетят, окно автоматически сместится к следующим датам."
            )
            directive = (
                f"Дифференцированная тактика: для вылетов в ближайшие {min_d}–7 дней фиксируйте предложения на историческом дне. "
                f"Для дат через {avg_d}+ дней спешки нет — держите отели на контроле до D-14."
            )
            headline = f"Горизонт {nearest_dep}–{furthest_dep}: ближайшие рейсы через {min_d} дн., дальние на плато"
        else:
            phase_title = f"Плато скользящего окна ({nearest_dep}–{furthest_dep})"
            phase_desc = (
                f"Ближайшие вылеты в фильтре стартуют через {min_d} дн. ({nearest_dep}), дальний край окна — через {max_d} дн. ({furthest_dep}). "
                f"Вся выборка находится на комфортном плато раннего набора со средней ценой {med_price:,.0f} zł. "
                f"По мере приближения дат окно будет смещаться вперед."
            )
            directive = (
                f"Спешки нет. Для вылетов на {nearest_dep} окно оптимизации наступит за 10–14 дней до старта. "
                f"Для дальних дат ({furthest_dep}) имеет смысл бронировать только знаковые 5★ с дефицитом мест."
            )
            headline = f"Горизонт {nearest_dep}–{furthest_dep}: плато цен, достаточный запас времени"
    else:
        if min_d <= 3:
            phase_title = f"Зона Last Minute (вылет через {min_d} дн.)"
            phase_desc = f"Ближайшие вылеты через {min_d} дн.{dep_label}. Чартерные блоки практически закрыты. Отели либо сбрасывают последние кресла с максимальным дисконтом, либо уходят в Stop-Sale."
            directive = "Бронировать немедленно при наличии мест. Ожидание даже нескольких часов чревато отменой предложения."
            headline = f"Зона Last Minute: вылет через {min_d} дн., финальная зачистка мест"
        elif min_d <= 7:
            phase_title = f"Чартерный демпинг (вылет через {min_d} дн.)"
            phase_desc = f"Ближайшие вылеты через {min_d} дн.{dep_label}. Туроператоры активно сбрасывают нераспроданные блоки кресел. Медиана рынка держится на уровне {med_price:,.0f} zł."
            directive = f"Рекомендуется выкуп для {floor_count} отелей на историческом дне. Для остальных — наблюдать до D-3."
            headline = f"Чартерный демпинг: вылет через {min_d} дн., время выгодных сделок"
        elif min_d <= 14:
            phase_title = f"Первая волна зачистки (вылет через {min_d} дн.)"
            phase_desc = f"Ближайшие вылеты через {min_d} дн.{dep_label}. Стартовал первый этап оптимизации доходности туроператоров (Yield Clearance). Нижний дециль отелей доступен от {p10_price:,.0f} zł."
            directive = "Хорошее окно для бронирования качественных 5★ с детьми. Риск дальнейшего ожидания не оправдывает потенциал экономии в 150–200 zł."
            headline = f"Первая волна зачистки: вылет через {min_d} дн., баланс цены и мест"
        else:
            phase_title = f"Плато бронирования (вылет через {min_d} дн.)"
            phase_desc = f"Ближайшие вылеты через {min_d} дн.{dep_label}. Цены стабилизировались. Медиана предложения: {med_price:,.0f} zł. Агрессивного демпинга не наблюдается."
            directive = "Спешки нет. Можно зафиксировать отели с ценой ниже нижнего дециля или ждать входа в интервал D-14."
            headline = f"Плато раннего бронирования: вылет через {min_d} дн., стабильный коридор"

    # Top anomalies
    anomalies: List[Dict[str, str]] = []
    if floor_count > 0:
        anomalies.append({
            "type": "floor",
            "title": f"Ценовое дно: {floor_count} отелей ({floor_pct}%)",
            "text": f"Зафиксирован исторический минимум стоимости. Минимальный входной билет: {min_price:,.0f} zł."
        })

    # Dossiers for selected hotels
    dossiers: Dict[str, Dict[str, Any]] = {}
    for h in market_context.get("selected_hotel_dossiers", []):
        h_name = h.get("hotel_name")
        cur_p = h.get("current_price", 0.0)
        hist_min = h.get("historical_min", cur_p)
        quantile = h.get("quantile_in_filter", 0.5)
        archetype = h.get("archetype", "BALANCED")

        if cur_p <= hist_min * 1.02:
            verdict = "BUY_NOW"
            verdict_badge = "🟢 BUY NOW"
            rationale = f"Текущая цена {cur_p:,.0f} zł находится на абсолютном историческом дне сезона (квантиль {int(quantile*100)}%)."
            risk = "Риск sold-out и обратного отскока превышает 80%. Потенциал дальнейшего падения минимален (< 120 zł)."
            advice = "Фиксировать бронь сегодня. Лучшая точка входа в текущем цикле."
        elif quantile <= 0.25:
            verdict = "GOOD_PRICE"
            verdict_badge = "🔵 ХОРОШАЯ ЦЕНА"
            rationale = f"Цена {cur_p:,.0f} zł ниже 75% конкурентных предложений на эти даты."
            risk = "Умеренный риск изменения цены. Возможен сброс еще на 3-5% при приближении к D-7."
            advice = "Брать, если даты вылета строго зафиксированы."
        else:
            verdict = "WAIT"
            verdict_badge = "🟡 ЖДАТЬ"
            rationale = f"Текущая цена {cur_p:,.0f} zł находится в среднем ценовом сегменте. Поведение отеля ({archetype}) предполагает сброс ближе к вылету."
            risk = "Переплата при покупке сегодня: до 400–600 zł."
            advice = f"Ждать целевой отметки ~{cur_p * 0.92:,.0f} zł. Ставить контрольную точку за 7 дней до вылета."

        dossiers[h_name] = {
            "verdict": verdict,
            "badge_text": verdict_badge,
            "rationale": rationale,
            "risk_assessment": risk,
            "action_advice": advice,
        }

    clean_filter_title = market_context.get("filter_title") or ""

    return {
        "macro_briefing": {
            "headline": headline,
            "market_phase": phase_title,
            "filter_title": clean_filter_title,
            "charter_dynamics": phase_desc,
            "floor_status": f"{floor_count} отелей ({floor_pct}%) торгуются на сезонном минимуме.",
            "strategic_directive": directive,
            "key_anomalies": anomalies,
            "synthesized_by": "Rule-Based Deterministic Engine (Offline)",
        },
        "hotel_dossiers": dossiers,
    }


def call_gemini_oracle(
    market_context: Dict[str, Any],
    api_key: str,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Invokes Google Gemini API with strict JSON schema.
    Defaults to 'gemini-3.7-flash' with fallback to 'gemini-2.0-flash' and 'gemini-1.5-flash'.
    """
    target_models = [model] if model else [os.getenv("GEMINI_MODEL", "gemini-3.7-flash"), "gemini-2.0-flash", "gemini-1.5-flash"]

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров и выдай экспертное заключение в формате JSON:

ВХОДНЫЕ ДАННЫЕ РЫНКА:
{json.dumps(market_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Яркий ёмкий аналитический заголовок ситуации на рынке (СТРОГО БЕЗ названий файлов, slug или filter_id. Пример: 'Плато раннего бронирования: цены стабильны, окно для фиксации лидеров')",
    "market_phase": "Название фазы (например: Чартерная зачистка D-11)",
    "charter_dynamics": "2-3 предложения с цифрами о поведении цен операторов",
    "floor_status": "Сводка по отелям на дне цены",
    "strategic_directive": "Четкая рекомендация: кому брать сейчас, кому ждать",
    "key_anomalies": [
      {{ "type": "drop|arbitrage|overprice", "title": "...", "text": "..." }}
    ]
  }},
  "hotel_dossiers": {{
    "<ИМЯ_ОТЕЛЯ>": {{
      "verdict": "BUY_NOW | GOOD_PRICE | WAIT | OVERPRICED",
      "badge_text": "🟢 BUY NOW | 🔵 ХОРОШАЯ ЦЕНА | 🟡 ЖДАТЬ | 🔴 ОВЕРПРАЙС",
      "rationale": "Конкретное обоснование с цифрами",
      "risk_assessment": "Анализ риска sold-out vs потенциал экономии",
      "action_advice": "Точная инструкция к действию"
    }}
  }}
}}
Ответь ТОЛЬКО валидным JSON без markdown оберток.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": SYSTEM_INSTRUCTION},
                    {"text": user_prompt}
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
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                result = json.loads(raw_text)
                result["macro_briefing"]["synthesized_by"] = f"Google Gemini ({m_name})"
                return result
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
    target_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    url = "https://api.openai.com/v1/chat/completions"

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров и выдай экспертное заключение в формате JSON:

ВХОДНЫЕ ДАННЫЕ РЫНКА:
{json.dumps(market_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Яркий ёмкий аналитический заголовок ситуации на рынке (СТРОГО БЕЗ названий файлов, slug или filter_id. Пример: 'Плато раннего бронирования: цены стабильны, окно для фиксации лидеров')",
    "market_phase": "Название фазы (например: Чартерная зачистка D-11)",
    "charter_dynamics": "2-3 предложения с цифрами о поведении цен операторов",
    "floor_status": "Сводка по отелям на дне цены",
    "strategic_directive": "Четкая рекомендация: кому брать сейчас, кому ждать",
    "key_anomalies": [
      {{ "type": "drop|arbitrage|overprice", "title": "...", "text": "..." }}
    ]
  }},
  "hotel_dossiers": {{
    "<ИМЯ_ОТЕЛЯ>": {{
      "verdict": "BUY_NOW | GOOD_PRICE | WAIT | OVERPRICED",
      "badge_text": "🟢 BUY NOW | 🔵 ХОРОШАЯ ЦЕНА | 🟡 ЖДАТЬ | 🔴 ОВЕРПРАЙС",
      "rationale": "Конкретное обоснование с цифрами",
      "risk_assessment": "Анализ риска sold-out vs потенциал экономии",
      "action_advice": "Точная инструкция к действию"
    }}
  }}
}}
Ответь ТОЛЬКО валидным JSON без markdown оберток.
"""

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
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["choices"][0]["message"]["content"]
            result = json.loads(raw_text)
            result["macro_briefing"]["synthesized_by"] = f"OpenAI ({target_model})"
            return result
    except Exception as e:
        logger.warning(f"OpenAI call with {target_model} failed: {e}. Falling back...")
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
    Supports OpenAI (gpt-4o / gpt-4o-mini), Google Gemini (gemini-2.0-flash / gemini-1.5-flash),
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

