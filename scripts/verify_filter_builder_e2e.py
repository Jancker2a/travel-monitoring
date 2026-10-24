#!/usr/bin/env python3
"""
Comprehensive E2E Test Suite for Custom Filter Builder
Simulates a real user journey and tests all functional requirements.
"""

import json
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path("/Users/andreiyankouski/.gemini/antigravity-ide/brain/36d05fcc-98dd-4435-854e-63bdcf57e835/test_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://localhost:8080"

test_results = []

def record(tc_id, name, status, details=""):
    print(f"[{status}] {tc_id}: {name} - {details}")
    test_results.append({
        "id": tc_id,
        "name": name,
        "status": status,
        "details": details
    })

def run_tests():
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            permissions=["clipboard-read", "clipboard-write"]
        )
        page = context.new_page()

        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # ---------------------------------------------------------
        # TC-01: Landing Page Header CTA Button
        # ---------------------------------------------------------
        try:
            page.goto(f"{BASE_URL}/index.html", wait_until="networkidle")
            page.screenshot(path=str(SCREENSHOT_DIR / "01_landing_initial.png"))
            
            cta_btn = page.query_selector("a.create-btn")
            assert cta_btn is not None, "CTA button not found in header"
            assert "create_filter.html" in cta_btn.get_attribute("href")
            record("TC-01", "Landing Header CTA Button", "PASSED", f"Found CTA: '{cta_btn.inner_text()}' -> create_filter.html")
        except Exception as e:
            record("TC-01", "Landing Header CTA Button", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-02: Landing Onboarding Card CTA
        # ---------------------------------------------------------
        try:
            onboarding_cta = page.query_selector("a.onboarding-card[href='create_filter.html']")
            assert onboarding_cta is not None, "Onboarding card CTA not found"
            title = onboarding_cta.query_selector(".onboarding-card-title").inner_text()
            record("TC-02", "Landing Onboarding Card CTA", "PASSED", f"Card title: '{title}'")
            
            # Click and navigate to create_filter.html
            cta_btn.click()
            page.wait_for_load_state("networkidle")
            assert "create_filter.html" in page.url
            page.screenshot(path=str(SCREENSHOT_DIR / "02_builder_locked_gate.png"))
            
            # Verify gate is displayed
            assert page.is_visible("#securityGateContainer"), "Security Gate should be displayed"
            record("TC-03", "Security Gate Locked Screen", "PASSED", "Access Gate correctly intercepts unauthenticated user")

            # Unlock with valid key
            page.fill("#gateKeyInput", "travel2026")
            page.click("button:has-text('Разблокировать доступ')")
            time.sleep(0.3)
            assert page.is_visible("#mainBuilderContainer"), "Builder should be unlocked after valid key"
            record("TC-03b", "Security Gate Key Unlock", "PASSED", "Successfully unlocked builder using passcode")
            page.screenshot(path=str(SCREENSHOT_DIR / "02b_builder_unlocked.png"))
        except Exception as e:
            record("TC-03", "Security Gate & Unlock", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-04: Error Handling on Invalid / Empty Fly.pl URL
        # ---------------------------------------------------------
        try:
            page.fill("#flyUrlInput", "https://google.com/search?q=tours")
            page.click("button:has-text('Распознать параметры')")
            status_el = page.query_selector("#parseStatus")
            assert "error" in status_el.get_attribute("class")
            record("TC-04", "Invalid URL Error Handling", "PASSED", f"Error message shown: '{status_el.inner_text()}'")
            page.screenshot(path=str(SCREENSHOT_DIR / "03_invalid_url_error.png"))
        except Exception as e:
            record("TC-04", "Invalid URL Error Handling", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-05: Quick Mode - Parsing Valid Fly.pl Search URL (Cyprus 2+1)
        # ---------------------------------------------------------
        try:
            valid_url = (
                "https://fly.pl/szukaj-wycieczek/?destinationLocation=12_170"
                "&departureLocation=Warszawa,Katowice"
                "&adults=2&children=10-12-2020&catering=all_inclusive"
                "&durationFrom=7&durationTo=10&priceTo=15000"
            )
            page.fill("#flyUrlInput", valid_url)
            page.click("button:has-text('Распознать параметры')")
            time.sleep(0.3)
            
            status_el = page.query_selector("#parseStatus")
            assert "success" in status_el.get_attribute("class")
            
            # Check synchronized form inputs
            selected_dest = page.query_selector(".dest-card.selected")
            assert "Кипр" in selected_dest.inner_text(), f"Expected Cyprus, got {selected_dest.inner_text()}"
            
            adults_val = page.inner_text("#adultsVal")
            assert adults_val == "2", f"Expected 2 adults, got {adults_val}"
            
            children_val = page.inner_text("#childrenVal")
            assert children_val == "1", f"Expected 1 child, got {children_val}"

            catering_val = page.input_value("#cateringSelect")
            assert catering_val == "all_inclusive", f"Expected all_inclusive, got {catering_val}"

            record("TC-05", "Valid URL Parsing & Form Sync", "PASSED", f"Cyprus, 2 adults, 1 child, All Inclusive recognized successfully")
            page.screenshot(path=str(SCREENSHOT_DIR / "04_parsed_cyprus_success.png"))
        except Exception as e:
            record("TC-05", "Valid URL Parsing & Form Sync", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-06: Interactive Visual Builder - Switching Destination & Airport Chips
        # ---------------------------------------------------------
        try:
            page.click("#tabVisual")
            time.sleep(0.2)
            
            # Switch to Greece
            page.click(".dest-card:has-text('Греция')")
            time.sleep(0.2)
            assert "selected" in page.query_selector(".dest-card:has-text('Греция')").get_attribute("class")
            
            # Click quick preset "Только Варшава"
            page.click("a:has-text('Только Варшава')")
            time.sleep(0.2)
            
            selected_chips = page.query_selector_all(".chip.selected")
            assert len(selected_chips) == 3, f"Expected 3 Warsaw airports, got {len(selected_chips)}"
            
            record("TC-06", "Destination & Airport Chips Interaction", "PASSED", "Switched to Greece & applied Warsaw 3-airports preset")
            page.screenshot(path=str(SCREENSHOT_DIR / "05_visual_greece_airports.png"))
        except Exception as e:
            record("TC-06", "Destination & Airport Chips Interaction", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-07: Airport Deselection Guard (Must keep at least 1 airport)
        # ---------------------------------------------------------
        try:
            # Deselect chips one by one until only 1 remains
            for _ in range(2):
                sel = page.query_selector_all(".chip.selected")
                if len(sel) > 1:
                    sel[0].click()
                    time.sleep(0.15)
            
            # Try deselecting the last remaining airport
            last_chip = page.query_selector(".chip.selected")
            assert last_chip is not None, "At least 1 airport should be selected"
            last_chip.click()
            time.sleep(0.15)
            
            # Verify it is still selected and toast message was triggered
            assert "selected" in page.query_selector(".chip.selected").get_attribute("class"), "Last airport should remain selected!"
            toast = page.query_selector("#toastMsg")
            assert "show" in toast.get_attribute("class"), "Toast notification should be displayed"
            record("TC-07", "Airport Deselection Guard", "PASSED", f"Protected from 0 airports: '{toast.inner_text()}'")
            page.screenshot(path=str(SCREENSHOT_DIR / "06_airport_guard_toast.png"))
        except Exception as e:
            record("TC-07", "Airport Deselection Guard", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-08: Date Mode Toggle & Fixed Dates Input
        # ---------------------------------------------------------
        try:
            page.click("#modeFixed")
            time.sleep(0.2)
            assert page.is_visible("#fixedDatesRow"), "Fixed dates input row should be visible"
            page.fill("#startDateMin", "2026-08-10")
            page.fill("#startDateMax", "2026-08-25")
            time.sleep(0.2)
            
            # Check that live preview URL contains 10-08-2026
            preview_url = page.inner_text("#previewUrlText")
            assert "10-08-2026" in preview_url, f"Date 10-08-2026 not found in preview URL: {preview_url}"
            record("TC-08", "Fixed Dates Toggle & Preview Sync", "PASSED", f"Preview URL updated with fixed dates: {preview_url[:65]}...")
            page.screenshot(path=str(SCREENSHOT_DIR / "07_fixed_dates.png"))
        except Exception as e:
            record("TC-08", "Fixed Dates Toggle & Preview Sync", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-09: Tourists & Children Stepper (Dynamic child birthday row visibility)
        # ---------------------------------------------------------
        try:
            # Decrease children to 0
            page.click("button:has-text('−'):near(#childrenVal)")
            time.sleep(0.2)
            assert page.inner_text("#childrenVal") == "0"
            assert not page.is_visible("#childrenBdaysRow"), "Child birthday row must be hidden when children=0"
            
            # Increase children to 1
            page.click("button:has-text('+'):near(#childrenVal)")
            time.sleep(0.2)
            assert page.inner_text("#childrenVal") == "1"
            assert page.is_visible("#childrenBdaysRow"), "Child birthday row must be shown when children=1"
            
            record("TC-09", "Guests Stepper & Dynamic Child Row", "PASSED", "Child birthday input conditionally toggles smoothly")
        except Exception as e:
            record("TC-09", "Guests Stepper & Dynamic Child Row", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-10: Dashboard Feature Toggles & Germany Direct Flight Sub-option
        # ---------------------------------------------------------
        try:
            # Check that Germany direct flight sub-switch is visible when Germany Arbitrage is ON
            assert page.is_visible("#directFlightItem"), "Direct flight option should be visible when arbitrage is ON"
            
            # Toggle Direct flight ON
            page.click("#modDirectFlight + .slider")
            time.sleep(0.2)
            assert page.is_checked("#modDirectFlight")
            
            # Toggle Arbitrage Germany OFF -> Direct flight option should hide
            page.click("#modArbitrage + .slider")
            time.sleep(0.2)
            assert not page.is_visible("#directFlightItem"), "Direct flight option should be hidden when arbitrage is OFF"
            
            # Toggle Arbitrage Germany back ON
            page.click("#modArbitrage + .slider")
            time.sleep(0.2)
            assert page.is_visible("#directFlightItem")
            
            record("TC-10", "Feature Toggles & Conditional Visibility", "PASSED", "Direct flight sub-option conditionally toggles with Germany arbitrage")
            page.screenshot(path=str(SCREENSHOT_DIR / "08_feature_toggles.png"))
        except Exception as e:
            record("TC-10", "Feature Toggles & Conditional Visibility", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-11: Live Preview Pill & Verification Link
        # ---------------------------------------------------------
        try:
            preview_link = page.query_selector("#previewFlyLink")
            fly_href = preview_link.get_attribute("href")
            assert fly_href.startswith("https://fly.pl/szukaj-wycieczek/?"), f"Invalid test link: {fly_href}"
            summary = page.inner_text("#previewSummary")
            assert "Греция" in summary, f"Expected Greece in summary, got: {summary}"
            record("TC-11", "Live Preview Verification Link", "PASSED", f"Link points to Fly.pl search with summary: '{summary}'")
        except Exception as e:
            record("TC-11", "Live Preview Verification Link", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-12: Collapsible JSON Code Preview
        # ---------------------------------------------------------
        try:
            page.click("button:has-text('Просмотр JSON')")
            time.sleep(0.2)
            assert page.is_visible("#jsonPreviewWrap"), "JSON code preview should be visible"
            code_text = page.inner_text("#jsonCodeView")
            parsed_json = json.loads(code_text)
            assert parsed_json["group"] == "greece"
            assert "url" in parsed_json
            assert "modules" in parsed_json
            record("TC-12", "Collapsible JSON Preview", "PASSED", f"Valid JSON generated with id: {parsed_json['id']}")
            page.screenshot(path=str(SCREENSHOT_DIR / "09_json_code_preview.png"))
        except Exception as e:
            record("TC-12", "Collapsible JSON Preview", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-13: Copy to Clipboard Interaction
        # ---------------------------------------------------------
        try:
            page.click("button:has-text('Скопировать')")
            time.sleep(0.3)
            toast = page.query_selector("#toastMsg")
            assert "show" in toast.get_attribute("class")
            record("TC-13", "Copy to Clipboard Action", "PASSED", f"Toast confirmation triggered: '{toast.inner_text()}'")
        except Exception as e:
            record("TC-13", "Copy to Clipboard Action", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-14: Download JSON File Interaction
        # ---------------------------------------------------------
        try:
            with page.expect_download() as download_info:
                page.click("button:has-text('Скачать')")
            download = download_info.value
            download_path = SCREENSHOT_DIR / download.suggested_filename
            download.save_as(download_path)
            assert download_path.is_file(), "Downloaded file not saved!"
            with open(download_path, "r", encoding="utf-8") as f:
                d_json = json.load(f)
            assert d_json["group"] == "greece"
            record("TC-14", "Download JSON File", "PASSED", f"Downloaded {download.suggested_filename} ({download_path.stat().st_size} bytes)")
        except Exception as e:
            record("TC-14", "Download JSON File", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-15: Issue Ops Button (Pre-filled URL check)
        # ---------------------------------------------------------
        try:
            # We intercept popup/new window
            with context.expect_page() as new_page_info:
                page.click("button:has-text('Сохранить и запустить мониторинг')")
            issue_page = new_page_info.value
            issue_url = issue_page.url
            assert "github.com/Jancker2a/travel-monitoring/issues/new" in issue_url
            assert "title=%5BNEW_FILTER%5D" in issue_url
            record("TC-15", "Issue Ops URL Generation", "PASSED", f"Generated URL: {issue_url[:80]}...")
            issue_page.close()
        except Exception as e:
            record("TC-15", "Issue Ops URL Generation", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-16: Theme Switching & Persistence across reload
        # ---------------------------------------------------------
        try:
            # Toggle to dark theme
            page.click("#themeToggleBtn")
            time.sleep(0.2)
            theme_attr = page.get_attribute("html", "data-theme")
            assert theme_attr == "dark", f"Expected data-theme='dark', got '{theme_attr}'"
            page.screenshot(path=str(SCREENSHOT_DIR / "10_dark_theme.png"))
            
            # Reload page and check persistence
            page.reload(wait_until="networkidle")
            theme_after_reload = page.get_attribute("html", "data-theme")
            assert theme_after_reload == "dark", f"Theme not persisted in localStorage! Got '{theme_after_reload}'"
            record("TC-16", "Theme Persistence across reload", "PASSED", "Dark theme persisted in localStorage")
        except Exception as e:
            record("TC-16", "Theme Persistence across reload", "FAILED", str(e))

        # ---------------------------------------------------------
        # TC-17: Console Errors Verification (0 PAGE ERRORs)
        # ---------------------------------------------------------
        if page_errors:
            record("TC-17", "Console Errors Check", "FAILED", f"Errors encountered: {page_errors}")
        else:
            record("TC-17", "Console Errors Check", "PASSED", "0 PAGE ERRORs in browser console")

        browser.close()

    print("\n" + "="*70)
    print("TEST EXECUTION SUMMARY:")
    passed_cnt = sum(1 for r in test_results if r["status"] == "PASSED")
    total_cnt = len(test_results)
    print(f"Total: {total_cnt} | Passed: {passed_cnt} | Failed: {total_cnt - passed_cnt}")
    print("="*70)

    # Save results to json
    report_json_path = SCREENSHOT_DIR / "test_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)

    return 0 if (total_cnt == passed_cnt) else 1

if __name__ == "__main__":
    sys.exit(run_tests())
