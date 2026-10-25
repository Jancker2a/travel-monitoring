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

    # Determine phase narrative
    if phase == "last_minute" or avg_d <= 3:
        phase_title = "Зона Last Minute (D ≤ 3)"
        phase_desc = f"До вылета осталось менее 3 дней. Чартерные блоки практически закрыты. Отели либо сбрасывают последние кресла с максимальным дисконтом, либо уходят в Stop-Sale."
        directive = "Бронировать немедленно при наличии мест. Ожидание даже нескольких часов чревато полной отменой предложения."
    elif phase == "panic_dump" or avg_d <= 7:
        phase_title = "Чартерный демпинг второй волны (D-7)"
        phase_desc = f"До вылета в среднем {avg_d} дн. Туроператоры активно сбрасывают нераспроданные блоки кресел. Медиана рынка держится на уровне {med_price:,.0f} zł."
        directive = f"Рекомендуется выкуп для {floor_count} отелей на историческом дне. Для остальных — наблюдать до D-3."
    elif phase == "first_markdown" or avg_d <= 14:
        phase_title = "Первая волна чартерной зачистки (D-14)"
        phase_desc = f"До вылета {avg_d} дн. Стартовал первый этап оптимизации доходности туроператоров (Yield Clearance). Нижний дециль отелей доступен от {p10_price:,.0f} zł."
        directive = "Хорошее окно для бронирования качественных 5★ с детьми. Риск дальнейшего ожидания не оправдывает потенциал экономии в 150–200 zł."
    else:
        phase_title = "Плато раннего бронирования"
        phase_desc = f"Вылеты через {avg_d} дн. Цены стабилизировались. Медиана предложения: {med_price:,.0f} zł. Агрессивного демпинга не наблюдается."
        directive = "Спешки нет. Можно зафиксировать отели с ценой ниже нижнего дециля или ждать входа в интервал D-14."

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

    return {
        "macro_briefing": {
            "headline": f"{market_context.get('filter_id')}: {phase_title}",
            "market_phase": phase_title,
            "charter_dynamics": phase_desc,
            "floor_status": f"{floor_count} отелей ({floor_pct}%) торгуются на сезонном минимуме.",
            "strategic_directive": directive,
            "key_anomalies": anomalies,
            "synthesized_by": "Rule-Based Deterministic Engine (Offline)",
        },
        "hotel_dossiers": dossiers,
    }


def call_gemini_oracle(market_context: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
    """
    Invokes Google Gemini 1.5 Flash via REST API with strict JSON schema.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    user_prompt = f"""
Проанализируй сжатые метрики рынка пакетных туров и выдай экспертное заключение в формате JSON:

ВХОДНЫЕ ДАННЫЕ РЫНКА:
{json.dumps(market_context, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ К ФОРМАТУ JSON:
{{
  "macro_briefing": {{
    "headline": "Яркий емкий заголовок ситуации на рынке",
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

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(raw_text)
            result["macro_briefing"]["synthesized_by"] = "Google Gemini 1.5 Flash (AI Market Oracle)"
            return result
    except Exception as e:
        logger.warning(f"Gemini API call failed: {e}. Falling back to rule-based engine.")
        return None


def synthesize_market_oracle(
    prices_csv_path: str,
    dna_profile_path: str = "market_dna_profile.json",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main orchestration function: extracts features and generates two-tier AI intelligence.
    """
    market_context = extract_filter_features(prices_csv_path, dna_profile_path=dna_profile_path)
    if "error" in market_context:
        return market_context

    gemini_key = api_key or os.getenv("GEMINI_API_KEY")
    if gemini_key:
        logger.info("Invoking Gemini 1.5 Flash API for market intelligence...")
        res = call_gemini_oracle(market_context, gemini_key)
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
