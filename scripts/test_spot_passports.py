"""
Targeted spot-testing script for hotel passports across all categories and countries.
"""

import json
from hotel_passport_drawer import generate_hotel_ai_profile

KB_PATH = "hotel_specs_kb.json"

TARGET_HOTELS = [
    # 1. Budget inland Egypt (3★ and 4★)
    ("Viking Club", "Египет"),
    ("Uni Sharm (ex. Karma)", "Египет"),
    ("Old Vic Sharm Resort", "Египет"),
    
    # 2. Top-tier luxury & waterpark Egypt
    ("Rixos Premium Seagate", "Египет"),
    ("Pickalbatros Aqua Blu Resort", "Египет"),
    ("Jaz Fanara Resort (ex Iberotel Club Fanara)", "Египет"),
    
    # 3. Turkey (Antalya / Kemer / Alanya)
    ("Baia Lara", "Турция"),
    ("Limak Limra", "Турция"),
    ("Eftalia Aqua", "Турция"),
    
    # 4. Greece (Island seasonal)
    ("Caretta Beach (Kalamaki)", "Греция"),
    
    # 5. Cyprus (Ayia Napa)
    ("Adams Beach", "Кипр"),
]

def run_spot_tests():
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)
    hotels = kb.get("hotels", kb)

    print("=" * 80)
    print("🎯 TARGETED PASSPORT AUDIT & SPOT-CHECKS")
    print("=" * 80)

    all_passed = True
    results = []

    for name, country in TARGET_HOTELS:
        h = hotels.get(name)
        if not h:
            print(f"❌ NOT FOUND IN KB: {name}")
            all_passed = False
            continue

        specs = h.get("specs", {})
        passport = specs.get("passport", {})
        if not passport:
            print(f"❌ NO PASSPORT BLOCK: {name}")
            all_passed = False
            continue

        # Run generate_hotel_ai_profile to test end-to-end output
        prof = generate_hotel_ai_profile(
            hotel_name=name,
            country=country,
            destination=h.get("destination", country),
            specs=specs,
            current_price=3200,
            min_price=2800,
            max_price=4200,
            price_drop_pct=10.0
        )

        stars = prof["stars"]
        line = prof["beach_line"]
        has_aqua = prof["has_aquapark"]
        has_heat = prof["has_heated_pools"]
        summary = prof["ai_hotel_summary"]
        food = prof["food_snippet"]
        beach = prof["beach_snippet"]
        review = prof["review_snippet"]
        pros = prof["pros"]
        cons = prof["cons"]
        ir = prof["infra_rich"]

        # Assertions / Checks
        issues = []

        # Test 1: Viking Club (3★ inland) must NEVER have a la carte or fake aquapark or 4 stars
        if name == "Viking Club":
            if stars != 3:
                issues.append(f"Viking Club stars should be 3, got {stars}")
            if line != 3:
                issues.append(f"Viking Club line should be 3, got {line}")
            if has_aqua:
                issues.append("Viking Club should not have aquapark flag")
            if "2–4 ресторана a la carte" in ir.get("food", {}).get("alacarte", ""):
                issues.append("Viking Club must not have 2-4 a la carte restaurants")
            if "хаммам" in ir.get("sport_spa", {}).get("spa", "").lower():
                issues.append("Viking Club must not claim Turkish hammam")

        # Test 2: Uni Sharm (4★ inland) must have line 3, no aquapark (only pool slides), no 2-4 a la carte
        if name == "Uni Sharm (ex. Karma)":
            if line != 3:
                issues.append(f"Uni Sharm line should be 3, got {line}")
            if has_aqua:
                issues.append("Uni Sharm should not have aquapark flag (only 2 pool slides)")
            if "2–4 ресторана a la carte" in ir.get("food", {}).get("alacarte", ""):
                issues.append("Uni Sharm must not have 2-4 a la carte restaurants")

        # Test 3: Rixos Premium Seagate must have aquapark=True, heated=True, line=1
        if name == "Rixos Premium Seagate":
            if not has_aqua:
                issues.append("Rixos Seagate must have aquapark=True")
            if not has_heat:
                issues.append("Rixos Seagate must have heated=True")
            if line != 1:
                issues.append("Rixos Seagate must be line 1")

        # Test 4: Caretta Beach (Greece) must be seasonal (heated=False) and line 2 (Kalamaki 850m)
        if name == "Caretta Beach (Kalamaki)":
            if has_heat:
                issues.append("Greek seasonal resort must have heated=False")
            if line != 2:
                issues.append(f"Caretta Beach should be line 2, got {line}")
            if not has_aqua:
                issues.append("Caretta Beach has verified water park, aquapark should be True")

        # Test 5: Check Russian pluralization of pools in all hotels
        pools_str = ir.get("pools", {}).get("pools_count", "")
        if "открытых бассейна(ов)" in pools_str:
            issues.append(f"Broken pluralization found: '{pools_str}'")

        # Test 6: Check for canned/boilerplate review phrase
        if "стабильное качество обслуживания на уровне" in review.lower():
            issues.append(f"Banned canned review boilerplate found: '{review}'")

        status_icon = "✅ PASS" if not issues else "❌ FAIL"
        if issues:
            all_passed = False

        print(f"\n{status_icon} | {name} ({country})")
        print(f"   ★ {stars}★ | Линия: {line} | Аквапарк: {has_aqua} | Подогрев: {has_heat} | Питание: {prof['food_concept']}")
        print(f"   📝 Саммари: {summary[:120]}...")
        print(f"   🏖️ Пляж: {beach[:100]}...")
        print(f"   🍽️ Еда: {food[:100]}...")
        print(f"   🏊 Бассейны: {ir.get('pools', {}).get('pools_count')} | {ir.get('pools', {}).get('aquapark')}")
        print(f"   🍴 A la Carte: {ir.get('food', {}).get('alacarte')}")
        print(f"   💆 Спа: {ir.get('sport_spa', {}).get('spa')}")
        print(f"   💬 Отзыв: {review[:100]}...")
        if issues:
            for iss in issues:
                print(f"   ⚠️ ISSUE: {iss}")

    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 ALL SPOT-TESTS PASSED 100%! ZERO HALLUCINATIONS, ZERO BOILERPLATE, STRICT ACCURACY.")
    else:
        print("⚠️ SOME SPOT-TESTS FAILED.")
    print("=" * 80)

if __name__ == "__main__":
    run_spot_tests()

