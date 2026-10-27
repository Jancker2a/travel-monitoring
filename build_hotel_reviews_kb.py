#!/usr/bin/env python3
"""
Weekly Hotel Reviews & Reputation Knowledge Base Builder.

Periodically collects, analyzes, and synthesizes deep hotel reputation intelligence
across all monitored package tour destinations (Egypt, Turkey, Cyprus, Greece, etc.):
1. Season Trends: Which hotels improved or degraded over the recent season (renovations, management changes).
2. Family & Kids Suitability: Beach entry slope, kids clubs, heated aquaparks.
3. Winter Season Nuances (Egypt): Sheltered bays vs windy bays, heated pool availability.
4. Review Sentiment Breakdown: Food, rooms, service, reef & beach.
5. Pros, Cons & Red Flags: Critical issues travelers should know.
6. Target Audience Verdict: Who should book this hotel and who should avoid it.

Outputs `hotel_reputation_kb.json` as permanent long-term memory for AI Oracle and Dashboards.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hotel_reviews_kb")

DEFAULT_KB_FILE = "hotel_reputation_kb.json"
DEFAULT_DNA_FILE = "market_dna_profile.json"
CACHE_EXPIRY_DAYS = 30
DEFAULT_CONCURRENCY = 5


SYSTEM_PROMPT = """
Ты — ведущий независимый эксперт по качеству отелей и аудиту отзывов туристов.
Твоя задача — составить краткое, честное и объективное репутационное резюме отеля на основе анализа реальных отзывов путешественников на TripAdvisor, Google Maps и HolidayCheck за последний сезон (2024–2026 гг.).

ПРАВИЛА И СТИЛЬ:
1. БУДЬ ЧЕСТНЫМ: Если отель испортился, питание однообразное или в номерах старая мебель — напиши об этом прямо без маркетинговых прикрас.
2. СЕЗОННЫЙ ТРЕНД (season_trend):
   - Отметь, стал ли отель лучше (реновация номеров, смена шеф-повара), хуже (экономия на сервисе, износ) или остался стабильным.
3. ДЛЯ ДЕТЕЙ (family_and_kids):
   - Оцени, подходит ли для детей: пологий ли песчаный заход в море или только с понтона на глубину, есть ли аквапарк/горки, подогреваются ли детские бассейны.
4. ЗИМНЯЯ СПЕЦИФИКА (для Египта):
   - Укажи бухту (Наама Бэй, Рас Ум Сид, Шаркс Бэй, Набк и т.д.), защищена ли от ветра, есть ли подогреваемый бассейн в зимний период (с ноября по апрель).
5. ПЛЮСЫ И МИНУСЫ (pros, cons_and_red_flags):
   - 2-3 главных реальных достоинства.
   - 1-2 главных недостатка или «красных флагов» (red flags).
6. ВЕРДИКТ:
   - 1-2 предложения: кому этот отель подходит идеально, а кому категорически не рекомендуется.

ФОРМАТ ОТВЕТА: строго валидный JSON без markdown-разметки:
{
  "season_trend": {
    "trend": "BETTER|WORSE|STABLE",
    "summary": "Краткая суть изменений за последний сезон"
  },
  "family_and_kids": {
    "score": 8.5,
    "suitable_for_children": true,
    "beach_entry": "Пологий песчаный / с понтона / кораллы",
    "kids_facilities": "Аквапарк, детский клуб, подогреваемый бассейн"
  },
  "winter_suitability": {
    "bay": "Название бухты/района",
    "wind_shelter": "Защищена от ветра / открытая ветреная",
    "heated_pools": true
  },
  "sentiment_scores": {
    "food": 8.0,
    "rooms": 8.5,
    "service": 8.0,
    "beach_and_reef": 9.0
  },
  "pros": [
    "...", "..."
  ],
  "cons_and_red_flags": [
    "...", "..."
  ],
  "verdict": "Рекомендация для кого отель подходит идеально, а кому не стоит брать"
}
"""


def is_valid_hotel_name(hn: str) -> bool:
    """Validates that a string is a real hotel name and not git conflict noise or NaN."""
    if not hn or not isinstance(hn, str):
        return False
    hn_clean = hn.strip()
    if len(hn_clean) < 3:
        return False
    if hn_clean.lower() in ("nan", "none", "", "null", "undefined", "true", "false"):
        return False
    if hn_clean.startswith(("<<<", "===", ">>>")):
        return False
    if any(k in hn_clean.lower() for k in ("updated upstream", "stashed changes", "stash", "merge branch")):
        return False
    return True


def discover_hotels(
    data_dirs: Optional[List[str]] = None,
    dna_file: str = DEFAULT_DNA_FILE,
    filters_manifest: str = "filters_manifest.json",
) -> Dict[str, Dict[str, Any]]:
    """
    Discovers all unique hotels across CSV files, DNA profile, and filter manifests.
    Returns mapping: {hotel_name: {hotel_name, destination, stars, sample_url, rating, review_count}}
    """
    hotels: Dict[str, Dict[str, Any]] = {}

    # 1. From DNA Profile
    if os.path.exists(dna_file):
        try:
            with open(dna_file, "r", encoding="utf-8") as f:
                dna_data = json.load(f)
                for h_name, h_info in dna_data.get("hotel_profiles", {}).items():
                    if not is_valid_hotel_name(h_name):
                        continue
                    hotels[h_name] = {
                        "hotel_name": h_name,
                        "destination": "",
                        "stars": 4,
                        "primary_operator": h_info.get("primary_operator", ""),
                    }
        except Exception as e:
            logger.warning(f"Could not load DNA profile {dna_file}: {e}")

    # 2. From all CSV files in data/ and data_runs/
    csv_paths = []
    search_dirs = data_dirs or ["data", "data/filters", "data_runs"]
    for d in search_dirs:
        if os.path.exists(d):
            csv_paths.extend(glob.glob(f"{d}/**/*prices*.csv", recursive=True))

    for p in csv_paths:
        try:
            df = pd.read_csv(p, nrows=2000)
            if "hotel_name" not in df.columns:
                continue

            # Infer destination from path
            dest = "Египет"
            p_lower = p.lower()
            if "turkey" in p_lower or "turcja" in p_lower:
                dest = "Турция"
            elif "cyprus" in p_lower or "cypr" in p_lower:
                dest = "Кипр"
            elif "greece" in p_lower or "grecja" in p_lower:
                dest = "Греция"
            elif "spain" in p_lower or "hiszpania" in p_lower:
                dest = "Испания"

            for _, row in df.iterrows():
                hn = str(row["hotel_name"]).strip()
                if not is_valid_hotel_name(hn):
                    continue

                existing = hotels.get(hn, {})
                offer_url = str(row.get("offer_url") or row.get("url") or "")
                r_val = 0.0
                for r_col in ("ta_rating", "rating", "hotel_rating"):
                    if r_col in row and pd.notna(row[r_col]):
                        try:
                            r_val = float(str(row[r_col]).replace(",", "."))
                            if r_val > 5.0:
                                r_val = round(r_val / 2.0, 1)
                            break
                        except Exception:
                            pass

                rev_val = 0
                for rev_col in ("ta_review_count", "review_count", "reviews"):
                    if rev_col in row and pd.notna(row[rev_col]):
                        try:
                            c = re.sub(r"[^\d]", "", str(row[rev_col]))
                            if c:
                                rev_val = int(c)
                                break
                        except Exception:
                            pass

                hotels[hn] = {
                    "hotel_name": hn,
                    "destination": existing.get("destination") or dest,
                    "stars": existing.get("stars", 4),
                    "rating": r_val or existing.get("rating", 0.0),
                    "review_count": rev_val or existing.get("review_count", 0),
                    "offer_url": offer_url or existing.get("offer_url", ""),
                    "primary_operator": existing.get("primary_operator", ""),
                }
        except Exception as e:
            logger.debug(f"Error scanning {p}: {e}")

    logger.info(f"Discovered {len(hotels)} unique hotels across all active filters.")
    return hotels


def load_reputation_kb(kb_path: str = DEFAULT_KB_FILE) -> Dict[str, Any]:
    """Loads existing reputation knowledge base if present, cleaning out any corrupt keys."""
    if os.path.exists(kb_path):
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "hotels" in data:
                    clean_hotels = {
                        k: v for k, v in data["hotels"].items()
                        if is_valid_hotel_name(k)
                    }
                    data["hotels"] = clean_hotels
                    return data
        except Exception as e:
            logger.warning(f"Failed to read existing KB from {kb_path}: {e}")

    return {
        "version": "1.0",
        "description": "Hotel Reviews & Reputation AI Knowledge Base",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "hotels": {},
    }


def save_reputation_kb(kb_data: Dict[str, Any], kb_path: str = DEFAULT_KB_FILE) -> None:
    """Saves updated reputation knowledge base atomically."""
    kb_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    kb_data["total_hotels"] = len(kb_data.get("hotels", {}))

    tmp_path = f"{kb_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, kb_path)
    logger.info(f"Successfully saved {kb_data['total_hotels']} hotels to {kb_path}")


def analyze_hotel_with_llm(
    hotel_info: Dict[str, Any],
    api_key: Optional[str] = None,
    provider: str = "gemini",
) -> Optional[Dict[str, Any]]:
    """
    Synthesizes hotel reputation using LLM (Gemini 2.0 Flash or OpenAI gpt-4o-mini).
    Includes rate-limit retry.
    """
    h_name = hotel_info["hotel_name"]
    dest = hotel_info.get("destination", "Египет / Шарм-эль-Шейх")
    stars = hotel_info.get("stars", 4)
    r_val = hotel_info.get("rating", 0.0)
    rev_cnt = hotel_info.get("review_count", 0)

    user_prompt = f"""
Проанализируй отель:
Название: "{h_name}"
Категория: {stars}★
Направление: {dest}
Оценка туристов: {r_val:g}★ ({rev_cnt:,} отзывов)

Составь экспертное резюме качества и репутации отеля на основе реальных отзывов путешественников (TripAdvisor, Google Reviews, HolidayCheck) за последний сезон.
Ответь ТОЛЬКО валидным JSON строго по указанной схеме.
"""

    if provider == "gemini" and api_key:
        models = [os.getenv("GEMINI_MODEL"), "gemini-2.0-flash", "gemini-1.5-flash"]
        target_models = [m for m in models if m]

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
            }
        }

        for model_name in target_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    res = json.loads(text)
                    if isinstance(res, dict) and "season_trend" in res:
                        return res
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.warning(f"Gemini 429 rate limit on {model_name} for '{h_name}'. Waiting 4s...")
                    time.sleep(4)
                else:
                    logger.warning(f"Gemini {model_name} HTTP {e.code} for '{h_name}': {e}")
            except Exception as e:
                logger.warning(f"Gemini {model_name} failed for '{h_name}': {e}")

    elif provider == "openai" and api_key:
        models = [os.getenv("OPENAI_MODEL"), "gpt-4o-mini", "gpt-4o"]
        target_models = [m for m in models if m]

        for model_name in target_models:
            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
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
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"].strip()
                    res = json.loads(text)
                    if isinstance(res, dict) and "season_trend" in res:
                        return res
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    logger.warning(f"OpenAI 429 rate limit on {model_name} for '{h_name}'. Waiting 4s...")
                    time.sleep(4)
                else:
                    logger.warning(f"OpenAI {model_name} HTTP {e.code} for '{h_name}': {e}")
            except Exception as e:
                logger.warning(f"OpenAI {model_name} failed for '{h_name}': {e}")

    return None


def generate_heuristic_reputation(hotel_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based reputation synthesizer for offline/zero-key environments.
    Grounded in geographical bay properties, hotel name tokens, and amenity heuristics.
    """
    h_name = hotel_info["hotel_name"]
    dest = hotel_info.get("destination", "Египет")
    h_lower = h_name.lower()
    stars = hotel_info.get("stars", 4)
    r_val = hotel_info.get("rating")
    rev_cnt = int(hotel_info.get("review_count", 0) or 0)
    if not r_val or float(r_val) <= 0:
        # Do not fabricate fake 4.1 ratings for unrated hotels.
        # Leave unrated hotels with r_val=0.0 and rev_cnt=0,
        # so AI adheres to Rule 6 (only use real verified ratings).
        r_val = 0.0
        rev_cnt = 0

    # 1. Geographic & Bay Nuances
    is_egypt = any(k in dest.lower() for k in ("египет", "egypt", "красное море"))

    if is_egypt:
        bay = "Курортный район"
        wind_shelter = "Умеренная ветровая защита"
        beach_entry = "Песчаный пляж с участками рифа"
        winter_comfort = "Стандартный зимний комфорт"

        if any(k in h_lower for k in ("naama", "promenade", "novotel", "maritim", "tropitel", "movenpick")):
            bay = "Бухта Наама Бэй (Naama Bay)"
            wind_shelter = "Защищена горами от зимних ветров (море спокойное)"
            beach_entry = "Пологий песчаный вход в воду, обувь не требуется"
            winter_comfort = "Высокий: комфортно для купания в декабре-феврале"
        elif any(k in h_lower for k in ("hadaba", "ras um sid", "faraana", "jaz fanara", "renaissance", "reef oasis", "sentido")):
            bay = "Бухта Рас Ум Сид / Хадаба"
            wind_shelter = "Защищена скалистым мысом от северного ветра"
            beach_entry = "Один из лучших живых коралловых рифов, вход с понтона"
            winter_comfort = "Высокий: теплая безветренная бухта"
        elif any(k in h_lower for k in ("shark", "sultan gardens", "grand rotana", "pyramisa", "white knight")):
            bay = "Бухта Шаркс Бэй (Shark's Bay)"
            wind_shelter = "Умеренный ветер, вид на остров Тиран"
            beach_entry = "Красивый риф, заход с понтона"
            winter_comfort = "Средний: при ветре возможны волны"
        elif any(k in h_lower for k in ("nabq", "amwaj", "rehana", "rixos premium seagate", "cleopatra", "parrotel", "barcelo", "albatros laguna")):
            bay = "Бухта Набк (Nabq Bay)"
            wind_shelter = "Открытая бухта, подвержена зимним ветрам"
            beach_entry = "Длинный понтон (до 500-800 м) через мелководный риф"
            winter_comfort = "Низкий зимой: частые ветра, возможен красный флаг на понтоне"
    else:
        # Mediterranean / European Destinations (Greece, Cyprus, Turkey, Spain, etc.)
        bay = "Курортная зона"
        wind_shelter = "Средиземноморское побережье"
        beach_entry = "Песчано-галечный пляж с удобным входом в море"
        winter_comfort = "Мягкий климат, экскурсионный сезон"

    # 2. Amenities
    has_aquapark = any(k in h_lower for k in ("aqua", "park", "water", "splash", "slide", "аквапарк"))
    is_adults_only = any(k in h_lower for k in ("adults", "16+", "18+"))
    family_friendly = not is_adults_only and (has_aquapark or any(k in h_lower for k in ("family", "kids", "albatros", "pickalbatros", "jaz")))
    has_heated_pool = any(k in h_lower for k in ("albatros", "pickalbatros", "rixos", "jaz", "baron", "sunrise", "steigenberger", "four seasons", "promenade", "maritim"))

    # 3. Pros and Cons
    pros = []
    cons = []

    if has_aquapark:
        pros.append("Большой аквапарк и водные горки на территории")
    if has_heated_pool:
        pros.append("Бассейны с подогревом в зимний период")
    if is_egypt and ("риф" in beach_entry.lower() or "рас ум сид" in bay.lower()):
        pros.append("Живописный коралловый риф для снорклинга")
    if is_egypt and "наама" in bay.lower():
        pros.append("Безветренная бухта с удобным песчаным входом в море")
    if not is_egypt:
        pros.append("Удобное расположение относительно моря и курортной инфраструктуры")
        pros.append("Чистое море и благоустроенная пляжная зона")

    if not pros:
        pros.append("Развитая инфраструктура и большая зеленая территория")
        pros.append("Удобное расположение относительно курортного променада")

    if "набк" in bay.lower():
        cons.append("Ветреная бухта зимой, частый красный флаг и длинный понтон")
    if not has_heated_pool and "египет" in dest.lower():
        cons.append("Отсутствие гарантированного подогрева бассейнов зимой")
    if stars <= 3 or r_val < 4.0:
        cons.append("Номерной фонд требует косметического обновления")

    if not cons:
        cons.append("Высокая популярность отеля: номера быстро разбирают в сезон")

    verdict = (
        f"Рекомендуется для семейного отдыха с детьми благодаря развитой инфраструктуре."
        if family_friendly
        else f"Качественный отель категории {stars}★ для комфортного отдыха на море."
    )

    return {
        "season_trend": {
            "trend": "STABLE",
            "summary": "Стабильное качество обслуживания на уровне категории отеля.",
        },
        "family_and_kids": {
            "score": 8.8 if family_friendly else 6.5,
            "suitable_for_children": family_friendly,
            "beach_entry": beach_entry,
            "kids_facilities": "Аквапарк и детская зона" if has_aquapark else "Стандартная детская площадка",
        },
        "winter_suitability": {
            "bay": bay,
            "wind_shelter": wind_shelter,
            "heated_pools": has_heated_pool,
        },
        "sentiment_scores": {
            "food": 8.0,
            "rooms": 8.0,
            "service": 8.2,
            "beach_and_reef": 8.5 if "риф" in beach_entry.lower() else 7.5,
        },
        "pros": pros[:3],
        "cons_and_red_flags": cons[:2],
        "verdict": verdict,
        "ta_rating": float(r_val) if (r_val and float(r_val) > 0) else None,
        "ta_review_count": int(rev_cnt or 0),
    }


def build_hotel_reviews_kb(
    output_file: str = DEFAULT_KB_FILE,
    dna_file: str = DEFAULT_DNA_FILE,
    force_refresh: bool = False,
    max_hotels: Optional[int] = None,
    destination_filter: Optional[str] = None,
    data_dirs: Optional[List[str]] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> Dict[str, Any]:
    """
    Main orchestrator: updates the hotel reputation knowledge base incrementally and in parallel.
    """
    logger.info("🏨 Starting Weekly Hotel Reviews & Reputation KB Builder...")

    # Load existing KB
    kb = load_reputation_kb(output_file)
    existing_hotels = kb.setdefault("hotels", {})

    # Discover all monitored hotels
    catalog = discover_hotels(data_dirs=data_dirs, dna_file=dna_file)
    for hn, h_data in existing_hotels.items():
        if hn not in catalog and is_valid_hotel_name(hn):
            catalog[hn] = {
                "hotel_name": hn,
                "destination": h_data.get("destination", "Египет"),
                "stars": h_data.get("stars", 4),
                "rating": h_data.get("ta_rating", 0.0),
                "review_count": h_data.get("ta_review_count", 0),
            }

    if not catalog:
        logger.warning("No hotels discovered. Exiting.")
        return kb

    now = datetime.utcnow()
    cutoff_date = now - timedelta(days=CACHE_EXPIRY_DAYS)

    # Filter hotels that need update
    hotels_to_process: List[Dict[str, Any]] = []
    for hn, h_info in catalog.items():
        if destination_filter and destination_filter.lower() not in h_info.get("destination", "").lower():
            continue

        existing = existing_hotels.get(hn)
        if not force_refresh and existing and "analyzed_at" in existing and existing.get("ta_rating") is not None:
            try:
                analyzed_at = datetime.fromisoformat(existing["analyzed_at"].replace("Z", "+00:00")).replace(tzinfo=None)
                if analyzed_at > cutoff_date:
                    continue  # Fresh enough, skip
            except Exception:
                pass

        hotels_to_process.append(h_info)

    logger.info(f"Total catalog: {len(catalog)} hotels | Needs update: {len(hotels_to_process)} hotels")
    if max_hotels and max_hotels > 0:
        hotels_to_process = hotels_to_process[:max_hotels]
        logger.info(f"Limited run to {len(hotels_to_process)} hotels (max_hotels={max_hotels})")

    if not hotels_to_process:
        logger.info("All hotels in catalog are already up to date!")
        return kb

    # API Keys
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    save_lock = threading.Lock()
    updated_count = 0
    total_hotels = len(hotels_to_process)
    stop_event = threading.Event()

    def process_hotel(item: Tuple[int, Dict[str, Any]]) -> Optional[str]:
        if stop_event.is_set():
            return None
        idx, h_info = item
        hn = h_info["hotel_name"]
        logger.info(f"[{idx}/{total_hotels}] Analyzing reputation for '{hn}'...")

        rep_result = None
        if gemini_key:
            rep_result = analyze_hotel_with_llm(h_info, api_key=gemini_key, provider="gemini")
        if not rep_result and openai_key:
            rep_result = analyze_hotel_with_llm(h_info, api_key=openai_key, provider="openai")
        if not rep_result:
            rep_result = generate_heuristic_reputation(h_info)

        hotel_record = {
            "hotel_name": hn,
            "destination": h_info.get("destination", "Египет"),
            "stars": h_info.get("stars", 4),
            "analyzed_at": now.isoformat() + "Z",
            **rep_result,
        }

        with save_lock:
            nonlocal updated_count
            existing_hotels[hn] = hotel_record
            updated_count += 1
            if updated_count % 10 == 0:
                save_reputation_kb(kb, output_file)

        return hn

    workers = max(1, min(concurrency, total_hotels))
    logger.info(f"⚡ Processing {total_hotels} hotels with {workers} parallel threads...")
    indexed_hotels = list(enumerate(hotels_to_process, 1))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_hotel, item): item[1]["hotel_name"] for item in indexed_hotels}
        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    h_name = futures.get(future, "unknown")
                    logger.warning(f"Error processing {h_name}: {e}")
        except KeyboardInterrupt:
            logger.warning("Keyboard interrupt received. Saving state...")
            stop_event.set()

    # Final save
    save_reputation_kb(kb, output_file)
    logger.info(f"🎉 Reputation KB update completed! Updated {updated_count} hotels. Total KB size: {len(existing_hotels)}")
    return kb


def main():
    parser = argparse.ArgumentParser(description="Weekly Hotel Reviews & Reputation Knowledge Base Builder")
    parser.add_argument("--output", default=DEFAULT_KB_FILE, help="Path to output hotel_reputation_kb.json")
    parser.add_argument("--dna", default=DEFAULT_DNA_FILE, help="Path to market_dna_profile.json")
    parser.add_argument("--force", action="store_true", help="Force refresh all hotels regardless of cache age")
    parser.add_argument("--max-hotels", type=int, default=None, help="Maximum number of hotels to process in this run")
    parser.add_argument("--destination", default=None, help="Filter by destination (egypt, turkey, cyprus, etc.)")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Number of parallel worker threads")

    args = parser.parse_args()
    build_hotel_reviews_kb(
        output_file=args.output,
        dna_file=args.dna,
        force_refresh=args.force,
        max_hotels=args.max_hotels,
        destination_filter=args.destination,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()
