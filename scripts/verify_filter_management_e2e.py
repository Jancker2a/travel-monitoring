#!/usr/bin/env python3
"""
Automated E2E Test Suite for Filter & Dashboard Management System (Admin Hub).
Tests:
1. Python engine: status changes (pause/resume/archive/delete), group reassignments, runner exclusions.
2. IssueOps payload execution & cryptographic signature verification.
3. Headless Playwright UI validation: Access Gate, stats, search, modals, 0 console errors.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import filter_registry
import scripts.manage_filter as manage_filter


def run_engine_tests():
    print("🧪 Running Filter Management Engine Unit Tests...")

    # 1. Verify manifest export
    manifest = filter_registry.get_filters_admin_manifest()
    assert manifest['counts']['total'] >= 13, f"Expected at least 13 filters, got {manifest['counts']['total']}"
    assert manifest['counts']['active'] >= 10, f"Expected active >= 10, got {manifest['counts']['active']}"
    print("  ✅ TC-01: Manifest export & counting passed")

    # 2. Test Pause action
    test_id = "turkey_7_10"
    manage_filter.set_filter_status(test_id, "paused")
    
    # Check runner exclusions
    active_monitors = filter_registry.get_all_monitor_configs()
    assert not any("turkey_7_10" in c for c in active_monitors), f"Paused filter {test_id} must be skipped in monitoring configs!"
    
    active_germany = filter_registry.get_all_germany_configs()
    assert not any("turkey_7_10" in c for c in active_germany), f"Paused filter {test_id} must be skipped in germany configs!"
    
    dashboard_configs = filter_registry.get_all_dashboard_configs()
    t_dash = next((d for d in dashboard_configs if "turkey_7_10" in d['config']), None)
    assert t_dash is not None, f"Paused filter {test_id} must still have dashboard definition!"
    assert t_dash.get('status') == 'paused', f"Dashboard config status must be 'paused', got {t_dash.get('status')}"
    print("  ✅ TC-02: Filter pause & runner exclusion passed")

    # 3. Test Resume action
    manage_filter.set_filter_status(test_id, "active")
    active_monitors_after = filter_registry.get_all_monitor_configs()
    assert any("turkey_7_10" in c for c in active_monitors_after), f"Resumed filter {test_id} must be included in monitoring configs!"
    print("  ✅ TC-03: Filter resume & monitoring inclusion passed")

    # 4. Test Category Reassignment
    manage_filter.set_filter_group(test_id, "cyprus")
    discovered = filter_registry.discover_filter_groups()
    cyprus_group = next((g for g in discovered if g['id'] == 'cyprus'), None)
    assert cyprus_group is not None, "Cyprus group must exist when filter moved there!"
    assert any(f['id'] == test_id for f in cyprus_group['filters']), f"Filter {test_id} must appear in Cyprus group!"
    print("  ✅ TC-04: Category reassignment passed")

    # Restore category to turkey
    manage_filter.set_filter_group(test_id, "turkey")
    discovered_restored = filter_registry.discover_filter_groups()
    turkey_group = next((g for g in discovered_restored if g['id'] == 'turkey'), None)
    assert any(f['id'] == test_id for f in turkey_group['filters']), f"Filter {test_id} must be back in Turkey group!"
    print("  ✅ TC-05: Category restoration passed")

    # 5. Test Custom Group Creation
    manage_filter.set_filter_group(test_id, "canary", group_label="Канарские о-ва", group_icon="🏝️")
    known = filter_registry.get_known_groups()
    assert "canary" in known, "Custom group 'canary' must be registered in known groups!"
    assert known["canary"]["label"] == "Канарские о-ва", "Custom group label mismatch!"
    # Restore
    manage_filter.set_filter_group(test_id, "turkey")
    meta = filter_registry.load_filters_meta()
    meta.get("custom_groups", {}).pop("canary", None)
    filter_registry.save_filters_meta(meta)
    print("  ✅ TC-06: Custom category creation & cleanup passed")

    # 6. Test IssueOps Payload Security Verification
    valid_payload = {
        "action": "pause",
        "filter_id": "turkey_7_10",
        "signature": manage_filter.AUTH_KEY_HASH,
    }
    res = manage_filter.process_payload(valid_payload)
    assert res['success'] is True, "Valid payload execution must succeed!"
    manage_filter.set_filter_status(test_id, "active")

    # Invalid signature test
    invalid_payload = {
        "action": "pause",
        "filter_id": "turkey_7_10",
        "signature": "wrong_signature_hash_12345",
    }
    try:
        manage_filter.process_payload(invalid_payload)
        assert False, "Execution with invalid signature must raise PermissionError!"
    except PermissionError:
        print("  ✅ TC-07: Cryptographic signature validation passed")

    print("\n✨ All Engine Unit Tests Passed Successfully!\n")


def run_browser_ui_tests():
    print("🌐 Running Playwright Browser UI Tests for Admin Hub...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️ Playwright not installed in environment, skipping browser UI tests.")
        return

    # Export fresh manifest before test
    manage_filter.export_manifest(ROOT / "filters_manifest.json")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1400, 'height': 900})
        page = context.new_page()

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("console", lambda msg: errors.append(f"CONSOLE {msg.type}: {msg.text}") if msg.type == "error" else None)

        base_url = "http://localhost:8080/admin_filters.html"

        # UI-01: Locked access gate
        page.goto(base_url, wait_until="networkidle")
        assert page.is_visible("#authOverlay"), "Access gate overlay must be visible on unauthorized visit!"
        assert not page.is_visible("#appMain"), "Main app must be hidden before unlock!"
        print("  ✅ UI-01: Access gate blocks unauthorized visit passed")

        # UI-02: Reject invalid passcode
        page.fill("#authKeyInput", "wrongpassword123")
        page.click("#authSubmitBtn")
        assert page.is_visible("#authErrorMsg"), "Error message must be shown for invalid password!"
        print("  ✅ UI-02: Invalid passcode rejection passed")

        # UI-03: Auto-unlock via ?key=travel2026
        page.goto(f"{base_url}?key=travel2026", wait_until="networkidle")
        page.wait_for_selector("#appMain", state="visible", timeout=5000)
        assert not page.is_visible("#authOverlay"), "Access gate overlay must be dismissed after auto-unlock!"
        print("  ✅ UI-03: Secret URL auto-unlock (?key=travel2026) passed")

        # UI-04: Stat summary cards check
        page.wait_for_selector("#totalFiltersCount", state="visible")
        total_text = page.inner_text("#totalFiltersCount")
        assert int(total_text) >= 13, f"Expected total filters >= 13, got {total_text}"
        print(f"  ✅ UI-04: Stat summary cards populated (total: {total_text}) passed")

        # UI-05: Dynamic Search filtering
        page.fill("#searchInput", "Турция")
        page.wait_for_timeout(300)
        cards = page.query_selector_all(".filter-item")
        assert len(cards) >= 3, f"Expected at least 3 Turkey filters, found {len(cards)}"
        page.fill("#searchInput", "")
        page.wait_for_timeout(300)
        print("  ✅ UI-05: Real-time search filter passed")

        # UI-06: Status Tabs filter
        page.click(".filter-tab[data-status='active']")
        page.wait_for_timeout(200)
        active_tab = page.query_selector(".filter-tab[data-status='active']")
        assert "active" in active_tab.get_attribute("class")
        page.click(".filter-tab[data-status='all']")
        print("  ✅ UI-06: Status tabs filtering passed")

        # UI-07: Modals (Category, Settings) open & close
        page.click("#settingsBtn")
        assert page.is_visible("#settingsModal"), "Settings modal must open on click!"
        page.click("#settingsModal .modal-close")
        page.wait_for_timeout(200)
        assert not page.is_visible("#settingsModal"), "Settings modal must close on &times; click!"
        print("  ✅ UI-07: Settings modal interaction passed")

        # UI-08: Check 0 console errors
        assert len(errors) == 0, f"Expected 0 console/page errors, but got {len(errors)}: {errors}"
        print("  ✅ UI-08: Zero console/page errors (100% clean) passed")

        browser.close()

    print("\n🎉 All Browser UI E2E Tests Passed Successfully!\n")


if __name__ == "__main__":
    run_engine_tests()
    run_browser_ui_tests()
