#!/usr/bin/env python3
"""
Process new filter submission from GitHub Issue body.
Extracts, validates JSON configuration, and writes to configs/filters/config_ci_<slug>.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filter_registry import detect_group_for_config, KNOWN_GROUPS


def extract_json_payload(body: str) -> Dict[str, Any]:
    """Extracts JSON payload from markdown code block or raw text."""
    # Try finding ```json ... ``` or ``` ... ```
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
    if code_block_match:
        raw_json = code_block_match.group(1).strip()
    else:
        # Fallback to finding outermost { ... }
        brace_match = re.search(r"(\{.*\})", body, re.DOTALL)
        if brace_match:
            raw_json = brace_match.group(1).strip()
        else:
            raw_json = body.strip()

    try:
        data = json.loads(raw_json)
        if not isinstance(data, dict):
            raise ValueError("Payload must be a JSON object (dictionary)")
        return data
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid JSON format: {err}")


def sanitize_slug(name: str) -> str:
    """Sanitizes filter identifier into safe ASCII alphanumeric and underscores."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "custom_filter"


def validate_and_normalize_filter(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Validates required fields and applies safe defaults."""
    url = str(cfg.get("url") or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise ValueError("Field 'url' is required and must start with http:// or https://")

    title = str(cfg.get("title") or "").strip()
    if not title:
        title = "Индивидуальный мониторинг"

    # Derive safe slug
    raw_id = str(cfg.get("id") or "").strip()
    if raw_id:
        slug = sanitize_slug(raw_id.replace("config_ci_", "").replace("filter_", ""))
    else:
        slug = sanitize_slug(title)

    flt_id = f"filter_{slug}"
    config_file_name = f"config_ci_{slug}.json"
    data_dir = f"data/filters/{flt_id}"

    # Country / Group
    group = detect_group_for_config(cfg)
    group_meta = KNOWN_GROUPS.get(group, KNOWN_GROUPS["custom"])

    # Required URL contains based on country
    country_subpaths = {
        "egypt": "/wycieczka/egipt",
        "turkey": "/wycieczka/turcja",
        "greece": "/wycieczka/grecja",
        "cyprus": "/wycieczka/cypr",
        "spain": "/wycieczka/hiszpania",
        "italy": "/wycieczka/wlochy",
        "bulgaria": "/wycieczka/bulgaria",
        "tunisia": "/wycieczka/tunezja",
        "uae": "/wycieczka/zjednoczone-emiraty-arabskie",
        "malta": "/wycieczka/malta",
    }
    req_contains = list(cfg.get("required_offer_url_contains") or [])
    if group in country_subpaths and country_subpaths[group] not in req_contains:
        req_contains.insert(0, country_subpaths[group])
    if "transport=accommodation_flight" not in req_contains:
        req_contains.append("transport=accommodation_flight")

    excl_contains = list(cfg.get("excluded_offer_url_contains") or [
        "/wycieczka/polska",
        "/wycieczka/czechy",
        "transport=accommodation&",
    ])

    # Price thresholds & display ceilings
    try:
        max_price = int(cfg.get("max_price_threshold") or 25000)
    except Exception:
        max_price = 25000
    try:
        min_price = int(cfg.get("min_price_threshold") or 2000)
    except Exception:
        min_price = 2000
    try:
        disp_ceiling = int(cfg.get("display_price_ceiling") or 12000)
    except Exception:
        disp_ceiling = 12000

    # Modules
    user_modules = cfg.get("modules") or {}
    modules = {
        "arbitrage_germany": bool(user_modules.get("arbitrage_germany", True)),
        "hopper_predictor": bool(user_modules.get("hopper_predictor", True)),
        "departure_analytics": bool(user_modules.get("departure_analytics", True)),
        "deal_score": bool(user_modules.get("deal_score", True)),
        "room_types": bool(user_modules.get("room_types", True)),
        "telegram_alerts": bool(user_modules.get("telegram_alerts", False)),
    }

    # Germany params
    user_germany = cfg.get("germany_params") or {}
    germany_params = {
        "enabled": bool(user_germany.get("enabled", modules["arbitrage_germany"])),
        "departure_airport": str(user_germany.get("departure_airport") or "BER").upper(),
        "direct_flight_only": bool(user_germany.get("direct_flight_only", False)),
    }

    normalized = {
        "allow_empty_offers": True,
        "id": flt_id,
        "title": title,
        "subtitle": str(cfg.get("subtitle") or f"{title} • сбор ≤{max_price} PLN, показ ≤{disp_ceiling}"),
        "group": group,
        "group_label": group_meta["label"],
        "group_icon": group_meta["icon"],
        "url": url,
        "max_price_threshold": max_price,
        "min_price_threshold": min_price,
        "display_price_ceiling": disp_ceiling,
        "history_price_ceiling": disp_ceiling,
        "required_offer_url_contains": req_contains,
        "excluded_offer_url_contains": excl_contains,
        "wait_timeout": int(cfg.get("wait_timeout") or 30000),
        "max_retries": int(cfg.get("max_retries") or 3),
        "max_offers": 0,
        "max_pages": int(cfg.get("max_pages") or 10),
        "retry_delay": 5,
        "data_dir": data_dir,
        "output_data_file": "travel_prices.csv",
        "description": f"Пользовательский фильтр • {title} • сбор {min_price}-{max_price} PLN, показ ≤{disp_ceiling}",
        "modules": modules,
        "germany_params": germany_params,
        "created_at": cfg.get("created_at") or "",
    }

    # Pass through dynamic / fixed trip params if present
    if "filter_mode" in cfg:
        normalized["filter_mode"] = cfg["filter_mode"]
    if "dynamic_search_dates" in cfg:
        normalized["dynamic_search_dates"] = bool(cfg["dynamic_search_dates"])
    if "trip_anchor_date" in cfg:
        normalized["trip_anchor_date"] = cfg["trip_anchor_date"]
    if "retire_after" in cfg:
        normalized["retire_after"] = cfg["retire_after"]
    if "trip_duration_buckets" in cfg:
        normalized["trip_duration_buckets"] = cfg["trip_duration_buckets"]

    return normalized


def save_filter_config(normalized_cfg: Dict[str, Any]) -> Path:
    """Saves normalized config into configs/filters/ directory and ensures it is active in filters_registry_meta.json."""
    target_dir = ROOT / "configs" / "filters"
    target_dir.mkdir(parents=True, exist_ok=True)

    slug = normalized_cfg["id"].replace("filter_", "")
    target_path = target_dir / f"config_ci_{slug}.json"

    with target_path.open("w", encoding="utf-8") as f:
        json.dump(normalized_cfg, f, ensure_ascii=False, indent=2)

    # Ensure filter is not blocked by a legacy 'deleted' or 'paused' status in filters_registry_meta.json
    try:
        from filter_registry import load_filters_meta, save_filters_meta
        meta = load_filters_meta()
        flt_id = normalized_cfg["id"]
        if flt_id in meta.get("filters", {}):
            meta["filters"][flt_id]["status"] = "active"
            meta["filters"][flt_id]["updated_at"] = normalized_cfg.get("created_at") or ""
            save_filters_meta(meta)
    except Exception as e:
        print(f"Warning: could not update filters_registry_meta.json: {e}", file=sys.stderr)

    return target_path


def main():
    parser = argparse.ArgumentParser(description="Process new filter GitHub Issue body")
    parser.add_argument("--body-file", help="Path to file containing issue body")
    parser.add_argument("--body-text", help="Raw issue body string")
    parser.add_argument("--output-json", help="Path to write created config metadata")
    args = parser.parse_args()

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
    elif args.body_text:
        raw_text = args.body_text
    else:
        raw_text = sys.stdin.read()

    try:
        payload = extract_json_payload(raw_text)
        normalized = validate_and_normalize_filter(payload)
        out_path = save_filter_config(normalized)
        print(f"SUCCESS: Filter config saved to {out_path.relative_to(ROOT)}")
        print(f"FILTER_ID={normalized['id']}")
        print(f"FILTER_TITLE={normalized['title']}")
        print(f"CONFIG_PATH={out_path.relative_to(ROOT)}")

        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump({
                    "success": True,
                    "id": normalized["id"],
                    "title": normalized["title"],
                    "config_path": str(out_path.relative_to(ROOT)),
                    "href": f"index_{normalized['id']}.html",
                }, f, ensure_ascii=False, indent=2)

        return 0
    except Exception as e:
        print(f"ERROR: Failed to process filter: {e}", file=sys.stderr)
        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump({"success": False, "error": str(e)}, f, ensure_ascii=False, indent=2)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
