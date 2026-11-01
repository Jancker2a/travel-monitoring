#!/usr/bin/env python3
"""
Hotel Catalog Builder.

Aggregates hotel pricing, package options, specs, and monitoring coverage across all filters:
- Resolves raw hotel names to canonical entities via HotelCanonicalRegistry
- Computes accurate package composition labels (e.g., '2 взр. + 1 реб.', '2 взр.', '1 взр.')
- Evaluates price cascade (7-8d standard -> 9-11d -> 14d) for catalog reference badges
- Cross-references hotel_specs_kb.json, hotel_reputation_kb.json, and market_dna_profile.json
- Assigns strict confidence_level ('high', 'medium', 'low') preventing hallucinated archetypes
- Produces hotels_catalog_data.json and builds a premium interactive hotels.html dashboard
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import logging
import math
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from hotel_name_normalizer import (
    HotelCanonicalRegistry,
    clean_hotel_title,
    normalize_for_matching,
    slugify_hotel_name,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_hotel_catalog")

DEFAULT_OUTPUT_HTML = "hotels.html"
DEFAULT_OUTPUT_JSON = "hotels_catalog_data.json"
MANIFEST_FILE = "filters_manifest.json"
SPECS_KB_FILE = "hotel_specs_kb.json"
REPUTATION_KB_FILE = "hotel_reputation_kb.json"
DNA_PROFILE_FILE = "market_dna_profile.json"


def extract_package_composition(config_dict: Dict[str, Any], url_str: str = "") -> Dict[str, Any]:
    """
    Extracts adults and children from config dict, URL parameters, and subtitle.
    Prevents false assumption of '2 adults' when filter searches 2+1 or 1 adult.
    """
    url = url_str or config_dict.get("url", "")
    subtitle = str(config_dict.get("subtitle", "")).lower()

    adults = 2
    children = 0

    # 1. Check URL parameters
    m_p = re.search(r"[?&](?:filter\[person\]|person|adults)=(\d+)", url)
    if m_p:
        adults = int(m_p.group(1))

    m_c = re.search(r"[?&](?:filter\[child\]|child)=(\d+)", url)
    if m_c:
        children = int(m_c.group(1))
    else:
        m_children_raw = re.search(r"[?&]children=([\d\-,]+)", url)
        if m_children_raw:
            val = m_children_raw.group(1)
            # e.g. children=10-12-2020 or children=20201210
            years = re.findall(r"(?:19|20)\d{2}", val)
            children = len(years) if years else 1

    # 2. Check subtitle overrides
    if "1 взр" in subtitle or "1 чел" in subtitle or "1p" in config_dict.get("id", ""):
        adults = 1
        children = 0
    elif "2+1" in subtitle or "2 взр + 1 реб" in subtitle:
        adults = 2
        children = 1

    if children > 0:
        label = f"{adults} взр. + {children} реб."
        short_label = f"{adults}+{children}"
    else:
        label = f"{adults} взр." if adults > 1 else "1 взр."
        short_label = f"{adults} чел."

    return {
        "adults": adults,
        "children": children,
        "label": label,
        "short_label": short_label,
    }


def parse_duration_days(duration_str: str) -> int:
    """Extracts integer days from strings like '8 dni', '7-10', '14 days'."""
    if not duration_str:
        return 7
    m = re.search(r"(\d+)", str(duration_str))
    return int(m.group(1)) if m else 7


def load_filters_meta(manifest_path: str = MANIFEST_FILE) -> Dict[str, Dict[str, Any]]:
    """Loads all known filter definitions and their configs."""
    filters = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for f_item in data.get("filters", []):
                    f_id = f_item.get("id")
                    if f_id:
                        filters[f_id] = f_item
        except Exception as e:
            logger.warning(f"Error loading {manifest_path}: {e}")

    # Also scan config_ci_filter_*.json and configs/filters/*.json
    config_paths = glob.glob("config*.json") + glob.glob("configs/**/*.json", recursive=True)
    for c_path in config_paths:
        try:
            with open(c_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                if not isinstance(c_data, dict):
                    continue
                f_id = c_data.get("id") or os.path.splitext(os.path.basename(c_path))[0]
                if f_id not in filters:
                    filters[f_id] = {
                        "id": f_id,
                        "title": c_data.get("title") or c_data.get("description") or f_id,
                        "subtitle": c_data.get("subtitle") or "",
                        "href": f"index_{f_id}.html" if not f_id.startswith("index_") else f"{f_id}.html",
                        "config": c_path,
                        "data_dir": c_data.get("data_dir") or f"data/filters/{f_id}",
                    }
        except Exception:
            pass

    return filters


def load_hotel_specs(specs_path: str = SPECS_KB_FILE) -> Dict[str, Any]:
    """Loads enriched hotel specifications KB."""
    if os.path.exists(specs_path):
        try:
            with open(specs_path, "r", encoding="utf-8") as f:
                return json.load(f).get("hotels", {})
        except Exception as e:
            logger.warning(f"Error loading specs KB: {e}")
    return {}


def load_reputation_kb(rep_path: str = REPUTATION_KB_FILE) -> Dict[str, Any]:
    """Loads reputation KB."""
    if os.path.exists(rep_path):
        try:
            with open(rep_path, "r", encoding="utf-8") as f:
                return json.load(f).get("hotels", {})
        except Exception as e:
            logger.warning(f"Error loading reputation KB: {e}")
    return {}


def load_market_dna(dna_path: str = DNA_PROFILE_FILE) -> Dict[str, Any]:
    """Loads market DNA profiles."""
    if os.path.exists(dna_path):
        try:
            with open(dna_path, "r", encoding="utf-8") as f:
                return json.load(f).get("hotel_profiles", {})
        except Exception as e:
            logger.warning(f"Error loading market DNA: {e}")
    return {}


def collect_hotel_data() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Main aggregator: parses CSVs, hotel_series JSONs, and builds unified canonical records.
    """
    registry = HotelCanonicalRegistry()
    filters_meta = load_filters_meta()
    specs_kb = load_hotel_specs()
    reputation_kb = load_reputation_kb()
    market_dna = load_market_dna()

    # Raw collections per canonical slug:
    # slug -> { "canonical_record": ..., "history_points": [], "packages": [], "filters": {} }
    hotel_entries: Dict[str, Dict[str, Any]] = {}

    def get_or_create_entry(raw_hotel_name: str, dest_hint: str = "") -> Dict[str, Any]:
        can_rec = registry.register_hotel(raw_hotel_name, destination=dest_hint)
        slug = can_rec["slug"]
        if slug not in hotel_entries:
            hotel_entries[slug] = {
                "slug": slug,
                "canonical_name": can_rec["canonical_name"],
                "destination": dest_hint or can_rec["destination"] or "Средиземноморье",
                "aliases": can_rec["aliases"],
                "history_points": [],  # list of {date, price, filter_id}
                "packages": [],        # list of package offers
                "tracked_filters": {}, # filter_id -> filter summary dict
                "images": set(),
                "latest_offer_url": "",
                "stars": 4,
                "user_rating": None,
            }
        return hotel_entries[slug]

    # 1. Parse hotel_series JSON files (data/filters/**/hotel_series/*.json and data_runs/**/hotel_series/*.json)
    series_files = glob.glob("data/filters/**/hotel_series/*.json", recursive=True) + \
                   glob.glob("data_runs/**/hotel_series/*.json", recursive=True)

    logger.info(f"Scanning {len(series_files)} hotel_series JSON files...")
    for s_path in series_files:
        try:
            with open(s_path, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                h_name = s_data.get("hotel_name")
                if not h_name:
                    continue

                filter_id = s_data.get("filter_id")
                if not filter_id:
                    # Deduce from path
                    parts = s_path.split(os.sep)
                    for i, p in enumerate(parts):
                        if p in ("filters", "data_runs") and i + 1 < len(parts):
                            filter_id = parts[i + 1]
                            break
                filter_id = filter_id or "default_filter"
                f_meta = filters_meta.get(filter_id, {})
                comp = extract_package_composition(f_meta)

                dest = f_meta.get("group_label") or ("Кипр" if "cyprus" in filter_id else "Турция" if "turkey" in filter_id else "Египет" if "egypt" in filter_id else "")
                entry = get_or_create_entry(h_name, dest_hint=dest)

                meta = s_data.get("meta", {})
                img = meta.get("image_url")
                if img and not img.endswith("placeholder.jpg"):
                    entry["images"].add(img)
                if meta.get("offer_url") and not entry["latest_offer_url"]:
                    entry["latest_offer_url"] = meta.get("offer_url")

                # Load historical series points
                xs = s_data.get("x", [])
                ys = s_data.get("y", [])
                hovers = s_data.get("hover", [])
                pts_count = len(ys)

                if pts_count > 0:
                    filter_points = []
                    for idx in range(pts_count):
                        x_val = xs[idx] if idx < len(xs) else ""
                        y_val = ys[idx]
                        h_val = hovers[idx] if idx < len(hovers) else ""
                        pt = {
                            "date": x_val,
                            "price": float(y_val),
                            "filter_id": filter_id,
                            "hover": h_val,
                        }
                        entry["history_points"].append(pt)
                        filter_points.append(pt)

                    # Update tracked filter for this hotel
                    f_prices = [p["price"] for p in filter_points if p["price"] > 0]
                    if f_prices:
                        entry["tracked_filters"][filter_id] = {
                            "filter_id": filter_id,
                            "filter_name": f_meta.get("title") or filter_id,
                            "dashboard_file": f_meta.get("href") or f"index_{filter_id}.html",
                            "adults": comp["adults"],
                            "children": comp["children"],
                            "composition_label": comp["label"],
                            "duration_bucket": meta.get("duration", "7-10"),
                            "history_points_count": len(f_prices),
                            "first_seen": xs[0] if xs else None,
                            "last_seen": xs[-1] if xs else None,
                            "min_price": min(f_prices),
                            "max_price": max(f_prices),
                            "current_price": f_prices[-1],
                            "series": [{"x": p["date"], "y": p["price"]} for p in filter_points],
                        }

                # Register package
                dur = meta.get("duration", "7-10")
                if ys:
                    entry["packages"].append({
                        "filter_id": filter_id,
                        "filter_title": f_meta.get("title") or filter_id,
                        "duration": dur,
                        "duration_days": parse_duration_days(dur),
                        "dates": meta.get("dates", s_data.get("trip_dates_label", "—")),
                        "composition_label": comp["label"],
                        "composition_short": comp["short_label"],
                        "price": float(ys[-1]),
                        "offer_url": meta.get("offer_url") or "",
                        "deal_score": s_data.get("deal_score"),
                    })
        except Exception as e:
            logger.debug(f"Could not parse series {s_path}: {e}")

    # 2. Parse CSV files (data/filters/**/travel_prices.csv and data_runs/**/*.csv)
    csv_files = glob.glob("data/filters/**/travel_prices.csv", recursive=True) + \
                glob.glob("data_runs/**/*.csv", recursive=True)

    logger.info(f"Scanning {len(csv_files)} CSV files for package tours...")
    for c_path in csv_files:
        try:
            import csv
            with open(c_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                filter_id = "default"
                parts = c_path.split(os.sep)
                for i, p in enumerate(parts):
                    if p in ("filters", "data_runs") and i + 1 < len(parts):
                        filter_id = parts[i + 1]
                        break

                f_meta = filters_meta.get(filter_id, {})
                comp = extract_package_composition(f_meta)
                dest = f_meta.get("group_label") or ("Турция" if "turkey" in filter_id else "Египет" if "egypt" in filter_id else "Кипр" if "cyprus" in filter_id else "")

                for row in reader:
                    h_name = row.get("hotel_name")
                    if not h_name:
                        continue
                    try:
                        p_val = float(row.get("price", 0))
                    except ValueError:
                        continue
                    if p_val <= 0:
                        continue

                    entry = get_or_create_entry(h_name, dest_hint=dest)
                    img = row.get("image_url")
                    if img and not img.endswith("placeholder.jpg"):
                        entry["images"].add(img)

                    offer_url = row.get("offer_url") or row.get("url") or ""
                    if offer_url and not entry["latest_offer_url"]:
                        entry["latest_offer_url"] = offer_url

                    scraped_at = row.get("scraped_at") or ""
                    entry["history_points"].append({
                        "date": scraped_at,
                        "price": p_val,
                        "filter_id": filter_id,
                        "hover": f"{row.get('dates', '')} • {p_val:g} zł",
                    })

                    dur = row.get("duration", "7-10")
                    entry["packages"].append({
                        "filter_id": filter_id,
                        "filter_title": f_meta.get("title") or filter_id,
                        "duration": dur,
                        "duration_days": parse_duration_days(dur),
                        "dates": row.get("dates", "—"),
                        "composition_label": comp["label"],
                        "composition_short": comp["short_label"],
                        "departure": row.get("departure_airport", "WAW/WMI"),
                        "price": p_val,
                        "offer_url": offer_url,
                        "deal_score": None,
                    })
        except Exception as e:
            logger.debug(f"Error parsing CSV {c_path}: {e}")

    # Also register review candidates
    registry.save_review_manifest()

    # 3. Consolidate and compute metrics for each canonical hotel
    catalog_hotels = []
    logger.info(f"Consolidating {len(hotel_entries)} canonical hotel profiles...")

    for slug, entry in hotel_entries.items():
        h_name = entry["canonical_name"]
        pts = entry["history_points"]
        if not pts:
            continue

        prices = [p["price"] for p in pts if p["price"] > 0]
        if not prices:
            continue

        pts_sorted = sorted(pts, key=lambda p: p["date"] or "")
        current_price = pts_sorted[-1]["price"]
        min_price = min(prices)
        max_price = max(prices)
        median_price = sorted(prices)[len(prices) // 2]
        total_samples = len(prices)

        price_drop_pct = 0.0
        if max_price > min_price and current_price < max_price:
            price_drop_pct = round(((max_price - current_price) / max_price) * 100, 1)

        # Select primary image
        image_url = sorted(list(entry["images"]))[0] if entry["images"] else ""

        # Price Cascade for reference badge:
        # Priority 1: 7-8 days, minimal composition
        # Priority 2: 9-11 days
        # Priority 3: 13-16 days
        packages = entry["packages"]
        # Deduplicate packages by (duration_days, composition_label, price)
        unique_packages = {}
        for pkg in packages:
            key = (pkg["duration_days"], pkg["composition_label"])
            if key not in unique_packages or pkg["price"] < unique_packages[key]["price"]:
                unique_packages[key] = pkg
        deduped_packages = sorted(unique_packages.values(), key=lambda p: (p["duration_days"], p["price"]))

        ref_pkg = None
        # P1: 7-8 days
        p1 = [p for p in deduped_packages if 7 <= p["duration_days"] <= 8]
        if p1:
            ref_pkg = p1[0]
        else:
            # P2: 9-11 days
            p2 = [p for p in deduped_packages if 9 <= p["duration_days"] <= 11]
            if p2:
                ref_pkg = p2[0]
            else:
                # P3: any other
                ref_pkg = deduped_packages[0] if deduped_packages else None

        if ref_pkg:
            ref_price = ref_pkg["price"]
            ref_badge = f"{int(ref_price):,} zł · {ref_pkg['duration_days']} дн. · {ref_pkg['composition_label']}".replace(",", " ")
        else:
            ref_price = current_price
            ref_badge = f"{int(current_price):,} zł · 7 дн. · 2 взр.".replace(",", " ")

        # Specs & KB integration
        specs_data = specs_kb.get(h_name) or specs_kb.get(clean_hotel_title(h_name))
        is_specs_enriched = bool(specs_data and specs_data.get("is_enriched"))
        specs = specs_data.get("specs") if is_specs_enriched else None

        rep_data = reputation_kb.get(h_name) or reputation_kb.get(clean_hotel_title(h_name))
        dna_data = market_dna.get(h_name) or market_dna.get(clean_hotel_title(h_name))

        # Check if reputation is template
        is_rep_canned = False
        if rep_data:
            fk = rep_data.get("family_and_kids", {})
            if fk.get("beach_entry") == "Песчано-галечный пляж с удобным входом в море":
                is_rep_canned = True

        # STRICT CONFIDENCE LEVEL CALCULATION
        # Decision 9:
        # high: >=5 samples + verified KB (not canned)
        # medium: 3-4 samples
        # low: 1-2 samples or canned template
        if total_samples >= 5 and (is_specs_enriched or (rep_data and not is_rep_canned)):
            confidence_level = "high"
            confidence_badge = "Высокая надежность"
        elif total_samples >= 3:
            confidence_level = "medium"
            confidence_badge = "Средняя надежность"
        else:
            confidence_level = "low"
            confidence_badge = "Мало замеров"

        # Verdict and Archetype: ONLY DISPLAYED IF CONFIDENCE IS HIGH OR MEDIUM!
        archetype = None
        verdict = None
        if confidence_level in ("high", "medium"):
            if dna_data and dna_data.get("archetype"):
                archetype = dna_data.get("archetype")
            if rep_data and not is_rep_canned and rep_data.get("verdict"):
                verdict = rep_data.get("verdict")
            elif specs and specs.get("highlights"):
                verdict = " • ".join(specs["highlights"][:2])

        # Country / Destination detection
        country = "Турция"
        dest_str = entry["destination"].lower()
        if "египет" in dest_str or "egypt" in dest_str:
            country = "Египет"
        elif "кипр" in dest_str or "cypr" in dest_str:
            country = "Кипр"
        elif "грец" in dest_str or "grec" in dest_str:
            country = "Греция"
        elif "испан" in dest_str or "spain" in dest_str:
            country = "Испания"
        elif "болгар" in dest_str or "bulgar" in dest_str:
            country = "Болгария"

        # Rating: verified TripAdvisor or rep rating
        rating = None
        reviews_count = None
        if specs and specs.get("tripadvisor_rating"):
            rating = float(specs["tripadvisor_rating"])
            reviews_count = specs.get("tripadvisor_reviews")
        elif rep_data and rep_data.get("sentiment_scores"):
            scores = rep_data["sentiment_scores"]
            if any(s > 0 for s in scores.values()):
                rating = round(sum(scores.values()) / max(len(scores), 1) / 2, 1)  # scale 10 to 5

        # Smart Collections tagging
        collections = []
        if price_drop_pct >= 8.0:
            collections.append("flash_drops")
        if rating and rating >= 4.4 and current_price <= 7000:
            collections.append("hidden_gems")
        if (specs and (specs.get("aquapark") or specs.get("sea_entry") == "shallow_sand")) or any(p["composition_short"] == "2+1" for p in deduped_packages):
            collections.append("family_kids")
        if (specs and specs.get("heated_pools_winter")) or (rep_data and rep_data.get("winter_suitability", {}).get("heated_pools")):
            collections.append("warm_winter")
        if any("eb_" in p["filter_id"] or "aug27" in p["filter_id"] or "jul27" in p["filter_id"] for p in deduped_packages):
            collections.append("early_booking")
        if any("germany" in p["filter_id"] or "ber" in p["filter_id"] for p in deduped_packages):
            collections.append("ber_arbitrage")

        catalog_hotels.append({
            "slug": slug,
            "hotel_name": h_name,
            "country": country,
            "destination": entry["destination"],
            "image_url": image_url,
            "offer_url": entry["latest_offer_url"],
            "rating": rating,
            "reviews_count": reviews_count,
            "current_price": current_price,
            "min_price": min_price,
            "max_price": max_price,
            "median_price": median_price,
            "price_drop_pct": price_drop_pct,
            "ref_price": ref_price,
            "ref_badge": ref_badge,
            "total_samples": total_samples,
            "confidence_level": confidence_level,
            "confidence_badge": confidence_badge,
            "archetype": archetype,
            "verdict": verdict,
            "collections": collections,
            "specs": specs,
            "has_verified_specs": is_specs_enriched,
            "tracked_filters": list(entry["tracked_filters"].values()),
            "packages": deduped_packages,
        })

    # Sort catalog: hotels with best price drop and most tracked filters first
    catalog_hotels.sort(key=lambda h: (len(h["collections"]), h["price_drop_pct"], len(h["tracked_filters"])), reverse=True)

    summary_stats = {
        "total_hotels": len(catalog_hotels),
        "total_countries": len(set(h["country"] for h in catalog_hotels)),
        "total_flash_drops": sum(1 for h in catalog_hotels if "flash_drops" in h["collections"]),
        "total_family_hotels": sum(1 for h in catalog_hotels if "family_kids" in h["collections"]),
        "total_verified_specs": sum(1 for h in catalog_hotels if h["has_verified_specs"]),
        "high_confidence_count": sum(1 for h in catalog_hotels if h["confidence_level"] == "high"),
    }

    return catalog_hotels, summary_stats


def render_hotel_catalog_html(hotels: List[Dict[str, Any]], stats: Dict[str, Any]) -> str:
    """
    Renders premium hotels.html single-page application with inline data, Plotly charts,
    instant search, filtering chips, and side drawer passport.
    """
    hotels_json = json.dumps(hotels, ensure_ascii=False, separators=(",", ":"))

    html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Каталог отелей • Мониторинг цен на туры</title>
  <meta name="description" content="Единый каталог отелей с агрегированной историей цен, динамикой мониторинга по фильтрам, сравнением пакетов и объективными характеристиками.">
  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <!-- Plotly 2.35.2 CDN (AGENTS.md rule) -->
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --bg-body: #0b0f19;
      --bg-card: #131b2e;
      --bg-card-hover: #1a253e;
      --bg-surface: #1e293b;
      --bg-drawer: #0f172a;
      --border-color: rgba(255, 255, 255, 0.08);
      --border-accent: rgba(99, 102, 241, 0.3);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --primary-light: rgba(99, 102, 241, 0.15);
      --accent-cyan: #06b6d4;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 18px;
      --radius-full: 9999px;
      --shadow-card: 0 4px 20px -2px rgba(0, 0, 0, 0.5);
      --shadow-hover: 0 12px 32px -4px rgba(99, 102, 241, 0.25);
      --font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font-family);
      background-color: var(--bg-body);
      color: var(--text-main);
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }}

    a {{ color: inherit; text-decoration: none; }}

    /* Layout Container */
    .catalog-container {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 1.5rem 1.5rem 4rem;
      width: 100%;
    }}

    /* Header & Top Bar */
    .catalog-header {{
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      margin-bottom: 2rem;
    }}
    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
    }}
    .header-brand {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    .brand-icon {{
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, var(--primary), var(--accent-cyan));
      border-radius: var(--radius-md);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.5rem;
      box-shadow: 0 0 16px rgba(99, 102, 241, 0.4);
    }}
    .brand-title h1 {{
      font-size: 1.5rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      background: linear-gradient(to right, #fff, #cbd5e1);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .brand-title p {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}

    .nav-actions {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    .btn-nav {{
      padding: 0.5rem 1rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      color: var(--text-main);
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.2s ease;
    }}
    .btn-nav:hover {{
      background: var(--primary);
      border-color: var(--primary);
      color: #fff;
    }}

    /* KPI Bar */
    .kpi-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 1rem 1.25rem;
    }}
    .kpi-item {{
      display: flex;
      flex-direction: column;
    }}
    .kpi-val {{
      font-size: 1.4rem;
      font-weight: 800;
      color: #fff;
    }}
    .kpi-val.highlight-green {{ color: var(--accent-emerald); }}
    .kpi-val.highlight-indigo {{ color: #818cf8; }}
    .kpi-val.highlight-cyan {{ color: var(--accent-cyan); }}
    .kpi-lbl {{
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}

    /* Control Panel: Search & Chips */
    .controls-panel {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 1rem;
      margin-bottom: 2rem;
      box-shadow: var(--shadow-card);
    }}
    .search-row {{
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
    }}
    .search-box-wrapper {{
      flex: 1;
      min-width: 280px;
      position: relative;
    }}
    .search-icon {{
      position: absolute;
      left: 1rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-dim);
      font-size: 1.1rem;
      pointer-events: none;
    }}
    .search-input {{
      width: 100%;
      padding: 0.75rem 1rem 0.75rem 2.75rem;
      background: var(--bg-body);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      color: #fff;
      font-size: 0.95rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s;
    }}
    .search-input:focus {{
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--primary-light);
    }}
    .sort-select {{
      padding: 0.75rem 1rem;
      background: var(--bg-body);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      color: #fff;
      font-size: 0.9rem;
      font-family: inherit;
      outline: none;
      cursor: pointer;
    }}

    /* Filter Chips */
    .chips-group {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }}
    .chips-label {{
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-right: 0.5rem;
    }}
    .chip {{
      padding: 0.4rem 0.85rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-full);
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      transition: all 0.15s ease;
      user-select: none;
    }}
    .chip:hover {{
      background: var(--bg-card-hover);
      color: #fff;
      border-color: rgba(255, 255, 255, 0.2);
    }}
    .chip.active {{
      background: var(--primary);
      border-color: var(--primary);
      color: #fff;
      box-shadow: 0 0 12px rgba(99, 102, 241, 0.4);
    }}
    .chip-count {{
      background: rgba(0, 0, 0, 0.3);
      padding: 0.1rem 0.4rem;
      border-radius: var(--radius-full);
      font-size: 0.7rem;
    }}

    /* Hotel Cards Grid */
    .hotels-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.5rem;
    }}

    /* Hotel Card */
    .hotel-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-lg);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow: var(--shadow-card);
      transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s, border-color 0.2s;
      cursor: pointer;
      position: relative;
    }}
    .hotel-card:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-hover);
      border-color: var(--border-accent);
    }}

    .card-img-wrapper {{
      width: 100%;
      height: 190px;
      position: relative;
      background: linear-gradient(135deg, #1e293b, #0f172a);
      overflow: hidden;
    }}
    .card-img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: transform 0.4s ease;
    }}
    .hotel-card:hover .card-img {{
      transform: scale(1.05);
    }}
    .img-placeholder {{
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 3rem;
      opacity: 0.4;
    }}

    .card-floating-badges {{
      position: absolute;
      top: 0.75rem;
      left: 0.75rem;
      right: 0.75rem;
      display: flex;
      justify-content: space-between;
      pointer-events: none;
    }}
    .badge-country {{
      padding: 0.25rem 0.65rem;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: var(--radius-full);
      font-size: 0.75rem;
      font-weight: 700;
      color: #fff;
    }}
    .badge-drop {{
      padding: 0.25rem 0.65rem;
      background: var(--accent-rose);
      border-radius: var(--radius-full);
      font-size: 0.75rem;
      font-weight: 800;
      color: #fff;
      box-shadow: 0 2px 8px rgba(244, 63, 94, 0.5);
    }}

    .card-body {{
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      flex: 1;
      gap: 0.6rem;
    }}

    .card-header-row {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.5rem;
    }}
    .card-title {{
      font-size: 1.05rem;
      font-weight: 700;
      color: #fff;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .card-rating {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: var(--accent-emerald);
      padding: 0.15rem 0.45rem;
      border-radius: var(--radius-sm);
      font-size: 0.75rem;
      font-weight: 800;
      white-space: nowrap;
    }}

    .card-geo {{
      font-size: 0.8rem;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }}

    .card-verdict-snippet {{
      font-size: 0.8rem;
      color: #cbd5e1;
      background: rgba(255, 255, 255, 0.03);
      border-left: 2px solid var(--primary);
      padding: 0.4rem 0.6rem;
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      line-height: 1.35;
      margin-top: 0.25rem;
      font-style: italic;
    }}

    .card-package-box {{
      margin-top: auto;
      padding-top: 0.75rem;
      border-top: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }}
    .card-package-badge {{
      font-size: 0.75rem;
      color: var(--accent-cyan);
      font-weight: 600;
      background: rgba(6, 182, 212, 0.1);
      padding: 0.25rem 0.5rem;
      border-radius: var(--radius-sm);
      width: fit-content;
    }}
    .card-price-row {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
    }}
    .price-wrap {{
      display: flex;
      flex-direction: column;
    }}
    .price-main {{
      font-size: 1.35rem;
      font-weight: 800;
      color: #fff;
      line-height: 1.1;
    }}
    .price-sub {{
      font-size: 0.7rem;
      color: var(--text-dim);
    }}

    .card-footer-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.75rem;
      color: var(--text-dim);
      margin-top: 0.4rem;
    }}
    .tracked-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      color: #818cf8;
      font-weight: 600;
    }}

    /* Slide-Over Side Drawer / Modal (Deep Hotel Passport) */
    .drawer-overlay {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(6px);
      z-index: 1000;
      opacity: 0;
      visibility: hidden;
      transition: all 0.25s ease;
    }}
    .drawer-overlay.open {{
      opacity: 1;
      visibility: visible;
    }}

    .passport-drawer {{
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 100%;
      max-width: 820px;
      background: var(--bg-drawer);
      border-left: 1px solid var(--border-color);
      box-shadow: -8px 0 32px rgba(0, 0, 0, 0.8);
      z-index: 1001;
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    .passport-drawer.open {{
      transform: translateX(0);
    }}

    /* Drawer Top Bar */
    .drawer-header {{
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-card);
    }}
    .drawer-title-box h2 {{
      font-size: 1.25rem;
      font-weight: 800;
      color: #fff;
    }}
    .drawer-title-box p {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    .drawer-close-btn {{
      width: 36px;
      height: 36px;
      border-radius: var(--radius-full);
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.2rem;
      cursor: pointer;
      transition: background 0.15s;
    }}
    .drawer-close-btn:hover {{
      background: var(--bg-card-hover);
    }}

    /* Drawer Scrollable Content */
    .drawer-content {{
      padding: 1.5rem;
      overflow-y: auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }}

    /* Passport Hero */
    .passport-hero {{
      display: grid;
      grid-template-columns: 200px 1fr;
      gap: 1.25rem;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 1.25rem;
    }}
    .hero-thumb {{
      width: 100%;
      height: 140px;
      border-radius: var(--radius-sm);
      object-fit: cover;
    }}
    .hero-info {{
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .hero-stat-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }}
    .stat-pill {{
      padding: 0.35rem 0.65rem;
      background: var(--bg-surface);
      border-radius: var(--radius-sm);
      font-size: 0.75rem;
      color: var(--text-muted);
    }}
    .stat-pill strong {{
      color: #fff;
    }}

    /* Tabs Bar */
    .tabs-nav {{
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 0.5rem;
    }}
    .tab-btn {{
      padding: 0.5rem 1rem;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 0.9rem;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      border-radius: var(--radius-sm);
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }}
    .tab-btn:hover {{
      color: #fff;
      background: var(--bg-surface);
    }}
    .tab-btn.active {{
      color: #fff;
      background: var(--primary);
    }}

    /* Tab Panes */
    .tab-pane {{
      display: none;
      flex-direction: column;
      gap: 1rem;
    }}
    .tab-pane.active {{
      display: flex;
    }}

    /* Plotly Chart Container */
    .chart-box {{
      width: 100%;
      min-height: 380px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 1rem;
    }}

    /* Packages Table */
    .packages-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      background: var(--bg-card);
      border-radius: var(--radius-md);
      overflow: hidden;
      border: 1px solid var(--border-color);
    }}
    .packages-table th {{
      background: var(--bg-surface);
      padding: 0.75rem 1rem;
      text-align: left;
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .packages-table td {{
      padding: 0.75rem 1rem;
      border-top: 1px solid var(--border-color);
      color: #cbd5e1;
    }}
    .packages-table tr:hover td {{
      background: var(--bg-card-hover);
    }}
    .btn-book-sm {{
      padding: 0.35rem 0.75rem;
      background: var(--primary);
      color: #fff;
      border-radius: var(--radius-sm);
      font-size: 0.75rem;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }}
    .btn-book-sm:hover {{
      background: var(--primary-hover);
    }}

    /* Infrastructure Grid */
    .infra-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }}
    .infra-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }}
    .infra-icon {{
      font-size: 1.5rem;
      margin-bottom: 0.25rem;
    }}
    .infra-title {{
      font-size: 0.8rem;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
    }}
    .infra-val {{
      font-size: 1rem;
      font-weight: 700;
      color: #fff;
    }}

    /* Tracked Filters List */
    .filter-coverage-list {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    .coverage-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-md);
      padding: 1rem 1.25rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.75rem;
    }}
    .coverage-info h4 {{
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
    }}
    .coverage-meta {{
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 0.2rem;
    }}
    .btn-link-dash {{
      padding: 0.45rem 0.9rem;
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      font-size: 0.8rem;
      font-weight: 600;
      color: #818cf8;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .btn-link-dash:hover {{
      background: var(--primary);
      color: #fff;
    }}

    /* Empty State */
    .empty-state {{
      grid-column: 1 / -1;
      text-align: center;
      padding: 4rem 1rem;
      background: var(--bg-card);
      border: 1px dashed var(--border-color);
      border-radius: var(--radius-lg);
    }}
    .empty-icon {{ font-size: 3rem; margin-bottom: 1rem; opacity: 0.5; }}
    .empty-title {{ font-size: 1.2rem; font-weight: 700; color: #fff; }}
    .empty-desc {{ font-size: 0.9rem; color: var(--text-muted); margin-top: 0.5rem; }}

    /* Responsive */
    @media (max-width: 768px) {{
      .passport-hero {{ grid-template-columns: 1fr; }}
      .hero-thumb {{ height: 160px; }}
      .catalog-container {{ padding: 1rem 1rem 3rem; }}
    }}
  </style>
</head>
<body>

  <div class="catalog-container">
    <!-- Header -->
    <header class="catalog-header">
      <div class="header-top">
        <div class="header-brand">
          <div class="brand-icon">🏨</div>
          <div class="brand-title">
            <h1>Каталог отелей</h1>
            <p>Агрегированная история цен, паспорта инфраструктуры и мониторинг туров</p>
          </div>
        </div>
        <div class="nav-actions">
          <a href="index.html" class="btn-nav">← К дашбордам</a>
        </div>
      </div>

      <!-- KPI Bar -->
      <div class="kpi-bar">
        <div class="kpi-item">
          <span class="kpi-val highlight-indigo" id="kpiTotalHotels">{stats.get('total_hotels', 0)}</span>
          <span class="kpi-lbl">Отелей в каталоге</span>
        </div>
        <div class="kpi-item">
          <span class="kpi-val highlight-green">{stats.get('total_flash_drops', 0)}</span>
          <span class="kpi-lbl">Горящих скидок (≥8%)</span>
        </div>
        <div class="kpi-item">
          <span class="kpi-val highlight-cyan">{stats.get('total_family_hotels', 0)}</span>
          <span class="kpi-lbl">Для отдыха с детьми</span>
        </div>
        <div class="kpi-item">
          <span class="kpi-val">{stats.get('high_confidence_count', 0)}</span>
          <span class="kpi-lbl">С глубокой историей</span>
        </div>
      </div>
    </header>

    <!-- Controls Panel -->
    <section class="controls-panel">
      <!-- Search & Sort -->
      <div class="search-row">
        <div class="search-box-wrapper">
          <span class="search-icon">🔍</span>
          <input type="text" id="searchInput" class="search-input" placeholder="Поиск по названию отеля, курорту или региону..." autocomplete="off">
        </div>
        <select id="sortSelect" class="sort-select">
          <option value="drop">Сначала лучшие скидки (↓ %)</option>
          <option value="price_asc">Сначала дешевле (zł)</option>
          <option value="rating_desc">Сначала высокий рейтинг</option>
          <option value="tracked_desc">Больше всего фильтров</option>
        </select>
      </div>

      <!-- Country Chips -->
      <div class="chips-group" id="countryChips">
        <span class="chips-label">Страна:</span>
        <button class="chip active" data-country="all">Все страны</button>
        <button class="chip" data-country="Турция">🇹🇷 Турция</button>
        <button class="chip" data-country="Египет">🇪🇬 Египет</button>
        <button class="chip" data-country="Кипр">🇨🇾 Кипр</button>
        <button class="chip" data-country="Греция">🇬🇷 Греция</button>
        <button class="chip" data-country="Испания">🇪🇸 Испания</button>
        <button class="chip" data-country="Болгария">🇧🇬 Болгария</button>
      </div>

      <!-- Collection Chips -->
      <div class="chips-group" id="collectionChips">
        <span class="chips-label">Подборки:</span>
        <button class="chip" data-collection="flash_drops">⚡ Скидки</button>
        <button class="chip" data-collection="hidden_gems">💎 Жемчужины</button>
        <button class="chip" data-collection="family_kids">👶 С детьми</button>
        <button class="chip" data-collection="warm_winter">☀️ Теплая зима</button>
        <button class="chip" data-collection="early_booking">🏷️ Раннее бронь</button>
        <button class="chip" data-collection="ber_arbitrage">🇩🇪 Выгода BER</button>
      </div>
    </section>

    <!-- Hotels Grid -->
    <main class="hotels-grid" id="hotelsGrid">
      <!-- Rendered dynamically -->
    </main>
  </div>

  <!-- Deep Hotel Passport Drawer -->
  <div class="drawer-overlay" id="drawerOverlay"></div>
  <aside class="passport-drawer" id="passportDrawer">
    <div class="drawer-header">
      <div class="drawer-title-box">
        <h2 id="drawerHotelTitle">Название отеля</h2>
        <p id="drawerHotelSubtitle">Страна • Курорт</p>
      </div>
      <button class="drawer-close-btn" id="drawerCloseBtn" title="Закрыть">✕</button>
    </div>

    <div class="drawer-content">
      <!-- Hero -->
      <div class="passport-hero">
        <img id="drawerHeroImg" class="hero-thumb" src="" alt="Отель">
        <div class="hero-info">
          <div>
            <div id="drawerBadgeRow" style="display:flex; gap:0.5rem; align-items:center;"></div>
            <p id="drawerVerdict" style="margin-top:0.4rem; font-size:0.85rem; color:#cbd5e1;"></p>
          </div>
          <div class="hero-stat-pills" id="drawerHeroStats"></div>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <div class="tabs-nav">
        <button class="tab-btn active" data-tab="history">📈 История цен</button>
        <button class="tab-btn" data-tab="packages">📦 Все пакеты</button>
        <button class="tab-btn" data-tab="infra">🏖 Инфраструктура</button>
        <button class="tab-btn" data-tab="monitoring">📡 Мониторинг</button>
      </div>

      <!-- Tab 1: History Plotly Chart -->
      <div class="tab-pane active" id="paneHistory">
        <div class="chart-box" id="hotelPlotlyChart"></div>
      </div>

      <!-- Tab 2: Packages Table -->
      <div class="tab-pane" id="panePackages">
        <table class="packages-table">
          <thead>
            <tr>
              <th>Фильтр</th>
              <th>Длительность</th>
              <th>Состав</th>
              <th>Даты тура</th>
              <th>Цена</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="drawerPackagesTbody"></tbody>
        </table>
      </div>

      <!-- Tab 3: Infrastructure -->
      <div class="tab-pane" id="paneInfra">
        <div class="infra-grid" id="drawerInfraGrid"></div>
      </div>

      <!-- Tab 4: Monitoring Coverage -->
      <div class="tab-pane" id="paneMonitoring">
        <div class="filter-coverage-list" id="drawerCoverageList"></div>
      </div>
    </div>
  </aside>

  <!-- Inline Raw Data Bundle -->
  <script>
    const RAW_HOTELS = {hotels_json};
    let currentHotels = [...RAW_HOTELS];
    let selectedCountry = 'all';
    let selectedCollection = null;
    let searchQuery = '';
    let currentSort = 'drop';
    let activeHotel = null;

    // Elements
    const hotelsGrid = document.getElementById('hotelsGrid');
    const searchInput = document.getElementById('searchInput');
    const sortSelect = document.getElementById('sortSelect');
    const drawerOverlay = document.getElementById('drawerOverlay');
    const passportDrawer = document.getElementById('passportDrawer');
    const drawerCloseBtn = document.getElementById('drawerCloseBtn');

    // Debounce helper
    function debounce(fn, ms) {{
      let t;
      return function(...args) {{
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), ms);
      }};
    }}

    // Filter & Render Pipeline
    function filterAndRender() {{
      const q = searchQuery.toLowerCase().trim();
      currentHotels = RAW_HOTELS.filter(h => {{
        // Country filter
        if (selectedCountry !== 'all' && h.country !== selectedCountry) {{
          return false;
        }}
        // Collection filter
        if (selectedCollection && !h.collections.includes(selectedCollection)) {{
          return false;
        }}
        // Search text
        if (q) {{
          const matchName = h.hotel_name.toLowerCase().includes(q);
          const matchDest = (h.destination || '').toLowerCase().includes(q);
          const matchCountry = (h.country || '').toLowerCase().includes(q);
          if (!matchName && !matchDest && !matchCountry) return false;
        }}
        return true;
      }});

      // Sorting
      if (currentSort === 'drop') {{
        currentHotels.sort((a, b) => b.price_drop_pct - a.price_drop_pct);
      }} else if (currentSort === 'price_asc') {{
        currentHotels.sort((a, b) => a.current_price - b.current_price);
      }} else if (currentSort === 'rating_desc') {{
        currentHotels.sort((a, b) => (b.rating || 0) - (a.rating || 0));
      }} else if (currentSort === 'tracked_desc') {{
        currentHotels.sort((a, b) => (b.tracked_filters.length || 0) - (a.tracked_filters.length || 0));
      }}

      renderGrid();
    }}

    function renderGrid() {{
      if (currentHotels.length === 0) {{
        hotelsGrid.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">Отели не найдены</div>
            <div class="empty-desc">Попробуйте изменить поисковый запрос или сбросить фильтры</div>
          </div>
        `;
        return;
      }}

      hotelsGrid.innerHTML = currentHotels.map(h => {{
        const dropBadge = h.price_drop_pct >= 5
          ? `<span class="badge-drop">↓ -${{h.price_drop_pct}}%</span>`
          : '';

        const ratingBadge = h.rating
          ? `<span class="card-rating">★ ${{h.rating.toFixed(1)}}</span>`
          : '';

        const verdictSnippet = h.verdict
          ? `<div class="card-verdict-snippet">«${{escapeHtml(h.verdict)}}»</div>`
          : '';

        const imgBlock = h.image_url
          ? `<img class="card-img" src="${{escapeHtml(h.image_url)}}" alt="${{escapeHtml(h.hotel_name)}}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
             <div class="img-placeholder" style="display:none">🏨</div>`
          : `<div class="img-placeholder">🏨</div>`;

        return `
          <article class="hotel-card" onclick="openHotelPassport('${{h.slug}}')">
            <div class="card-img-wrapper">
              ${{imgBlock}}
              <div class="card-floating-badges">
                <span class="badge-country">${{escapeHtml(h.country)}}</span>
                ${{dropBadge}}
              </div>
            </div>
            <div class="card-body">
              <div class="card-header-row">
                <h3 class="card-title">${{escapeHtml(h.hotel_name)}}</h3>
                ${{ratingBadge}}
              </div>
              <div class="card-geo">📍 ${{escapeHtml(h.destination || h.country)}}</div>
              ${{verdictSnippet}}
              <div class="card-package-box">
                <div class="card-package-badge">${{escapeHtml(h.ref_badge)}}</div>
                <div class="card-price-row">
                  <div class="price-wrap">
                    <div class="price-main">${{Math.round(h.current_price).toLocaleString('ru-RU')}} zł</div>
                    <div class="price-sub">мин. ${{Math.round(h.min_price).toLocaleString('ru-RU')}} zł</div>
                  </div>
                  <span class="tracked-badge">📡 ${{h.tracked_filters.length}} фил.</span>
                </div>
              </div>
            </div>
          </article>
        `;
      }}).join('');
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }}

    // Hotel Passport Side Drawer
    window.openHotelPassport = function(slug) {{
      const h = RAW_HOTELS.find(item => item.slug === slug);
      if (!h) return;
      activeHotel = h;
      window.location.hash = slug;

      document.getElementById('drawerHotelTitle').textContent = h.hotel_name;
      document.getElementById('drawerHotelSubtitle').textContent = `${{h.country}} • ${{h.destination || ''}}`;

      const heroImg = document.getElementById('drawerHeroImg');
      if (h.image_url) {{
        heroImg.src = h.image_url;
        heroImg.style.display = 'block';
      }} else {{
        heroImg.style.display = 'none';
      }}

      // Badge row
      const badgeRow = document.getElementById('drawerBadgeRow');
      let badgesHtml = `<span class="stat-pill" style="color:#818cf8; font-weight:700;">${{h.confidence_badge}}</span>`;
      if (h.rating) {{
        badgesHtml += `<span class="stat-pill" style="color:var(--accent-emerald); font-weight:700;">★ ${{h.rating.toFixed(1)}} (${{h.reviews_count || 'TripAdvisor'}})</span>`;
      }}
      if (h.archetype) {{
        badgesHtml += `<span class="stat-pill" style="color:var(--accent-amber); font-weight:700;">🏷️ ${{h.archetype}}</span>`;
      }}
      badgeRow.innerHTML = badgesHtml;

      // Verdict
      document.getElementById('drawerVerdict').textContent = h.verdict ? `«${{h.verdict}}»` : '';

      // Hero stats
      const statsBox = document.getElementById('drawerHeroStats');
      statsBox.innerHTML = `
        <span class="stat-pill">Текущая: <strong>${{Math.round(h.current_price).toLocaleString('ru-RU')}} zł</strong></span>
        <span class="stat-pill">Минимум: <strong>${{Math.round(h.min_price).toLocaleString('ru-RU')}} zł</strong></span>
        <span class="stat-pill">Максимум: <strong>${{Math.round(h.max_price).toLocaleString('ru-RU')}} zł</strong></span>
        <span class="stat-pill">Замеров: <strong>${{h.total_samples}}</strong></span>
      `;

      // Packages tbody
      const tbody = document.getElementById('drawerPackagesTbody');
      if (h.packages && h.packages.length > 0) {{
        tbody.innerHTML = h.packages.map(p => `
          <tr>
            <td><strong>${{escapeHtml(p.filter_title)}}</strong></td>
            <td>${{p.duration_days}} дн.</td>
            <td>${{escapeHtml(p.composition_label)}}</td>
            <td>${{escapeHtml(p.dates)}}</td>
            <td style="color:#fff; font-weight:700;">${{Math.round(p.price).toLocaleString('ru-RU')}} zł</td>
            <td>
              ${{p.offer_url ? `<a href="${{escapeHtml(p.offer_url)}}" target="_blank" rel="noopener" class="btn-book-sm">Fly.pl ↗</a>` : '—'}}
            </td>
          </tr>
        `).join('');
      }} else {{
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:1.5rem;">Нет данных по пакетам</td></tr>`;
      }}

      // Infrastructure Tab
      const infraGrid = document.getElementById('drawerInfraGrid');
      if (h.specs) {{
        const s = h.specs;
        infraGrid.innerHTML = `
          <div class="infra-card">
            <span class="infra-icon">🏖</span>
            <span class="infra-title">Пляж и линия</span>
            <span class="infra-val">${{s.beach_line || 1}}-я линия • ${{s.beach_type || 'Песок'}}</span>
          </div>
          <div class="infra-card">
            <span class="infra-icon">🌊</span>
            <span class="infra-title">Вход в море</span>
            <span class="infra-val">${{s.sea_entry || 'Пологий песчаный'}}</span>
          </div>
          <div class="infra-card">
            <span class="infra-icon">🏊</span>
            <span class="infra-title">Бассейны</span>
            <span class="infra-val">${{s.pool_count || '1+'}} шт. ${{s.heated_pools_winter ? '• с подогревом ♨' : ''}}</span>
          </div>
          <div class="infra-card">
            <span class="infra-icon">🎢</span>
            <span class="infra-title">Аквапарк</span>
            <span class="infra-val">${{s.aquapark ? 'Есть водные горки' : 'Без аквапарка'}}</span>
          </div>
          <div class="infra-card">
            <span class="infra-icon">🍽</span>
            <span class="infra-title">Концепция питания</span>
            <span class="infra-val">${{s.food_concept || 'All Inclusive'}}</span>
          </div>
          <div class="infra-card">
            <span class="infra-icon">✨</span>
            <span class="infra-title">Реновация</span>
            <span class="infra-val">${{s.last_renovation_year || 'Свежий ремонт'}}</span>
          </div>
        `;
      }} else {{
        infraGrid.innerHTML = `
          <div style="grid-column:1/-1; padding:2rem; text-align:center; color:var(--text-muted); background:var(--bg-card); border-radius:var(--radius-md);">
            ℹ️ Точные характеристики инфраструктуры для данного отеля находятся на этапе верификации.
          </div>
        `;
      }}

      // Monitoring Tab
      const coverageList = document.getElementById('drawerCoverageList');
      if (h.tracked_filters && h.tracked_filters.length > 0) {{
        coverageList.innerHTML = h.tracked_filters.map(f => `
          <div class="coverage-card">
            <div class="coverage-info">
              <h4>${{escapeHtml(f.filter_name)}}</h4>
              <div class="coverage-meta">
                ${{f.composition_label}} • ${{f.duration_bucket}} • Наблюдений: ${{f.history_points_count}}
              </div>
              <div class="coverage-meta" style="color:var(--text-main); margin-top:0.25rem;">
                Диапазон: ${{Math.round(f.min_price)}} – ${{Math.round(f.max_price)}} zł (тек. ${{Math.round(f.current_price)}} zł)
              </div>
            </div>
            <a href="${{escapeHtml(f.dashboard_file)}}" class="btn-link-dash">Открыть дашборд ↗</a>
          </div>
        `).join('');
      }} else {{
        coverageList.innerHTML = `<div style="padding:1.5rem; text-align:center; color:var(--text-muted);">Отель отслеживается в общем потоке мониторинга</div>`;
      }}

      // Render Plotly Chart (Tab 1)
      renderHotelPlotlyChart(h);

      // Open Drawer
      drawerOverlay.classList.add('open');
      passportDrawer.classList.add('open');
    }};

    function closeHotelPassport() {{
      drawerOverlay.classList.remove('open');
      passportDrawer.classList.remove('open');
      if (window.location.hash) {{
        history.replaceState(null, null, window.location.pathname);
      }}
    }}

    // Multi-trace Plotly chart for tracked filters (conforming to AGENTS.md rules)
    function renderHotelPlotlyChart(h) {{
      const chartEl = document.getElementById('hotelPlotlyChart');
      if (!chartEl || !window.Plotly) return;

      const traces = [];
      const colors = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#f43f5e', '#a855f7'];

      if (h.tracked_filters && h.tracked_filters.length > 0) {{
        h.tracked_filters.forEach((tf, idx) => {{
          if (tf.series && tf.series.length > 0) {{
            traces.push({{
              x: tf.series.map(pt => pt.x),
              y: tf.series.map(pt => pt.y),
              mode: 'lines+markers',
              name: tf.filter_name,
              line: {{ color: colors[idx % colors.length], width: 2 }},
              marker: {{ size: 5 }},
              hovertemplate: tf.filter_name + '<br>Дата: %{{x}}<br>Цена: %{{y}} zł<extra></extra>',
            }});
          }}
        }});
      }}

      // If no tracked series, fallback to single trace
      if (traces.length === 0 && h.current_price) {{
        traces.push({{
          x: [new Date().toISOString()],
          y: [h.current_price],
          mode: 'markers',
          name: 'Текущая цена',
          marker: {{ color: '#6366f1', size: 10 }},
        }});
      }}

      const layout = {{
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: {{ l: 50, r: 20, t: 25, b: 50 }},
        font: {{ family: 'Inter, sans-serif', color: '#94a3b8' }},
        xaxis: {{
          gridcolor: 'rgba(255, 255, 255, 0.06)',
          tickformat: '%d.%m',
          hoverformat: '%d.%m.%Y',
        }},
        yaxis: {{
          gridcolor: 'rgba(255, 255, 255, 0.06)',
          ticksuffix: ' zł',
        }},
        hovermode: 'closest',
        legend: {{
          orientation: 'h',
          yanchor: 'bottom',
          y: 1.02,
          xanchor: 'right',
          x: 1,
          font: {{ size: 11 }},
        }},
      }};

      const config = {{
        responsive: true,
        displayModeBar: false,
      }};

      Plotly.newPlot('hotelPlotlyChart', traces, layout, config);
    }}

    // Multi-phase resize for tabs/accordions (AGENTS.md rule 3)
    function triggerPlotlyResize() {{
      const chartEl = document.getElementById('hotelPlotlyChart');
      if (chartEl && window.Plotly) {{
        [40, 150, 350].forEach(delay => {{
          setTimeout(() => {{
            if (chartEl && window.Plotly) Plotly.Plots.resize(chartEl);
          }}, delay);
        }});
      }}
    }}

    // Event Handlers
    drawerCloseBtn.onclick = function(e) {{
      e.preventDefault();
      closeHotelPassport();
    }};
    drawerOverlay.onclick = function(e) {{
      e.preventDefault();
      closeHotelPassport();
    }};

    // Tabs switching
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.onclick = function(e) {{
        e.preventDefault();
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

        btn.classList.add('active');
        const targetPane = document.getElementById('pane' + btn.dataset.tab.charAt(0).toUpperCase() + btn.dataset.tab.slice(1));
        if (targetPane) {{
          targetPane.classList.add('active');
          if (btn.dataset.tab === 'history') {{
            triggerPlotlyResize();
          }}
        }}
      }};
    }});

    // Search input debounce
    searchInput.addEventListener('input', debounce(function() {{
      searchQuery = searchInput.value;
      filterAndRender();
    }}, 60));

    // Sort select
    sortSelect.addEventListener('change', function() {{
      currentSort = sortSelect.value;
      filterAndRender();
    }});

    // Country chips
    document.querySelectorAll('#countryChips .chip').forEach(chip => {{
      chip.onclick = function(e) {{
        e.preventDefault();
        document.querySelectorAll('#countryChips .chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        selectedCountry = chip.dataset.country;
        filterAndRender();
      }};
    }});

    // Collection chips
    document.querySelectorAll('#collectionChips .chip').forEach(chip => {{
      chip.onclick = function(e) {{
        e.preventDefault();
        if (chip.classList.contains('active')) {{
          chip.classList.remove('active');
          selectedCollection = null;
        }} else {{
          document.querySelectorAll('#collectionChips .chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          selectedCollection = chip.dataset.collection;
        }}
        filterAndRender();
      }};
    }});

    // Deep linking handler: checks #slug on page load and hashchange
    function checkHashRoute() {{
      const hash = window.location.hash.replace('#', '').trim();
      if (hash) {{
        openHotelPassport(hash);
      }}
    }}
    window.addEventListener('hashchange', checkHashRoute);

    // Initial render
    filterAndRender();
    checkHashRoute();
  </script>
</body>
</html>
"""
    return html_content


def build_hotel_catalog(
    output_html: str = DEFAULT_OUTPUT_HTML,
    output_json: str = DEFAULT_OUTPUT_JSON,
) -> None:
    """Builds the full hotel catalog, writes JSON data and HTML dashboard."""
    hotels, stats = collect_hotel_data()
    logger.info(f"Built catalog with {len(hotels)} hotels. Stats: {stats}")

    # 1. Write JSON data
    try:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "stats": stats,
                "hotels": hotels,
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved catalog data JSON to {output_json}")
    except Exception as e:
        logger.warning(f"Error saving JSON {output_json}: {e}")

    # 2. Render HTML
    html_markup = render_hotel_catalog_html(hotels, stats)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_markup)
    logger.info(f"Successfully generated Hotel Catalog dashboard: {output_html} ({len(html_markup)} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Build Hotel Catalog Dashboard")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_HTML, help="Output HTML file path")
    parser.add_argument("--output-json", default=DEFAULT_OUTPUT_JSON, help="Output JSON file path")
    args = parser.parse_args()

    build_hotel_catalog(output_html=args.output, output_json=args.output_json)


if __name__ == "__main__":
    main()
