"""
storage/repository.py — High-level Data Access Object (DAO) for hotel offers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from hotel_name_normalizer import HotelCanonicalRegistry
from storage.database import TravelDatabase

logger = logging.getLogger("storage.repository")


class PriceRepository:
    """High-level repository for inserting, querying, and analyzing hotel prices."""

    def __init__(self, db: Optional[TravelDatabase] = None):
        self.db = db or TravelDatabase()
        self.registry = HotelCanonicalRegistry()

    def register_filter(self, filter_id: str, country: str = "", title: str = "") -> None:
        """Registers a filter entity if not already present."""
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO filters (id, country, title)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    country = CASE WHEN excluded.country != '' THEN excluded.country ELSE country END,
                    title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END;
                """,
                (filter_id, country, title),
            )

    def save_scrape_run(
        self,
        filter_id: str,
        offers: List[Dict[str, Any]],
        scraped_at: Optional[str] = None,
        status: str = "ok",
        duration_seconds: float = 0.0,
    ) -> int:
        """Atomically records a scrape run and its offers in a single transaction."""
        self.register_filter(filter_id)
        run_ts = scraped_at or datetime.now(timezone.utc).isoformat()

        with self.db.transaction() as cur:
            # 1. Insert scrape run
            cur.execute(
                """
                INSERT INTO scrape_runs (filter_id, scraped_at, offers_count, status, duration_seconds)
                VALUES (?, ?, ?, ?, ?)
                """,
                (filter_id, run_ts, len(offers), status, duration_seconds),
            )
            run_id = cur.lastrowid

            # 2. Batch insert offers
            offer_tuples = []
            for o in offers:
                h_name = str(o.get("hotel_name") or "").strip()
                canonical = self.registry.get_canonical(h_name) or h_name

                raw_price = o.get("price")
                try:
                    price_val = float(raw_price) if raw_price is not None else 0.0
                except (ValueError, TypeError):
                    price_val = 0.0

                ta_r = o.get("ta_rating")
                try:
                    ta_rating_val = float(ta_r) if ta_r not in (None, "", "null") else None
                except (ValueError, TypeError):
                    ta_rating_val = None

                ta_rev = o.get("ta_review_count")
                try:
                    ta_rev_val = int(ta_rev) if ta_rev not in (None, "", "null") else None
                except (ValueError, TypeError):
                    ta_rev_val = None

                offer_tuples.append(
                    (
                        run_id,
                        filter_id,
                        h_name,
                        canonical,
                        price_val,
                        str(o.get("dates") or ""),
                        str(o.get("departure_date") or ""),
                        str(o.get("return_date") or ""),
                        str(o.get("duration") or ""),
                        o.get("days") or o.get("duration_days"),
                        str(o.get("duration_bucket") or ""),
                        str(o.get("departure_airport") or ""),
                        str(o.get("rating") or ""),
                        ta_rating_val,
                        ta_rev_val,
                        str(o.get("ta_source") or ""),
                        str(o.get("scraped_at") or run_ts),
                        str(o.get("url") or ""),
                        str(o.get("image_url") or ""),
                        str(o.get("offer_url") or ""),
                    )
                )

            if offer_tuples:
                cur.executemany(
                    """
                    INSERT INTO offers (
                        run_id, filter_id, hotel_name, canonical_hotel_name,
                        price, dates, departure_date, return_date, duration,
                        duration_days, duration_bucket, departure_airport,
                        rating, ta_rating, ta_review_count, ta_source,
                        scraped_at, url, image_url, offer_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    offer_tuples,
                )

        logger.info(
            "Saved scrape run #%d for filter '%s': %d offers recorded",
            run_id,
            filter_id,
            len(offers),
        )
        return run_id

    def get_latest_slice(self, filter_id: str) -> pd.DataFrame:
        """Returns the most recent scrape run slice for a filter as a DataFrame."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT * FROM offers
                WHERE filter_id = ?
                  AND scraped_at = (
                      SELECT MAX(scraped_at) FROM offers WHERE filter_id = ?
                  )
                ORDER BY price ASC;
            """
            return pd.read_sql_query(query, conn, params=(filter_id, filter_id))
        finally:
            conn.close()

    def get_hotel_price_history(
        self,
        hotel_name: str,
        filter_id: Optional[str] = None,
        lookback_days: Optional[int] = None,
        dates: Optional[str] = None,
        since_scraped_at: Optional[str] = None,
    ) -> pd.DataFrame:
        """Returns historical price points for a hotel, using canonical matching."""
        canonical = self.registry.get_canonical(hotel_name) or hotel_name
        conn = self.db.get_connection()
        try:
            params: List[Any] = [hotel_name, canonical]
            filter_clause = ""
            if filter_id:
                filter_clause = "AND filter_id = ?"
                params.append(filter_id)

            dates_clause = ""
            if dates:
                dates_clause = "AND dates = ?"
                params.append(dates)

            since_clause = ""
            if since_scraped_at:
                since_clause = "AND scraped_at >= ?"
                params.append(since_scraped_at)

            date_clause = ""
            if lookback_days:
                date_clause = "AND scraped_at >= datetime('now', ?)"
                params.append(f"-{int(lookback_days)} days")

            query = f"""
                SELECT hotel_name, canonical_hotel_name, price, scraped_at,
                       departure_airport, duration, dates, offer_url
                FROM offers
                WHERE (hotel_name = ? OR canonical_hotel_name = ?)
                  {filter_clause}
                  {dates_clause}
                  {since_clause}
                  {date_clause}
                ORDER BY scraped_at ASC;
            """
            return pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()

    def get_price_range(self, filter_id: str) -> Tuple[Optional[float], Optional[float]]:
        """Returns the min and max price observed for a filter."""
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT MIN(price), MAX(price) FROM offers WHERE filter_id = ? AND price > 0;",
                (filter_id,),
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                return float(row[0]), float(row[1])
            return None, None
        finally:
            conn.close()

    def get_filter_dataframe(self, filter_id: str) -> pd.DataFrame:
        """Returns all historical offers for a filter as a DataFrame, sorted chronologically."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT * FROM offers
                WHERE filter_id = ?
                ORDER BY scraped_at ASC;
            """
            return pd.read_sql_query(query, conn, params=(filter_id,))
        finally:
            conn.close()

    def get_all_offers_df(self, min_price: float = 1000.0) -> pd.DataFrame:
        """Returns all valid historical offers across all filters as a DataFrame."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT DISTINCT hotel_name, canonical_hotel_name, price, dates,
                                duration, duration_days, duration_bucket, departure_airport,
                                rating, ta_rating, ta_review_count, ta_source,
                                scraped_at, url, image_url, offer_url, filter_id
                FROM offers
                WHERE price >= ?
                ORDER BY scraped_at ASC;
            """
            return pd.read_sql_query(query, conn, params=(min_price,))
        finally:
            conn.close()

    def count_offers(self, filter_id: Optional[str] = None) -> int:
        """Returns the total number of offers stored."""
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            if filter_id:
                cur.execute("SELECT COUNT(*) FROM offers WHERE filter_id = ?;", (filter_id,))
            else:
                cur.execute("SELECT COUNT(*) FROM offers;")
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
