#!/usr/bin/env python3
"""Run multiple travel_monitor.py configs in parallel (separate data_dir per filter)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from filter_trip import load_config_json, should_skip_monitor_config, skip_monitor_reason

DEFAULT_CONFIGS = [
    "config_ci_filter_7_10.json",
    "config_ci_filter_13_16.json",
    "config_ci_filter_turkey_7_10.json",
    "config_ci_filter_turkey_9_11.json",
    "config_ci_filter_turkey_13_16.json",
    "config_ci_filter_greece_7_10.json",
    "config_ci_filter_greece_13_16.json",
    "config_ci_filter_egypt_autumn_7_10.json",
    "config_ci_filter_egypt_autumn_7_10_any_airports.json",
    "config_ci_filter_egypt_ny_dec24_7_10.json",
    "config_ci_filter_egypt_ny_dec28_7_10.json",
    "config_ci_filter_egypt_sharm_dec20_29_1p.json",
]


def _run_one(config_name: str, log_dir: Path, timeout_s: int = 300) -> tuple[str, int, float]:
    config_path = ROOT / config_name
    if not config_path.is_file():
        return config_name, 127, 0.0
    if should_skip_monitor_config(str(config_path)):
        try:
            reason = skip_monitor_reason(load_config_json(str(config_path))) or "пропуск"
        except Exception:
            reason = "пропуск"
        print(f"  ⏭ {config_name} ({reason})", flush=True)
        return config_name, 0, 0.0

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{config_path.stem}.log"
    import random
    time.sleep(random.uniform(0.5, 3.5))
    t0 = time.monotonic()
    print(f"  ▶️ Starting {config_name} (timeout={timeout_s}s)...", flush=True)
    with log_path.open("w", encoding="utf-8") as log_f:
        log_f.write(
            f"# {config_name}\n"
            f"# started {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# pid={os.getpid()} jobs_env={os.environ.get('MONITOR_PARALLEL_JOBS', '')}\n"
            f"# HTTP_MAX_RETRIES={os.environ.get('HTTP_MAX_RETRIES', '')}\n"
            f"# timeout={timeout_s}s\n\n"
        )
        log_f.flush()
        try:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "travel_monitor.py"), "--config", str(config_path)],
                cwd=str(ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
                timeout=timeout_s,
            )
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            log_f.write(f"\n# TIMEOUT: process exceeded {timeout_s}s limit\n")
            log_f.flush()
            print(f"  ⏰ {config_name} TIMED OUT after {timeout_s}s!", flush=True)
            returncode = 124
    elapsed = time.monotonic() - t0
    return config_name, returncode, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel travel_monitor runs")
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=int(os.environ.get("MONITOR_PARALLEL_JOBS", "3")),
        help="Max concurrent monitors (default: 3, env MONITOR_PARALLEL_JOBS)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("MONITOR_TIMEOUT_PER_CONFIG", "300")),
        help="Timeout in seconds per config (default: 300s, env MONITOR_TIMEOUT_PER_CONFIG)",
    )
    parser.add_argument(
        "--log-dir",
        default=str(ROOT / "logs" / "parallel"),
        help="Directory for per-config log files",
    )
    parser.add_argument(
        "configs",
        nargs="*",
        default=DEFAULT_CONFIGS,
        help="Config JSON paths (default: all 8 CI filters)",
    )
    args = parser.parse_args()
    jobs = max(1, args.jobs)
    log_dir = Path(args.log_dir)

    active_configs = [
        cfg for cfg in args.configs
        if (ROOT / cfg).is_file() and not should_skip_monitor_config(str(ROOT / cfg))
    ]

    print(
        f"Parallel monitoring: {len(active_configs)} active configs "
        f"(jobs={jobs}, timeout={args.timeout}s)",
        flush=True,
    )
    print(f"Logs: {log_dir}", flush=True)
    t0 = time.monotonic()
    failed: list[str] = []

    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_run_one, cfg, log_dir, args.timeout): cfg for cfg in active_configs}
        for fut in as_completed(futures):
            cfg, code, elapsed = fut.result()
            if code == 0:
                print(f"  ✓ {cfg} ({elapsed:.0f}s)", flush=True)
            elif code == 124:
                print(f"  ⏰ {cfg} TIMED OUT ({elapsed:.0f}s) → {log_dir / Path(cfg).stem}.log", flush=True)
                failed.append(cfg)
            else:
                print(f"  ✗ {cfg} exit={code} ({elapsed:.0f}s) → {log_dir / Path(cfg).stem}.log", flush=True)
                failed.append(cfg)

    total = time.monotonic() - t0
    print(f"Done in {total:.0f}s — ok {len(active_configs) - len(failed)}/{len(active_configs)}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
