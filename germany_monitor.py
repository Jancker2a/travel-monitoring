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

# Allowed German border airports close to Poland (East Germany):
# BER: Berlin Brandenburg (~80 km from border, direct A2/train from Warsaw/Poznań)
# DRS: Dresden (~100 km from Zgorzelec, direct A4 from Wrocław/Lower Silesia)
# LEJ: Leipzig/Halle (~200 km from border)
ALLOWED_BORDER_AIRPORTS = {"BER", "DRS", "LEJ"}


class GermanyTourMonitor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_csv = config.get(
            'output_data_file',
            os.path.join(config.get('data_dir', 'data'), 'germany_prices.csv'),
        )
        ap = str(config.get('departure_airport', 'BER')).upper().strip()
        if ap not in ALLOWED_BORDER_AIRPORTS:
            logger.warning(
                f"Requested airport '{ap}' is too far from Polish border. Enforcing nearest border hub 'BER'."
            )
            ap = "BER"
        self.airport = ap
        self.max_pages = int(config.get('max_pages', 3))
        self.max_offers = int(config.get('max_offers', 50))
        self.wait_timeout = int(config.get('wait_timeout', 20000))


    def _build_search_url(self, page_number: int = 1) -> str:
        """Constructs Check24 package search URL with airport, area, and dates."""
        base_url = self.config.get('url')
        if base_url:
            # Normalize legacy parameters if present in explicit URL
            if 'travelPeriod=' in base_url:
                import re
                m = re.search(r'travelPeriod=(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})', base_url)
                if m:
                    base_url = base_url.replace(m.group(0), f"departureDate={m.group(1)}&returnDate={m.group(2)}")
            if 'duration=' in base_url and 'days=' not in base_url:
                base_url = base_url.replace('duration=', 'days=')

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
        room_allocation = self.config.get('room_allocation', 'A-A')
        airport = self.airport

        url = (
            f"https://urlaub.check24.de/suche/hotel?"
            f"airport={airport}&transportType=flight&roomAllocation={room_allocation}&areaId={area_id}"
        )
        if travel_period:
            if '_' in travel_period:
                dep_d, ret_d = travel_period.split('_', 1)
                url += f"&departureDate={dep_d}&returnDate={ret_d}"
            else:
                url += f"&departureDate={travel_period}"
        if duration:
            url += f"&days={duration}"
        catering = self.config.get('catering')
        if catering:
            url += f"&catering={catering}"
        if page_number > 1:
            url += f"&page={page_number}"

        return url

    async def _dismiss_consent(self, page) -> bool:
        """Dismisses the German cookie consent dialog if displayed."""
        try:
            selectors = [
                '.c24-cookie-consent-button',
                'a.c24-cookie-consent-button',
                'a:has-text("Geht klar")',
                'button:has-text("Geht klar")',
                '.c24-cookie-consent-functional',
                'a:has-text("Nur notwendige Cookies")',
                'button:has-text("Alle akzeptieren")',
                'button:has-text("Zustimmen")',
            ]
            for sel in selectors:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(0.5)
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
                // Skip placeholder skeleton loading cards
                if (art.className && art.className.includes('Loading')) continue;
                
                // Hotel title
                const titleEl = art.querySelector('h2, h3, [class*="Title"], [class*="headline"], [class*="hotelName"]');
                const title = titleEl ? titleEl.innerText.trim() : (art.innerText.split('\\n')[0] || '').trim();
                if (!title || title === '•') continue;
                
                // Location
                const locEl = art.querySelector('[class*="Location"], [class*="location"], [class*="Region"], [class*="region"]');
                let location = locEl ? locEl.innerText.trim() : '';
                if (!location) {
                    const lines = art.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
                    if (lines.length > 1) location = lines[1];
                }
                
                // Parse Price (EUR) - prefer final total price element, exclude strikethrough prices
                let price = 0;
                const totalPriceEl = art.querySelector('[class*="TotalPrice"], [class*="_Price_"]');
                if (totalPriceEl) {
                    const clean = totalPriceEl.innerText.replace(/[^0-9,]/g, '').replace(',', '.');
                    price = parseFloat(clean) || 0;
                }
                
                // Fallback to text lines if price selector not matched
                if (price <= 0) {
                    const lines = art.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
                    for (const l of lines) {
                        if (l.includes('€') && !l.includes('Punkte') && !l.includes('Gutschein') && !l.includes('Rabatt')) {
                            const clean = l.replace(/[^0-9,]/g, '').replace(',', '.');
                            price = parseFloat(clean) || 0;
                            if (price > 0) break;
                        }
                    }
                }
                
                // Parse Duration and passenger info
                let duration = '';
                const durEl = art.querySelector('[class*="Duration"], [class*="duration"], [class*="TravelPeriod"]');
                if (durEl) {
                    duration = durEl.innerText.trim();
                } else {
                    for (const l of art.innerText.split('\\n')) {
                        if (l.includes('Tage') || l.includes('Nächte')) {
                            duration = l.trim();
                            break;
                        }
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
            offer_url = str(item.get('offer_url', '')).strip()[:1000]
            dates_val = self.config.get('travel_period', '')
            if 'departureDate=' in offer_url:
                try:
                    from urllib.parse import parse_qs, urlparse
                    u_qs = parse_qs(urlparse(offer_url).query)
                    dep = u_qs.get('departureDate', [''])[0]
                    ret = u_qs.get('returnDate', [''])[0]
                    if dep and ret:
                        dates_val = f"{dep}_{ret}"
                    elif dep:
                        dates_val = dep
                except Exception:
                    pass

            cleaned_offers.append({
                'hotel_name': str(item.get('hotel_name', '')).strip()[:100],
                'price': float(item.get('price', 0.0)),
                'dates': dates_val,
                'duration': str(item.get('duration', ''))[:50],
                'destination': destination,
                'location': str(item.get('location', ''))[:100],
                'departure_airport': airport,
                'scraped_at': now_iso,
                'offer_url': offer_url,
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
                    '--disable-blink-features=AutomationControlled',
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
                },
            )
            page = await context.new_page()

            # Block heavy media assets for speed (3-5x faster scraping)
            await page.route(
                '**/*.{png,jpg,jpeg,webp,svg,woff,woff2}',
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

                    # Wait for articles WITH real prices to render (timeout 15s)
                    try:
                        await page.wait_for_selector('article:has-text("€")', timeout=15000)
                    except Exception:
                        # Fallback: re-attempt consent dismissal in case it was slow
                        await self._dismiss_consent(page)
                        try:
                            await page.wait_for_selector('article:has-text("€")', timeout=5000)
                        except Exception:
                            logger.info(f"Page {page_num}: No priced articles found, checking page state...")
                            title = await page.title()
                            logger.info(f"Page title: '{title}'")
                            break

                    # Scroll down to trigger lazy loading of additional offers on this page
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(0.5)

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
                        h_name = str(row.get('hotel_name') or '').strip()
                        if not h_name or h_name.startswith(('<<<', '===', '>>>')):
                            continue
                        normalized = {k: row.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS}
                        existing_data.append(normalized)
            except Exception as e:
                logger.warning(f"Error reading existing CSV: {e}, rewriting afresh.")
                existing_data = []

        # Deduplicate records by (hotel_name, departure_airport, dates) keeping the newest scrape
        deduped_records = {}
        for row in existing_data:
            key = (row.get('hotel_name', '').strip().lower(), row.get('departure_airport', '').strip().upper(), row.get('dates', '').strip())
            deduped_records[key] = {k: row.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS}
        for offer in new_offers:
            key = (offer.get('hotel_name', '').strip().lower(), offer.get('departure_airport', '').strip().upper(), offer.get('dates', '').strip())
            deduped_records[key] = {k: offer.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS}

        final_records = list(deduped_records.values())

        with open(self.output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=GERMANY_PRICE_CSV_FIELDS, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for record in final_records:
                writer.writerow(record)

        logger.info(
            f"Saved {len(new_offers)} new offers to {self.output_csv} (Total unique records: {len(final_records)})"
        )

        # Also sync to central CSV if saving to a filter-specific CSV
        central_csv = os.path.join("data", "germany", "germany_prices.csv")
        try:
            if os.path.abspath(self.output_csv) != os.path.abspath(central_csv):
                os.makedirs(os.path.dirname(os.path.abspath(central_csv)), exist_ok=True)
                write_hdr = not os.path.exists(central_csv) or os.path.getsize(central_csv) == 0
                with open(central_csv, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=GERMANY_PRICE_CSV_FIELDS, quoting=csv.QUOTE_ALL)
                    if write_hdr:
                        writer.writeheader()
                    for offer in new_offers:
                        writer.writerow({k: offer.get(k, '') for k in GERMANY_PRICE_CSV_FIELDS})
        except Exception as e:
            logger.debug(f"Central CSV sync: {e}")

        return self.output_csv


def map_polish_config_to_germany_params(polish_cfg: Dict[str, Any], cfg_name: str = "") -> Dict[str, Any]:
    """
    Extracts equivalent Check24 query parameters from any Polish travel_monitor JSON config:
    - destination & areaId (Antalya 578, Sharm 674, Hurghada 673, Crete 603, etc.)
    - travelPeriod (from filter[whenFrom] and filter[whenTo])
    - duration (from filter[duration])
    - roomAllocation (A for 1 adult, A-A for 2 adults)
    - data_dir & output_data_file (stores directly in filter's data_dir and/or data/germany)
    """
    from urllib.parse import parse_qs, urlparse
    from filter_params import resolve_config_url
    url = resolve_config_url(polish_cfg) if polish_cfg else ""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # 1. Dates: whenFrom/startDateMin and whenTo/returnDate -> YYYY-MM-DD_YYYY-MM-DD
    w_from = (qs.get('startDateMin') or qs.get('filter[whenFrom]') or [''])[0]
    w_to = (qs.get('returnDate') or qs.get('filter[whenTo]') or [''])[0]
    period = ''
    if w_from and w_to:
        f_p = w_from.split('-')
        t_p = w_to.split('-')
        if len(f_p) == 3 and len(t_p) == 3:
            if len(f_p[0]) == 4:
                # ISO format YYYY-MM-DD
                period = f"{w_from}_{w_to}"
            else:
                # DD-MM-YYYY format
                period = f"{f_p[2]}-{f_p[1]}-{f_p[0]}_{t_p[2]}-{t_p[1]}-{t_p[0]}"

    # 2. Duration: Polish nights (durationFrom/durationTo or filter[duration]) -> Check24 days (nights + 1)
    dur_f, dur_t = 7, 10
    if 'durationFrom' in qs and 'durationTo' in qs:
        try:
            dur_f = int(qs['durationFrom'][0])
            dur_t = int(qs['durationTo'][0])
        except (ValueError, TypeError):
            dur_f, dur_t = 7, 10
    else:
        raw_dur = qs.get('filter[duration]', ['7:10'])[0].replace(':', '-')
        parts = raw_dur.split('-')
        try:
            dur_f = int(parts[0])
            dur_t = int(parts[1]) if len(parts) > 1 else dur_f
        except (ValueError, TypeError):
            dur_f, dur_t = 7, 10

    # Check24 'days' represents trip calendar days (nights + 1, e.g. 7 nights = 8 days):
    c24_dur_from = dur_f + 1
    c24_dur_to = min(14, dur_t + 1)
    dur = f"{c24_dur_from}-{c24_dur_to}"

    # 3. Room allocation (Adults + Children with exact age)
    adults = 2
    children = 0
    child_age = 6
    try:
        adults = int((qs.get('adults') or qs.get('filter[person]') or [2])[0])
        raw_children = (qs.get('children') or qs.get('filter[childAge][1]') or [''])[0].strip()
        if raw_children:
            children = 1
            m_yr = re.search(r'\b(20\d{2})\b', raw_children)
            if m_yr:
                birth_yr = int(m_yr.group(1))
                child_age = max(1, min(17, 2026 - birth_yr))
            else:
                m_dig = re.search(r'\b(\d{1,2})\b', raw_children)
                if m_dig:
                    child_age = int(m_dig.group(1))
        else:
            children = int((qs.get('filter[child]') or [0])[0])
    except (ValueError, TypeError):
        adults, children = 2, 0

    if adults == 1 and children == 0:
        room = 'A'
    elif adults == 1 and children > 0:
        room = f'A-{child_age}'
    elif adults == 2 and children > 0:
        room = f'A-A-{child_age}'
    else:
        room = '-'.join(['A'] * adults)

    # 4. Catering mapping
    raw_cat = (qs.get('catering') or qs.get('filter[service]') or [''])[0].lower()
    if 'all' in raw_cat or 'ai' in raw_cat:
        check24_catering = 'allInclusive'
    elif 'hb' in raw_cat or 'half' in raw_cat:
        check24_catering = 'halfBoard'
    elif 'bb' in raw_cat or 'bed' in raw_cat:
        check24_catering = 'bedAndBreakfast'
    else:
        check24_catering = 'allInclusive'

    # 5. Destination & Area mapping
    dest_loc = (qs.get('destinationLocation') or qs.get('filter[dest]') or [''])[0]
    if dest_loc.startswith('11_154'):
        dest_name, dest_key, area_id = 'Egypt', 'egypt_sharm', 674
    elif dest_loc.startswith('11'):
        dest_name, dest_key, area_id = 'Egypt', 'egypt_hurghada', 673
    elif dest_loc.startswith('14'):
        dest_name, dest_key, area_id = 'Greece', 'greece_crete', 603
    elif dest_loc.startswith('39'):
        dest_name, dest_key, area_id = 'Turkey', 'turkey_antalya', 578
    else:
        req_urls = " ".join(polish_cfg.get('required_offer_url_contains', []))
        data_dir_name = str(polish_cfg.get('data_dir', ''))
        comb = f"{cfg_name} {url} {data_dir_name} {polish_cfg.get('description', '')} {req_urls}".lower()

        if any(k in comb for k in ['sharm', 'шарм']):
            dest_name, dest_key, area_id = 'Egypt', 'egypt_sharm', 674
        elif any(k in comb for k in ['egypt', 'egipt', 'египет', 'hurghada', 'хургада', 'marsa', 'марса']):
            dest_name, dest_key, area_id = 'Egypt', 'egypt_hurghada', 673
        elif any(k in comb for k in ['greece', 'grecja', 'греция', 'kreta', 'крит', 'rhodes', 'rodos', 'родос']):
            dest_name, dest_key, area_id = 'Greece', 'greece_crete', 603
        elif any(k in comb for k in ['turkey', 'turcja', 'турция', 'antalya', 'анталья', 'анталия', 'belek', 'kemer', 'side', 'alanya']):
            dest_name, dest_key, area_id = 'Turkey', 'turkey_antalya', 578
        else:
            dest_name, dest_key, area_id = 'Turkey', 'turkey_antalya', 578

    data_dir = polish_cfg.get('data_dir', 'data/germany')
    out_file = os.path.join(data_dir, 'germany_prices.csv')

    return {
        'destination': dest_name,
        'destination_key': dest_key,
        'area_id': area_id,
        'travel_period': period,
        'duration': dur,
        'room_allocation': room,
        'catering': check24_catering,
        'data_dir': data_dir,
        'output_data_file': out_file,
        'departure_airport': 'BER',
    }


def parse_args():
    parser = argparse.ArgumentParser(description="German Tour Package Monitor (BER/DRS)")
    parser.add_argument("--config", help="Path to JSON configuration file")
    parser.add_argument("--from-polish-config", help="Derive German search parameters from a Polish filter JSON config")
    parser.add_argument("--destination", default=None, help="Destination name (Turkey, Egypt, Greece)")
    parser.add_argument("--destination-key", default=None, help="Key for Check24 area mapping")
    parser.add_argument("--airport", default=None, choices=["BER", "DRS", "LEJ"], help="Departure airport close to Polish border (BER, DRS, LEJ)")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum number of pages to scrape")
    parser.add_argument("--max-offers", type=int, default=None, help="Maximum offers to extract")
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and print without saving")
    return parser.parse_args()


async def main_async():
    args = parse_args()
    config = {}

    if args.from_polish_config and os.path.exists(args.from_polish_config):
        with open(args.from_polish_config, 'r', encoding='utf-8') as f:
            p_cfg = json.load(f)
        config.update(map_polish_config_to_germany_params(p_cfg, args.from_polish_config))
    elif args.config and os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)

    # CLI args override config only when explicitly set
    if args.destination is not None:
        config['destination'] = args.destination
    if args.destination_key is not None:
        config['destination_key'] = args.destination_key
    if args.airport is not None:
        config['departure_airport'] = args.airport
    if args.max_pages is not None:
        config['max_pages'] = args.max_pages
    if args.max_offers is not None:
        config['max_offers'] = args.max_offers
    if args.output is not None:
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
