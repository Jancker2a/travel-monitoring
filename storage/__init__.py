"""
storage — Unified Database and Storage Engine for Travel Price Monitor.

Provides SQLite-based structured storage, indexing, and high-performance querying
for hotel price histories, scrapings, and alerts.
"""

from storage.database import TravelDatabase
from storage.repository import PriceRepository

__all__ = ["TravelDatabase", "PriceRepository"]
