#!/usr/bin/env python3
"""
Hotel Entity Matcher for Cross-Border Tour Arbitrage (Germany vs Poland).

Matches hotel names across different tour operators, languages, and naming conventions:
- German OTAs (e.g., Check24, HolidayCheck): "Delphin Imperial Resort & Spa (AYT12045)"
- Polish OTAs (e.g., Fly.pl, Wakacje.pl): "Delphin Imperial Hotel Lara (Antalya)"

Pipeline:
1. Text normalization: lowercase, strip punctuation, remove common hotel stop-words
   ('hotel', 'resort', 'spa', 'beach', 'club', 'village', 'palace', 'deluxe', 'premium', 'ex.', etc.).
2. Token sort ratio & sequence similarity score.
3. Optional region / destination constraint (e.g. both must be in 'Antalya' or 'Hurghada').
4. Persistent JSON dictionary cache for O(1) repeated lookups.
"""

from __future__ import annotations

import difflib
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple


STOP_WORDS: Set[str] = {
    "hotel", "hotels", "resort", "resorts", "spa", "all", "inclusive",
    "the", "and", "und", "i", "ex", "ex.", "star", "stars", "view", "of",
}

# Major resort regions and location names that frequently appear in hotel titles.
# These identify WHERE an entity is located, but MUST NOT be used as the primary
# identity for entity matching (e.g., 'Sharm El Sheikh' is not a hotel brand).
LOCATION_WORDS: Set[str] = {
    # Egypt
    "sharm", "sheikh", "el", "naama", "nabq", "hadaba", "shark", "sharks", "bay",
    "hurghada", "makadi", "marsa", "alam", "safaga", "soma", "el-gouna", "gouna",
    "dahar", "dahab", "taba", "cairo", "luxor", "ras", "nasrani", "um", "sid",
    # Turkey
    "antalya", "lara", "kundu", "belek", "side", "kemer", "alanya", "bodrum",
    "marmaris", "fethiye", "oludeniz", "cesme", "kusadasi", "didim", "istanbul",
    "manavgat", "avsallar", "konakli", "okurcalar", "turkler", "beldibi", "goynuk",
    "kiris", "camyuva", "tekirova", "bogazkent",
    # Greece
    "rhodes", "rodos", "faliraki", "lindos", "kolymbia", "kallithea", "ixia",
    "kreta", "crete", "heraklion", "chania", "rethymno", "hersonissos", "malia",
    "corfu", "kerkyra", "kos", "zakynthos", "zante", "santorini", "mykonos",
    # Spain & Islands
    "mallorca", "majorca", "palma", "alcudia", "can", "picafort", "cala",
    "ibiza", "menorca", "tenerife", "fuerteventura", "gran", "canaria", "lanzarote",
    # Bulgaria / Others
    "burgas", "varna", "sunny", "golden", "sands", "nessebar", "sozopol", "albena",
    "zanzibar", "dubai", "abu", "dhabi", "fujairah", "sharjah", "cyprus", "paphos", "ayia", "napa",
}

# Canonical mapping for conflicting major regions
MAJOR_REGIONS: Dict[str, str] = {
    "sharm": "sharm", "sheikh": "sharm", "naama": "sharm", "nabq": "sharm", "hadaba": "sharm", "shark": "sharm", "sharks": "sharm",
    "hurghada": "hurghada", "makadi": "hurghada", "gouna": "hurghada", "safaga": "hurghada", "soma": "hurghada", "dahar": "hurghada",
    "marsa": "marsa_alam", "alam": "marsa_alam",
    "antalya": "antalya", "lara": "antalya", "kundu": "antalya",
    "belek": "belek", "bogazkent": "belek",
    "side": "side", "manavgat": "side",
    "kemer": "kemer", "beldibi": "kemer", "goynuk": "kemer", "kiris": "kemer", "camyuva": "kemer", "tekirova": "kemer",
    "alanya": "alanya", "avsallar": "alanya", "konakli": "alanya", "okurcalar": "alanya", "turkler": "alanya",
    "bodrum": "bodrum",
    "marmaris": "marmaris",
    "fethiye": "fethiye",
    "rhodes": "rhodes", "rodos": "rhodes", "faliraki": "rhodes", "lindos": "rhodes", "kolymbia": "rhodes",
    "kreta": "crete", "crete": "crete", "heraklion": "crete", "chania": "crete", "rethymno": "crete", "hersonissos": "crete",
    "corfu": "corfu", "kerkyra": "corfu",
    "kos": "kos",
    "zakynthos": "zakynthos", "zante": "zakynthos",
    "mallorca": "mallorca", "majorca": "mallorca", "palma": "mallorca", "alcudia": "mallorca",
    "ibiza": "ibiza",
    "menorca": "menorca",
    "tenerife": "tenerife",
    "fuerteventura": "fuerteventura",
    "lanzarote": "lanzarote",
    "zanzibar": "zanzibar",
    "dubai": "dubai",
    "burgas": "burgas",
    "varna": "varna",
}

# Distinctive hotel chains and brands that distinguish different hotel operators
STRONG_BRANDS: Set[str] = {
    "rixos", "pickalbatros", "albatros", "baron", "hilton", "steigenberger",
    "jaz", "sunrise", "titanic", "delphin", "sheraton", "marriott", "kempinski",
    "movenpick", "radisson", "sentido", "tui", "iberostar", "riu", "paloma",
    "voyage", "maxx", "limak", "crystal", "alva", "donna", "dobedan", "papillon",
    "akka", "swandor", "selectum", "xanadu", "gloria", "concorde", "calista",
    "mitsis", "grecotel", "aldemar", "barcelo", "melia", "h10", "lopesan",
    "sol", "cleopatra", "rotana", "novotel", "mercure", "sofitel", "swissotel",
    "hyatt", "intercontinental", "amarina", "labranda", "azur", "three", "corners",
    "aladdin", "ali", "baba",
}

# Generic hotel descriptors that may differ across OTAs without representing a different property
GENERIC_DESCRIPTORS: Set[str] = {
    "palace", "deluxe", "premium", "luxury", "royal", "grand", "park", "beach",
    "aqua", "aquapark", "club", "village", "inn", "suites", "suite", "boutique",
    "garden", "gardens", "sea", "view", "blue", "golden", "sun", "city", "centre",
    "resort", "hotel", "spa",
}

DEFAULT_CACHE_FILE = "hotel_crossborder_mapping.json"
DEFAULT_SIMILARITY_THRESHOLD = 0.78


def clean_hotel_name(raw_name: str) -> str:
    """
    Cleans raw hotel name into canonical search tokens:
    - Strips operator suffixes and codes like (AYT12045) or (ex. Sunshine)
    - Removes punctuation and extra whitespace
    - Lowercases text and filters pure noise
    """
    if not raw_name or not isinstance(raw_name, str):
        return ""

    text = raw_name.lower().strip()

    # Strip parentheses contents if they look like operator codes or former names: (ex. ...) or (AYT...)
    text = re.sub(r"\((?:ex\.?|dawniej)?[^)]*\)", " ", text)
    # Strip brackets
    text = re.sub(r"\[[^\]]*\]", " ", text)
    # Replace hyphens, slashes, ampersands with space
    text = re.sub(r"[-_/,+&.]", " ", text)
    # Remove non-alphanumeric except spaces
    text = re.sub(r"[^\w\s]", " ", text)

    tokens = [t.strip() for t in text.split() if t.strip()]
    meaningful = [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

    # If all tokens were filtered out, keep non-trivial tokens
    if not meaningful:
        meaningful = [t for t in tokens if len(t) > 1]

    return " ".join(sorted(meaningful))


def calculate_hotel_similarity(name1: str, name2: str) -> float:
    """
    Computes a composite similarity ratio [0.0, 1.0] between two hotel names.
    Enforces Brand Guard, Location Words separation, and chain sub-property conflict resolution.
    """
    c1 = clean_hotel_name(name1)
    c2 = clean_hotel_name(name2)

    if not c1 or not c2:
        return 0.0

    if c1 == c2:
        return 1.0

    raw1_tokens = set(c1.split())
    raw2_tokens = set(c2.split())

    # 1. Geographic Conflict Check: different major regions cannot match
    r1 = set(MAJOR_REGIONS[t] for t in raw1_tokens if t in MAJOR_REGIONS)
    r2 = set(MAJOR_REGIONS[t] for t in raw2_tokens if t in MAJOR_REGIONS)
    if r1 and r2 and not (r1.intersection(r2)):
        return 0.0

    # 2. Brand Conflict Check: two different strong brands cannot match (e.g. Rixos vs Baron)
    b1 = raw1_tokens.intersection(STRONG_BRANDS)
    b2 = raw2_tokens.intersection(STRONG_BRANDS)
    if b1 and b2 and not (b1.intersection(b2)):
        return 0.0

    # 3. Core Tokens: separate distinctive hotel identity from pure location tokens
    core1 = set(t for t in raw1_tokens if t not in LOCATION_WORDS)
    core2 = set(t for t in raw2_tokens if t not in LOCATION_WORDS)
    if not core1:
        core1 = set(raw1_tokens)
    if not core2:
        core2 = set(raw2_tokens)

    # 4. Zero Core Overlap: if two hotels have no non-location words in common, they cannot match
    inter = core1.intersection(core2)
    if not inter:
        return 0.0

    # 5. Chain Sub-Property Conflict Check:
    # If both hotels belong to the same chain (e.g. 'sunrise'), but their specific property names
    # are completely distinct (e.g. 'remal' vs 'diamond'), they are DIFFERENT hotels in that chain.
    if b1 and b2 and (b1 == b2):
        non_b1 = core1 - b1 - GENERIC_DESCRIPTORS
        non_b2 = core2 - b2 - GENERIC_DESCRIPTORS
        if non_b1 and non_b2 and not (non_b1.intersection(non_b2)):
            return 0.35

    # 6. Jaccard & Containment Overlap on Core Tokens
    union = core1.union(core2)
    jaccard = len(inter) / max(1, len(union))

    if core1.issubset(core2) or core2.issubset(core1):
        diff = core1 ^ core2
        # Subset boost is only permitted if differences are generic descriptors
        if diff.issubset(GENERIC_DESCRIPTORS):
            jaccard = max(jaccard, 0.90)

    # 7. Sequence similarity on sorted canonical strings
    str1 = " ".join(sorted(core1))
    str2 = " ".join(sorted(core2))
    seq_ratio = difflib.SequenceMatcher(None, str1, str2).ratio()

    # Composite score
    score = 0.60 * jaccard + 0.40 * seq_ratio
    return round(score, 3)


class HotelEntityMatcher:
    def __init__(
        self,
        cache_file: str = DEFAULT_CACHE_FILE,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ):
        self.cache_file = cache_file
        self.similarity_threshold = similarity_threshold
        self.mappings: Dict[str, str] = {}  # polish_name -> german_name
        self._load_cache()

    def _load_cache(self) -> None:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.mappings = json.load(f)
            except Exception:
                self.mappings = {}

    def save_cache(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.mappings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def match_hotel(
        self,
        target_name: str,
        candidate_names: List[str],
        destination: Optional[str] = None,
    ) -> Optional[Tuple[str, float]]:
        """
        Finds the best matching hotel name from a list of candidate names.
        Returns:
            (best_matched_candidate, similarity_score) or None
        """
        if not target_name or not candidate_names:
            return None

        # Check cache
        if target_name in self.mappings:
            cached = self.mappings[target_name]
            if cached in candidate_names:
                return (cached, 1.0)

        best_candidate: Optional[str] = None
        best_score = 0.0

        for cand in candidate_names:
            score = calculate_hotel_similarity(target_name, cand)
            if score > best_score:
                best_score = score
                best_candidate = cand

        if best_candidate and best_score >= self.similarity_threshold:
            self.mappings[target_name] = best_candidate
            return (best_candidate, best_score)

        return None

    def match_all_pairs(
        self,
        polish_hotels: List[str],
        german_hotels: List[str],
    ) -> Dict[str, Tuple[str, float]]:
        """
        Matches a list of Polish hotel names against German candidate names.
        Returns mapping: {pl_hotel: (de_hotel, score)}
        """
        matched: Dict[str, Tuple[str, float]] = {}
        unique_pl = list(set(polish_hotels))
        unique_de = list(set(german_hotels))

        for pl_h in unique_pl:
            res = self.match_hotel(pl_h, unique_de)
            if res:
                matched[pl_h] = res

        return matched
