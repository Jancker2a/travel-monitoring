#!/usr/bin/env python3
"""
Hotel Name Normalizer and Canonical Entity Resolution.

Handles multi-operator name variations across Fly.pl, Wakacje.pl, Check24, etc.
- Strips legacy hotel tags: (ex. ...), (dawniej ...), (ehem. ...)
- Strips location tags in parentheses: (Alanya), (Side), (Hurghada), etc.
- Strips star ratings: 5*, 4*, ****, etc.
- Produces clean canonical_name and URL-safe slug.
- Provides two-phase deduplication:
    Phase 1: Exact match by normalized canonical name.
    Phase 2: Fuzzy similarity match (threshold >= 0.85) + writes hotel_aliases_review.json.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from hotel_entity_matcher import calculate_hotel_similarity
except ImportError:
    calculate_hotel_similarity = None

logger = logging.getLogger("hotel_normalizer")

# Known prefixes / suffixes inside parentheses to strip
EX_PATTERN = re.compile(
    r"\s*\((?:ex\.?|dawniej|ehem\.?|formerly|previously|prev\.?)[^)]*\)",
    re.IGNORECASE,
)
PAREN_LOCATION_PATTERN = re.compile(
    r"\s*\((?:alanya|side|kemer|belek|antalya|lara|kundu|manavgat|avsallar|hurghada|sharm|sharm el sheikh|makadi|marsa alam|el gouna|paphos|ayia napa|limassol|larnaca|rhodes|rodos|crete|kreta|heraklion|chania|corfu|kos|mallorca|ibiza|tenerife|burgas|varna)[^)]*\)",
    re.IGNORECASE,
)
STAR_PATTERN = re.compile(
    r"\s*(?:[1-5]\*|\*{1,5}|[1-5]\s*gwiazd(?:ki|ek)?(?:\b|$))(?:\s+|$)",
    re.IGNORECASE,
)
GEO_EXTRA_PATTERN = re.compile(
    r"\b(?:alanya|side|kemer|belek|antalya|lara|kundu|manavgat|avsallar|okurcalar|hurghada|sharm el sheikh|sharm|makadi bay|makadi|marsa alam|el gouna|paphos|ayia napa|limassol|larnaca)\b",
    re.IGNORECASE,
)

# Generic descriptor words that can vary across tour operators
GENERIC_SUFFIX_WORDS = [
    "hotel & resort",
    "resort & spa",
    "hotel & spa",
    "resort & aqua park",
    "aqua park & resort",
    "beach resort & spa",
    "resort and spa",
    "hotel and resort",
    "resort and aqua park",
    "hotel",
    "resort",
    "spa",
    "beach",
    "club",
    "palace",
    "deluxe",
    "suites",
    "village",
]


def clean_hotel_title(name: str) -> str:
    """
    Cleans raw hotel title by removing parenthetical ex-names, stars, and location tags,
    returning a clean display title.
    """
    if not name:
        return ""
    text = str(name).strip()

    # 1. Strip (ex. ...)
    text = EX_PATTERN.sub("", text)

    # 2. Strip location in parentheses: (Alanya), (Side), etc.
    text = PAREN_LOCATION_PATTERN.sub("", text)

    # 3. Strip any remaining empty parentheses: ()
    text = re.sub(r"\s*\(\s*\)", "", text)

    # 4. Strip star notations: 5*, 4*, ****
    text = STAR_PATTERN.sub("", text)

    # 5. Clean up duplicate spaces and punctuation
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return text


def slugify_hotel_name(name: str) -> str:
    """
    Generates a deterministic, clean, URL-safe slug for a hotel name.
    Preserves core brand words while removing noise.
    """
    cleaned = clean_hotel_title(name)
    # Remove apostrophes / quotes
    cleaned = re.sub(r"['\"`]", "", cleaned)
    # Replace non-alphanumeric with hyphen
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", cleaned.lower()).strip("-")
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug or "hotel"


def normalize_for_matching(name: str) -> str:
    """
    Normalizes hotel title for canonical identity matching:
    - Clean title
    - Lowercase
    - Strip common generic hotel words (hotel, resort, spa, etc.)
    - Strip location words
    - Sort tokens to be order-independent
    """
    cleaned = clean_hotel_title(name).lower()

    # Replace punctuation with space
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)

    tokens = [t for t in cleaned.split() if len(t) > 1]
    # Remove generic filler words
    stop_tokens = {
        "hotel", "hotels", "resort", "resorts", "spa", "beach", "club",
        "palace", "deluxe", "village", "suites", "and", "und", "the",
        "all", "inclusive", "park", "aqua", "aquapark",
    }
    filtered = [t for t in tokens if t not in stop_tokens]
    if not filtered:
        # Fallback to all tokens if everything was filtered
        filtered = tokens

    # Sort tokens to handle "Imperial Delphin" vs "Delphin Imperial"
    return " ".join(sorted(filtered))


class HotelCanonicalRegistry:
    """
    Manages canonical hotel entity resolution and deduplication across monitors.
    """

    def __init__(self, review_file: str = "hotel_aliases_review.json"):
        self.review_file = review_file
        # slug -> canonical hotel dict
        self._canonical_hotels: Dict[str, Dict[str, Any]] = {}
        # normalized_key -> slug
        self._normalized_index: Dict[str, str] = {}
        # list of potential aliases detected during fuzzy matching
        self._aliases_to_review: List[Dict[str, Any]] = []

    def register_hotel(
        self,
        raw_name: str,
        destination: str = "",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Resolves raw hotel name to a canonical hotel entity.
        Performs Phase 1 exact match and Phase 2 fuzzy matching.
        """
        raw_clean = clean_hotel_title(raw_name)
        norm_key = normalize_for_matching(raw_name)
        target_slug = slugify_hotel_name(raw_clean)

        # Phase 1: Exact match on normalized token key
        if norm_key in self._normalized_index:
            existing_slug = self._normalized_index[norm_key]
            canonical = self._canonical_hotels[existing_slug]
            if raw_name not in canonical["aliases"]:
                canonical["aliases"].append(raw_name)
            return canonical

        # Phase 1b: Exact match on slug
        if target_slug in self._canonical_hotels:
            canonical = self._canonical_hotels[target_slug]
            self._normalized_index[norm_key] = target_slug
            if raw_name not in canonical["aliases"]:
                canonical["aliases"].append(raw_name)
            return canonical

        # Phase 2: Fuzzy match across existing canonical entities (threshold >= 0.85)
        best_match_slug = None
        best_score = 0.0

        for slug, cand in self._canonical_hotels.items():
            if calculate_hotel_similarity:
                ratio = calculate_hotel_similarity(raw_clean, cand["canonical_name"])
            else:
                cand_norm = cand["normalized_key"]
                ratio = difflib.SequenceMatcher(None, norm_key, cand_norm).ratio()

            if ratio > best_score:
                best_score = ratio
                best_match_slug = slug

        if best_match_slug and best_score >= 0.85:
            matched_canonical = self._canonical_hotels[best_match_slug]
            if raw_name not in matched_canonical["aliases"]:
                matched_canonical["aliases"].append(raw_name)
            self._normalized_index[norm_key] = best_match_slug

            # Record in aliases review
            self._aliases_to_review.append({
                "raw_name": raw_name,
                "canonical_name": matched_canonical["canonical_name"],
                "canonical_slug": best_match_slug,
                "similarity_score": round(best_score, 3),
                "norm_key": norm_key,
                "cand_norm": self._canonical_hotels[best_match_slug]["normalized_key"],
            })
            return matched_canonical

        # Brand new canonical entity
        canonical_record = {
            "slug": target_slug,
            "canonical_name": raw_clean,
            "normalized_key": norm_key,
            "destination": destination,
            "aliases": [raw_name],
            "extra_meta": extra_meta or {},
        }
        self._canonical_hotels[target_slug] = canonical_record
        self._normalized_index[norm_key] = target_slug
        return canonical_record

    def get_canonical(self, slug: str) -> Optional[Dict[str, Any]]:
        return self._canonical_hotels.get(slug)

    def all_hotels(self) -> List[Dict[str, Any]]:
        return list(self._canonical_hotels.values())

    def save_review_manifest(self) -> None:
        """Saves fuzzy matched aliases for transparency and review."""
        if not self._aliases_to_review:
            return
        try:
            with open(self.review_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "total_fuzzy_matches": len(self._aliases_to_review),
                        "matches": self._aliases_to_review,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info(f"Saved {len(self._aliases_to_review)} alias review candidates to {self.review_file}")
        except Exception as e:
            logger.warning(f"Could not save aliases review file: {e}")
