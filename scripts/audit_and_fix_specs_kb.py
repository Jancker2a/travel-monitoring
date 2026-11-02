#!/usr/bin/env python3
"""
Hotel Specifications & Infrastructure Knowledge Base Audit and Sanity Engine.

Audits, cleanses, and verifies hotel_specs_kb.json against:
1. Anti-hallucination checks (Beach line vs Shuttle / Distance / Inland geography).
2. Heated pools sanity (Cross-referenced with reputation KB and negative pool flags).
3. Bay & Wind shelter classification (Accurate Sharm/Hurghada winter bay mapping).
4. Template / Canned response removal.
5. Consistent normalization across the entire hotel catalog.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("specs_auditor")

SPECS_FILE = "hotel_specs_kb.json"
REPUTATION_FILE = "hotel_reputation_kb.json"

# Known inland / 2nd-3rd line resort indicators
INLAND_KEYWORDS = [
    r"\b(city|inn|suites|apartments?|gardens?|hills?|residences?|village|park)\b",
    r"\b(old vic|coral hills|falcon hills|falcon naama|delta sharm|verginia sharm|sharm cliff)\b",
    r"\b(tivoli|sharm holiday|amphoras aqua|albatros aqua blu|albatros aqua park)\b",
    r"\b(parrotel aqua park|palma dive|eden rock|halomy|sharm reef|dive inn)\b",
    r"\b(solymar naama|jaz fanara residence|regency lodge|sunset)\b",
]

# Known Sharm El Sheikh bays
SHARM_BAYS = {
    "nabq": ["nabq", "набк", "parrotel", "barcelo tiran", "regency plaza", "aurora oriental", "charmillion", "sea life", "sea club"],
    "naama": ["naama", "наама", "maritim jolie ville", "novotel sharm", "movenpick sharm", "marina sharm", "tropitel naama"],
    "hadaba_ras_um_sid": ["hadaba", "хадаба", "ras um sid", "рас ум сид", "fanara", "renaissance", "albatros sharm", "reef oasis beach", "jaz fanara"],
    "sharks_bay": ["sharks bay", "шаркс бэй", "sultan gardens", "concorde el salam", "island view", "savoy", "sierra", "grand rotana"],
    "sharm_el_maya": ["sharm el maya", "шарм-эль-майя", "старый город", "old vic", "seti sharm", "albatros aqua park", "aqua blu"],
    "ras_nasrani": ["ras nasrani", "рас насрани", "baron resort", "cyrene", "coral sea imperial", "sensatori"],
    "pasha_coast": ["pasha", "паша", "sheraton sharm", "continental plaza", "hyatt regency"],
}

# Known Hurghada bays / regions
HURGHADA_BAYS = {
    "makadi_bay": ["makadi", "макади", "cleopatra luxury makadi", "jaz makadi", "prima life", "sunrise makadi", "labranda makadi"],
    "soma_bay": ["soma bay", "сома бэй", "sheraton soma", "kempinski soma", "robinson soma", "caribbean world"],
    "sahl_hasheesh": ["sahl hasheesh", "сахл хашиш", "baron palace", "gravity", "tropitel sahl", "albatros citadel"],
    "el_gouna": ["el gouna", "эль гуна", "movenpick gouna", "steigenberger golf", "sheraton miramar"],
}


def audit_and_cleanse_specs(specs_path: str = SPECS_FILE, rep_path: str = REPUTATION_FILE) -> Dict[str, Any]:
    """Runs deep audit on hotel_specs_kb.json, repairing hallucinations and discrepancies."""
    if not os.path.exists(specs_path):
        logger.error(f"Specs file {specs_path} not found!")
        return {}

    with open(specs_path, "r", encoding="utf-8") as f:
        kb_data = json.load(f)

    rep_hotels = {}
    if os.path.exists(rep_path):
        with open(rep_path, "r", encoding="utf-8") as f:
            rep_hotels = json.load(f).get("hotels", {})

    hotels = kb_data.get("hotels", {})
    logger.info(f"Loaded {len(hotels)} hotels from {specs_path} for verification audit.")

    fixed_beach_lines = 0
    fixed_heated_pools = 0
    fixed_aquaparks = 0
    enriched_bays = 0
    cleansed_canned = 0

    for h_name, entry in hotels.items():
        specs = entry.get("specs")
        if not specs or not isinstance(specs, dict):
            continue

        h_lower = h_name.lower()
        country = (entry.get("destination") or "").lower()

        # Cross-reference with reputation KB
        rep_entry = rep_hotels.get(h_name, {})
        rep_winter = rep_entry.get("winter_suitability", {})
        rep_cons = " ".join(rep_entry.get("cons_and_red_flags", [])).lower()
        spec_cautions = " ".join([str(c) for c in (specs.get("caution_notes") or [])]).lower()
        spec_highlights = " ".join([str(h) for h in (specs.get("highlights") or [])]).lower()

        # ----------------------------------------------------
        # 1. BEACH LINE VERIFICATION & ANTI-HALLUCINATION
        # ----------------------------------------------------
        cur_line = specs.get("beach_line")

        # Is inland by name / shuttle / distance?
        is_inland = any(re.search(pat, h_lower) for pat in INLAND_KEYWORDS)
        has_shuttle_mention = ("шаттл" in spec_cautions or "шаттл" in spec_highlights or 
                               "автобус" in spec_cautions or "автобус" in spec_highlights or
                               "2-я линия" in spec_cautions or "3-я линия" in spec_cautions or
                               "до моря" in spec_cautions)

        if (is_inland or has_shuttle_mention) and cur_line == 1:
            # Determine whether 2nd or 3rd line
            if "old vic" in h_lower or "falcon hills" in h_lower or "delta sharm" in h_lower or "2.5" in spec_cautions:
                new_line = 3
                dist = 2500
            elif "aqua park" in h_lower or "aqua blu" in h_lower:
                new_line = 2
                dist = 600
            else:
                new_line = 2
                dist = 450

            specs["beach_line"] = new_line
            specs["beach_distance_meters"] = dist
            specs["shuttle_bus"] = "free"
            fixed_beach_lines += 1

            # Remove conflicting "прямой доступ к пляжу" if present
            specs["highlights"] = [h for h in (specs.get("highlights") or []) if "прямой доступ к пляжу" not in str(h).lower()]
            if not any("шаттл" in str(c).lower() or "линия" in str(c).lower() for c in (specs.get("caution_notes") or [])):
                specs.setdefault("caution_notes", []).append(f"{new_line}-я линия: до пляжа курсирует бесплатный шаттл-бас")
        else:
            if cur_line == 1:
                specs["beach_distance_meters"] = 0
                specs["shuttle_bus"] = "none"
            elif cur_line == 2:
                specs.setdefault("beach_distance_meters", 400)
                specs.setdefault("shuttle_bus", "free")
            elif cur_line == 3:
                specs.setdefault("beach_distance_meters", 2000)
                specs.setdefault("shuttle_bus", "free")

        # ----------------------------------------------------
        # 2. HEATED POOLS SANITY CHECK
        # ----------------------------------------------------
        cur_heated = bool(specs.get("heated_pools_winter"))
        no_heat_flag = ("без подогрева" in spec_cautions or 
                        "отсутствие гарантированного подогрева" in spec_cautions or 
                        "отсутствие гарантированного подогрева" in rep_cons or
                        "без подогрева" in rep_cons or
                        "холодные бассейны" in rep_cons)
        
        explicit_rep_no_heat = (rep_winter.get("heated_pools") is False)

        if cur_heated and (no_heat_flag or explicit_rep_no_heat):
            # Check if this is an economy 3-4 star hotel
            if entry.get("stars", 4) <= 4 or is_inland or explicit_rep_no_heat:
                specs["heated_pools_winter"] = False
                fixed_heated_pools += 1
                # Ensure caution notes mention unheated pools
                if not any("подогрев" in str(c).lower() for c in (specs.get("caution_notes") or [])):
                    specs.setdefault("caution_notes", []).append("Бассейны без постоянного зимнего подогрева")

        # ----------------------------------------------------
        # 3. AQUAPARK ACCURACY
        # ----------------------------------------------------
        cur_aqua = bool(specs.get("aquapark"))
        has_aqua_in_name = bool(re.search(r"aqua\s*park|water\s*park|аквапарк", h_lower))
        has_slides_in_hl = any("аквапарк" in str(h).lower() or "горк" in str(h).lower() for h in (specs.get("highlights") or []))

        # If flagged as aquapark but hotel is 3-star or small city hotel without slides in highlights or name
        if cur_aqua and not has_aqua_in_name and not has_slides_in_hl:
            if is_inland or (specs.get("pool_count") or 1) <= 2:
                specs["aquapark"] = False
                fixed_aquaparks += 1

        # ----------------------------------------------------
        # 4. BAY & WIND SHELTER RESOLUTION (EGYPT)
        # ----------------------------------------------------
        if "египет" in country or "egypt" in country:
            resolved_bay = None
            resolved_wind = None

            # Sharm El Sheikh check
            for b_name, b_keywords in SHARM_BAYS.items():
                if any(kw in h_lower for kw in b_keywords):
                    resolved_bay = b_name
                    if b_name == "nabq":
                        resolved_wind = "windy"
                    elif b_name in ("sharm_el_maya", "naama"):
                        resolved_wind = "protected"
                    else:
                        resolved_wind = "moderate"
                    break

            # Hurghada check
            if not resolved_bay:
                for b_name, b_keywords in HURGHADA_BAYS.items():
                    if any(kw in h_lower for kw in b_keywords):
                        resolved_bay = b_name
                        resolved_wind = "moderate"
                        break

            if resolved_bay:
                specs["bay"] = resolved_bay
                specs["wind_shelter"] = resolved_wind
                enriched_bays += 1

                # If windy bay Nabq, add caution note if not present
                if resolved_wind == "windy" and not any("ветр" in str(c).lower() or "понтон" in str(c).lower() for c in (specs.get("caution_notes") or [])):
                    specs.setdefault("caution_notes", []).append("Бухта Набк: зимой возможен сильный ветер и частый красный флаг")

        # ----------------------------------------------------
        # 5. ANTI-TEMPLATE & CANNED PHRASE SCRUBBER
        # ----------------------------------------------------
        cleaned_hl = []
        canned_phrases = [
            "песчано-галечный пляж с удобным входом в море",
            "стандартная детская площадка",
            "умеренная ветровая защита",
            "стандартный зимний комфорт",
            "стабильное качество обслуживания",
        ]
        for hl in (specs.get("highlights") or []):
            hl_str = str(hl).strip()
            if not any(cp in hl_str.lower() for cp in canned_phrases):
                cleaned_hl.append(hl_str)
            else:
                cleansed_canned += 1
        specs["highlights"] = cleaned_hl

    # Update metadata
    kb_data["verified_at"] = datetime.utcnow().isoformat() + "Z"
    kb_data["audit_version"] = "2.0_verified"
    kb_data["total_enriched"] = sum(1 for h in hotels.values() if h.get("is_enriched"))
    kb_data["total_hotels"] = len(hotels)

    # Save cleansed file atomically
    tmp_path = f"{specs_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, specs_path)

    logger.info("=== AUDIT AND SANITY RESULTS ===")
    logger.info(f"Fixed Beach Lines (hallucinated 1st line -> 2nd/3rd): {fixed_beach_lines}")
    logger.info(f"Fixed Heated Pools (hallucinated heat -> false): {fixed_heated_pools}")
    logger.info(f"Fixed Aquaparks (hallucinated aquapark -> false): {fixed_aquaparks}")
    logger.info(f"Enriched Bays & Wind Shelter: {enriched_bays}")
    logger.info(f"Cleansed Canned Template Phrases: {cleansed_canned}")
    logger.info(f"Successfully saved audited knowledge base to {specs_path}")

    return {
        "fixed_beach_lines": fixed_beach_lines,
        "fixed_heated_pools": fixed_heated_pools,
        "fixed_aquaparks": fixed_aquaparks,
        "enriched_bays": enriched_bays,
        "cleansed_canned": cleansed_canned,
        "total_hotels": len(hotels),
    }


if __name__ == "__main__":
    audit_and_cleanse_specs()
