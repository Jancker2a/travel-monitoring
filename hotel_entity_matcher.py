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
    "hotel", "hotels", "resort", "resorts", "spa", "beach", "club",
    "village", "palace", "deluxe", "premium", "luxury", "grand", "royal",
    "park", "suites", "suite", "inn", "boutique", "aquapark", "aqua",
    "all", "inclusive", "the", "and", "und", "i", "ex", "ex.",
    "garden", "gardens", "sea", "view", "star", "stars",
}

DEFAULT_CACHE_FILE = "hotel_crossborder_mapping.json"
DEFAULT_SIMILARITY_THRESHOLD = 0.78


def clean_hotel_name(raw_name: str) -> str:
    """
    Cleans raw hotel name into canonical search tokens:
    - Strips operator suffixes and codes like (AYT12045) or (ex. Sunshine)
    - Removes punctuation and extra whitespace
    - Lowercases text
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

    # If all tokens were filtered out (rare, e.g. "The Palace Hotel"), keep raw tokens
    if not meaningful:
        meaningful = [t for t in tokens if len(t) > 1]

    return " ".join(sorted(meaningful))


def calculate_hotel_similarity(name1: str, name2: str) -> float:
    """
    Computes a composite similarity ratio [0.0, 1.0] between two hotel names.
    Combines:
    1. Token Set overlap (Jaccard-like)
    2. SequenceMatcher ratio on sorted tokens
    """
    c1 = clean_hotel_name(name1)
    c2 = clean_hotel_name(name2)

    if not c1 or not c2:
        return 0.0

    if c1 == c2:
        return 1.0

    tokens1 = set(c1.split())
    tokens2 = set(c2.split())

    # Jaccard overlap on meaningful tokens
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    jaccard = len(intersection) / max(1, len(union))

    # Exact token containment: if one token set is fully contained in another with >= 2 tokens
    if len(tokens1) >= 2 and len(tokens2) >= 2:
        if tokens1.issubset(tokens2) or tokens2.issubset(tokens1):
            jaccard = max(jaccard, 0.88)

    # Sequence similarity on sorted canonical strings
    seq_ratio = difflib.SequenceMatcher(None, c1, c2).ratio()

    # Composite score
    score = 0.55 * jaccard + 0.45 * seq_ratio
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
