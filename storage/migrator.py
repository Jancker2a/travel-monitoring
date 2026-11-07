"""
storage/migrator.py — Tool for migrating historical CSV price data to SQLite and back.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from storage.database import TravelDatabase
from storage.repository import PriceRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("storage.migrator")


def import_csv_to_db(
    csv_path: Union[str, Path],
    filter_id: str,
    repository: PriceRepository,
    dry_run: bool = False,
) -> int:
    """Imports a single travel_prices.csv file into the database grouped by scrape runs."""
    csv_file = Path(csv_path)
    if not csv_file.is_file():
        logger.warning("CSV file not found: %s", csv_path)
        return 0

    try:
        df = pd.read_csv(csv_file, on_bad_lines="skip")
    except Exception as e:
        logger.error("Error reading %s: %e", csv_path, e)
        return 0

    if df.empty or "scraped_at" not in df.columns:
        logger.warning("CSV %s is empty or missing 'scraped_at' column", csv_path)
        return 0

    total_rows = len(df)
    logger.info("Importing %s: %d total rows", csv_file.name, total_rows)

    if dry_run:
        runs_count = df["scraped_at"].nunique()
        logger.info("[DRY RUN] Would import %d runs and %d offers into filter '%s'", runs_count, total_rows, filter_id)
        return total_rows

    imported = 0
    # Group rows by distinct scrape run timestamp
    for scraped_at, run_df in df.groupby("scraped_at"):
        offers = run_df.to_dict("records")
        repository.save_scrape_run(
            filter_id=filter_id,
            offers=offers,
            scraped_at=str(scraped_at),
            status="ok",
        )
        imported += len(offers)

    logger.info("✓ Successfully imported %d offers into filter '%s'", imported, filter_id)
    return imported


def export_filter_to_csv(
    filter_id: str,
    output_path: Union[str, Path],
    repository: PriceRepository,
) -> int:
    """Exports all offers for a filter from SQLite into travel_prices.csv format."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    conn = repository.db.get_connection()
    try:
        query = """
            SELECT hotel_name, price, dates, duration, duration_bucket,
                   rating, ta_rating, ta_review_count, ta_source,
                   departure_airport, scraped_at, url, image_url, offer_url
            FROM offers
            WHERE filter_id = ?
            ORDER BY scraped_at ASC, price ASC;
        """
        df = pd.read_sql_query(query, conn, params=(filter_id,))
        df.to_csv(out_file, index=False, quoting=csv.QUOTE_ALL)
        logger.info("Exported %d rows for filter '%s' to %s", len(df), filter_id, output_path)
        return len(df)
    finally:
        conn.close()


def migrate_all_filters(
    data_dir: Union[str, Path] = "data/filters",
    repository: Optional[PriceRepository] = None,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Scans all filter folders and imports travel_prices.csv files into SQLite."""
    repo = repository or PriceRepository()
    filters_dir = Path(data_dir)
    if not filters_dir.is_dir():
        logger.warning("Filters directory not found: %s", data_dir)
        return 0, 0

    total_files = 0
    total_offers = 0

    for filter_folder in sorted(filters_dir.iterdir()):
        if not filter_folder.is_dir():
            continue
        csv_path = filter_folder / "travel_prices.csv"
        if csv_path.is_file():
            filter_id = filter_folder.name
            count = import_csv_to_db(csv_path, filter_id, repo, dry_run=dry_run)
            total_files += 1
            total_offers += count

    logger.info("Migration finished: %d files processed, %d offers migrated", total_files, total_offers)
    return total_files, total_offers


def main() -> int:
    parser = argparse.ArgumentParser(description="Travel Price Monitor CSV <-> SQLite Migrator")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without committing to database")
    parser.add_argument("--import-all", action="store_true", help="Import all CSVs from data/filters/")
    parser.add_argument("--import-file", type=str, help="Path to single travel_prices.csv")
    parser.add_argument("--filter-id", type=str, help="Filter ID for single file import/export")
    parser.add_argument("--export-file", type=str, help="Export a filter to destination CSV")
    parser.add_argument("--db-path", type=str, default="data/travel_monitor.db", help="SQLite database path")
    args = parser.parse_args()

    db = TravelDatabase(args.db_path)
    repo = PriceRepository(db)

    if args.import_all:
        migrate_all_filters(repository=repo, dry_run=args.dry_run)
        return 0

    if args.import_file:
        if not args.filter_id:
            logger.error("--filter-id is required when importing a single file")
            return 1
        import_csv_to_db(args.import_file, args.filter_id, repo, dry_run=args.dry_run)
        return 0

    if args.export_file:
        if not args.filter_id:
            logger.error("--filter-id is required when exporting")
            return 1
        export_filter_to_csv(args.filter_id, args.export_file, repo)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
