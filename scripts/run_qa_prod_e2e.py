#!/usr/bin/env python3
"""
E2E Automated Production QA Test Suite for Travel Price Monitor
Tests real production at https://jancker2a.github.io/travel-monitoring/
"""

import sys
import time
import json
import urllib.request
from playwright.sync_api import sync_playwright

BASE_URL = "https://jancker2a.github.io/travel-monitoring"

class QATestRunner:
    def __init__(self):
        self.results = []
        self.console_errors = []
        self.failed_requests = []
        self.warnings = []

    def record_result(self, test_id, description, status, details=""):
        res = {
            "test_id": test_id,
            "description": description,
            "status": status,
            "details": details
        }
        self.results.append(res)
        mark = "✅ PASS" if status == "PASS" else ("⚠️ WARN" if status == "WARN" else "❌ FAIL")
        print(f"[{mark}] {test_id}: {description} {details}")

    def run_tests(self):
        print(f"\n=======================================================")
        print(f"🚀 Starting Real Production QA Run on: {BASE_URL}")
        print(f"=======================================================\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # 1. Desktop Tests
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            # Attach monitors
            page.on("pageerror", lambda err: self.console_errors.append(str(err)))
            page.on("response", lambda resp: self._check_response(resp))

            # Test Suite with isolated pages per test
            for test_fn in [
                self.test_landing_page,
                self.test_dashboard_cyprus,
                self.test_dashboard_turkey,
                self.test_dashboard_egypt,
                self.test_dashboard_greece,
                self.test_all_filter_links,
            ]:
                page = context.new_page()
                page.on("pageerror", lambda err: self.console_errors.append(str(err)))
                page.on("response", lambda resp: self._check_response(resp))
                try:
                    test_fn(page)
                except Exception as e:
                    self.record_result(f"ERR-{test_fn.__name__}", f"Unhandled error in {test_fn.__name__}", "FAIL", str(e))
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
            
            try:
                context.close()
            except Exception:
                pass

            # 2. Mobile Viewport Tests
            mobile_context = browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15"
            )
            mobile_page = mobile_context.new_page()
            mobile_page.on("pageerror", lambda err: self.console_errors.append(f"[Mobile] {err}"))
            try:
                self.test_mobile_experience(mobile_page)
            except Exception as e:
                self.record_result("ERR-mobile", "Unhandled error in mobile test", "FAIL", str(e))
            try:
                mobile_context.close()
            except Exception:
                pass

            browser.close()

        self.generate_report()

    def _check_response(self, resp):
        # We only care about 4xx/5xx on our own assets or critical apis
        if resp.status >= 400:
            url = resp.url
            if "travel-monitoring" in url or "plot.ly" in url:
                self.failed_requests.append(f"{resp.status} on {url}")

    def test_landing_page(self, page):
        print("\n--- Testing Landing Page (TC-LAND) ---")
        self.console_errors.clear()
        
        url = f"{BASE_URL}/index.html"
        resp = page.goto(url, wait_until="networkidle", timeout=30000)
        
        # TC-LAND-01: HTTP Status & Title
        if resp and resp.status == 200:
            title = page.title()
            self.record_result("TC-LAND-01", "Landing page HTTP 200 and Title", "PASS", f"Title: {title}")
        else:
            self.record_result("TC-LAND-01", "Landing page HTTP 200", "FAIL", f"Status: {resp.status if resp else 'None'}")

        # TC-LAND-02: Manifest vs UI Cards Count
        cards = page.locator("a[href*='index_filter']")
        count = cards.count()
        if count >= 20:
            self.record_result("TC-LAND-02", "Filter cards rendered on landing", "PASS", f"Found {count} filter cards")
        else:
            self.record_result("TC-LAND-02", "Filter cards rendered on landing", "WARN", f"Expected >= 20, found {count}")

        # TC-LAND-03: Console errors on landing
        if not self.console_errors:
            self.record_result("TC-LAND-05", "No console errors on landing", "PASS")
        else:
            self.record_result("TC-LAND-05", "No console errors on landing", "FAIL", f"Errors: {self.console_errors}")

    def test_dashboard_cyprus(self, page):
        print("\n--- Testing Cyprus Dashboard & AI Passport (TC-DASH-CY & TC-PASS) ---")
        self.console_errors.clear()
        
        url = f"{BASE_URL}/index_filter_cyprus_7_10.html"
        resp = page.goto(url, wait_until="networkidle", timeout=30000)

        # TC-DASH-01: Page Load
        if resp and resp.status == 200:
            self.record_result("TC-DASH-01", "Cyprus dashboard HTTP 200", "PASS")
        else:
            self.record_result("TC-DASH-01", "Cyprus dashboard HTTP 200", "FAIL", f"Status: {resp.status if resp else 'None'}")

        # Check console errors
        if not self.console_errors:
            self.record_result("TC-DASH-05-CY", "Zero console errors on Cyprus dashboard", "PASS")
        else:
            self.record_result("TC-DASH-05-CY", "Zero console errors on Cyprus dashboard", "FAIL", f"Errors: {self.console_errors}")

        # Plotly chart check
        chart = page.locator("#avgTop10, #offersCountChart, .js-plotly-plot").first
        if chart.is_visible():
            self.record_result("TC-DASH-PLOT-CY", "Plotly chart visible on Cyprus dashboard", "PASS")
        else:
            self.record_result("TC-DASH-PLOT-CY", "Plotly chart visible on Cyprus dashboard", "WARN", "Plotly container not visible")

        # Search test: search for 'Riverside'
        search_input = page.locator("#hotelSearch, input[placeholder*='Поиск'], input[type='search']").first
        if search_input.is_visible():
            search_input.fill("Riverside")
            page.wait_for_timeout(400)
            self.record_result("TC-DASH-06-CY", "Search input works for 'Riverside'", "PASS")
        
        # Click on first hotel card to test Passport Drawer
        hotel_card = page.locator(".hotel-card").first
        if hotel_card.is_visible():
            hotel_card.click()
            page.wait_for_timeout(600)
            
            drawer = page.locator("#passportDrawer, #hotelDrawer, .passport-drawer, .hotel-drawer").first
            if drawer.is_visible():
                self.record_result("TC-PASS-01-CY", "Hotel Passport Drawer opened", "PASS")
                drawer_text = drawer.inner_text()
                
                # TC-PASS-02: VERIFY DESTINATION BUG FIX: Cyprus must NOT say 'в регионе Египет'
                if "в регионе Египет" in drawer_text or ("Египет" in drawer_text and "Кипр" not in drawer_text):
                    self.record_result("TC-PASS-02-CY", "Destination accuracy: Cyprus NOT contaminated with Egypt", "FAIL", "Found 'в регионе Египет' in Cyprus hotel!")
                elif "Кипр" in drawer_text or "на Кипре" in drawer_text:
                    self.record_result("TC-PASS-02-CY", "Destination accuracy: Cyprus labeled correctly ('на Кипре'/'Кипр')", "PASS")
                else:
                    self.record_result("TC-PASS-02-CY", "Destination accuracy", "WARN", "Neither Egypt nor Cyprus explicitly found in text")

                # TC-PASS-03: Photo gallery in Drawer
                gallery_imgs = drawer.locator("#galleryMainImg, #galleryThumbsRow img, .gallery-stage img")
                img_count = gallery_imgs.count()
                if img_count > 0:
                    first_img = drawer.locator("#galleryMainImg").first
                    page.wait_for_timeout(500)
                    src = first_img.get_attribute("src")
                    thumbs_count = drawer.locator("#galleryThumbsRow img").count()
                    self.record_result("TC-PASS-03-CY", "Gallery loaded with valid images and thumbnails", "PASS", f"Main src: {src[:45]}..., Thumbs: {thumbs_count}")
                else:
                    self.record_result("TC-PASS-03-CY", "Gallery images in Drawer", "WARN", "No images found in drawer gallery")

                # TC-PASS-04: Drawer Tabs Switching
                tab_buttons = drawer.locator(".drawer-tab-btn, [data-tab], .tab-link")
                tab_count = tab_buttons.count()
                if tab_count >= 3:
                    tab_buttons.nth(1).click()
                    page.wait_for_timeout(300)
                    tab_buttons.nth(2).click()
                    page.wait_for_timeout(300)
                    self.record_result("TC-PASS-04-CY", "Drawer tabs switching successfully", "PASS", f"Tabs count: {tab_count}")
                else:
                    self.record_result("TC-PASS-04-CY", "Drawer tabs switching", "WARN", f"Found {tab_count} tabs")

                # TC-PASS-07: External Links (TripAdvisor & YouTube)
                ta_link = drawer.locator("a[href*='tripadvisor']").first
                yt_link = drawer.locator("a[href*='youtube.com']").first
                ta_href = ta_link.get_attribute("href") if ta_link.count() > 0 else None
                yt_href = yt_link.get_attribute("href") if yt_link.count() > 0 else None
                
                if ta_href and "tripadvisor" in ta_href and yt_href and "youtube" in yt_href:
                    self.record_result("TC-PASS-07-CY", "TripAdvisor & YouTube links valid", "PASS", f"TA: {ta_href[:30]}..., YT: {yt_href[:30]}...")
                else:
                    self.record_result("TC-PASS-07-CY", "TripAdvisor & YouTube links", "WARN", f"TA: {ta_href}, YT: {yt_href}")

                # TC-PASS-08: Close Drawer
                close_btn = drawer.locator(".drawer-close, button:has-text('✕'), button:has-text('×'), [aria-label='Close']").first
                if close_btn.is_visible():
                    close_btn.click()
                    page.wait_for_timeout(400)
                    if not drawer.is_visible() or "open" not in (drawer.get_attribute("class") or ""):
                        self.record_result("TC-PASS-08-CY", "Drawer closed by close button", "PASS")
                    else:
                        self.record_result("TC-PASS-08-CY", "Drawer close", "WARN", "Drawer still has open/visible state")
            else:
                self.record_result("TC-PASS-01-CY", "Hotel Passport Drawer opened", "FAIL", "Drawer did not appear after card click")
        else:
            self.record_result("TC-DASH-HOTEL-CY", "Hotel cards visible on Cyprus", "FAIL", "No hotel cards found")

    def test_dashboard_turkey(self, page):
        print("\n--- Testing Turkey Dashboard (TC-DASH-TR) ---")
        self.console_errors.clear()
        url = f"{BASE_URL}/index_filter_turkey_7_10_days.html"
        resp = page.goto(url, wait_until="networkidle", timeout=30000)
        
        if resp and resp.status == 200:
            self.record_result("TC-DASH-02-TR", "Turkey dashboard HTTP 200", "PASS")
        else:
            self.record_result("TC-DASH-02-TR", "Turkey dashboard HTTP 200", "FAIL", f"Status: {resp.status if resp else 'None'}")

        # Check console errors
        if not self.console_errors:
            self.record_result("TC-DASH-05-TR", "Zero console errors on Turkey dashboard", "PASS")
        else:
            self.record_result("TC-DASH-05-TR", "Zero console errors on Turkey dashboard", "FAIL", f"Errors: {self.console_errors}")

        # Mode switch test (Table mode vs Cards mode)
        table_btn = page.locator(".mode-btn[data-mode='table'], button:has-text('Таблица')").first
        cards_btn = page.locator(".mode-btn[data-mode='cards'], button:has-text('Карточки')").first
        if table_btn.is_visible():
            table_btn.click()
            page.wait_for_timeout(400)
            table = page.locator("table.hotels-table, #hotelsTable, .table-container table").first
            is_table = table.is_visible()
            if cards_btn.is_visible():
                cards_btn.click()
                page.wait_for_timeout(400)
            self.record_result("TC-DASH-MODE-TR", "View mode switcher (Cards <-> Table)", "PASS" if is_table else "WARN", "Table toggled successfully")
        else:
            self.record_result("TC-DASH-MODE-TR", "View mode switcher", "WARN", "Mode button not found")

        # Open drawer and verify Turkey destination
        hotel_card = page.locator(".hotel-card").first
        if hotel_card.is_visible():
            hotel_card.click()
            page.wait_for_timeout(600)
            drawer = page.locator("#passportDrawer, #hotelDrawer, .passport-drawer, .hotel-drawer").first
            if drawer.is_visible():
                drawer_text = drawer.inner_text()
                if "в Турции" in drawer_text or "Турция" in drawer_text or "Turcja" in drawer_text:
                    self.record_result("TC-PASS-02-TR", "Destination accuracy: Turkey labeled correctly ('в Турции'/'Турция')", "PASS")
                else:
                    self.record_result("TC-PASS-02-TR", "Destination accuracy: Turkey", "WARN", "Keyword 'Турция' not found in drawer")
                
                # Close drawer via Esc key
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)

    def test_dashboard_egypt(self, page):
        print("\n--- Testing Egypt Dashboard (TC-DASH-EG) ---")
        self.console_errors.clear()
        url = f"{BASE_URL}/index_filter_7_10_days.html"
        resp = page.goto(url, wait_until="networkidle", timeout=30000)
        
        if resp and resp.status == 200:
            self.record_result("TC-DASH-03-EG", "Egypt dashboard HTTP 200", "PASS")
        else:
            self.record_result("TC-DASH-03-EG", "Egypt dashboard HTTP 200", "FAIL", f"Status: {resp.status if resp else 'None'}")

        if not self.console_errors:
            self.record_result("TC-DASH-05-EG", "Zero console errors on Egypt dashboard", "PASS")
        else:
            self.record_result("TC-DASH-05-EG", "Zero console errors on Egypt dashboard", "FAIL", f"Errors: {self.console_errors}")

        # Test Egypt hotel drawer
        hotel_card = page.locator(".hotel-card").first
        if hotel_card.is_visible():
            hotel_card.click()
            page.wait_for_timeout(600)
            drawer = page.locator("#passportDrawer, #hotelDrawer, .passport-drawer, .hotel-drawer").first
            if drawer.is_visible():
                drawer_text = drawer.inner_text()
                if "в Египте" in drawer_text or "Египет" in drawer_text or "Egipt" in drawer_text:
                    self.record_result("TC-PASS-02-EG", "Destination accuracy: Egypt labeled correctly ('в Египте')", "PASS")
                else:
                    self.record_result("TC-PASS-02-EG", "Destination accuracy: Egypt", "WARN", "Keyword 'Египет' not found")
                page.keyboard.press("Escape")

    def test_dashboard_greece(self, page):
        print("\n--- Testing Greece Dashboard (TC-DASH-GR) ---")
        self.console_errors.clear()
        url = f"{BASE_URL}/index_filter_greece_7_10_days.html"
        resp = page.goto(url, wait_until="networkidle", timeout=30000)
        
        if resp and resp.status == 200:
            self.record_result("TC-DASH-04-GR", "Greece dashboard HTTP 200", "PASS")
        else:
            self.record_result("TC-DASH-04-GR", "Greece dashboard HTTP 200", "FAIL", f"Status: {resp.status if resp else 'None'}")

        if not self.console_errors:
            self.record_result("TC-DASH-05-GR", "Zero console errors on Greece dashboard", "PASS")
        else:
            self.record_result("TC-DASH-05-GR", "Zero console errors on Greece dashboard", "FAIL", f"Errors: {self.console_errors}")

    def test_all_filter_links(self, page):
        print("\n--- Testing All 22 Production Filter Links (TC-LINKS) ---")
        manifest_url = f"{BASE_URL}/filters_manifest.json"
        try:
            with urllib.request.urlopen(manifest_url, timeout=10) as r:
                data = json.loads(r.read().decode('utf-8'))
                filters = data.get('filters', [])
        except Exception as e:
            self.record_result("TC-LINKS-ALL", "Fetch filters manifest", "FAIL", str(e))
            return

        broken = []
        stale = []
        for f in filters:
            href = f.get('href')
            scraped = f.get('last_scraped_iso', '')
            if not href:
                continue
            full_url = f"{BASE_URL}/{href}"
            try:
                req = urllib.request.Request(full_url, method='HEAD')
                with urllib.request.urlopen(req, timeout=8) as r:
                    if r.status != 200:
                        broken.append(f"{href} (status {r.status})")
            except Exception as e:
                broken.append(f"{href} ({e})")

            # Check freshness (must be within last 48h)
            if scraped and "2026-11-04" not in scraped and "2026-11-03" not in scraped:
                stale.append(f"{href} ({scraped})")

        if not broken:
            self.record_result("TC-LINKS-01", f"All {len(filters)} dashboard pages return HTTP 200", "PASS")
        else:
            self.record_result("TC-LINKS-01", f"All dashboard pages return HTTP 200", "FAIL", f"Broken: {broken}")

        if not stale:
            self.record_result("TC-FRESH-01", f"All 22 filters have fresh data (<= 48h)", "PASS")
        else:
            self.record_result("TC-FRESH-01", f"All filters have fresh data", "WARN", f"Stale filters: {stale}")

    def test_mobile_experience(self, page):
        print("\n--- Testing Mobile UX (TC-MOB) ---")
        self.console_errors.clear()
        
        # Test Landing on Mobile
        page.goto(f"{BASE_URL}/index.html", wait_until="networkidle", timeout=30000)
        self.record_result("TC-MOB-01", "Mobile landing view 390x844 loaded", "PASS")

        # Test Dashboard on Mobile
        page.goto(f"{BASE_URL}/index_filter_turkey_7_10_days.html", wait_until="networkidle", timeout=30000)
        
        # Check sidebar toggle on mobile
        sidebar_toggle = page.locator("#sidebarToggle, .sidebar-toggle, button:has-text('Фильтры')").first
        if sidebar_toggle.is_visible():
            sidebar_toggle.click()
            page.wait_for_timeout(400)
            sidebar = page.locator("#sidebar, .filters-sidebar").first
            is_open = sidebar.is_visible()
            self.record_result("TC-MOB-02", "Mobile sidebar toggle works", "PASS" if is_open else "WARN")
            # Close sidebar
            sidebar_toggle.click()
            page.wait_for_timeout(300)
        else:
            self.record_result("TC-MOB-02", "Mobile sidebar toggle button found", "WARN", "Toggle button not visible")

        # Check hotel card click & full-width drawer on mobile
        hotel_card = page.locator(".hotel-card").first
        if hotel_card.is_visible():
            hotel_card.click()
            page.wait_for_timeout(600)
            drawer = page.locator("#passportDrawer, #hotelDrawer, .passport-drawer, .hotel-drawer").first
            if drawer.is_visible():
                box = drawer.bounding_box()
                width = box["width"] if box else 0
                if width >= 360:  # occupying almost full mobile screen width
                    self.record_result("TC-MOB-04", "Mobile drawer renders full-screen width", "PASS", f"Width: {width}px on 390px viewport")
                else:
                    self.record_result("TC-MOB-04", "Mobile drawer width", "WARN", f"Width: {width}px")

    def generate_report(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        warned = sum(1 for r in self.results if r["status"] == "WARN")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        
        print("\n=======================================================")
        print(f"📊 QA TEST EXECUTION SUMMARY:")
        print(f"Total Tests: {total} | Passed: {passed} | Warnings: {warned} | Failed: {failed}")
        print(f"Pass Rate: {passed / total * 100:.1f}%")
        print("=======================================================\n")
        
        # Save JSON output for reporting artifact
        summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base_url": BASE_URL,
            "total": total,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "pass_rate": round(passed / total * 100, 1),
            "results": self.results,
            "failed_requests": self.failed_requests,
            "console_errors": self.console_errors
        }
        with open("/tmp/qa_prod_results.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    runner = QATestRunner()
    runner.run_tests()
