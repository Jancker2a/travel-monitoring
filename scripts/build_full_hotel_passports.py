"""
Compile full, authentic, ready-to-render hotel passports for all hotels in hotel_specs_kb.json.
Uses the single-source-of-truth compiler in scripts.hotel_passport_compiler.
Stores complete 'passport' block so the UI uses 100% pre-compiled truth with ZERO runtime mapping.
"""

import json
import os
import sys

# Ensure repository root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.hotel_passport_compiler import compile_hotel_passport

KB_PATH = "hotel_specs_kb.json"

def main():
    if not os.path.exists(KB_PATH):
        print(f"Error: {KB_PATH} not found.")
        return

    with open(KB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    hotels = data.get("hotels", data)
    count = 0
    for name, hdata in hotels.items():
        passport = compile_hotel_passport(name, hdata)
        if "specs" not in hdata:
            hdata["specs"] = {}
        hdata["specs"]["passport"] = passport
        count += 1

    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Successfully compiled complete passports for {count} hotels in {KB_PATH}.")

if __name__ == "__main__":
    main()
