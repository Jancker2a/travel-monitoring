#!/usr/bin/env python3
"""
German Package Tour Monitor (Playwright Crawler).
Collects Pauschalreisen from German aggregators (Check24) for departures from BER / DRS / LEJ.

Follows the exact architecture and standards of travel_monitor.py:
- Config-driven (JSON configuration) or CLI flags.
- Headless Chromium with Playwright, image-blocking optimization, and cookie banner handling.
- Multi-page pagination support.
- Incremental append-only CSV persistence with schema normalization.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('germany_monitor.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

GERMANY_PRICE_CSV_FIELDS = [
    'hotel_name',
    'price',
    'dates',
    'duration',
    'destination',
    'location',
    'departure_airport',
    'scraped_at',
    'offer_url',
]

# Destination Area IDs for Check24:
CHECK24_AREAS = {
    # Turkey
    "turkey_antalya": 578,      # Antalya & Belek
    "turkey_side": 586,         # Side & Alanya
    "turkey_kemer": 580,        # Kemer & Beldibi
    "turkey_bodrum": 581,       # Bodrum
    # Egypt
    "egypt_hurghada": 673,      # Hurghada & Safaga
    "egypt_sharm": 674,         # Sharm el Sheikh
    "egypt_marsa_alam": 675,    # Marsa Alam & Quseir
    # Greece
    "greece_crete": 603,        # Kreta
    "greece_rhodes": 600,       # Rhodos
    "greece_corfu": 608,        # Korfu
}


class GermanyTourMonitor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_csv = config.get(
            'output_data_file',
            os.path.join(config.get('data_dir', 'data'), 'germany_prices.csv'),
        )
        self.airport = config.get('departure_airport', 'BER')
        self.max_pages = int(config.get('max_pages', 3))
        self.max_offers = int(config.get('max_offers', 50))
        self.wait_timeout = int(config.get('wait_timeout', 20000))

    def _build_search_url(self, page_number: int = 1) -> str:
        """Constructs Check24 package search URL with airport, area, and dates."""
        base_url = self.config.get('url')
        if base_url:
            # If explicit URL provided in config
            if page_number > 1:
                sep = '&' if '?' in base_url else '?'
                return f"{base_url}{sep}page={page_number}"
            return base_url

        area_id = self.config.get('area_id')
        if not area_id:
            dest_key = self.config.get('destination_key', 'turkey_antalya')
            area_id = CHECK24_AREAS.get(dest_key, 578)

        travel_period = self.config.get('travel_period', '')
        duration = self.config.get('duration', '7-10')
        airport = self.airport

        url = (
            f"https://urlaub.check24.de/suche/hotel?"
            f"airport={airport}&transportType=flight&roomAllocation=A-A&areaId={area_id}"
        )
        if travel_period:
            url += f"&travelPeriod={travel_period}"
        if duration:
            url += f"&duration={duration}"
        if page_number > 1:
            url += f"&page={page_number}"

        return url

    async def _dismiss_consent(self, page) -> bool:
        """Dismisses the German cookie consent dialog if displayed."""
        try:
            selectors = [
                'button:has-text("Geht klar")',
                'button:has-text("Alle akzeptieren")',
                'button:has-text("Zustimmen")',
            ]
            for sel in selectors:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1.5)
                    logger.info("Cookie consent dismissed successfully.")
                    return True
        except Exception as e:
            logger.debug(f"Cookie consent check: {e}")
        return False

    async def extract_offers_from_page(self, page) -> List[Dict[str, Any]]:
        """Extracts hotel offers from <article> elements rendered by Check24."""
        offers_js = """
        () => {
            const list = [];
            const articles = document.querySelectorAll('article');
            for (const art of articles) {
                const text = art.innerText || '';
                if (!text.includes('€')) continue;
                
                const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                const title = lines[0] || '';
                const location = lines[1] || '';
                
                // Parse Price (EUR)
                let price = 0;
                for (const l of lines) {
                    if (l.includes('€') && !l.includes('Punkte') && !l.includes('Gutschein') && !l.includes('Rabatt')) {
                        // Formats: '1.062,00 €' or '956 €'
                        const clean = l.replace(/[^0-9,]/g, '').replace(',', '.');
                        price = parseFloat(clean) || 0;
                        if (price > 0) break;
                    }
                }
                
                // Parse Duration and passenger info
                let duration = '';
                for (const l of lines) {
                    if (l.includes('Tage') || l.includes('Nächte')) {
                        duration = l;
                        break;
                    }
                }
                
                // Offer link
                const anchor = art.querySelector('a[href]');
                const offer_url = anchor ? anchor.href : '';
                
                if (title && price > 0) {
                    list.push({
                        hotel_name: title,
                        price: price,
                        duration: duration,
                        location: location,
                        offer_url: offer_url
                    });
                }
            }
            return list;
        }
        """
        raw_list = await page.evaluate(offers_js)
        now_iso = datetime.now(timezone.utc).isoformat()
        airport = self.airport
        destination = self.config.get('destination', 'Turkey')

        cleaned_offers = []
        for item in raw_list:
            cleaned_offers.append({
                'hotel_name': str(item.get('hotel_name', '')).strip()[:100],
                'price': float(item.get('price', 0.0)),
                'dates': self.config.get('travel_period', ''),
                'duration': str(item.get('duration', ''))[:50],
                'destination': destination,
                'location': str(item.get('location', ''))[:100],
                'departure_airport': airport,
                'scraped_at': now_iso,
                'offer_url': str(item.get('offer_url', ''))[:250],
            })
        return cleaned_offers

    async def scrape_offers(self) -> List[Dict[str, Any]]:
        """Main scraping loop across pages using Playwright Chromium."""
        all_offers: List[Dict[str, Any]] = []

        async with async_playwright() as p:
            logger.info("Launching Playwright Chromium for German tour monitoring...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1920, 'height': 1080},
            )
            page = await context.new_page()

            # Block heavy media assets for speed (3-5x faster scraping)
            await page.route(
                '**/*.{png,jpg,jpeg,webp,svg,gif,woff,woff2}',
                lambda r: r.abort(),
            )
            page.set_default_timeout(self.wait_timeout)

            try:
                for page_num in range(1, self.max_pages + 1):
                    url = self._build_search_url(page_num)
                    logger.info(f"Navigating to page {page_num}: {url[:100]}...")
                    t0 = time.monotonic()

                    try:
                        resp = await page.goto(url, wait_until='domcontentloaded')
                        if resp and resp.status >= 400:
                            logger.warning(f"HTTP error {resp.status} on page {page_num}")
                            break
                    except Exception as e:
                        logger.warning(f"Goto timeout/error on page {page_num}: {e}")
                        break

                    # Handle cookie banner on first page
                    if page_num == 1:
                        await self._dismiss_consent(page)

                    # Wait for articles to render
                    try:
                        await page.wait_for_selector('article', timeout=8000)
                    except Exception:
                        logger.info(f"No articles found on page {page_num}, stopping pagination.")
                        break

                    # Scroll down to trigger lazy loading of additional offers on this page
                    for _ in range(2):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1.0)

                    offers = await self.extract_offers_from_page(page)
                    elapsed = time.monotonic() - t0
                    logger.info(
                        f"Page {page_num}: extracted {len(offers)} offers in {elapsed:.1f}s"
                    )

                    if not offers:
                        break

                    all_offers.extend(offers)

                    if self.max_offers > 0 and len(all_offers) >= self.max_offers:
                        all_offers = all_offers[:self.max_offers]
                        logger.info(f"Reached max offers limit ({self.max_offers}), terminating.")
                        break

            finally:
                await browser.close()

        logger.info(f"Total German offers scraped: {len(all_offers)}")
        return all_offers

    def save_offers_to_csv(self, new_offers: List[Dict[str, Any]]) -> str:
        """
        Appends newly scraped offers to CSV file, ensuring headers and historical continuity.
        Matches the travel_monitor.py persistence architecture.
        """
        if not new_offers:
            logger.warning("No offers to save.")
            return self.output_csv

        os.makedirs(os.path.dirname(os.path.abspath(self.output_csv)), exist_ok=True)
        existing_data: List[Dict[str, Any]] = []

        if os.path.exists(self.output_csv):
            try:
                with open(self.output_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        normalized = {k: row.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS}
                        existing_data.append(normalized)
            except Exception as e:
                logger.warning(f"Error reading existing CSV: {e}, rewriting afresh.")
                existing_data = []

        with open(self.output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=GERMANY_PRICE_CSV_FIELDS, quoting=csv.QUOTE_ALL)
            writer.writeheader()

            for row in existing_data:
                writer.writerow({k: row.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS})

            for offer in new_offers:
                writer.writerow({k: offer.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS})

        logger.info(
            f"Saved {len(new_offers)} new offers to {self.output_csv} (Total records: {len(existing_data) + len(new_offers)})"
        )
        return self.output_csv


def parse_args():
    parser = argparse.ArgumentParser(description="German Tour Package Monitor (BER/DRS)")
    parser.add_argument("--config", help="Path to JSON configuration file")
    parser.add_argument("--destination", default="Turkey", help="Destination name (Turkey, Egypt, Greece)")
    parser.add_argument("--destination-key", default="turkey_antalya", help="Key for Check24 area mapping")
    parser.add_argument("--airport", default="BER", help="Departure airport (BER, DRS, LEJ)")
    parser.add_argument("--max-pages", type=int, default=2, help="Maximum number of pages to scrape")
    parser.add_argument("--max-offers", type=int, default=25, help="Maximum offers to extract")
    parser.add_argument("--output", default="data/germany_prices.csv", help="Output CSV path")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and print without saving")
    return parser.parse_args()


async def main_async():
    args = parse_args()
    config = {}

    if args.config and os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)

    # CLI args override config
    if args.destination:
        config['destination'] = args.destination
    if args.destination_key:
        config['destination_key'] = args.destination_key
    if args.airport:
        config['departure_airport'] = args.airport
    if args.max_pages:
        config['max_pages'] = args.max_pages
    if args.max_offers:
        config['max_offers'] = args.max_offers
    if args.output:
        config['output_data_file'] = args.output

    monitor = GermanyTourMonitor(config)
    offers = await monitor.scrape_offers()

    if args.dry_run:
        print(f"--- DRY RUN: Scraped {len(offers)} offers ---")
        for o in offers[:10]:
            print(f"{o['hotel_name']} | {o['price']} EUR | {o['departure_airport']} | {o['location']}")
    else:
        monitor.save_offers_to_csv(offers)


def main():
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
