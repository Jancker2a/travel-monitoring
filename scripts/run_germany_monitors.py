#!/usr/bin/env python3
"""
Runs German Package Tour monitoring for all persistent Polish filters and specific trips (e.g. Sharm 1-person).
Uses germany_monitor.py with --from-polish-config to automatically derive Check24 parameters.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# All persistent filters + Sharm 1-person trip
GERMANY_TARGET_CONFIGS = [
    "config_ci_filter_turkey_7_10.json",
    "config_ci_filter_turkey_9_11.json",
    "config_ci_filter_turkey_13_16.json",
    "config_ci_filter_turkey_vacation_jul18.json",
    "config_ci_filter_egypt_autumn_7_10.json",
    "config_ci_filter_egypt_autumn_13_16.json",
    "config_ci_filter_greece_7_10.json",
    "config_ci_filter_greece_13_16.json",
    "config_ci_filter_egypt_sharm_dec20_29_1p.json",
]


def run_germany_monitoring():
    print(f"🇩🇪 Starting German Tour Monitoring (BER/DRS) for {len(GERMANY_TARGET_CONFIGS)} filters...")
    t_start = time.monotonic()
    success_count = 0

    for cfg_name in GERMANY_TARGET_CONFIGS:
        cfg_path = ROOT / cfg_name
        if not cfg_path.is_file():
            print(f"  ⏭ Skipping {cfg_name} (file not found)")
            continue

        print(f"  🛫 Scraping German pairs for {cfg_name}...")
        cmd = [
            sys.executable,
            str(ROOT / "germany_monitor.py"),
            "--from-polish-config",
            str(cfg_path),
            "--max-pages",
            "1",
        ]

        t0 = time.monotonic()
        try:
            res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            elapsed = time.monotonic() - t0
            if res.returncode == 0:
                success_count += 1
                print(f"     ✅ {cfg_name} completed in {elapsed:.1f}s")
            else:
                print(f"     ⚠️ {cfg_name} warning (exit code {res.returncode}): {res.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"     ⏰ {cfg_name} timed out after 60s")
        except Exception as e:
            print(f"     ❌ {cfg_name} error: {e}")

    total_elapsed = time.monotonic() - t_start
    print(
        f"✅ German Tour Monitoring finished: {success_count}/{len(GERMANY_TARGET_CONFIGS)} "
        f"successful in {total_elapsed:.1f}s"
    )


if __name__ == "__main__":
    run_germany_monitoring()
