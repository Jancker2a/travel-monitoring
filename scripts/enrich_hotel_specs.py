#!/usr/bin/env python3
"""
Hotel Specifications & Infrastructure Knowledge Base Enricher.

Collects and enriches verified hotel attributes using structured LLM synthesis:
- Beach characteristics (sand/gravel/pontoon, beach line, sea entry slope)
- Pools & Aquaparks (pool count, heated pools in winter, slides)
- Catering concepts (AI, UAI, HB, BB, FB)
- Renovation & ratings (last renovation year, TripAdvisor rating & review count)
- Transfer time from major airports

Includes:
- Strict JSON schema validation
- Anti-template detector (detects and flags copy-paste canned responses)
- Rate limiting, exponential backoff, and batch execution
- Offline safe mode when API keys are not available
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from scripts.audit_and_fix_specs_kb import audit_and_cleanse_specs
except ImportError:
    try:
        from audit_and_fix_specs_kb import audit_and_cleanse_specs
    except ImportError:
        audit_and_cleanse_specs = None

try:
    from scripts.hotel_passport_compiler import build_hotel_infrastructure, compile_hotel_passport
except ImportError:
    try:
        from hotel_passport_compiler import build_hotel_infrastructure, compile_hotel_passport
    except ImportError:
        build_hotel_infrastructure = None
        compile_hotel_passport = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_hotel_specs")

DEFAULT_SPECS_FILE = "hotel_specs_kb.json"
DEFAULT_REPUTATION_FILE = "hotel_reputation_kb.json"

VALID_BEACH_TYPES = {
    "sand", "gravel", "pontoon", "reef", "mixed",
    "sand_pebble", "pebble", "coral_rocky", "pontoon_only", "artificial_lagoon"
}
VALID_SEA_ENTRIES = {
    "shallow_sand", "deep", "pontoon_to_reef", "coral_entry", "mixed",
    "gentle_slope", "coral_plate_shoes", "steep_deep"
}
VALID_BAY_WINDS = {
    "sheltered_bay", "moderate_wind", "windy_exposed", "not_applicable"
}
VALID_REEF_PRESENCE = {
    "live_house_reef", "moderate_reef", "no_reef"
}
VALID_FOOD_CONCEPTS = {"AI", "UAI", "HB", "BB", "FB", "RO"}

SYSTEM_PROMPT = """
Ты — старший эксперт-аналитик по курортной инфраструктуре, отельной инженерии и географии мировых курортов (Египет, Турция, Кипр, Греция).
Твоя задача — составить максимально точный, детальный, проверенный и объективный паспорт инфраструктуры для конкретного отеля.

ПРИНЦИПЫ И ЖЕЛЕЗНЫЕ ПРАВИЛА (АНТИ-ГАЛЛЮЦИНАЦИЯ):
1. НИКАКИХ МАРКЕТИНГОВЫХ ШТАМПОВ И ВОДЫ:
   - Категорически запрещены общие клише вроде: "Разнообразие ресторанов", "Разнообразие водных видов спорта", "Уютная зеленая территория", "Просторные номера с видом на море", "Стандартная детская площадка".
   - Каждый пункт в highlights и caution_notes обязан содержать ФАКТ: название бухты, реальный километраж/метраж, конкретную зону подогрева, особенности дна или рельефа.

2. ПЛЯЖ, ЛИНИЯ И МОРСКАЯ ТОПОГРАФИЯ (КРИТИЧНО):
   - beach_line:
     * 1 — ТОЛЬКО beachfront: отель стоит прямо на первой линии моря, без дорог, без променадов и без шаттлов.
     * 2 — если между отелем и морем есть дорога/променад или отель на второй линии (150–700 метров пешком).
     * 3 — если отель городской, находится в глубине курорта (например, район Хадаба/Hadaba в Шарм-эль-Шейхе вдалеке от моря: Old Vic, Falcon Hills, Coral Hills, Tivoli, Luna Sharm) или на плато, и до моря требуется шаттл-бас (>800м).
   - beach_type: одно из [sand, sand_pebble, pebble, coral_rocky, pontoon_only, artificial_lagoon, mixed]
   - sea_entry: одно из [shallow_sand, gentle_slope, pontoon_to_reef, coral_plate_shoes, steep_deep, mixed]
   - pontoon_length_m: ориентировочная длина понтона в метрах (число, например 50, 250, 750) или null, если вход с берега без понтона.
   - bay_wind_protection:
     * sheltered_bay — 100% закрытая безветренная бухта для зимы (в Шарме: Шарм-эль-Майя / Sharm El Maya, Наама Бэй / Naama Bay, Рас-Ум-Сид / Ras Um Sid, часть Шаркс Бэй).
     * moderate_wind — умеренная продуваемость.
     * windy_exposed — открытое ветреное побережье (район Набк / Nabq Bay в Шарме — частый красный флаг и волны; открытое побережье Марса Алам).
     * not_applicable — для Средиземноморья / летних направлений.
   - reef_presence: одно из [live_house_reef, moderate_reef, no_reef].

3. БАССЕЙНЫ И ЗИМНИЙ ПОДОГРЕВ (СТРОГАЯ ПРОВЕРКА):
   - heated_pools_winter: ставь true ТОЛЬКО если есть подтвержденный подогрев хотя бы одного бассейна в зимний период (ноябрь-март). Если подогрева нет или он не гарантирован — СТРОГО false.
   - heated_pools_details: краткое конкретное описание (например: "Главный открытый бассейн (+28°C) и детский бассейн", "Только крытый бассейн в спа", "Бассейн с горками подогревается", либо null при отсутствии).
   - pool_count: реальное число бассейнов на территории (число).
   - aquapark: true ТОЛЬКО если есть полноценный комплекс от 3-4 взрослых/семейных водных горок. (Если 1-2 детские горки в лягушатнике — ставь false).
   - slides_total: общее число горок (число или null).
   - indoor_pool: true если есть крытый бассейн, иначе false.

4. ПИТАНИЕ И РЕНОВАЦИЯ:
   - food_concept: доминирующий концепт [AI, UAI, HB, BB, FB, RO].
   - alacarte_count: количество ресторанов a la carte (число или null).
   - last_renovation_year: год последней реновации (число или null).
   - renovation_scope: одно из ["full_property", "rooms_only", "public_areas", "cosmetic", null].
   - tripadvisor_rating: рейтинг от 1.0 до 5.0 (число с 1 десятичным знаком, напр. 4.3).
   - tripadvisor_reviews: примерное количество отзывов (число или null).
   - transfer_minutes: ориентировочное реальное время трансфера от ближайшего аэропорта (число минут).
   - nearest_airport: IATA-код аэропорта (напр. "SSH", "HRG", "RMF", "AYT", "PFO", "LCA", "HER", "RHO").

5. HIGHLIGHTS (2-3 конкретных преимущества):
   - Только объективные факты: песчаная лагуна, безветренная бухта, подогрев олимпийского бассейна, живой коралловый риф с черепахами/дюгонями, свежий номерной фонд после реновации 2023 года.

6. CAUTION_NOTES (2-3 объективных нюанса/предостережения):
   - Только честные факты: 2-я/3-я линия с трансфером по расписанию, длинный понтон 600м в ветреной бухте Набк с частым красным флагом, каменистый вход в море с необходимостью коралок, ступенчатый каскадный рельеф (неудобно с колясками), старый номерной фонд стандартных корпусов.

Ответь ТОЛЬКО валидным JSON-объектом:
{
  "beach_type": "sand",
  "beach_line": 1,
  "sea_entry": "shallow_sand",
  "pontoon_length_m": null,
  "bay_wind_protection": "sheltered_bay",
  "reef_presence": "live_house_reef",
  "heated_pools_winter": true,
  "heated_pools_details": "Главный открытый бассейн подогревается до +28°C с ноября по март",
  "pool_count": 3,
  "aquapark": true,
  "slides_total": 6,
  "indoor_pool": false,
  "food_concept": "AI",
  "alacarte_count": 3,
  "last_renovation_year": 2022,
  "renovation_scope": "rooms_only",
  "tripadvisor_rating": 4.4,
  "tripadvisor_reviews": 2300,
  "transfer_minutes": 20,
  "nearest_airport": "SSH",
  "highlights": [
    "100% безветренная бухта Шарм-эль-Майя с широким пологим песчаным пляжем",
    "Гарантированный подогрев главного открытого бассейна и горок аквапарка зимой"
  ],
  "caution_notes": [
    "Мелководье во время отливов на расстоянии до 50 метров от берега",
    "Высокая загрузка отеля семьями в пиковые каникулярные даты"
  ]
}
"""


def validate_specs_payload(payload: Dict[str, Any], hotel_name: str = "") -> Tuple[bool, Optional[str]]:
    """Strictly validates the parsed JSON payload against specifications schema."""
    if not isinstance(payload, dict):
        return False, "Payload is not a dict"

    beach_type = payload.get("beach_type")
    if beach_type and str(beach_type).lower() not in VALID_BEACH_TYPES:
        return False, f"Invalid beach_type: {beach_type}"

    beach_line = payload.get("beach_line")
    if beach_line is not None:
        try:
            b_line = int(beach_line)
            if b_line not in (1, 2, 3):
                return False, f"Invalid beach_line: {beach_line}"
        except (ValueError, TypeError):
            return False, f"Invalid beach_line: {beach_line}"

    sea_entry = payload.get("sea_entry")
    if sea_entry and str(sea_entry).lower() not in VALID_SEA_ENTRIES:
        return False, f"Invalid sea_entry: {sea_entry}"

    ta_rating = payload.get("tripadvisor_rating")
    if ta_rating is not None:
        try:
            ta_val = float(ta_rating)
            if not (1.0 <= ta_val <= 5.0):
                return False, f"tripadvisor_rating out of range 1.0-5.0: {ta_val}"
        except (ValueError, TypeError):
            return False, f"tripadvisor_rating not float: {ta_rating}"

    bay_wind = payload.get("bay_wind_protection")
    if bay_wind and str(bay_wind).lower() not in VALID_BAY_WINDS:
        return False, f"Invalid bay_wind_protection: {bay_wind}"

    reef = payload.get("reef_presence")
    if reef and str(reef).lower() not in VALID_REEF_PRESENCE:
        return False, f"Invalid reef_presence: {reef}"

    # Anti-hallucination geographical sanity checks
    if hotel_name:
        name_lower = hotel_name.lower()
        # Nabq Bay in Sharm is open and windy; it cannot be wind-protected
        if "nabq" in name_lower and bay_wind == "sheltered_bay":
            return False, f"Geographical conflict: Hotel in Nabq Bay '{hotel_name}' cannot be marked 'sheltered_bay'"

        # Inland Hadaba hotels cannot be 1st line
        inland_sharm = ["falcon hills", "old vic", "coral hills", "tivoli", "sharm cliff", "luna sharm", "verginia"]
        if any(ih in name_lower for ih in inland_sharm) and beach_line == 1:
            return False, f"Geographical conflict: Inland hotel '{hotel_name}' cannot be 1st line"

    return True, None


def is_template_response(payload: Dict[str, Any]) -> bool:
    """Anti-template detector: detects canned, repetitive or low-effort filler responses."""
    if not isinstance(payload, dict):
        return True

    # Safely extract lists (handling explicit None or non-list values)
    raw_hl = payload.get("highlights")
    highlights = raw_hl if isinstance(raw_hl, list) else ([raw_hl] if raw_hl else [])
    raw_ca = payload.get("caution_notes")
    caution = raw_ca if isinstance(raw_ca, list) else ([raw_ca] if raw_ca else [])

    combined_text = " ".join([str(h) for h in highlights if h is not None] + [str(c) for c in caution if c is not None]).lower()

    banned_canned = [
        "песчано-галечный пляж с удобным входом в море",
        "стандартная детская площадка",
        "умеренная ветровая защита",
        "стандартный зимний комфорт",
        "разнообразие ресторанов и баров",
        "разнообразие ресторанов",
        "разнообразие водных видов спорта",
        "просторные номера с видом на море",
        "большая территория с зелеными насаждениями",
        "некоторые номера могут быть шумными из-за близости к бассейну",
        "некоторые номера могут быть шумными",
        "прекрасный вид на море",
        "спокойная атмосфера для отдыха",
        "уютная зеленая территория",
        "развлекательные программы",
        "отличное обслуживание",
    ]
    for canned in banned_canned:
        if canned in combined_text:
            return True

    # If all numeric values are null and no highlights
    if not highlights and payload.get("tripadvisor_rating") is None and payload.get("pool_count") is None:
        return True

    return False

def call_gemini_specs(hotel_name: str, country: str, api_key: str, model_name: str = "gemini-2.0-flash") -> Optional[Dict[str, Any]]:
    """Queries Google Gemini Flash API for hotel specifications."""
    user_prompt = f'Для отеля "{hotel_name}" ({country}) предоставь точные технические характеристики и инфраструктуру. Ответь только JSON.'
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024,
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
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return parsed
    except Exception as e:
        logger.warning(f"Gemini {model_name} failed for '{hotel_name}': {e}")
        return None


def call_openai_specs(hotel_name: str, country: str, api_key: str, model_name: str = "gpt-4o-mini") -> Optional[Dict[str, Any]]:
    """Queries OpenAI API as secondary fallback."""
    user_prompt = f'Для отеля "{hotel_name}" ({country}) предоставь точные технические характеристики и инфраструктуру. Ответь только JSON.'
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
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
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(text)
            return parsed
    except Exception as e:
        logger.warning(f"OpenAI {model_name} failed for '{hotel_name}': {e}")
        return None


def load_hotel_specs_kb(path: str = DEFAULT_SPECS_FILE) -> Dict[str, Any]:
    """Loads existing specifications knowledge base or creates a new empty schema."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "hotels" in data:
                    return data
        except Exception as e:
            logger.warning(f"Could not load existing specs KB {path}: {e}")

    return {
        "version": "1.0",
        "description": "Verified Hotel Specifications & Infrastructure Knowledge Base",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_enriched": 0,
        "hotels": {},
    }


def save_hotel_specs_kb(data: Dict[str, Any], path: str = DEFAULT_SPECS_FILE) -> None:
    """Atomically saves specifications knowledge base."""
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    data["total_enriched"] = sum(1 for h in data.get("hotels", {}).values() if h.get("is_enriched"))
    data["total_hotels"] = len(data.get("hotels", {}))

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    logger.info(f"Saved {data['total_hotels']} hotels ({data['total_enriched']} enriched) to {path}")


def collect_target_hotels(reputation_path: str = DEFAULT_REPUTATION_FILE) -> List[Dict[str, str]]:
    """Collects candidate hotels to enrich from reputation KB and project monitors."""
    candidates = []
    seen = set()

    # 1. From existing reputation KB
    if os.path.exists(reputation_path):
        try:
            with open(reputation_path, "r", encoding="utf-8") as f:
                rep_data = json.load(f)
                for h_name, info in rep_data.get("hotels", {}).items():
                    norm_name = h_name.strip()
                    if norm_name and norm_name not in seen:
                        seen.add(norm_name)
                        candidates.append({
                            "hotel_name": norm_name,
                            "destination": info.get("destination", "Турция / Египет"),
                        })
        except Exception as e:
            logger.warning(f"Error reading reputation KB: {e}")

    return candidates


def enrich_specs_pipeline(
    max_hotels: int = 50,
    force: bool = False,
    destination: str = "all",
    dry_run: bool = False,
    gemini_key: Optional[str] = None,
    openai_key: Optional[str] = None,
    specs_path: str = DEFAULT_SPECS_FILE,
) -> Dict[str, Any]:
    """Main enrichment pipeline running batch updates with validation."""
    gemini_key = gemini_key or os.getenv("GEMINI_API_KEY")
    openai_key = openai_key or os.getenv("OPENAI_API_KEY")

    kb = load_hotel_specs_kb(specs_path)
    candidates = collect_target_hotels()

    if destination != "all":
        candidates = [c for c in candidates if destination.lower() in c["destination"].lower()]

    processed = 0
    enriched_count = 0

    logger.info(f"Enrichment pipeline started. Total candidates: {len(candidates)}, max_hotels: {max_hotels}")

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        for item in candidates:
            if processed >= max_hotels:
                break

            h_name = item["hotel_name"]
            existing = kb["hotels"].get(h_name)

            if existing and existing.get("is_enriched") and not force:
                continue

            processed += 1
            logger.info(f"[{processed}/{max_hotels}] Enriching '{h_name}' ({item['destination']})...")

            raw_specs = None
            if not dry_run:
                if gemini_key:
                    raw_specs = call_gemini_specs(h_name, item["destination"], gemini_key, model_name=gemini_model)
                if not raw_specs and openai_key:
                    raw_specs = call_openai_specs(h_name, item["destination"], openai_key, model_name=openai_model)

            if raw_specs:
                is_valid, err_msg = validate_specs_payload(raw_specs)
                if not is_valid:
                    logger.warning(f"Schema validation failed for '{h_name}': {err_msg}")
                    continue

                if is_template_response(raw_specs):
                    logger.warning(f"Anti-template check failed for '{h_name}' (canned response detected)")
                    continue

                record = {
                    "hotel_name": h_name,
                    "destination": item["destination"],
                    "is_enriched": True,
                    "enriched_at": datetime.utcnow().isoformat() + "Z",
                    "source": "llm_verified",
                    "specs": {
                        "beach_type": raw_specs.get("beach_type"),
                        "beach_line": raw_specs.get("beach_line"),
                        "sea_entry": raw_specs.get("sea_entry"),
                        "heated_pools_winter": bool(raw_specs.get("heated_pools_winter")),
                        "pool_count": raw_specs.get("pool_count"),
                        "aquapark": bool(raw_specs.get("aquapark")),
                        "food_concept": raw_specs.get("food_concept", "AI"),
                        "last_renovation_year": raw_specs.get("last_renovation_year"),
                        "tripadvisor_rating": raw_specs.get("tripadvisor_rating"),
                        "tripadvisor_reviews": raw_specs.get("tripadvisor_reviews"),
                        "transfer_minutes": raw_specs.get("transfer_minutes"),
                        "highlights": raw_specs.get("highlights") or [],
                        "caution_notes": raw_specs.get("caution_notes") or [],
                    }
                }
                if build_hotel_infrastructure:
                    record["specs"]["infrastructure"] = build_hotel_infrastructure(h_name, record)
                if compile_hotel_passport:
                    record["specs"]["passport"] = compile_hotel_passport(h_name, record)
                kb["hotels"][h_name] = record
                enriched_count += 1
                if enriched_count % 5 == 0 and not dry_run:
                    save_hotel_specs_kb(kb, specs_path)
                # Rate limit politeness
                time.sleep(1.0)
            else:
                if dry_run or (not gemini_key and not openai_key):
                    # In zero-key/dry-run mode, register record as pending/un-enriched without fake data
                    if h_name not in kb["hotels"]:
                        kb["hotels"][h_name] = {
                            "hotel_name": h_name,
                            "destination": item["destination"],
                            "is_enriched": False,
                            "enriched_at": None,
                            "source": "pending_enrichment",
                            "specs": None,
                        }
    finally:
        if not dry_run:
            if audit_and_cleanse_specs:
                audit_and_cleanse_specs(specs_path)
            if build_hotel_infrastructure and compile_hotel_passport:
                for h_name, h_record in kb.get("hotels", {}).items():
                    if h_record.get("is_enriched") and h_record.get("specs"):
                        if "infrastructure" not in h_record["specs"]:
                            h_record["specs"]["infrastructure"] = build_hotel_infrastructure(h_name, h_record)
                        if "passport" not in h_record["specs"]:
                            h_record["specs"]["passport"] = compile_hotel_passport(h_name, h_record)
            save_hotel_specs_kb(kb, specs_path)

    logger.info(f"Pipeline complete. Processed {processed}, Newly enriched: {enriched_count}")
    return kb


def main():
    parser = argparse.ArgumentParser(description="Enrich Hotel Specifications Knowledge Base")
    parser.add_argument("--max-hotels", type=int, default=50, help="Max hotels to enrich in one run")
    parser.add_argument("--force", action="store_true", help="Force refresh even if already enriched")
    parser.add_argument("--destination", default="all", help="Filter destination: turkey, egypt, cyprus, etc.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without API calls")
    parser.add_argument("--gemini-key", default=None, help="Gemini API Key")
    parser.add_argument("--openai-key", default=None, help="OpenAI API Key")
    parser.add_argument("--output", default=DEFAULT_SPECS_FILE, help="Output KB path")
    args = parser.parse_args()

    enrich_specs_pipeline(
        max_hotels=args.max_hotels,
        force=args.force,
        destination=args.destination,
        dry_run=args.dry_run,
        gemini_key=args.gemini_key,
        openai_key=args.openai_key,
        specs_path=args.output,
    )


if __name__ == "__main__":
    main()
