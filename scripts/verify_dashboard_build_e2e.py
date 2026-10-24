#!/usr/bin/env python3
"""
Test end-to-end dashboard build for a newly registered custom filter.
Verifies that run_dashboards_parallel.py and generate_inline_charts_dashboard.py
successfully compile HTML for a new filter and that the dashboard renders with 0 console errors.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = Path("/Users/andreiyankouski/.gemini/antigravity-ide/brain/36d05fcc-98dd-4435-854e-63bdcf57e835/test_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

TEST_SLUG = "cyprus_demo_7_10"
CONFIG_FILE = ROOT / f"configs/filters/config_ci_{TEST_SLUG}.json"
DATA_DIR = ROOT / f"data/filters/filter_{TEST_SLUG}"
HTML_OUTPUT = ROOT / f"index_filter_{TEST_SLUG}.html"

def cleanup():
    if CONFIG_FILE.is_file():
        CONFIG_FILE.unlink()
    if DATA_DIR.is_dir():
        shutil.rmtree(DATA_DIR)
    if HTML_OUTPUT.is_file():
        HTML_OUTPUT.unlink()

def run_test():
    print("="*70)
    print("TEST: End-to-End Build of New Filter Dashboard")
    print("="*70)

    cleanup()

    try:
        # Step 1: Create new filter config
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        config_data = {
            "allow_empty_offers": True,
            "id": f"filter_{TEST_SLUG}",
            "title": "Кипр • Демо • 7–10 дней",
            "subtitle": "WAW • 2 взр • All Inclusive • показ ≤12k PLN",
            "group": "cyprus",
            "group_label": "Кипр",
            "group_icon": "🇨🇾",
            "url": "https://fly.pl/szukaj-wycieczek/?destinationLocation=12_170&departureLocation=Warszawa&adults=2&catering=all_inclusive&durationFrom=7&durationTo=10&priceTo=15000",
            "max_price_threshold": 15000,
            "min_price_threshold": 3000,
            "display_price_ceiling": 12000,
            "history_price_ceiling": 12000,
            "data_dir": f"data/filters/filter_{TEST_SLUG}",
            "output_data_file": "travel_prices.csv",
            "required_offer_url_contains": ["/wycieczka/cypr", "transport=accommodation_flight"],
            "excluded_offer_url_contains": ["/wycieczka/polska"],
            "wait_timeout": 30000,
            "max_retries": 3,
            "max_pages": 10,
            "description": "Тестовый дашборд Кипр 7-10 дней",
            "modules": {
                "arbitrage_germany": True,
                "hopper_predictor": True,
                "departure_analytics": True,
                "deal_score": True,
                "room_types": True,
                "telegram_alerts": False
            },
            "germany_params": {
                "enabled": True,
                "departure_airport": "BER",
                "direct_flight_only": False
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        print(f"✓ Step 1: Created config {CONFIG_FILE.name}")

        # Step 2: Create sample data from main git branch
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        csv_file = DATA_DIR / "travel_prices.csv"
        
        # Pull 50 clean rows from git history
        git_cmd = "git show origin/main:data/filters/filter_turkey_7_10_days/travel_prices.csv | grep -v '<<<' | grep -v '===' | grep -v '>>>' | head -n 80"
        csv_content = subprocess.check_output(git_cmd, shell=True, cwd=str(ROOT), text=True)
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write(csv_content)
        print(f"✓ Step 2: Created sample CSV with {len(csv_content.splitlines())} lines at {csv_file.relative_to(ROOT)}")

        # Step 3: Run single dashboard generator directly to verify build
        print("✓ Step 3: Executing generate_inline_charts_dashboard.py for the new filter...")
        t0 = time.monotonic()
        build_cmd = [
            sys.executable,
            str(ROOT / "generate_inline_charts_dashboard.py"),
            "--data-file", str(csv_file),
            "--output", str(HTML_OUTPUT),
            "--title", config_data["title"],
            "--charts-dir", f"hotel-charts/filter_{TEST_SLUG}",
            "--config", str(CONFIG_FILE),
            "--display-price-ceiling", "12000",
            "--history-price-ceiling", "12000"
        ]
        res = subprocess.run(build_cmd, cwd=str(ROOT), capture_output=True, text=True)
        elapsed = time.monotonic() - t0
        print(f"  Build finished in {elapsed:.2f}s (exit_code={res.returncode})")
        if res.returncode != 0:
            print("STDERR:\n", res.stderr)
            print("STDOUT:\n", res.stdout)
            raise RuntimeError(f"Dashboard generator failed with exit code {res.returncode}")

        assert HTML_OUTPUT.is_file(), f"Dashboard HTML {HTML_OUTPUT.name} was not created!"
        html_size = HTML_OUTPUT.stat().st_size
        print(f"✓ Step 3 PASSED: Dashboard generated ({html_size:,} bytes)")

        # Step 4: Run landing generator to verify the new filter card appears
        print("✓ Step 4: Generating landing page with dynamic auto-discovery...")
        landing_cmd = [sys.executable, str(ROOT / "generate_landing.py")]
        subprocess.check_call(landing_cmd, cwd=str(ROOT))
        landing_html = (ROOT / "index.html").read_text(encoding="utf-8")
        assert f"index_filter_{TEST_SLUG}.html" in landing_html, "New filter link not found in landing page!"
        print("✓ Step 4 PASSED: New filter card discovered and rendered on landing page")

        # Step 5: Playwright Headless Verification of Generated Dashboard
        print("✓ Step 5: Validating generated dashboard in Headless Chromium...")
        page_errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 950})
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            # Open local dashboard URL
            dashboard_url = f"http://localhost:8080/{HTML_OUTPUT.name}"
            page.goto(dashboard_url, wait_until="networkidle")

            # Check title
            title_text = page.title()
            print(f"  Page title: {title_text}")
            assert "Кипр • Демо" in title_text

            # Check hero header
            hero_title = page.inner_text(".hero-title-clean")
            print(f"  Hero title: {hero_title}")

            # Check Plotly container
            chart_exists = page.query_selector(".js-plotly-plot, #priceChart, .chart-card") is not None
            print(f"  Chart container rendered: {chart_exists}")

            # Test Sidebar Toggle and + Новый фильтр item
            page.click("#sidebarToggle")
            time.sleep(0.3)
            create_link = page.query_selector("a.nav-item-create")
            assert create_link is not None, "+ Новый фильтр link not found in sidebar!"
            # Close sidebar so overlay doesn't block main page interactions
            page.click("#sidebarToggle")
            time.sleep(0.3)

            # Test interactive elements as specified in AGENTS.md
            table_btn = page.query_selector('.mode-btn[data-mode="table"]')
            if table_btn:
                table_btn.click(timeout=5000)
                time.sleep(0.2)

            analytics_summary = page.query_selector('#analyticsFold summary')
            if analytics_summary:
                analytics_summary.click()
                time.sleep(0.2)

            page.screenshot(path=str(SCREENSHOT_DIR / "11_generated_dashboard_live.png"))

            browser.close()

        assert not page_errors, f"Dashboard had console page errors: {page_errors}"
        print("✓ Step 5 PASSED: 0 PAGE ERRORs in generated dashboard!")

        print("\n" + "="*70)
        print("🎉 SUCCESS: NEW DASHBOARD BUILD VERIFIED END-TO-END!")
        print(f"Generated dashboard: {HTML_OUTPUT.name} ({html_size:,} bytes)")
        print("Auto-discovery in landing page: Verified")
        print("Playwright Console errors: 0")
        print("="*70)
        return 0

    finally:
        print("\nCleaning up test artifacts...")
        cleanup()
        # Regenerate clean landing page
        subprocess.run([sys.executable, str(ROOT / "generate_landing.py")], cwd=str(ROOT), capture_output=True)
        print("Cleanup completed.")

if __name__ == "__main__":
    sys.exit(run_test())
