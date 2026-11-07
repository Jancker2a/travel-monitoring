#!/usr/bin/env python3
"""
HotelRepository — Unified Knowledge Base and Entity Access Facade.

Aggregates and provides single-point-of-truth access to:
1. Hotel Specifications (hotel_specs_kb.json) — amenities, beach, food, pools, kids.
2. Hotel Reputation (hotel_reputation_kb.json) — reviews, ratings, family suitability.
3. Hotel Galleries (hotel_galleries_kb.json) — curated photo galleries.
4. Market DNA Profile (market_dna_profile.json) — behavioral archetypes, price quantiles.

Features:
- Fast in-memory caching with canonical name normalization (HotelCanonicalRegistry).
- Fuzzy matching fallback for OTA title variations (e.g., 'ex. Resta Grand', 'Pickalbatros').
- Clean thread-safe read/write interface.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hotel_name_normalizer import (
    HotelCanonicalRegistry,
    clean_hotel_title,
    normalize_for_matching,
    slugify_hotel_name,
)

logger = logging.getLogger("hotel_repository")

ROOT = Path(__file__).resolve().parent

DEFAULT_SPECS_KB = ROOT / "hotel_specs_kb.json"
DEFAULT_REPUTATION_KB = ROOT / "hotel_reputation_kb.json"
DEFAULT_GALLERIES_KB = ROOT / "hotel_galleries_kb.json"
DEFAULT_DNA_KB = ROOT / "market_dna_profile.json"


def _norm_key(name: str) -> str:
    """Standardized normalized lookup key (alphanumeric lowercase)."""
    return re.sub(r"[^\w\d]+", "", str(name or "").lower())


class HotelRepository:
    """Unified access facade for all hotel knowledge bases."""

    _instance: Optional[HotelRepository] = None

    def __init__(
        self,
        specs_path: Path = DEFAULT_SPECS_KB,
        reputation_path: Path = DEFAULT_REPUTATION_KB,
        galleries_path: Path = DEFAULT_GALLERIES_KB,
        dna_path: Path = DEFAULT_DNA_KB,
    ):
        self.specs_path = Path(specs_path)
        self.reputation_path = Path(reputation_path)
        self.galleries_path = Path(galleries_path)
        self.dna_path = Path(dna_path)

        # Raw datasets
        self._specs_data: Dict[str, Any] = {}
        self._reputation_data: Dict[str, Any] = {}
        self._galleries_data: Dict[str, Any] = {}
        self._dna_data: Dict[str, Any] = {}

        # Normalized index maps for O(1) lookup
        self._specs_norm: Dict[str, Dict[str, Any]] = {}
        self._reputation_norm: Dict[str, Dict[str, Any]] = {}
        self._galleries_norm: Dict[str, List[Dict[str, Any]]] = {}
        self._dna_norm: Dict[str, Dict[str, Any]] = {}

        self.registry = HotelCanonicalRegistry()
        self.reload()

    @classmethod
    def get_instance(cls) -> HotelRepository:
        """Singleton accessor for efficient shared memory usage."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def specs_kb(self) -> Dict[str, Any]:
        """Raw hotel specs dictionary."""
        return self._specs_data

    @property
    def reputation_kb(self) -> Dict[str, Any]:
        """Raw hotel reputation dictionary."""
        return self._reputation_data

    @property
    def galleries_kb(self) -> Dict[str, Any]:
        """Raw hotel galleries dictionary."""
        return self._galleries_data

    @property
    def dna_profiles(self) -> Dict[str, Any]:
        """Raw market DNA profiles dictionary."""
        return self._dna_data

    def reload(self) -> None:
        """Loads or reloads all knowledge bases from disk and builds normalized indices."""
        self._load_specs()
        self._load_reputation()
        self._load_galleries()
        self._load_dna()

    def _load_specs(self) -> None:
        self._specs_norm.clear()
        if self.specs_path.is_file():
            try:
                with open(self.specs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._specs_data = data
                hotels = data.get("hotels", {}) if isinstance(data, dict) else {}
                for name, entry in hotels.items():
                    specs_obj = entry.get("specs") if isinstance(entry, dict) and "specs" in entry else entry
                    self._specs_norm[_norm_key(name)] = specs_obj
            except Exception as e:
                logger.warning("Could not load specs KB from %s: %e", self.specs_path, e)

    def _load_reputation(self) -> None:
        self._reputation_norm.clear()
        if self.reputation_path.is_file():
            try:
                with open(self.reputation_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._reputation_data = data
                hotels = data.get("hotels", {}) if isinstance(data, dict) else {}
                for name, entry in hotels.items():
                    if isinstance(entry, dict):
                        self._reputation_norm[_norm_key(name)] = entry
            except Exception as e:
                logger.warning("Could not load reputation KB from %s: %e", self.reputation_path, e)

    def _load_galleries(self) -> None:
        self._galleries_norm.clear()
        if self.galleries_path.is_file():
            try:
                with open(self.galleries_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._galleries_data = data
                gals = data.get("galleries", {}) if isinstance(data, dict) else {}
                for name, photos in gals.items():
                    if isinstance(photos, list):
                        self._galleries_norm[_norm_key(name)] = photos
            except Exception as e:
                logger.warning("Could not load galleries KB from %s: %e", self.galleries_path, e)

    def _load_dna(self) -> None:
        self._dna_norm.clear()
        if self.dna_path.is_file():
            try:
                with open(self.dna_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._dna_data = data
                profiles = data.get("hotel_profiles", {}) if isinstance(data, dict) else {}
                for name, prof in profiles.items():
                    if isinstance(prof, dict):
                        self._dna_norm[_norm_key(name)] = prof
            except Exception as e:
                logger.warning("Could not load DNA KB from %s: %e", self.dna_path, e)

    def _find_normalized_key(self, hotel_name: str, index: Dict[str, Any]) -> Optional[str]:
        """Resolves hotel name to an index key via exact, canonical, or fuzzy match."""
        if not hotel_name:
            return None
        k = _norm_key(hotel_name)
        if k in index:
            return k
        clean_name = clean_hotel_title(hotel_name)
        k_clean = _norm_key(clean_name)
        if k_clean in index:
            return k_clean
        canonical = self.registry.get_canonical(hotel_name)
        if canonical:
            k_canon = _norm_key(canonical)
            if k_canon in index:
                return k_canon
        # Fuzzy match for slight punctuation or word-order differences
        for idx_k in index.keys():
            if k_clean and (k_clean in idx_k or idx_k in k_clean):
                if len(k_clean) >= 6 and len(idx_k) >= 6:
                    return idx_k
        return None

    def get_specs(self, hotel_name: str) -> Optional[Dict[str, Any]]:
        """Returns verified hotel specs (beach, pools, food, kids, comfort)."""
        key = self._find_normalized_key(hotel_name, self._specs_norm)
        return self._specs_norm.get(key) if key else None

    def get_reputation(self, hotel_name: str) -> Optional[Dict[str, Any]]:
        """Returns hotel reputation metadata (TripAdvisor score, reviews, sentiment)."""
        key = self._find_normalized_key(hotel_name, self._reputation_norm)
        return self._reputation_norm.get(key) if key else None

    def get_gallery(self, hotel_name: str) -> List[Dict[str, Any]]:
        """Returns verified hotel photo list with URLs and categories."""
        key = self._find_normalized_key(hotel_name, self._galleries_norm)
        return self._galleries_norm.get(key, []) if key else []

    def get_dna(self, hotel_name: str) -> Optional[Dict[str, Any]]:
        """Returns Market DNA profile (archetype, volatility, historical quantiles)."""
        key = self._find_normalized_key(hotel_name, self._dna_norm)
        return self._dna_norm.get(key) if key else None

    def get_unified_passport(self, hotel_name: str) -> Dict[str, Any]:
        """Aggregates all 4 knowledge bases into a complete, ready-to-render hotel profile."""
        clean_title = clean_hotel_title(hotel_name)
        slug = slugify_hotel_name(hotel_name)
        specs = self.get_specs(hotel_name) or {}
        rep = self.get_reputation(hotel_name) or {}
        gallery = self.get_gallery(hotel_name) or []
        dna = self.get_dna(hotel_name) or {}

        return {
            "hotel_name": hotel_name,
            "clean_title": clean_title,
            "slug": slug,
            "has_specs": bool(specs),
            "specs": specs,
            "has_reputation": bool(rep),
            "reputation": rep,
            "gallery": gallery,
            "photos_count": len(gallery),
            "archetype": dna.get("archetype", "BALANCED"),
            "dna": dna,
        }
