#!/usr/bin/env python3
"""CSS and client-side JavaScript templates for the travel price dashboard."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def get_dashboard_css(passport_css: str = "", inline: Optional[bool] = None) -> str:
    """Returns the responsive CSS stylesheet for the dashboard.
    
    If inline is False (or None when assets/css/dashboard.css exists),
    links to external assets/css/dashboard.css to enable browser caching
    and reduce HTML payload by ~162 KB. Dynamic passport_css is retained
    in a compact inline <style> block.
    """
    if inline is False or (inline is None and os.path.exists("assets/css/dashboard.css")):
        passport_tag = f"\n    <style>\n{passport_css}\n    </style>" if passport_css.strip() else ""
        return f'    <link rel="stylesheet" href="assets/css/dashboard.css">{passport_tag}'

    css_content = """        :root {
            --primary-color: #4f46e5;
            --primary-dark: #3730a3;
            --secondary-color: #0891b2;
            --accent-color: #f59e0b;
            --success-color: #10b981;
            --danger-color: #ef4444;
            --warning-color: #f59e0b;
            --info-color: #3b82f6;
            
            --gradient-primary: linear-gradient(135deg, #4f46e5 0%, #0ea5e9 100%);
            --gradient-success: linear-gradient(135deg, #10b981 0%, #22d3ee 100%);
            --gradient-danger: linear-gradient(135deg, #ef4444 0%, #fb7185 100%);
            --gradient-card: linear-gradient(145deg, rgba(255,255,255,0.88) 0%, rgba(250,252,255,0.80) 100%);

            --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
            --shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
            --shadow-lg: 0 14px 34px rgba(15, 23, 42, 0.12);
            --shadow-xl: 0 24px 52px rgba(15, 23, 42, 0.16);
            --section-gap: 1.35rem;
            --section-inner-x: 1.5rem;
            --panel-shell-radius: 16px;
            --table-block-max-width: 100%;
            --content-max-width: 1880px;
            --page-gutter: clamp(10px, 1.35vw, 24px);
            --container-padding: clamp(1rem, 1.5vw, 2rem);

            --radius-sm: 10px;
            --radius-md: 14px;
            --radius-lg: 18px;
            --radius-xl: 24px;

            --transition-fast: .15s ease;
            --transition-normal: .25s ease;
            --transition-slow: .45s ease;

            --surface: rgba(255,255,255,0.78);
            --surface-strong: rgba(255,255,255,0.92);
            --border-soft: rgba(148, 163, 184, 0.28);
            --text-main: #0f172a;
            --text-muted: #64748b;
        }
        
        * {
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background: #f0f6fc;
            min-height: 100vh;
            line-height: 1.6;
            color: var(--text-main);
            position: relative;
            overflow-x: hidden;
        }

        body::before {
            content: "";
            position: fixed;
            inset: 0;
            z-index: -2;
            background: linear-gradient(180deg, #e8f3fc 0%, #f0f7ff 60%, #e8f3fc 100%);
        }

        body::after {
            content: "";
            position: fixed;
            inset: 0;
            z-index: -1;
            background:
                radial-gradient(1400px 700px at -10% -25%, rgba(186, 230, 253, 0.35), transparent 58%),
                radial-gradient(1200px 800px at 120% -10%, rgba(224, 242, 254, 0.4), transparent 56%),
                radial-gradient(900px 600px at 50% 120%, rgba(199, 210, 254, 0.25), transparent 60%);
            animation: gradientDrift 18s ease-in-out infinite alternate;
        }
        
        .container {
            width: min(var(--content-max-width), calc(100% - (var(--page-gutter) * 2)));
            margin: 0 auto;
            background: transparent;
            padding: var(--container-padding);
            border-radius: 0;
            box-shadow: none;
            margin-top: 1rem;
            margin-bottom: 2rem;
            border: none;
            animation: sectionFadeIn .65s ease both;
        }
        
        .header {
            text-align: center;
            margin-bottom: 3rem;
            padding: 3rem 2rem;
            background: var(--gradient-primary);
            color: white;
            border-radius: var(--radius-xl);
            position: relative;
            overflow: hidden;
        }
        
        .header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="white" opacity="0.1"/><circle cx="75" cy="75" r="1" fill="white" opacity="0.1"/><circle cx="50" cy="10" r="0.5" fill="white" opacity="0.1"/><circle cx="10" cy="60" r="0.5" fill="white" opacity="0.1"/><circle cx="90" cy="40" r="0.5" fill="white" opacity="0.1"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
            opacity: 0.3;
        }
        
        .header h1 {
            font-size: 3rem;
            font-weight: 800;
            margin: 0 0 1rem 0;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            position: relative;
            z-index: 1;
        }
        
        .header p {
            font-size: 1.125rem;
            opacity: 0.9;
            margin: 0;
            position: relative;
            z-index: 1;
        }
        
        /* Темная тема */
        .dark-theme {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --text-primary: #f1f5f9;
            --text-secondary: #cbd5e1;
            --border-color: #334155;
        }
        
        .dark-theme body {
            background: #0f172a !important;
            color: #f1f5f9 !important;
        }
        .dark-theme body::before {
            background: linear-gradient(180deg, #0b1329 0%, #0f172a 100%) !important;
        }
        
        .dark-theme .main-content {
            background: #0f172a !important;
        }
        
        .dark-theme .container {
            background: transparent;
            color: #f1f5f9;
        }
        
        .dark-theme .metric {
            background: #1e293b;
            border: 1px solid #334155;
            box-shadow: 0 4px 14px rgba(0,0,0,0.3);
        }
        
        .dark-theme .hotels-section {
            background: transparent;
            border: none;
        }
        
        .dark-theme .hotels-table th {
            background: transparent;
            color: #38bdf8;
            border: none;
        }
        
        .dark-theme .hotels-table th:hover {
            background: transparent;
            color: #7dd3fc;
        }
        
        .dark-theme .hotels-table tbody tr {
            background: #1e293b;
            border-color: #334155;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        
        .dark-theme .hotels-table tbody tr:hover {
            background: #1e293b;
            border-color: #38bdf8;
            box-shadow: 0 8px 24px rgba(56, 189, 248, 0.15);
        }
        
        .dark-theme .airport {
            background: #1e293b;
            color: #e2e8f0;
            border: 1px solid #475569;
        }
        
        .dark-theme .airport-alt {
            background: linear-gradient(135deg, #064e3b 0%, #065f46 100%);
            border: 1px solid #10b981;
            color: #ecfdf5;
        }
        
        .dark-theme .airport-alt:hover {
            background: linear-gradient(135deg, #065f46 0%, #047857 100%);
        }
        
        .dark-theme .airport-alt small {
            color: #6ee7b7;
        }
        
        .dark-theme .filter-input,
        .dark-theme .filter-select {
            background: #1e293b;
            border-color: #475569;
            color: #f1f5f9;
        }
        
        .dark-theme .filter-input:focus,
        .dark-theme .filter-select:focus {
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        
        .dark-theme .sidebar {
            background: linear-gradient(145deg, #1e293b 0%, #334155 100%);
        }
        
        .dark-theme .nav-item {
            color: #cbd5e1;
        }
        
        .dark-theme .nav-item:hover {
            background: #334155;
            color: #3b82f6;
        }
        
        .dark-theme .nav-item.active {
            background: linear-gradient(90deg, #1e40af 0%, #3b82f6 100%);
            color: white;
        }
        
        .dark-theme .avg-top10-section {
            background: linear-gradient(145deg, #1e293b 0%, #334155 100%);
            border: 1px solid #475569;
        }
        
        .dark-theme .avg-top10-section h3 {
            color: #f1f5f9;
        }
        
        .dark-theme .trend-section {
            background: linear-gradient(145deg, #1e293b 0%, #334155 100%);
            border: 1px solid #475569;
        }
        
        .dark-theme .trend-section h3 {
            color: #f1f5f9;
        }
        
        .dark-theme .footer {
            background: #1e293b;
            color: #cbd5e1;
        }
        
        .dark-theme .pagination button {
            background: #1e293b;
            border-color: #475569;
            color: #cbd5e1;
        }
        
        .dark-theme .pagination button:hover:not(:disabled) {
            background: var(--gradient-primary);
            color: white;
        }
        
        .dark-theme .pagination button.active {
            background: var(--gradient-primary);
            color: white;
        }
        
        .dark-theme .pagination-info {
            color: #cbd5e1;
        }
        
        .theme-toggle {
            position: static;
            background: var(--gradient-primary);
            border: none;
            border-radius: 50%;
            width: 2.25rem;
            height: 2.25rem;
            color: white;
            cursor: pointer;
            box-shadow: var(--shadow-sm);
            transition: var(--transition-normal);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            flex-shrink: 0;
        }
        
        .theme-toggle:hover {
            transform: scale(1.1);
            box-shadow: var(--shadow-xl);
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }
        
        .metric {
            background: var(--gradient-card);
            padding: 2rem;
            border-radius: var(--radius-xl);
            text-align: center;
            box-shadow: var(--shadow-md);
            transition: var(--transition-normal);
            border: 1px solid var(--border-soft);
            position: relative;
            overflow: hidden;
            animation: floatSoft 6s ease-in-out infinite;
        }
        
        .metric::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: var(--gradient-primary);
        }
        
        .metric:hover {
            transform: translateY(-4px);
            box-shadow: var(--shadow-lg);
        }
        
        .metric-value {
            font-size: 2.5rem;
            font-weight: 800;
            background: var(--gradient-primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin: 0.5rem 0;
        }
        
        .metric-label {
            font-size: 0.875rem;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .metrics.metrics-compact {
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: .6rem;
            margin-bottom: 1rem;
        }
        .metrics.metrics-compact .metric {
            padding: .62rem .78rem;
            border-radius: 12px;
            text-align: left;
            display: flex;
            align-items: center;
            justify-content: space-between;
            min-height: 54px;
            animation: none;
        }
        .metrics.metrics-compact .metric::before {
            height: 2px;
        }
        .metrics.metrics-compact .metric:hover {
            transform: translateY(-1px);
        }
        .metrics.metrics-compact .metric-value {
            font-size: 1.55rem;
            margin: 0;
            line-height: 1;
            white-space: nowrap;
            flex: 0 0 auto;
            margin-right: .7rem;
        }
        .metrics.metrics-compact .metric > div:last-child,
        .metrics.metrics-compact .metric-label {
            font-size: .77rem;
            font-weight: 600;
            color: #475569;
            line-height: 1.2;
        }
        .metric.metric-tip {
            cursor: help;
        }
        .metric.metric-tip:hover {
            border-color: rgba(79, 70, 229, 0.28);
            box-shadow: var(--shadow-md);
        }
        
        .avg-top10-section {
            background: var(--gradient-card);
            padding: 1.35rem;
            border-radius: var(--radius-xl);
            margin-top: var(--section-gap);
            margin-bottom: 1.1rem;
            box-shadow: var(--shadow-md);
            border: 1px solid var(--border-soft);
        }
        
        .avg-top10-section h3 {
            font-size: 1.5rem;
            font-weight: 700;
            margin: 0 0 1.5rem 0;
            color: #1f2937;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .chart-section-note {
            margin: -0.85rem 0 1rem;
            font-size: 0.82rem;
            color: var(--text-muted);
            line-height: 1.4;
        }
        
        .trend-section {
            background: var(--gradient-card);
            padding: 2rem;
            border-radius: var(--radius-xl);
            margin-bottom: 3rem;
            box-shadow: var(--shadow-md);
            border: 1px solid var(--border-soft);
        }
        
        .trend-index-section {
            background: var(--gradient-card);
            padding: 1.25rem;
            border-radius: var(--radius-xl);
            margin-bottom: .75rem;
            box-shadow: var(--shadow-md);
            border: 1px solid var(--border-soft);
            border-top: 3px solid #7C3AED;
        }
        details.dashboard-fold {
            margin: 0 0 1rem 0;
            background: var(--gradient-card);
            border: 1px solid var(--border-soft);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-sm);
            overflow: hidden;
        }
        details.dashboard-fold > summary {
            list-style: none;
            cursor: pointer;
            padding: .8rem 1rem;
            font-weight: 700;
            color: #1e293b;
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
            align-items: center;
            gap: .75rem;
            user-select: none;
        }
        details.dashboard-fold > summary::-webkit-details-marker {
            display: none;
        }
        details.dashboard-fold > summary > span:first-child {
            justify-self: start;
            min-width: 0;
        }
        .fold-title-meta {
            justify-self: center;
            text-align: center;
            font-size: .78rem;
            color: var(--text-muted);
            font-weight: 500;
            white-space: nowrap;
        }
        .fold-chevron {
            justify-self: end;
            font-size: .85rem;
            opacity: .75;
            transition: transform .16s ease;
        }
        details.dashboard-fold[open] .fold-chevron {
            transform: rotate(180deg);
        }
        .fold-content {
            padding: 0 1rem .9rem;
        }
        .fold-content .trend-index-section,
        .fold-content .metrics,
        .fold-content .changes-section,
        .fold-content .entry-signal {
            margin-top: 0;
        }
        .fold-content .metrics:last-child,
        .fold-content .entry-signal:last-child {
            margin-bottom: 0;
        }

        /* --- Секция «Когда покупать» --- */
        .timing-banner {
            background: rgba(255,255,255,.55);
            border: 1px solid var(--border-soft);
            border-radius: 12px;
            padding: .7rem .9rem;
            margin: .2rem 0 .8rem;
        }
        .timing-banner-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            font-size: .85rem;
            padding: .15rem 0;
        }
        .timing-banner-label { color: var(--text-muted); }
        .timing-banner-value { font-weight: 700; color: #1e293b; }
        .timing-reco {
            background: linear-gradient(135deg, rgba(6,182,212,.14), rgba(99,102,241,.12));
            border: 1px solid rgba(6,182,212,.25);
            border-radius: 12px;
            padding: .7rem .9rem;
            font-size: .92rem;
            color: #0f172a;
            margin-bottom: .8rem;
            line-height: 1.45;
        }
        .timing-badges {
            display: flex;
            flex-wrap: wrap;
            gap: .5rem;
            margin-bottom: 1rem;
        }
        .timing-badge {
            display: flex;
            align-items: center;
            gap: .4rem;
            background: rgba(255,255,255,.6);
            border: 1px solid var(--border-soft);
            border-radius: 999px;
            padding: .3rem .6rem;
            font-size: .76rem;
        }
        .timing-badge-name { font-weight: 700; color: #1e293b; }
        .timing-badge-prog { color: var(--text-muted); }
        .timing-pill {
            font-weight: 700;
            border-radius: 999px;
            padding: .1rem .45rem;
            font-size: .72rem;
        }
        .timing-pill-collecting { background: rgba(148,163,184,.25); color: #475569; }
        .timing-pill-prelim { background: rgba(245,158,11,.22); color: #b45309; }
        .timing-pill-reliable { background: rgba(16,185,129,.22); color: #047857; }
        .timing-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
        }
        .timing-chart-card {
            background: rgba(255,255,255,.5);
            border: 1px solid var(--border-soft);
            border-radius: 12px;
            padding: .7rem .8rem;
        }
        .timing-chart-card.timing-chart-wide { grid-column: 1 / -1; }
        .timing-chart-card h4 {
            margin: 0 0 .5rem;
            font-size: .92rem;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: .4rem;
        }
        .timing-info-tag {
            font-size: .68rem;
            font-weight: 700;
            background: rgba(148,163,184,.25);
            color: #475569;
            border-radius: 999px;
            padding: .08rem .4rem;
        }
        .timing-hint {
            margin: .5rem 0 0;
            font-size: .76rem;
            color: var(--text-muted);
            line-height: 1.4;
        }
        @media (max-width: 768px) {
            .timing-grid { grid-template-columns: 1fr; }
        }

        /* --- AI Market Intelligence Oracle Fold --- */
        details.ai-oracle-fold {
            margin-top: 1.25rem;
            margin-bottom: 1.5rem;
            background: #ffffff;
            border: 1px solid rgba(124, 58, 237, 0.22);
            border-top: 3px solid #7c3aed;
            border-radius: var(--radius-lg, 16px);
            box-shadow: 0 4px 20px rgba(124, 58, 237, 0.05), var(--shadow-sm);
            overflow: hidden;
            transition: var(--transition-normal);
        }
        details.ai-oracle-fold > summary {
            background: linear-gradient(90deg, #faf5ff 0%, #f8fafc 100%);
            padding: 0.9rem 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            user-select: none;
            border-bottom: 1px solid rgba(226, 232, 240, 0.8);
        }
        .ai-oracle-icon-box {
            width: 36px;
            height: 36px;
            border-radius: 10px;
            background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            box-shadow: 0 2px 8px rgba(124, 58, 237, 0.25);
            flex-shrink: 0;
        }
        .ai-oracle-title-wrap {
            display: flex;
            flex-direction: column;
            gap: 0.15rem;
        }
        .ai-oracle-title-row {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            flex-wrap: wrap;
        }
        .ai-oracle-main-title {
            font-weight: 700;
            color: #0f172a;
            font-size: 1.05rem;
            letter-spacing: -0.01em;
        }
        .ai-phase-badge {
            background: #ede9fe;
            color: #6d28d9;
            border: 1px solid #ddd6fe;
            padding: 0.18rem 0.55rem;
            border-radius: 9999px;
            font-size: 0.76rem;
            font-weight: 600;
        }
        .ai-oracle-subtitle {
            font-size: 0.82rem;
            color: #64748b;
            font-weight: 400;
            line-height: 1.35;
        }
        .ai-oracle-headline {
            color: #4338ca;
            font-weight: 600;
        }
        .ai-filter-title {
            color: #334155;
            font-weight: 600;
        }
        .ai-oracle-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .ai-card-pulse {
            background: #f8fafc;
            padding: 1.1rem;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            border-left: 4px solid #7c3aed;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }
        .ai-card-directive {
            background: #f0fdf4;
            padding: 1.1rem;
            border-radius: 12px;
            border: 1px solid #bbf7d0;
            border-left: 4px solid #10b981;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }
        .ai-card-header-purple {
            font-size: 0.78rem;
            color: #6d28d9;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.45rem;
            display: flex;
            align-items: center;
            gap: 0.35rem;
        }
        .ai-card-header-green {
            font-size: 0.78rem;
            color: #047857;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.45rem;
            display: flex;
            align-items: center;
            gap: 0.35rem;
        }
        .ai-card-body {
            font-size: 0.92rem;
            color: #334155;
            line-height: 1.55;
        }
        .ai-card-body-green {
            font-size: 0.92rem;
            color: #166534;
            line-height: 1.55;
            font-weight: 500;
        }
        .ai-floor-badge {
            margin-top: 0.65rem;
            padding: 0.35rem 0.65rem;
            border-radius: 6px;
            background: #e0e7ff;
            border: 1px solid #c7d2fe;
            color: #3730a3;
            font-size: 0.8rem;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
        }
        .ai-anomaly-tag {
            background: #faf5ff;
            border: 1px solid #e9d5ff;
            padding: 0.4rem 0.75rem;
            border-radius: 8px;
            font-size: 0.82rem;
            color: #4c1d95;
            display: inline-flex;
            align-items: baseline;
            gap: 0.35rem;
        }
        .ai-anomaly-tag strong {
            color: #7e22ce;
        }

        /* Feature: Если покупать сейчас */
        .ai-buy-now-box {
            margin-top: 0.85rem;
            border-radius: 12px;
            padding: 1rem 1.15rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            transition: all 0.2s ease;
        }
        .ai-buy-now--active {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(5, 150, 105, 0.03) 100%);
            border: 1px solid rgba(16, 185, 129, 0.35);
            border-left: 4px solid #10b981;
        }
        .ai-buy-now--wait {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(217, 119, 6, 0.03) 100%);
            border: 1px solid rgba(245, 158, 11, 0.35);
            border-left: 4px solid #f59e0b;
        }
        .ai-buy-now-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
        }
        .ai-buy-now-title-group {
            display: flex;
            align-items: center;
            gap: 0.65rem;
        }
        .ai-buy-now-icon {
            font-size: 1.35rem;
            line-height: 1;
        }
        .ai-buy-now-titles {
            display: flex;
            flex-direction: column;
            gap: 0.15rem;
        }
        .ai-buy-now-kicker {
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #475569;
        }
        .ai-buy-now--active .ai-buy-now-kicker {
            color: #047857;
        }
        .ai-buy-now--wait .ai-buy-now-kicker {
            color: #b45309;
        }
        .ai-buy-now-heading {
            font-size: 1rem;
            font-weight: 800;
            color: #0f172a;
        }
        .ai-buy-now-pill {
            font-size: 0.72rem;
            font-weight: 800;
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            letter-spacing: 0.03em;
        }
        .ai-buy-now-pill.pill--active {
            background: #d1fae5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }
        .ai-buy-now-pill.pill--wait {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fde68a;
        }
        .ai-buy-now-advice {
            font-size: 0.88rem;
            line-height: 1.5;
            color: #334155;
        }
        .ai-picks-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 0.75rem;
        }
        .ai-pick-card {
            background: #ffffff;
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 10px;
            padding: 0.75rem 0.9rem;
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }
        .ai-pick-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.5rem;
        }
        .ai-pick-name {
            font-size: 0.95rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.3;
        }
        .ai-pick-price {
            font-size: 1.15rem;
            font-weight: 800;
            color: #047857;
            white-space: nowrap;
        }
        .ai-pick-meta {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
            font-size: 0.82rem;
        }
        .ai-pick-badge {
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            color: #065f46;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.15rem 0.45rem;
            border-radius: 6px;
            white-space: nowrap;
        }
        .ai-pick-why {
            color: #475569;
            font-size: 0.82rem;
            line-height: 1.35;
        }
        .ai-pick-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 0.25rem;
        }
        .ai-pick-btn {
            font-size: 0.78rem;
            font-weight: 600;
            padding: 0.3rem 0.65rem;
            border-radius: 6px;
            text-decoration: none;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
        }
        .ai-pick-btn--chart {
            background: #f1f5f9;
            color: #334155;
            border: 1px solid #cbd5e1;
        }
        .ai-pick-btn--chart:hover {
            background: #e2e8f0;
        }
        .ai-pick-btn--offer {
            background: #10b981;
            color: #ffffff;
            border: 1px solid #059669;
        }
        .ai-pick-btn--offer:hover {
            background: #059669;
        }

        /* Dark Theme Support for Buy Now Recommendation */
        .dark-theme .ai-buy-now--active {
            background: rgba(16, 185, 129, 0.12);
            border-color: rgba(16, 185, 129, 0.4);
        }
        .dark-theme .ai-buy-now--wait {
            background: rgba(245, 158, 11, 0.12);
            border-color: rgba(245, 158, 11, 0.4);
        }
        .dark-theme .ai-buy-now-heading {
            color: #f1f5f9;
        }
        .dark-theme .ai-buy-now-advice {
            color: #cbd5e1;
        }
        .dark-theme .ai-pick-card {
            background: #1e293b;
            border-color: rgba(255, 255, 255, 0.1);
        }
        .dark-theme .ai-pick-name {
            color: #f8fafc;
        }
        .dark-theme .ai-pick-price {
            color: #34d399;
        }
        .dark-theme .ai-pick-why {
            color: #94a3b8;
        }
        .dark-theme .ai-pick-btn--chart {
            background: #334155;
            color: #e2e8f0;
            border-color: #475569;
        }

        /* Dark Theme Support for AI Oracle */
        .dark-theme details.ai-oracle-fold {
            background: #1e293b;
            border-color: #334155;
            border-top-color: #a78bfa;
        }
        .dark-theme details.ai-oracle-fold > summary {
            background: #0f172a;
            border-bottom-color: #334155;
        }
        .dark-theme .ai-oracle-main-title {
            color: #f1f5f9;
        }
        .dark-theme .ai-oracle-subtitle {
            color: #94a3b8;
        }
        .dark-theme .ai-oracle-headline {
            color: #c4b5fd;
        }
        .dark-theme .ai-filter-title {
            color: #e2e8f0;
        }
        .dark-theme .ai-phase-badge {
            background: rgba(124, 58, 237, 0.25);
            color: #c4b5fd;
            border-color: rgba(124, 58, 237, 0.45);
        }
        .dark-theme details.ai-oracle-fold .fold-content {
            background: #1e293b;
        }
        .dark-theme .ai-card-pulse {
            background: #0f172a;
            border-color: #334155;
        }
        .dark-theme .ai-card-header-purple {
            color: #c4b5fd;
        }
        .dark-theme .ai-card-body {
            color: #cbd5e1;
        }
        .dark-theme .ai-card-directive {
            background: rgba(6, 78, 59, 0.25);
            border-color: rgba(16, 185, 129, 0.35);
        }
        .dark-theme .ai-card-header-green {
            color: #6ee7b7;
        }
        .dark-theme .ai-card-body-green {
            color: #d1fae5;
        }
        .dark-theme .ai-floor-badge {
            background: rgba(79, 70, 229, 0.25);
            border-color: rgba(99, 102, 241, 0.4);
            color: #c7d2fe;
        }
        .dark-theme .ai-anomaly-tag {
            background: rgba(124, 58, 237, 0.2);
            border-color: rgba(124, 58, 237, 0.4);
            color: #e9d5ff;
        }
        .dark-theme .ai-anomaly-tag strong {
            color: #c4b5fd;
        }

        /* --- Секция "Выпавшие отели" --- */
        .vanished-hint {
            margin: .2rem 0 .8rem;
            font-size: .82rem;
            color: var(--text-muted);
            line-height: 1.45;
        }
        .vanished-table th, .vanished-table td {
            vertical-align: top;
        }
        .vanished-badge {
            display: inline-block;
            margin-left: .4rem;
            font-size: .7rem;
            font-weight: 700;
            color: #b45309;
            background: rgba(245,158,11,.18);
            border-radius: 999px;
            padding: .08rem .45rem;
            white-space: nowrap;
        }
        .vanished-reason {
            display: inline-block;
            font-size: .76rem;
            font-weight: 600;
            border-radius: 8px;
            padding: .2rem .5rem;
            line-height: 1.3;
        }
        .vanished-reason-sold { background: rgba(16,185,129,.16); color: #047857; }
        .vanished-reason-up { background: rgba(239,68,68,.14); color: #b91c1c; }
        .vanished-reason-flat { background: rgba(148,163,184,.2); color: #475569; }
        
        .trend-section h3 {
            font-size: 1.5rem;
            font-weight: 700;
            margin: 0 0 1.5rem 0;
            color: #1f2937;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .changes-section {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .changes-block {
            background: var(--surface-strong);
            padding: 20px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-soft);
            box-shadow: var(--shadow-sm);
        }
        .changes-block h3 {
            margin-top: 0;
            text-align: center;
        }
        .change-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            margin: 5px 0;
            background: rgba(255,255,255,0.95);
            border-radius: 8px;
            border-left: 4px solid;
        }
        .change-decrease {
            border-left-color: #28a745;
        }
        .change-increase {
            border-left-color: #dc3545;
        }
        .change-price {
            font-weight: bold;
        }
        .change-percent {
            font-size: 0.9em;
            opacity: 0.8;
        }
        .entry-signal {
            margin: 0 0 2rem 0;
            border-radius: var(--radius-lg);
            padding: 1rem;
            border: 1px solid var(--border-soft);
            box-shadow: var(--shadow-sm);
        }
        .entry-high {
            background: linear-gradient(135deg, rgba(16,185,129,.12), rgba(34,197,94,.08));
            border-color: rgba(16,185,129,.35);
        }
        .entry-medium {
            background: linear-gradient(135deg, rgba(245,158,11,.12), rgba(234,179,8,.08));
            border-color: rgba(245,158,11,.35);
        }
        .entry-low {
            background: linear-gradient(135deg, rgba(59,130,246,.10), rgba(14,165,233,.08));
            border-color: rgba(59,130,246,.28);
        }
        .entry-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .entry-note {
            color: var(--text-muted);
            font-size: .9rem;
            margin-bottom: 8px;
        }
        .entry-stats {
            font-size: .84rem;
            color: var(--text-muted);
            margin-bottom: 8px;
        }
        .entry-list {
            display: grid;
            gap: 8px;
        }
        .entry-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: .65rem .75rem;
            border-radius: 10px;
            background: rgba(255,255,255,.78);
            border: 1px solid rgba(148,163,184,.20);
            transition: transform .16s ease;
        }
        .entry-item:hover {
            transform: translateY(-2px);
        }
        .departures-strip {
            margin: 0 0 1rem 0;
            padding: .9rem 1rem;
            border-radius: var(--radius-lg);
            background: linear-gradient(135deg, rgba(59,130,246,.11), rgba(14,165,233,.08));
            border: 1px solid rgba(59,130,246,.24);
            box-shadow: var(--shadow-sm);
        }
        .departures-head {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
            margin-bottom: .65rem;
        }
        .departures-head h3 {
            margin: 0;
            font-size: 1.05rem;
            font-weight: 800;
            color: #0f172a;
        }
        .departures-head p {
            margin: .18rem 0 0;
            font-size: .82rem;
            color: var(--text-muted);
        }
        .departure-mini-stats {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: .35rem;
            max-width: 48%;
        }
        .departure-mini-stats span {
            font-size: .72rem;
            font-weight: 700;
            color: #1d4ed8;
            background: rgba(255,255,255,.7);
            border: 1px solid rgba(59,130,246,.18);
            border-radius: 999px;
            padding: .16rem .48rem;
            white-space: nowrap;
        }
        .departure-legend {
            margin: -.15rem 0 .65rem;
            color: var(--text-muted);
            font-size: .76rem;
            line-height: 1.35;
        }
        .departure-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: .55rem;
        }
        .departure-card {
            display: flex;
            flex-direction: column;
            gap: .42rem;
            padding: .68rem .72rem;
            border-radius: 13px;
            background: rgba(255,255,255,.86);
            border: 1px solid rgba(148,163,184,.20);
            min-width: 0;
            box-shadow: 0 8px 20px rgba(15,23,42,.04);
        }
        .departure-card.is-warm {
            background: linear-gradient(135deg, rgba(255,247,237,.95), rgba(255,255,255,.82));
            border-color: rgba(245,158,11,.34);
        }
        .departure-card.is-hot {
            background: linear-gradient(135deg, rgba(254,226,226,.98), rgba(255,247,237,.88));
            border-color: rgba(239,68,68,.42);
            box-shadow: 0 10px 24px rgba(239,68,68,.12);
        }
        .departure-card-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: .5rem;
        }
        .departure-title {
            font-size: .98rem;
            font-weight: 800;
            color: #0f172a;
            white-space: normal;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            line-height: 1.12;
        }
        .departure-hub-resorts {
            font-size: .68rem;
            color: var(--text-muted);
            line-height: 1.35;
            font-weight: 700;
        }
        .departure-facts {
            display: flex;
            flex-wrap: wrap;
            gap: .24rem;
        }
        .departure-facts span {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .12rem .38rem;
            background: rgba(59,130,246,.08);
            color: #1e3a8a;
            font-size: .68rem;
            font-weight: 800;
            line-height: 1.25;
        }
        .departure-delta {
            display: flex;
            flex-wrap: wrap;
            gap: .25rem;
        }
        .departure-change {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .14rem .4rem;
            font-size: .68rem;
            font-weight: 800;
            white-space: normal;
        }
        .departure-change.drop {
            color: #047857;
            background: rgba(16,185,129,.16);
        }
        .departure-change.up {
            color: #b91c1c;
            background: rgba(239,68,68,.14);
        }
        .departure-change.muted {
            color: var(--text-muted);
        }
        .hero {
            margin-bottom: 1.25rem;
            border-radius: var(--radius-xl);
            overflow: hidden;
            box-shadow: var(--shadow-lg);
            border: 1px solid var(--border-soft);
            background:
                linear-gradient(180deg, rgba(2,6,23,.18), rgba(2,6,23,.48)),
                url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1800&q=80') center/cover no-repeat;
            min-height: 180px;
            position: relative;
            animation: sectionFadeIn .7s ease both;
        }
        .hero-content {
            position: relative;
            z-index: 1;
            color: #fff;
            padding: 1.4rem 1.35rem;
        }

        /* Option 1: Fintech / Flight Terminal Header Banner */
        .hero-terminal, .hero--mockup {
            margin-bottom: 1.5rem;
            padding: 1.5rem 1.75rem;
            border-radius: 20px;
            background: linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 50%, #e0f2fe 100%);
            border: 1px solid #bae6fd;
            box-shadow: 0 10px 30px rgba(2, 132, 199, 0.08);
        }
        .dark-theme .hero-terminal, .dark-theme .hero--mockup {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-color: #334155;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }

        .hero-terminal-top {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }
        .hero-terminal-title-area {
            flex: 1;
            min-width: 260px;
        }
        .hero-terminal-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 3px 10px;
            border-radius: 9999px;
            background: rgba(2, 132, 199, 0.12);
            color: #0369a1;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            margin-bottom: 6px;
        }
        .dark-theme .hero-terminal-badge {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
        }
        .hero-terminal-title {
            margin: 0;
            font-size: clamp(1.3rem, 2.2vw, 1.85rem);
            font-weight: 800;
            color: #0f172a;
            line-height: 1.25;
            letter-spacing: -0.02em;
        }
        .dark-theme .hero-terminal-title {
            color: #f8fafc;
        }
        .btn-open-fly {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            background: #0284c7;
            color: #ffffff !important;
            font-size: 0.84rem;
            font-weight: 600;
            padding: 8px 15px;
            border-radius: 10px;
            text-decoration: none;
            box-shadow: 0 2px 8px rgba(2, 132, 199, 0.25);
            transition: all 0.2s ease;
            white-space: nowrap;
            align-self: center;
        }
        .btn-open-fly:hover {
            background: #0369a1;
            box-shadow: 0 4px 14px rgba(2, 132, 199, 0.35);
            transform: translateY(-1px);
            text-decoration: none;
        }
        .dark-theme .btn-open-fly {
            background: #0284c7;
            color: #ffffff !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
        }
        .dark-theme .btn-open-fly:hover {
            background: #38bdf8;
            color: #0f172a !important;
        }

        /* Dynamic Metadata Chips */
        .hero-terminal-chips {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 1.15rem;
        }
        .terminal-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.88);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(186, 230, 253, 0.7);
            border-radius: 10px;
            padding: 6px 12px;
            font-size: 0.82rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
            transition: all 0.15s ease;
        }
        .terminal-chip:hover {
            background: #ffffff;
            border-color: #38bdf8;
            box-shadow: 0 2px 6px rgba(2, 132, 199, 0.12);
        }
        .dark-theme .terminal-chip {
            background: rgba(30, 41, 59, 0.85);
            border-color: rgba(51, 65, 85, 0.9);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
        }
        .dark-theme .terminal-chip:hover {
            background: #1e293b;
            border-color: #38bdf8;
        }
        .chip-icon {
            font-size: 0.92rem;
            line-height: 1;
        }
        .chip-label {
            font-size: 0.76rem;
            font-weight: 600;
            color: #64748b;
        }
        .dark-theme .chip-label {
            color: #94a3b8;
        }
        .chip-val {
            font-size: 0.82rem;
            font-weight: 700;
            color: #0f172a;
            white-space: nowrap;
        }
        .dark-theme .chip-val {
            color: #f8fafc;
        }

        /* 4 White KPI Cards */
        .kpi-cards-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
        }
        @media (max-width: 900px) {
            .kpi-cards-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        @media (max-width: 500px) {
            .kpi-cards-grid {
                grid-template-columns: 1fr;
            }
        }

        .kpi-card-white {
            background: #ffffff;
            border-radius: 16px;
            padding: 14px 18px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
            border: 1px solid rgba(226, 232, 240, 0.8);
            display: flex;
            align-items: center;
            gap: 14px;
        }
        .dark-theme .kpi-card-white {
            background: #1e293b;
            border-color: #334155;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }

        .kpi-card-icon-box {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            background: #e0f2fe;
            color: #0284c7;
        }
        .dark-theme .kpi-card-icon-box {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
        }
        .kpi-icon--price {
            background: #ecfdf5 !important;
            color: #059669 !important;
        }
        .dark-theme .kpi-icon--price {
            background: rgba(16, 185, 129, 0.15) !important;
            color: #34d399 !important;
        }
        .kpi-icon--buy {
            background: #f0fdf4 !important;
            color: #16a34a !important;
        }
        .dark-theme .kpi-icon--buy {
            background: rgba(22, 163, 74, 0.15) !important;
            color: #4ade80 !important;
        }
        .kpi-icon--drop {
            background: #eff6ff !important;
            color: #2563eb !important;
        }
        .dark-theme .kpi-icon--drop {
            background: rgba(37, 99, 235, 0.15) !important;
            color: #60a5fa !important;
        }
        .kpi-icon--time {
            background: #f1f5f9 !important;
            color: #64748b !important;
        }
        .dark-theme .kpi-icon--time {
            background: rgba(148, 163, 184, 0.15) !important;
            color: #94a3b8 !important;
        }

        .kpi-svg {
            width: 22px;
            height: 22px;
        }

        .kpi-card-info {
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        .kpi-card-number {
            font-size: clamp(1.2rem, 1.8vw, 1.45rem);
            font-weight: 800;
            color: #0f172a;
            line-height: 1.1;
            white-space: nowrap;
        }
        .dark-theme .kpi-card-number {
            color: #f8fafc;
        }
        .kpi-card-title {
            font-size: 0.78rem;
            font-weight: 600;
            color: #64748b;
            margin-top: 2px;
            white-space: nowrap;
        }
        .dark-theme .kpi-card-title {
            color: #94a3b8;
        }

        .kpi-status-tag {
            font-size: 0.75rem;
            font-weight: 700;
            color: #16a34a;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .dark-theme .kpi-status-tag {
            color: #4ade80;
        }
        .departure-price-line {
            display: flex;
            flex-wrap: wrap;
            gap: .38rem .65rem;
            border-radius: 10px;
            padding: .42rem .5rem;
            background: rgba(248,250,252,.9);
            border: 1px solid rgba(226,232,240,.8);
            color: var(--text-muted);
            font-size: .72rem;
            font-weight: 800;
        }
        .departure-price-line strong {
            color: #0f172a;
            font-weight: 900;
            font-size: .9rem;
        }
        .departure-status {
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .22rem .5rem;
            font-size: .72rem;
            font-weight: 900;
            white-space: nowrap;
        }
        .departure-status.hot { background: rgba(239,68,68,.16); color: #b91c1c; }
        .departure-status.warm { background: rgba(245,158,11,.18); color: #b45309; }
        .departure-status.calm { background: rgba(59,130,246,.14); color: #1d4ed8; }
        .departure-score.hot { background: rgba(239,68,68,.16); color: #b91c1c; }
        .departure-score.warm { background: rgba(245,158,11,.18); color: #b45309; }
        .departure-score.calm { background: rgba(59,130,246,.14); color: #1d4ed8; }
        .departure-score.mini {
            width: 30px;
            height: 30px;
            font-size: .78rem;
        }
        .departure-foot {
            display: flex;
            justify-content: flex-end;
            font-size: .66rem;
            font-weight: 700;
            color: var(--text-muted);
        }
        .departure-history-hint {
            margin: .2rem 0 .8rem;
            font-size: .82rem;
            color: var(--text-muted);
            line-height: 1.45;
        }
        .departure-history-table th,
        .departure-history-table td {
            vertical-align: top;
        }
        .departure-history-table td span {
            color: var(--text-muted);
            font-size: .78rem;
        }
        .departure-card-clickable,
        .departure-history-row {
            cursor: pointer;
            transition: transform var(--transition-fast), box-shadow var(--transition-fast), border-color var(--transition-fast);
        }
        .departure-card-clickable:hover,
        .departure-card-clickable:focus-visible,
        .departure-history-row:hover,
        .departure-history-row:focus-visible {
            transform: translateY(-1px);
            box-shadow: 0 12px 28px rgba(15,23,42,.10);
            outline: none;
        }
        .departure-card-clickable:focus-visible,
        .departure-history-row:focus-visible {
            border-color: rgba(79,70,229,.45);
            box-shadow: 0 0 0 3px rgba(79,70,229,.18);
        }
        .departure-history-row:hover td {
            background: rgba(79,70,229,.04);
        }
        .departure-modal {
            position: fixed;
            inset: 0;
            z-index: 1200;
            display: none;
            align-items: center;
            justify-content: center;
            padding: 1rem;
        }
        .departure-modal.open {
            display: flex;
        }
        .departure-modal-backdrop {
            position: absolute;
            inset: 0;
            background: rgba(15,23,42,.58);
            backdrop-filter: blur(2px);
        }
        .departure-modal-dialog {
            position: relative;
            width: min(920px, 100%);
            max-height: min(82vh, 860px);
            display: flex;
            flex-direction: column;
            background: #fff;
            border-radius: 16px;
            box-shadow: var(--shadow-xl);
            overflow: hidden;
        }
        .departure-modal-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: .75rem;
            padding: 1rem 1.1rem .55rem;
            border-bottom: 1px solid var(--border-soft);
        }
        .departure-modal-header h3 {
            margin: 0;
            font-size: 1.05rem;
            line-height: 1.25;
        }
        .departure-modal-close {
            border: 0;
            background: rgba(148,163,184,.16);
            color: #334155;
            width: 34px;
            height: 34px;
            border-radius: 10px;
            font-size: 1.35rem;
            line-height: 1;
            cursor: pointer;
        }
        .departure-modal-meta {
            margin: 0;
            padding: 0 1.1rem .75rem;
            color: var(--text-muted);
            font-size: .82rem;
        }
        .departure-modal-chart-title {
            margin: 0;
            padding: 0 1.1rem .35rem;
            color: var(--text-muted);
            font-size: .82rem;
            font-weight: 600;
        }
        .departure-modal-chart {
            display: none;
            flex-shrink: 0;
            width: calc(100% - 2.2rem);
            height: 300px;
            min-height: 300px;
            margin: 0 1.1rem 12px;
            border: 1px solid rgba(226,232,240,.95);
            border-radius: 12px;
            background: #f8fafc;
            overflow: visible;
        }
        .departure-modal-body {
            flex: 1 1 auto;
            min-height: 0;
            overflow: auto;
            padding: 0 1.1rem 1rem;
            -webkit-overflow-scrolling: touch;
        }
        .departure-modal-table-scroll {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            max-width: 100%;
            margin: 0 -.15rem;
            padding: 0 .15rem .15rem;
        }
        .departure-offers-table {
            width: 100%;
            min-width: 520px;
            border-collapse: collapse;
        }
        .departure-offers-table th,
        .departure-offers-table td {
            padding: .55rem .45rem;
            border-bottom: 1px solid rgba(226,232,240,.9);
            text-align: left;
            vertical-align: middle;
            font-size: .86rem;
        }
        .departure-offers-table th {
            position: sticky;
            top: 0;
            background: #fff;
            z-index: 1;
            font-size: .74rem;
            text-transform: uppercase;
            letter-spacing: .03em;
            color: var(--text-muted);
        }
        .departure-offers-table td.price {
            font-weight: 800;
            white-space: nowrap;
        }
        .departure-offers-table td.delta-drop {
            color: #047857;
            font-weight: 800;
            white-space: nowrap;
        }
        .departure-offers-table td.delta-up {
            color: #b91c1c;
            font-weight: 800;
            white-space: nowrap;
        }
        .departure-offers-table td.delta-flat {
            color: var(--text-muted);
            white-space: nowrap;
        }
        .departure-offers-table .deal-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .18rem .48rem;
            font-size: .72rem;
            font-weight: 800;
            border: 1px solid transparent;
            white-space: nowrap;
        }
        .departure-offers-table .deal-pill.hot { background: rgba(245,158,11,.18); color: #92400e; border-color: rgba(245,158,11,.32); }
        .departure-offers-table .deal-pill.good { background: rgba(16,185,129,.17); color: #065f46; border-color: rgba(16,185,129,.32); }
        .departure-offers-table .deal-pill.normal { background: rgba(148,163,184,.18); color: #334155; border-color: rgba(148,163,184,.35); }
        .departure-offers-table .deal-pill.bad { background: rgba(239,68,68,.15); color: #991b1b; border-color: rgba(239,68,68,.32); }
        .departure-offers-table .deal-pill.warm { background: rgba(14,165,233,.16); color: #0c4a6e; border-color: rgba(14,165,233,.35); }
        .departure-offers-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: .32rem .62rem;
            border-radius: 999px;
            background: var(--gradient-primary);
            color: #fff;
            text-decoration: none;
            font-size: .76rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .departure-offers-actions {
            display: flex;
            flex-wrap: wrap;
            gap: .35rem;
        }
        .departure-offers-link.secondary {
            background: #fff;
            color: #4f46e5;
            border: 1px solid rgba(79,70,229,.28);
        }
        .departure-modal-empty {
            padding: 1rem 0;
            color: var(--text-muted);
            font-size: .88rem;
        }
        @media (max-width: 760px) {
            .departures-head { display: block; }
            .departure-mini-stats { max-width: none; justify-content: flex-start; margin-top: .55rem; }
            .departure-grid { grid-template-columns: 1fr; }
        }
        .deal-legend {
            margin: 0 0 1rem 0;
            padding: .85rem 1rem;
            border-radius: 10px;
            background: rgba(255,255,255,.82);
            border: 1px solid var(--border-soft);
            color: var(--text-muted);
            font-size: .88rem;
            line-height: 1.45;
        }
        .deal-badge-hot { color: #b45309; font-weight: 700; }
        .deal-badge-good { color: #166534; font-weight: 700; }
        .deal-badge-normal { color: #64748b; font-weight: 600; }
        .deal-badge-bad { color: #b91c1c; font-weight: 700; }
        .deal-badge-warm { color: #0369a1; font-weight: 700; }
        .hero {
            margin-bottom: 1.25rem;
            border-radius: var(--radius-xl);
            overflow: hidden;
            box-shadow: var(--shadow-lg);
            border: 1px solid var(--border-soft);
            background:
                linear-gradient(180deg, rgba(2,6,23,.18), rgba(2,6,23,.48)),
                url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1800&q=80') center/cover no-repeat;
            min-height: 180px;
            position: relative;
            animation: sectionFadeIn .7s ease both;
        }
        .hero-content {
            position: relative;
            z-index: 1;
            color: #fff;
            padding: 1.4rem 1.35rem;
        }
        .hero-kpis {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 1rem;
        }
        .hero-kpi {
            display: flex;
            align-items: flex-start;
            gap: .65rem;
            background: rgba(255,255,255,.14);
            border: 1px solid rgba(255,255,255,.26);
            border-radius: 14px;
            padding: .7rem .75rem;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 18px rgba(2,6,23,.12);
        }
        .hero-kpi__badge {
            flex-shrink: 0;
            width: 2.35rem;
            height: 2.35rem;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
        }
        .hero-kpi__badge--blue { background: linear-gradient(145deg, #3b82f6, #2563eb); }
        .hero-kpi__badge--green { background: linear-gradient(145deg, #22c55e, #16a34a); }
        .hero-kpi__badge--purple { background: linear-gradient(145deg, #a855f7, #7c3aed); }
        .hero-kpi__badge--gold { background: linear-gradient(145deg, #fbbf24, #d97706); }
        .hero-kpi__svg {
            width: 1.15rem;
            height: 1.15rem;
        }
        .hero-kpi__body {
            min-width: 0;
            flex: 1;
        }
        .hero-kpi__v {
            font-size: 1.35rem;
            font-weight: 800;
            line-height: 1.1;
            letter-spacing: -.02em;
            min-width: 0;
            overflow-wrap: anywhere;
        }
        .hero-kpi__datetime {
            display: flex;
            flex-direction: column;
            gap: .08rem;
            line-height: 1.15;
        }
        .hero-kpi__date {
            font-size: clamp(.82rem, 3vw, 1.1rem);
            font-weight: 800;
            white-space: nowrap;
        }
        .hero-kpi__time {
            font-size: clamp(.74rem, 2.6vw, .92rem);
            font-weight: 700;
            opacity: .9;
        }
        .hero-kpi__l {
            margin-top: .12rem;
            font-size: .74rem;
            font-weight: 700;
            opacity: .95;
        }
        .hero-kpi__s {
            margin-top: .18rem;
            font-size: .66rem;
            line-height: 1.3;
            opacity: .82;
        }
        /* —— Premium filter bar (mockup layout) —— */
        .filter-bar--premium {
            margin-top: .55rem;
            padding: .7rem .85rem .75rem;
            background: rgba(15,23,42,.42);
            border: 1px solid rgba(255,255,255,.22);
            border-radius: 16px;
            backdrop-filter: blur(14px);
            box-shadow: 0 8px 28px rgba(2,6,23,.18);
            animation: filterBarIn .45s ease both;
        }
        @keyframes filterBarIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .filter-bar__track {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: .35rem;
            width: 100%;
            overflow-x: auto;
            scrollbar-width: thin;
        }
        .duration-global-switch {
            margin-top: .65rem;
            display: flex;
            align-items: center;
            gap: .75rem;
            flex-wrap: wrap;
            padding: .55rem .7rem;
            border-radius: 14px;
            background: rgba(15,23,42,.34);
            border: 1px solid rgba(255,255,255,.18);
        }
        .duration-global-label {
            font-size: .78rem;
            font-weight: 700;
            letter-spacing: .04em;
            text-transform: uppercase;
            opacity: .9;
        }
        .duration-global-options {
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
        }
        .duration-global-btn {
            border: 1px solid rgba(255,255,255,.24);
            background: rgba(255,255,255,.08);
            color: inherit;
            border-radius: 999px;
            padding: .42rem .9rem;
            font-size: .82rem;
            font-weight: 700;
            cursor: pointer;
            transition: background .15s ease, border-color .15s ease, transform .15s ease;
        }
        .duration-global-btn:hover {
            background: rgba(255,255,255,.16);
        }
        .duration-global-btn.active {
            background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
            color: #1f2937;
            border-color: transparent;
            box-shadow: 0 4px 14px rgba(245,158,11,.35);
        }
        .fb-route-group {
            display: flex;
            align-items: flex-end;
            gap: .45rem;
            flex-shrink: 0;
        }
        .fb-route-arrow {
            font-size: 1.1rem;
            opacity: .55;
            padding-bottom: 1.1rem;
            flex-shrink: 0;
        }
        .fb-slot {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: .35rem;
            min-width: 4.5rem;
            max-width: 7.5rem;
            flex-shrink: 0;
            text-align: center;
        }
        .fb-badge {
            width: 2.5rem;
            height: 2.5rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            box-shadow: 0 4px 14px rgba(0,0,0,.2);
        }
        .fb-badge--blue {
            background: linear-gradient(145deg, #3b82f6, #1d4ed8);
            color: #fff;
        }
        .fb-badge--gold {
            background: linear-gradient(145deg, #fbbf24, #d97706);
            color: #fff;
        }
        .fb-badge--neutral {
            background: rgba(255,255,255,.16);
            border: 1px solid rgba(255,255,255,.22);
            color: #fff;
        }
        .fb-badge--flag {
            background: rgba(255,255,255,.12);
            border: 1px solid rgba(255,255,255,.2);
        }
        .fb-flag-emoji {
            font-size: 1.35rem;
            line-height: 1;
        }
        .fb-svg {
            width: 1.15rem;
            height: 1.15rem;
        }
        .fb-slot-body {
            display: flex;
            flex-direction: column;
            gap: .1rem;
            width: 100%;
            min-width: 0;
        }
        .fb-kicker {
            font-size: .58rem;
            font-weight: 700;
            letter-spacing: .09em;
            text-transform: uppercase;
            opacity: .72;
            line-height: 1.1;
        }
        .fb-value {
            font-size: .78rem;
            font-weight: 800;
            line-height: 1.2;
            color: #fff;
            max-width: 100%;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
        .fb-value--gold {
            color: #fde68a;
        }
        .fb-chev {
            display: inline-block;
            margin-left: .15rem;
            font-size: .62rem;
            opacity: .75;
            vertical-align: middle;
        }
        .fb-sub {
            font-size: .6rem;
            opacity: .78;
            line-height: 1.15;
            font-weight: 500;
        }
        .fb-vdiv {
            width: 1px;
            align-self: stretch;
            min-height: 3.2rem;
            margin: 0 .15rem;
            background: linear-gradient(180deg, transparent, rgba(255,255,255,.32), transparent);
            flex-shrink: 0;
        }
        @media (max-width: 1100px) {
            .filter-bar__track {
                justify-content: flex-start;
            }
        }
        @media (max-width: 720px) {
            .hero-kpis {
                grid-template-columns: 1fr 1fr;
            }
            .fb-vdiv {
                display: none;
            }
            .filter-bar__track {
                flex-wrap: wrap;
                row-gap: .65rem;
            }
            .fb-kicker {
                font-size: .68rem;
            }
            .fb-sub {
                font-size: .72rem;
            }
            .fb-value {
                font-size: .84rem;
            }
            .duration-global-switch {
                flex-direction: column;
                align-items: stretch;
                gap: .55rem;
            }
            .duration-global-options {
                width: 100%;
            }
            .duration-global-btn {
                flex: 1;
                text-align: center;
                min-width: 0;
            }
        }
        .mode-switch {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            border: none;
            border-radius: 10px;
            margin: .35rem 0 .85rem;
            background: rgba(118,118,128,.14);
            padding: 3px;
            isolation: isolate;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }
        .arb-count-badge {
            background: #10b981;
            color: #fff;
            font-size: 0.68rem;
            padding: 1px 6px;
            border-radius: 999px;
            font-weight: 700;
            margin-left: 4px;
        }
        .table-toolbar {
            display: inline-flex;
            align-items: center;
            gap: .5rem;
            margin-left: auto;
        }
        .table-toolbar-title {
            font-size: .76rem;
            color: var(--text-muted);
            font-weight: 600;
            white-space: nowrap;
        }
        .table-mode-switch {
            margin: 0;
            transform: scale(.92);
            transform-origin: right center;
        }
        .table-header-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .8rem;
            margin-bottom: .65rem;
        }
        .table-header-row h3 {
            margin: 0;
        }
        .mode-btn {
            position: relative;
            z-index: 1;
            border: none;
            background: transparent;
            padding: .42rem .95rem;
            font-size: .84rem;
            cursor: pointer;
            color: #64748b;
            font-weight: 600;
            white-space: nowrap;
            text-align: center;
            border-radius: 7px;
            transition: all .18s ease;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        .mode-btn:hover {
            color: #1e293b;
        }
        .mode-btn.active {
            background: #ffffff;
            color: #0f172a;
            box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.06);
        }
        .dark-theme .mode-switch {
            background: rgba(255,255,255,.08);
        }
        .dark-theme .mode-btn {
            color: #94a3b8;
        }
        .dark-theme .mode-btn:hover {
            color: #f1f5f9;
        }
        .dark-theme .mode-btn.active {
            background: #1e293b;
            color: #f8fafc;
            box-shadow: 0 1px 3px rgba(0,0,0,.4);
        }
        .cards-section {
            margin: 0 0 1.2rem 0;
        }
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px,1fr));
            gap: 12px;
        }
        .cards-pagination {
            margin-top: .85rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: .65rem;
            flex-wrap: wrap;
        }
        .cards-pagination-info {
            font-size: .84rem;
            color: var(--text-muted);
        }
        .cards-pagination button {
            padding: .48rem .85rem;
            border-radius: 999px;
            border: 1px solid var(--border-soft);
            background: rgba(255,255,255,.9);
            color: #1e293b;
            cursor: pointer;
            font-weight: 600;
        }
        .cards-pagination button:disabled {
            opacity: .45;
            cursor: not-allowed;
        }
        .hotel-card {
            background: rgba(255,255,255,.88);
            border: 1px solid var(--border-soft);
            border-radius: 14px;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
            animation: sectionFadeIn .45s ease both;
            display: flex;
            flex-direction: column;
            height: 100%;
        }
        .hotel-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
            border-color: rgba(79,70,229,.28);
        }
        .hotel-card-img {
            height: 120px;
            background: linear-gradient(135deg, rgba(79,70,229,.16), rgba(14,165,233,.16));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #334155;
            font-size: .9rem;
        }
        .hotel-card-img img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }
        .hotel-card-body {
            padding: .72rem .8rem .82rem;
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .hotel-card-title {
            margin: 0 0 .45rem 0;
            font-size: .96rem;
            font-weight: 700;
            color: #1e293b;
            line-height: 1.25;
            min-height: 2.5em;
        }
        .hotel-card-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: .5rem;
        }
        .hotel-card-price {
            font-size: 1.12rem;
            font-weight: 800;
            color: #111827;
        }
        .deal-pill {
            border-radius: 999px;
            padding: .18rem .5rem;
            font-size: .72rem;
            font-weight: 700;
            border: 1px solid transparent;
            white-space: nowrap;
        }
        .deal-pill.hot { background: rgba(245,158,11,.18); color: #92400e; border-color: rgba(245,158,11,.32); }
        .deal-pill.good { background: rgba(16,185,129,.17); color: #065f46; border-color: rgba(16,185,129,.32); }
        .deal-pill.normal { background: rgba(148,163,184,.18); color: #334155; border-color: rgba(148,163,184,.35); }
        .deal-pill.bad { background: rgba(239,68,68,.15); color: #991b1b; border-color: rgba(239,68,68,.32); }
        .deal-pill.warm { background: rgba(14,165,233,.16); color: #0c4a6e; border-color: rgba(14,165,233,.35); }
        .comeback-badge {
            display: inline-block;
            margin-top: .25rem;
            font-size: .72rem;
            font-weight: 700;
            color: #065f46;
            background: rgba(16,185,129,.14);
            border: 1px solid rgba(16,185,129,.28);
            border-radius: 999px;
            padding: .12rem .45rem;
        }
        .cheaper-alt-badge {
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 1px 4px;
            white-space: normal;
            margin-top: 3px;
            font-size: 0.68rem;
            line-height: 1.25;
            color: #475569;
            background: #f0f9ff;
            border: 1px solid #bae6fd;
            border-radius: 6px;
            padding: 2px 6px;
            text-decoration: none;
            max-width: 100%;
            transition: all 0.15s ease;
        }
        .cheaper-alt-badge:hover {
            background: #e0f2fe;
            border-color: #7dd3fc;
            color: #0369a1;
            text-decoration: none;
        }
        .cheaper-alt-badge .alt-label {
            color: #475569;
            font-weight: 600;
            white-space: nowrap;
        }
        .cheaper-alt-badge .alt-savings {
            color: #059669;
            font-weight: 700;
            white-space: nowrap;
        }
        .dark-theme .cheaper-alt-badge {
            background: rgba(56, 189, 248, 0.1);
            border-color: #334155;
            color: #cbd5e1;
        }
        .dark-theme .cheaper-alt-badge .alt-label {
            color: #cbd5e1;
        }
        .dark-theme .cheaper-alt-badge .alt-savings {
            color: #34d399;
        }

        /* Hopper Predictive Engine Pills */
        .hopper-pill {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border-radius: 999px;
            padding: .18rem .55rem;
            font-size: .72rem;
            font-weight: 700;
            border: 1px solid transparent;
            white-space: nowrap;
            cursor: help;
        }
        .hopper-pill::after {
            content: attr(data-tip);
            position: absolute;
            bottom: calc(100% + 7px);
            left: 50%;
            transform: translateX(-50%);
            background: #0f172a;
            color: #f8fafc;
            font-size: 0.74rem;
            font-weight: 500;
            line-height: 1.35;
            padding: .45rem .75rem;
            border-radius: 7px;
            white-space: normal;
            width: 250px;
            max-width: 85vw;
            box-shadow: 0 8px 20px rgba(0,0,0,.35);
            pointer-events: none;
            opacity: 0;
            visibility: hidden;
            transition: opacity .18s ease, visibility .18s ease;
            z-index: 10000;
            text-align: left;
        }
        .hopper-pill::before {
            content: "";
            position: absolute;
            bottom: calc(100% + 1px);
            left: 50%;
            transform: translateX(-50%);
            border-width: 6px 6px 0 6px;
            border-style: solid;
            border-color: #0f172a transparent transparent transparent;
            opacity: 0;
            visibility: hidden;
            transition: opacity .18s ease, visibility .18s ease;
            z-index: 10000;
        }
        .hopper-pill:hover::after,
        .hopper-pill:hover::before {
            opacity: 1;
            visibility: visible;
        }
        .hopper-pill.buy-now {
            background: rgba(16,185,129,.18);
            color: #065f46;
            border-color: rgba(16,185,129,.35);
        }
        .hopper-pill.wait {
            background: rgba(245,158,11,.18);
            color: #92400e;
            border-color: rgba(245,158,11,.35);
        }
        .hopper-pill.overpriced {
            background: rgba(239,68,68,.15);
            color: #991b1b;
            border-color: rgba(239,68,68,.32);
        }
        .dark-theme .hopper-pill.buy-now {
            background: rgba(16,185,129,.25);
            color: #34d399;
            border-color: rgba(16,185,129,.4);
        }
        .dark-theme .hopper-pill.wait {
            background: rgba(245,158,11,.25);
            color: #fbbf24;
            border-color: rgba(245,158,11,.4);
        }
        .dark-theme .hopper-pill.overpriced {
            background: rgba(239,68,68,.25);
            color: #f87171;
            border-color: rgba(239,68,68,.4);
        }
        .dark-theme .hopper-pill::after {
            background: #1e293b;
            color: #f1f5f9;
            border: 1px solid rgba(255,255,255,.1);
        }
        .dark-theme .hopper-pill::before {
            border-color: #1e293b transparent transparent transparent;
        }

        /* AI Smart Market Badges */
        .fair-price-pill {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 3px;
            border-radius: 999px;
            padding: .16rem .52rem;
            font-size: .70rem;
            font-weight: 700;
            border: 1px solid transparent;
            white-space: nowrap;
            cursor: help;
        }
        .fair-price-pill.bargain {
            background: rgba(6, 182, 212, 0.15);
            color: #0e7490;
            border-color: rgba(6, 182, 212, 0.35);
        }
        .fair-price-pill.overpriced {
            background: rgba(249, 115, 22, 0.15);
            color: #c2410c;
            border-color: rgba(249, 115, 22, 0.35);
        }
        .dark-theme .fair-price-pill.bargain {
            background: rgba(6, 182, 212, 0.22);
            color: #38bdf8;
            border-color: rgba(6, 182, 212, 0.45);
        }
        .dark-theme .fair-price-pill.overpriced {
            background: rgba(249, 115, 22, 0.22);
            color: #fb923c;
            border-color: rgba(249, 115, 22, 0.45);
        }

        .booking-window-pill {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 3px;
            border-radius: 999px;
            padding: .16rem .52rem;
            font-size: .70rem;
            font-weight: 700;
            border: 1px solid transparent;
            white-space: nowrap;
            cursor: help;
        }
        .booking-window-pill.in_window {
            background: rgba(99, 102, 241, 0.15);
            color: #4338ca;
            border-color: rgba(99, 102, 241, 0.35);
        }
        .booking-window-pill.early {
            background: rgba(100, 116, 139, 0.14);
            color: #475569;
            border-color: rgba(100, 116, 139, 0.3);
        }
        .booking-window-pill.late {
            background: rgba(244, 63, 94, 0.14);
            color: #be123c;
            border-color: rgba(244, 63, 94, 0.32);
        }
        .dark-theme .booking-window-pill.in_window {
            background: rgba(99, 102, 241, 0.25);
            color: #818cf8;
            border-color: rgba(99, 102, 241, 0.45);
        }
        .dark-theme .booking-window-pill.early {
            background: rgba(148, 163, 184, 0.18);
            color: #cbd5e1;
            border-color: rgba(148, 163, 184, 0.35);
        }
        .dark-theme .booking-window-pill.late {
            background: rgba(244, 63, 94, 0.22);
            color: #fb7185;
            border-color: rgba(244, 63, 94, 0.45);
        }

        .gem-pill {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 3px;
            border-radius: 999px;
            padding: .16rem .52rem;
            font-size: .70rem;
            font-weight: 700;
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.16), rgba(236, 72, 153, 0.12));
            color: #7e22ce;
            border: 1px solid rgba(168, 85, 247, 0.35);
            white-space: nowrap;
            cursor: help;
        }
        .dark-theme .gem-pill {
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.28), rgba(236, 72, 153, 0.22));
            color: #d8b4fe;
            border-color: rgba(168, 85, 247, 0.5);
        }

        .glitch-radar-pill {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 3px;
            border-radius: 999px;
            padding: .16rem .52rem;
            font-size: .70rem;
            font-weight: 800;
            background: rgba(239, 68, 68, 0.18);
            color: #b91c1c;
            border: 1px solid rgba(239, 68, 68, 0.42);
            white-space: nowrap;
            cursor: help;
            animation: glitchPulse 2.2s infinite ease-in-out;
        }
        .dark-theme .glitch-radar-pill {
            background: rgba(239, 68, 68, 0.28);
            color: #fca5a5;
            border-color: rgba(239, 68, 68, 0.55);
        }
        @keyframes glitchPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.03); }
        }

        .ai-dupe-line {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 0.70rem;
            line-height: 1.25;
            color: #4338ca;
            background: rgba(99, 102, 241, 0.08);
            border: 1px solid rgba(99, 102, 241, 0.2);
            border-radius: 6px;
            padding: 2px 7px;
            margin-top: 3px;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .ai-dupe-line a {
            color: inherit;
            text-decoration: underline;
            font-weight: 600;
        }
        .dark-theme .ai-dupe-line {
            color: #a5b4fc;
            background: rgba(99, 102, 241, 0.16);
            border-color: rgba(99, 102, 241, 0.35);
        }

        /* Table Smart Badges & Table Dupe */
        .tbl-smart-badges-wrap {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 4px;
            margin-top: 3px;
        }
        .tbl-badge {
            display: inline-flex;
            align-items: center;
            font-size: 0.65rem;
            font-weight: 700;
            padding: 1px 5px;
            border-radius: 4px;
            line-height: 1.25;
            cursor: help;
            white-space: nowrap;
        }
        .tbl-badge-flash {
            background: rgba(239, 68, 68, 0.18);
            color: #b91c1c;
            border: 1px solid rgba(239, 68, 68, 0.4);
            animation: glitchPulse 2.2s infinite ease-in-out;
        }
        .tbl-badge-gem {
            background: rgba(168, 85, 247, 0.16);
            color: #7e22ce;
            border: 1px solid rgba(168, 85, 247, 0.35);
        }
        .tbl-badge-bw {
            background: rgba(99, 102, 241, 0.15);
            color: #4338ca;
            border: 1px solid rgba(99, 102, 241, 0.35);
        }
        .tbl-badge-fp.bargain {
            background: rgba(6, 182, 212, 0.15);
            color: #0e7490;
            border: 1px solid rgba(6, 182, 212, 0.35);
        }
        .tbl-badge-fp.overpriced {
            background: rgba(249, 115, 22, 0.15);
            color: #c2410c;
            border: 1px solid rgba(249, 115, 22, 0.35);
        }
        .tbl-badge-kids {
            background: rgba(16, 185, 129, 0.15);
            color: #047857;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }
        .tbl-badge-heat {
            background: rgba(245, 158, 11, 0.15);
            color: #b45309;
            border: 1px solid rgba(245, 158, 11, 0.35);
        }
        .tbl-badge-shelter {
            background: rgba(20, 184, 166, 0.15);
            color: #0f766e;
            border: 1px solid rgba(20, 184, 166, 0.35);
        }
        .tbl-badge-better {
            background: rgba(14, 165, 233, 0.15);
            color: #0369a1;
            border: 1px solid rgba(14, 165, 233, 0.35);
        }
        .tbl-badge-worse {
            background: rgba(244, 63, 94, 0.15);
            color: #be123c;
            border: 1px solid rgba(244, 63, 94, 0.35);
        }
        .tbl-dupe-badge {
            display: inline-flex;
            align-items: center;
            gap: 2px 4px;
            font-size: 0.65rem;
            line-height: 1.25;
            color: #4338ca;
            background: rgba(99, 102, 241, 0.08);
            border: 1px solid rgba(99, 102, 241, 0.2);
            border-radius: 4px;
            padding: 1px 5px;
            margin-top: 3px;
            max-width: 100%;
            text-decoration: none;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .tbl-dupe-badge .tbl-dupe-label {
            font-weight: 600;
            text-decoration: underline;
        }
        .tbl-dupe-badge .tbl-dupe-savings {
            color: #059669;
            font-weight: 700;
        }
        .dark-theme .tbl-badge-flash {
            background: rgba(239, 68, 68, 0.25);
            color: #fca5a5;
            border-color: rgba(239, 68, 68, 0.5);
        }
        .dark-theme .tbl-badge-gem {
            background: rgba(168, 85, 247, 0.25);
            color: #d8b4fe;
            border-color: rgba(168, 85, 247, 0.45);
        }
        .dark-theme .tbl-badge-bw {
            background: rgba(99, 102, 241, 0.22);
            color: #818cf8;
            border-color: rgba(99, 102, 241, 0.45);
        }
        .dark-theme .tbl-badge-fp.bargain {
            background: rgba(6, 182, 212, 0.22);
            color: #38bdf8;
            border-color: rgba(6, 182, 212, 0.45);
        }
        .dark-theme .tbl-badge-fp.overpriced {
            background: rgba(249, 115, 22, 0.22);
            color: #fb923c;
            border-color: rgba(249, 115, 22, 0.45);
        }
        .dark-theme .tbl-badge-kids {
            background: rgba(16, 185, 129, 0.25);
            color: #6ee7b7;
            border-color: rgba(16, 185, 129, 0.5);
        }
        .dark-theme .tbl-badge-heat {
            background: rgba(245, 158, 11, 0.25);
            color: #fcd34d;
            border-color: rgba(245, 158, 11, 0.5);
        }
        .dark-theme .tbl-badge-shelter {
            background: rgba(20, 184, 166, 0.25);
            color: #5eead4;
            border-color: rgba(20, 184, 166, 0.5);
        }
        .dark-theme .tbl-badge-better {
            background: rgba(14, 165, 233, 0.25);
            color: #7dd3fc;
            border-color: rgba(14, 165, 233, 0.5);
        }
        .dark-theme .tbl-badge-worse {
            background: rgba(244, 63, 94, 0.25);
            color: #fda4af;
            border-color: rgba(244, 63, 94, 0.5);
        }
        .dark-theme .tbl-dupe-badge {
            color: #a5b4fc;
            background: rgba(99, 102, 241, 0.16);
            border-color: rgba(99, 102, 241, 0.35);
        }
        .dark-theme .tbl-dupe-badge .tbl-dupe-savings {
            color: #34d399;
        }

        /* Arbitrage Card Badge */
        .arbitrage-card-badge {
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 2px 5px;
            white-space: normal;
            margin-top: 3px;
            font-size: 0.68rem;
            line-height: 1.25;
            color: #065f46;
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            border-radius: 6px;
            padding: 2px 6px;
            text-decoration: none;
            max-width: 100%;
            transition: all 0.15s ease;
        }
        .arbitrage-card-badge:hover {
            background: #d1fae5;
            border-color: #6ee7b7;
            text-decoration: none;
        }
        .arbitrage-card-badge .arb-label {
            color: #065f46;
            font-weight: 600;
            white-space: nowrap;
        }
        .arbitrage-card-badge .arb-savings {
            color: #059669;
            font-weight: 700;
            white-space: nowrap;
        }
        .dark-theme .arbitrage-card-badge {
            background: rgba(16,185,129,0.12);
            border-color: #065f46;
            color: #6ee7b7;
        }
        .dark-theme .arbitrage-card-badge .arb-label {
            color: #a7f3d0;
        }
        .dark-theme .arbitrage-card-badge .arb-savings {
            color: #34d399;
        }

        /* Arbitrage Hub Section & Calculator */
        .full-width-arbitrage-section {
            width: 100%;
        }
        .arbitrage-calc-bar {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 1.1rem 1.4rem;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
        }
        .dark-theme .arbitrage-calc-bar {
            background: #1e293b;
            border-color: #334155;
        }
        .arbitrage-calc-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .arbitrage-slider-group {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 14px;
            font-size: 0.86rem;
        }
        .arbitrage-slider-group input[type="range"] {
            cursor: pointer;
            width: 130px;
        }
        .arb-badge-win {
            background: #059669;
            color: #fff;
            padding: 3px 8px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.76rem;
            white-space: nowrap;
            display: inline-block;
        }
        .arb-badge-neutral {
            background: #e2e8f0;
            color: #475569;
            padding: 3px 8px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.76rem;
            white-space: nowrap;
            display: inline-block;
        }
        .dark-theme .arb-badge-neutral {
            background: #334155;
            color: #cbd5e1;
        }
        .hotel-card-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
            margin-bottom: .6rem;
            color: #475569;
            font-size: .79rem;
        }
        .hotel-card-actions {
            display: flex;
            gap: 8px;
            margin-top: auto;
            padding-top: .6rem;
        }
        .card-btn {
            flex: 1;
            text-align: center;
            text-decoration: none;
            border-radius: 10px;
            padding: .45rem .5rem;
            font-size: .8rem;
            font-weight: 700;
            border: 1px solid var(--border-soft);
            color: #1e293b;
            background: rgba(255,255,255,.92);
            transition: transform .14s ease, box-shadow .14s ease;
        }
        .card-btn.primary {
            background: var(--gradient-primary);
            color: #fff;
            border-color: transparent;
        }
        .card-btn:hover {
            transform: translateY(-1px);
            box-shadow: var(--shadow-sm);
        }
        .alerts-section {
            margin-top: var(--section-gap);
            margin-bottom: var(--section-gap);
            background: var(--gradient-card);
            border-radius: var(--radius-xl);
            box-shadow: var(--shadow-md);
            border: 1px solid var(--border-soft);
            overflow: hidden;
        }
        .alerts-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            cursor: pointer;
            user-select: none;
            padding: 1rem var(--section-inner-x);
            border-bottom: 1px solid var(--border-soft);
        }
        .alerts-header:hover {
            background: rgba(248,250,252,.85);
        }
        .alerts-header-main {
            flex: 1;
            min-width: 0;
        }
        .alerts-header h3 {
            margin: 0 0 .35rem 0;
            font-size: 1.12rem;
            color: #1e293b;
        }
        .alerts-lead {
            margin: 0 0 .55rem 0;
            font-size: .84rem;
            line-height: 1.45;
            color: var(--text-muted);
            max-width: 62rem;
        }
        .alerts-summary-chips {
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
        }
        .alert-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: .18rem .55rem;
            font-size: .74rem;
            font-weight: 700;
            border: 1px solid transparent;
        }
        .alert-chip.drop {
            background: rgba(16,185,129,.14);
            color: #065f46;
            border-color: rgba(16,185,129,.28);
        }
        .alert-chip.up {
            background: rgba(239,68,68,.12);
            color: #991b1b;
            border-color: rgba(239,68,68,.26);
        }
        .alert-chip.missing {
            background: rgba(100,116,139,.14);
            color: #334155;
            border-color: rgba(100,116,139,.28);
        }
        .alerts-content {
            max-height: 680px;
            overflow-y: auto;
            transition: max-height 0.3s ease;
            background: rgba(248,250,252,.55);
        }
        .alerts-content.collapsed {
            max-height: 0;
            overflow: hidden;
            padding: 0;
        }
        .alerts-section-label {
            margin: 0;
            padding: .85rem var(--section-inner-x) .35rem;
            font-size: .78rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: .04em;
        }
        .alerts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 8px;
            padding: 0 var(--section-inner-x) .85rem;
        }
        .alert-card {
            display: flex;
            flex-direction: row;
            align-items: stretch;
            height: 100%;
            background: rgba(255,255,255,.95);
            border: 1px solid var(--border-soft);
            border-radius: 10px;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            transition: transform .14s ease, box-shadow .14s ease, border-color .14s ease;
        }
        .alert-card:hover {
            transform: translateY(-1px);
            box-shadow: var(--shadow-md);
        }
        .alert-card.drop {
            border-left: 3px solid #10b981;
        }
        .alert-card.up {
            border-left: 3px solid #ef4444;
        }
        .alert-card.missing {
            border-left: 3px solid #64748b;
        }
        .alert-card-img {
            width: 62px;
            flex-shrink: 0;
            background: linear-gradient(135deg, rgba(79,70,229,.12), rgba(14,165,233,.12));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #64748b;
            font-size: .75rem;
        }
        .alert-card-img img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }
        .alert-card-body {
            padding: .45rem .5rem .5rem;
            display: flex;
            flex-direction: column;
            flex: 1;
            min-width: 0;
        }
        .alert-card-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: .3rem;
            margin-bottom: .25rem;
        }
        .alert-badge {
            border-radius: 999px;
            padding: .1rem .38rem;
            font-size: .62rem;
            font-weight: 800;
            white-space: nowrap;
            flex: 0 0 auto;
            line-height: 1.2;
        }
        .alert-badge.drop { background: rgba(16,185,129,.16); color: #065f46; }
        .alert-badge.up { background: rgba(239,68,68,.14); color: #991b1b; }
        .alert-badge.missing { background: rgba(100,116,139,.16); color: #334155; }
        .alert-card-title {
            margin: 0;
            font-size: .78rem;
            font-weight: 700;
            line-height: 1.2;
            min-height: 2.4em;
        }
        .alert-card-title a {
            color: #1e293b;
            text-decoration: none;
        }
        .alert-card-title a:hover {
            color: #4f46e5;
            text-decoration: underline;
        }
        .alert-price-row {
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
            gap: .25rem;
            margin-bottom: .2rem;
        }
        .alert-price-old {
            font-size: .72rem;
            color: #64748b;
            text-decoration: line-through;
        }
        .alert-price-new {
            font-size: .88rem;
            font-weight: 800;
            color: #111827;
        }
        .alert-price-new.up {
            color: #b91c1c;
        }
        .alert-price-new.drop {
            color: #047857;
        }
        .alert-change-pct {
            font-size: .72rem;
            font-weight: 800;
        }
        .alert-change-pct.drop { color: #047857; }
        .alert-change-pct.up { color: #b91c1c; }
        .alert-card-meta {
            font-size: .68rem;
            color: #64748b;
            line-height: 1.25;
            margin-bottom: .35rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .alert-card-actions {
            display: flex;
            gap: 5px;
            margin-top: auto;
        }
        .alert-card-actions .card-btn {
            flex: 1;
            font-size: .68rem;
            padding: .28rem .35rem;
            border-radius: 8px;
        }
        .alerts-empty {
            color: #64748b;
            font-style: italic;
            padding: 1rem var(--section-inner-x) .5rem;
            font-size: .84rem;
        }
        .alerts-history-fold {
            margin: 0 var(--section-inner-x) .85rem;
            border: 1px solid var(--border-soft);
            border-radius: 10px;
            background: rgba(255,255,255,.72);
            overflow: hidden;
        }
        .alerts-history-fold > summary {
            list-style: none;
            cursor: pointer;
            padding: .55rem .75rem;
            font-size: .82rem;
            font-weight: 700;
            color: #475569;
            user-select: none;
        }
        .alerts-history-fold > summary::-webkit-details-marker {
            display: none;
        }
        .alerts-history-fold > summary:hover {
            background: rgba(248,250,252,.9);
        }
        .alert-history-list {
            border-top: 1px solid var(--border-soft);
            max-height: 320px;
            overflow-y: auto;
        }
        .alert-history-row {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto auto;
            align-items: center;
            gap: .55rem .65rem;
            padding: .45rem .75rem;
            border-bottom: 1px solid rgba(148,163,184,.16);
            font-size: .78rem;
            background: rgba(255,255,255,.82);
        }
        .alert-history-row:last-child {
            border-bottom: none;
        }
        .alert-history-row.drop { border-left: 3px solid #10b981; }
        .alert-history-row.up { border-left: 3px solid #ef4444; }
        .alert-history-row.missing { border-left: 3px solid #64748b; }
        .alert-history-badge {
            width: 1.35rem;
            text-align: center;
            font-weight: 800;
            font-size: .82rem;
            flex-shrink: 0;
        }
        .alert-history-badge.drop { color: #047857; }
        .alert-history-badge.up { color: #b91c1c; }
        .alert-history-badge.missing { color: #64748b; }
        .alert-history-info {
            min-width: 0;
        }
        .alert-history-name {
            display: block;
            font-weight: 700;
            color: #1e293b;
            text-decoration: none;
            line-height: 1.25;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .alert-history-name:hover {
            color: #4f46e5;
            text-decoration: underline;
        }
        .alert-history-sub {
            display: block;
            margin-top: .12rem;
            font-size: .68rem;
            color: #64748b;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .alert-history-price {
            white-space: nowrap;
            text-align: right;
            font-size: .76rem;
        }
        .alert-history-old {
            color: #94a3b8;
            text-decoration: line-through;
        }
        .alert-history-arrow {
            opacity: .55;
            margin: 0 .12rem;
        }
        .alert-history-new {
            font-weight: 800;
            color: #111827;
        }
        .alert-history-new.drop { color: #047857; }
        .alert-history-new.up { color: #b91c1c; }
        .alert-history-pct {
            margin-left: .35rem;
            font-weight: 800;
            font-size: .72rem;
        }
        .alert-history-pct.drop { color: #047857; }
        .alert-history-pct.up { color: #b91c1c; }
        .alert-history-chart,
        .alert-history-offer {
            font-size: .72rem;
            font-weight: 700;
            color: #4f46e5;
            text-decoration: none;
            white-space: nowrap;
        }
        .alert-history-links {
            display: flex;
            align-items: center;
            gap: .45rem;
            justify-content: flex-end;
        }
        .alert-history-chart:hover,
        .alert-history-offer:hover {
            text-decoration: underline;
        }
        .expand-icon {
            flex: 0 0 auto;
            margin-top: .15rem;
            font-size: .85rem;
            opacity: .75;
            transition: transform .16s ease;
        }
        .expand-icon.collapsed {
            transform: rotate(-90deg);
        }
        .delta { font-weight: bold; }
        .delta.up { color: #dc3545; }
        .delta.down { color: #28a745; }
        .delta.flat { color: #6c757d; }
        .hotels-section {
            margin-top: var(--section-gap);
            background: var(--gradient-card);
            border-radius: var(--radius-xl);
            padding: 2rem;
            box-shadow: var(--shadow-md);
            border: 1px solid var(--border-soft);
            animation: sectionFadeIn .75s ease both;
        }
        .hotels-section.full-width-table-section {
            padding: 2rem;
            overflow: visible;
            width: 100%;
            max-width: 100%;
            margin: var(--section-gap) 0 0 0;
        }
        .hotels-section.full-width-table-section h3,
        .hotels-section.full-width-table-section .deal-legend,
        .hotels-section.full-width-table-section .table-filters,
        .hotels-section.full-width-table-section .mobile-sort-bar,
        .hotels-section.full-width-table-section .pagination,
        .hotels-section.full-width-table-section .pagination-info {
            margin-left: 0;
            margin-right: 0;
            width: 100%;
            max-width: var(--table-block-max-width);
            margin-inline: auto;
        }
        .hotels-section.full-width-table-section .table-container {
            border-radius: var(--panel-shell-radius);
            margin-top: .45rem;
            width: 100%;
            max-width: var(--table-block-max-width);
            margin-left: 0;
            margin-right: 0;
        }
        
        .hotels-section h3 {
            font-size: 1.5rem;
            font-weight: 700;
            margin: 0 0 1.5rem 0;
            color: #1f2937;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .table-container {
            overflow-x: auto;
            overflow-y: hidden;
            -webkit-overflow-scrolling: touch;
            width: 100%;
            max-width: 100%;
            border-radius: 16px;
            box-shadow: none;
            background: #eef6fc;
            border: 1px solid #e2eef8;
            padding: 8px 12px;
        }
        .dark-theme .table-container {
            background: #0f172a;
            border-color: #1e293b;
        }
        .table-container--hotels {
            overflow-x: auto;
        }
        
        .hotels-table {
            width: 100%;
            min-width: 1080px;
            table-layout: fixed;
            border-collapse: separate;
            border-spacing: 0 6px;
            margin: 0;
            font-size: 0.85rem;
        }

        .hotels-table col.col-w-hotel { width: 22.0%; }
        .hotels-table col.col-w-price { width: 13.5%; }
        .hotels-table col.col-w-deal { width: 8.0%; }
        .hotels-table col.col-w-forecast { width: 9.0%; }
        .hotels-table col.col-w-ta { width: 7.0%; }
        .hotels-table col.col-w-d48 { width: 5.5%; }
        .hotels-table col.col-w-davg { width: 7.0%; }
        .hotels-table col.col-w-region { width: 9.0%; }
        .hotels-table col.col-w-dates { width: 11.0%; }
        .hotels-table col.col-w-dur { width: 4.0%; }
        .hotels-table col.col-w-link { width: 4.0%; }

        .hotels-table td.col-w-d48-td,
        .hotels-table td.col-w-davg-td,
        .hotels-table td.col-w-dur-td,
        .hotels-table td.col-duration,
        .hotels-table td.offer-link-cell {
            text-align: center !important;
        }

        .hero-title-clean {
            font-size: 1.75rem;
            font-weight: 700;
            color: #0f172a;
            letter-spacing: -0.02em;
            margin: 0 0 1rem 0;
            line-height: 1.25;
        }
        .dark-theme .hero-title-clean {
            color: #f8fafc;
        }

        .hotels-table td.col-tight,
        .hotels-table th.col-tight {
            white-space: nowrap;
            vertical-align: middle;
            padding: 0.55rem 0.5rem;
        }

        .hotels-table th.col-tight {
            font-size: 0.76rem;
            letter-spacing: 0.04em;
        }

        .hotels-table .col-dates {
            white-space: nowrap;
            font-size: .8rem;
        }

        .table-scroll-hint {
            display: none;
            margin: 0 0 .45rem;
            font-size: .74rem;
            color: var(--text-muted);
            line-height: 1.35;
        }
        
        .hotels-table thead tr {
            background: transparent !important;
            border-radius: 0;
        }
        .dark-theme .hotels-table thead tr {
            background: transparent !important;
        }
        
        .hotels-table th {
            background: transparent !important;
            color: #0284c7;
            font-weight: 800;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 0.6rem 0.5rem;
            text-align: left;
            cursor: pointer;
            user-select: none;
            position: sticky;
            top: 0;
            z-index: 10;
            border: none !important;
            box-shadow: none !important;
            white-space: nowrap;
            transition: var(--transition-fast);
        }
        .dark-theme .hotels-table th {
            color: #38bdf8;
        }
        
        .hotels-table th:hover {
            background: transparent !important;
            color: #0369a1;
            transform: none;
            box-shadow: none;
        }
        
        .hotels-table th.sortable::after {
            content: ' ↕';
            opacity: 0.55;
            margin-left: 0.35rem;
            font-size: 0.8rem;
        }
        
        .hotels-table th.sort-asc::after {
            content: ' ↑';
            opacity: 1;
            color: #0284c7;
        }
        
        .hotels-table th.sort-desc::after {
            content: ' ↓';
            opacity: 1;
            color: #0284c7;
        }
        
        .hotels-table td {
            height: auto;
            padding: 0.75rem 0.65rem;
            border: none;
            vertical-align: top;
            background: transparent;
            box-sizing: border-box;
            line-height: 1.3;
            transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* ── Alternating White Volumetric Floating Cards & Sky Blue Rows ── */
        .hotels-table tbody tr {
            transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .hotels-table tbody tr:nth-child(odd) td,
        .hotels-table tbody tr.row-odd td {
            background: #ffffff;
            border-top: 1px solid #e2eef8;
            border-bottom: 1px solid #e2eef8;
        }

        .hotels-table tbody tr:nth-child(odd) td:first-child,
        .hotels-table tbody tr.row-odd td:first-child {
            border-left: 1px solid #e2eef8;
            border-top-left-radius: 14px;
            border-bottom-left-radius: 14px;
        }

        .hotels-table tbody tr:nth-child(odd) td:last-child,
        .hotels-table tbody tr.row-odd td:last-child {
            border-right: 1px solid #e2eef8;
            border-top-right-radius: 14px;
            border-bottom-right-radius: 14px;
        }

        .hotels-table tbody tr:nth-child(odd),
        .hotels-table tbody tr.row-odd {
            box-shadow: 0 3px 10px rgba(0, 50, 100, 0.05);
        }

        .hotels-table tbody tr:nth-child(even) td,
        .hotels-table tbody tr.row-even td {
            background: transparent;
            border-top: 1px solid transparent;
            border-bottom: 1px solid transparent;
            border-left: 1px solid transparent;
            border-right: 1px solid transparent;
        }

        .hotels-table tbody tr:nth-child(even) td:first-child,
        .hotels-table tbody tr.row-even td:first-child {
            border-top-left-radius: 14px;
            border-bottom-left-radius: 14px;
        }
        .hotels-table tbody tr:nth-child(even) td:last-child,
        .hotels-table tbody tr.row-even td:last-child {
            border-top-right-radius: 14px;
            border-bottom-right-radius: 14px;
        }

        .hotels-table tbody tr:hover td {
            background: #ffffff !important;
            border-top: 1px solid #7dd3fc !important;
            border-bottom: 1px solid #7dd3fc !important;
        }
        .hotels-table tbody tr:hover td:first-child {
            border-left: 1px solid #7dd3fc !important;
            border-top-left-radius: 14px;
            border-bottom-left-radius: 14px;
        }
        .hotels-table tbody tr:hover td:last-child {
            border-right: 1px solid #7dd3fc !important;
            border-top-right-radius: 14px;
            border-bottom-right-radius: 14px;
        }
        .hotels-table tbody tr:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 18px -2px rgba(2, 132, 199, 0.14) !important;
        }

        .dark-theme .hotels-table tbody tr:nth-child(odd) td,
        .dark-theme .hotels-table tbody tr.row-odd td {
            background: #1e293b;
            border-top: 1px solid #334155;
            border-bottom: 1px solid #334155;
        }
        .dark-theme .hotels-table tbody tr:nth-child(odd) td:first-child,
        .dark-theme .hotels-table tbody tr.row-odd td:first-child {
            border-left: 1px solid #334155;
        }
        .dark-theme .hotels-table tbody tr:nth-child(odd) td:last-child,
        .dark-theme .hotels-table tbody tr.row-odd td:last-child {
            border-right: 1px solid #334155;
        }

        .dark-theme .hotels-table tbody tr:hover td {
            background: #1e293b !important;
            border-top-color: #38bdf8 !important;
            border-bottom-color: #38bdf8 !important;
        }
        .dark-theme .hotels-table tbody tr:hover td:first-child {
            border-left-color: #38bdf8 !important;
        }
        .dark-theme .hotels-table tbody tr:hover td:last-child {
            border-right-color: #38bdf8 !important;
        }

        /* ── Price formatting ── */
        .hotels-table td.price {
            color: #059669 !important;
            font-weight: 800;
            font-size: 1.02rem;
            line-height: 1.2;
            white-space: nowrap;
        }
        .hotels-table td.price .price-main {
            display: inline;
            font-weight: 800;
            color: #059669;
            vertical-align: middle;
        }
        .hotels-table .comeback-badge {
            display: inline-flex !important;
            align-items: center;
            font-size: 0.68rem;
            font-weight: 700;
            margin-left: 6px;
            padding: 1px 6px;
            border-radius: 999px;
            vertical-align: middle;
            line-height: 1.2;
            color: #065f46;
            background: rgba(16, 185, 129, 0.16);
            border: 1px solid rgba(16, 185, 129, 0.32);
        }
        .hotels-table td.price {
            vertical-align: middle;
            white-space: normal !important;
            padding: 0.35rem 0.5rem;
        }
        .hotels-table .price-cell-box {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            justify-content: center;
            gap: 2px;
            max-width: 100%;
            min-width: 0;
            overflow: hidden;
        }
        .hotels-table .price-main-row {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
            max-width: 100%;
        }
        .hotels-table .price-main {
            font-weight: 800;
            font-size: 1.02rem;
            color: var(--success-color);
            line-height: 1.2;
            white-space: nowrap;
        }
        .hotels-table .comeback-badge {
            display: inline-flex !important;
            align-items: center;
            font-size: 0.68rem;
            font-weight: 700;
            padding: 1px 6px;
            border-radius: 999px;
            vertical-align: middle;
            line-height: 1.2;
            color: #065f46;
            background: rgba(16, 185, 129, 0.16);
            border: 1px solid rgba(16, 185, 129, 0.32);
            white-space: nowrap;
            flex-shrink: 0;
        }
        .hotels-table .cheaper-alt-badge {
            display: inline-flex !important;
            align-items: center;
            gap: 3px;
            font-size: 0.64rem;
            font-weight: 600;
            margin-left: 0 !important;
            margin-top: 2px;
            padding: 1px 6px;
            border-radius: 6px;
            vertical-align: middle;
            line-height: 1.25;
            color: #0284c7;
            background: #e0f2fe;
            border: 1px solid #bae6fd;
            text-decoration: none;
            white-space: nowrap;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            box-sizing: border-box;
            transition: all 0.15s ease;
        }
        .hotels-table .cheaper-alt-badge:hover {
            background: #bae6fd;
            border-color: #38bdf8;
            color: #0369a1;
        }
        .hotels-table .cheaper-alt-badge .alt-label {
            color: #0369a1;
            font-weight: 600;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .hotels-table .cheaper-alt-badge .alt-savings {
            color: #059669;
            font-weight: 700;
            flex-shrink: 0;
        }
        .dark-theme .hotels-table td.price {
            color: #34d399 !important;
        }
        .dark-theme .hotels-table .price-main {
            color: #34d399 !important;
        }
        .dark-theme .hotels-table .comeback-badge {
            color: #34d399;
            background: rgba(16, 185, 129, 0.2);
            border-color: rgba(52, 211, 153, 0.4);
        }
        .dark-theme .hotels-table .cheaper-alt-badge {
            color: #38bdf8;
            background: rgba(56, 189, 248, 0.15);
            border-color: rgba(56, 189, 248, 0.3);
        }
        .dark-theme .hotels-table .cheaper-alt-badge .alt-label {
            color: #7dd3fc;
        }
        .dark-theme .hotels-table .cheaper-alt-badge .alt-savings {
            color: #34d399;
        }

        /* ── Link Button ── */
        .col-link-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: #e0f2fe;
            color: #0284c7;
            text-decoration: none;
            font-weight: 700;
            transition: all 0.18s ease;
            box-shadow: 0 2px 6px rgba(2, 132, 199, 0.12);
        }
        .col-link-btn:hover {
            background: #0284c7;
            color: #ffffff;
            transform: scale(1.08);
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3);
        }
        .dark-theme .col-link-btn {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
        }
        .dark-theme .col-link-btn:hover {
            background: #38bdf8;
            color: #0f172a;
        }

        /* ── Tooltip на заголовках таблицы ── */
        .th-tip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.1em;
            height: 1.1em;
            font-size: 0.7rem;
            background: rgba(255,255,255,.28);
            border-radius: 50%;
            cursor: help;
            position: relative;
            vertical-align: middle;
            margin-left: 2px;
            font-style: normal;
            font-weight: 700;
            line-height: 1;
            transition: background .15s;
            border: 1px solid rgba(255,255,255,.45);
        }
        .th-tip:hover {
            background: rgba(255,255,255,.55);
        }
        .th-tip::after {
            content: attr(data-tip);
            position: absolute;
            top: calc(100% + 8px);
            bottom: auto;
            left: 50%;
            transform: translateX(-50%);
            background: #1e293b;
            color: #f1f5f9;
            font-size: 0.78rem;
            font-weight: 400;
            text-transform: none;
            letter-spacing: 0;
            padding: .55rem .85rem;
            border-radius: 8px;
            white-space: normal;
            width: 220px;
            max-width: 90vw;
            box-shadow: 0 8px 24px rgba(0,0,0,.4);
            pointer-events: none;
            opacity: 0;
            transition: opacity .18s ease;
            z-index: 9999;
        }
        .th-tip::before {
            content: "";
            position: absolute;
            top: calc(100% + 2px);
            left: 50%;
            transform: translateX(-50%);
            border-width: 0 6px 6px 6px;
            border-style: solid;
            border-color: transparent transparent #1e293b transparent;
            opacity: 0;
            transition: opacity .18s ease;
            z-index: 10000;
            pointer-events: none;
        }
        .th-tip:hover::after,
        .th-tip:hover::before {
            opacity: 1;
        }

        /* ── Статус обновления ── */
        .update-status {
            display: inline-flex;
            align-items: center;
            gap: .35rem;
            font-size: 0.92rem;
            font-weight: 600;
            white-space: nowrap;
        }
        .update-status--ok    { color: #10b981; }
        .update-status--warn  { color: #f59e0b; }
        .update-status--err   { color: #ef4444; }

        /* ── Top Movers Widget ── */
        .top-movers-section {
            background: #fff;
            border: 1px solid var(--border-soft);
            border-radius: var(--radius-xl);
            padding: 1.1rem 1.3rem;
            margin-bottom: 1.5rem;
            box-shadow: var(--shadow-sm);
        }
        .top-movers-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: .4rem;
            margin-bottom: .85rem;
        }
        .top-movers-head h3 {
            margin: 0;
            font-size: 1.05rem;
            font-weight: 800;
            color: #1e293b;
        }
        .top-movers-sub {
            font-size: .8rem;
            color: var(--text-muted);
        }
        .top-movers-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: .85rem;
        }
        .top-movers-card {
            background: #f8fafc;
            border-radius: 12px;
            padding: .85rem 1rem;
            border: 1px solid #e2e8f0;
        }
        .top-movers-card--drops { border-left: 4px solid #10b981; }
        .top-movers-card--rises { border-left: 4px solid #ef4444; }
        .top-movers-card-title {
            font-size: .85rem;
            font-weight: 700;
            margin-bottom: .6rem;
            color: #334155;
        }
        .top-mover-empty {
            font-size: .8rem;
            color: var(--text-muted);
            font-style: italic;
            padding: .4rem 0;
        }
        .top-mover-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .4rem;
            padding: .45rem .6rem;
            border-radius: 8px;
            text-decoration: none;
            color: inherit;
            background: #fff;
            margin-bottom: .35rem;
            border: 1px solid #edf2f7;
            transition: background .15s ease, border-color .15s ease;
        }
        .top-mover-item:hover {
            background: #f1f5f9;
            border-color: #cbd5e1;
        }
        .top-mover-name {
            font-size: .84rem;
            font-weight: 600;
            color: #1e293b;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 150px;
        }
        .top-mover-prices {
            font-size: .78rem;
            color: #64748b;
        }
        .top-mover-badge {
            font-size: .75rem;
            font-weight: 700;
            padding: .12rem .4rem;
            border-radius: 999px;
            white-space: nowrap;
        }
        .top-mover-badge.drop {
            background: rgba(16,185,129,.15);
            color: #047857;
        }
        .top-mover-badge.up {
            background: rgba(239,68,68,.15);
            color: #b91c1c;
        }

        @keyframes sectionFadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes floatSoft {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-4px); }
        }
        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 rgba(255,255,255,0); }
            50% { box-shadow: 0 8px 22px rgba(255,255,255,.12); }
        }
        @keyframes gradientDrift {
            0% { transform: translate3d(0,0,0) scale(1); }
            100% { transform: translate3d(-10px, 8px, 0) scale(1.02); }
        }
        @keyframes taStarPulse {
            0%, 100% { transform: scale(1); filter: brightness(1); }
            50% { transform: scale(1.08); filter: brightness(1.15); }
        }
        @keyframes taGlow {
            0%, 100% { box-shadow: 0 0 0 rgba(245, 158, 11, 0); }
            50% { box-shadow: 0 0 12px rgba(245, 158, 11, 0.35); }
        }

        .ta-rating {
            display: inline-flex;
            flex-direction: column;
            align-items: center;
            gap: 0.1rem;
            line-height: 1.1;
            animation: taGlow 4s ease-in-out infinite;
        }
        .ta-rating--empty {
            opacity: 0.55;
            animation: none;
        }
        .ta-stars {
            display: inline-flex;
            gap: 0.05rem;
            letter-spacing: -0.05em;
        }
        .ta-star {
            font-size: 0.82rem;
            line-height: 1;
        }
        .ta-star--full, .ta-star--half {
            color: #f59e0b;
            text-shadow: 0 0 8px rgba(245, 158, 11, 0.35);
            animation: taStarPulse 2.8s ease-in-out infinite;
        }
        .ta-star--half {
            opacity: 0.72;
        }
        .ta-star--empty {
            color: #cbd5e1;
        }
        .ta-meta {
            display: inline-flex;
            align-items: baseline;
            gap: 0.35rem;
            font-size: 0.72rem;
            color: #64748b;
            white-space: nowrap;
        }
        .ta-score {
            font-weight: 800;
            color: #b45309;
            font-variant-numeric: tabular-nums;
        }
        .ta-reviews {
            opacity: 0.9;
        }
        .ta-reviews--new {
            font-style: italic;
            opacity: 0.75;
        }
        .hotels-table th.th-ta {
            text-align: center;
        }
        .th-ta-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.75rem;
            height: 1.2rem;
            border-radius: 0.25rem;
            background: #fff;
            padding: 0.08rem 0.12rem;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.18);
            vertical-align: middle;
        }
        .th-ta-svg {
            display: block;
            width: 100%;
            height: auto;
        }
        .hotels-table td.col-w-ta-td {
            font-size: 0.78rem;
            vertical-align: top;
            text-align: center;
        }
        
        .hotels-table .col-hotel {
            width: auto;
            max-width: 100%;
            padding: 0.75rem 0.65rem;
            overflow: visible;
        }

        .hotel-name {
            color: #0f172a;
            font-weight: 700;
            font-size: 0.88rem;
            line-height: 1.35;
            max-width: 100%;
            white-space: normal;
            overflow-wrap: break-word;
            word-break: break-word;
            display: block;
            overflow: visible;
        }
        
        .hotel-name a,
        .open-chart-link {
            color: #0f172a !important;
            text-decoration: none;
            transition: var(--transition-fast);
        }
        
        .hotel-name a:hover,
        .open-chart-link:hover {
            color: #0284c7 !important;
            text-decoration: underline;
        }

        .dark-theme .hotel-name,
        .dark-theme .hotel-name a,
        .dark-theme .open-chart-link {
            color: #f1f5f9 !important;
        }
        .dark-theme .hotel-name a:hover,
        .dark-theme .open-chart-link:hover {
            color: #38bdf8 !important;
        }

        .watchlist-star-btn {
            background: none;
            border: none;
            color: #94a3b8;
            cursor: pointer;
            font-size: 0.95rem;
            margin-right: 6px;
            padding: 0;
            vertical-align: middle;
            transition: color 0.15s ease;
        }
        .watchlist-star-btn:hover {
            color: #f59e0b;
        }

        .arrival-hub {
            font-weight: 700;
            font-size: 0.86rem;
            color: #0f172a;
            white-space: nowrap;
        }
        .dark-theme .arrival-hub {
            color: #f1f5f9;
        }

        .deal-cell-inline {
            display: inline-block;
            white-space: nowrap;
            line-height: 1.25;
            font-size: 0.82rem;
        }

        .deal-cell-inline .deal-conf-short {
            opacity: 0.6;
            font-size: 0.7rem;
            font-weight: 500;
            margin-left: 0.1rem;
        }

        .hotels-table .col-w-deal-td {
            font-size: 0.78rem;
        }

        .hotels-table .col-w-dur-td {
            font-size: 0.78rem;
        }

        .col-dates {
            font-size: 0.82rem;
            font-variant-numeric: tabular-nums;
        }

        .col-duration {
            font-size: 0.82rem;
        }
        
        .price {
            font-weight: 800;
            font-size: 1.05rem;
            color: var(--success-color);
            white-space: nowrap;
        }


        
        .airport {
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--text-color);
            background: #f0f9ff;
            border-radius: var(--radius-sm);
            padding: 0.5rem;
            text-align: center;
        }
        
        .alternatives {
            font-size: 0.8rem;
            max-width: 200px;
        }
        
        .alternatives-container {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }
        
        .airport-alt {
            background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
            border: 1px solid #16a34a;
            border-radius: var(--radius-sm);
            padding: 0.5rem;
            margin: 0.125rem 0;
            cursor: pointer;
            transition: var(--transition-fast);
        }
        
        .airport-alt:hover {
            background: linear-gradient(135deg, #bbf7d0 0%, #86efac 100%);
            transform: translateY(-1px);
            box-shadow: var(--shadow-sm);
        }
        
        .airport-alt small {
            color: #15803d;
            font-weight: 600;
        }
        
        .hotels-table .delta {
            font-weight: 700;
            font-size: 0.8rem;
            padding: 0.18rem 0.4rem;
            border-radius: var(--radius-sm);
            display: inline-block;
            white-space: nowrap;
            line-height: 1.15;
            text-align: center;
            box-sizing: border-box;
        }

        .hotels-table .col-w-davg-td,
        .hotels-table .col-w-d48-td {
            font-size: 0.78rem;
        }

        .delta {
            font-weight: 700;
            font-size: 0.9rem;
            padding: 0.25rem 0.5rem;
            border-radius: var(--radius-sm);
            display: inline-block;
            min-width: 3rem;
            text-align: center;
        }
        
        .delta.up {
            background: #fff1f2;
            color: #be123c;
            border: 1px solid #fecdd3;
            border-radius: 999px;
            padding: 0.15rem 0.6rem;
            font-size: 0.78rem;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        
        .delta.down {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
            border-radius: 999px;
            padding: 0.15rem 0.6rem;
            font-size: 0.78rem;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        
        .delta.flat {
            background: #f1f5f9;
            color: #94a3b8;
            border-radius: 999px;
            padding: 0.15rem 0.6rem;
            min-width: 2.2rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.78rem;
            font-weight: 600;
        }
        
        .offer-link {
            color: var(--primary-color);
            text-decoration: none;
            font-size: 1.2rem;
            padding: 0.5rem 0.75rem;
            background: var(--gradient-card);
            border-radius: var(--radius-md);
            border: 1px solid #e2e8f0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition-normal);
            box-shadow: var(--shadow-sm);
        }
        
        .offer-link:hover {
            background: var(--gradient-primary);
            color: white;
            transform: scale(1.1);
            box-shadow: var(--shadow-md);
            text-decoration: none;
        }
        
        .offer-link-cell {
            text-align: center;
            width: 80px;
        }
        
        /* Пагинация */
        .pagination {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 0.5rem;
            margin-top: 2rem;
            padding: 1rem;
        }
        
        .pagination button {
            padding: 0.5rem 1rem;
            border: 1px solid #e2e8f0;
            background: white;
            color: #64748b;
            border-radius: var(--radius-md);
            cursor: pointer;
            transition: var(--transition-fast);
            font-weight: 600;
        }
        
        .pagination button:hover:not(:disabled) {
            background: var(--gradient-primary);
            color: white;
            border-color: transparent;
        }
        
        .pagination button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .pagination button.active {
            background: var(--gradient-primary);
            color: white;
            border-color: transparent;
        }
        
        .pagination-info {
            color: #64748b;
            font-size: 0.875rem;
            margin: 0 1rem;
        }
        
        /* Фильтры */
        .table-filters {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .filter-input {
            padding: 0.75rem 1rem;
            border: 1px solid #e2e8f0;
            border-radius: var(--radius-md);
            background: white;
            font-size: 0.875rem;
            transition: var(--transition-fast);
            min-width: 200px;
        }
        
        .filter-input:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }
        
        .filter-select {
            padding: 0.75rem 1rem;
            border: 1px solid #e2e8f0;
            border-radius: var(--radius-md);
            background: white;
            font-size: 0.875rem;
            cursor: pointer;
            transition: var(--transition-fast);
        }
        
        .filter-select:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }

        .mobile-sort-bar {
            display: none;
        }
        
        /* Sidebar Navigation */
        .app-topbar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 52px;
            z-index: 1002;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 0.75rem;
            background: rgba(255,255,255,0.94);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid var(--border-soft);
        }

        .dark-theme .app-topbar {
            background: rgba(15, 23, 42, 0.94);
            border-bottom-color: #334155;
        }

        .sidebar {
            position: fixed;
            top: 52px;
            left: 0;
            width: 220px;
            height: calc(100vh - 52px);
            background: rgba(255,255,255,.92);
            backdrop-filter: blur(18px);
            box-shadow: var(--shadow-xl);
            z-index: 1000;
            transform: translateX(-100%);
            transition: var(--transition-normal);
            overflow-y: auto;
        }
        
        .sidebar.open {
            transform: translateX(0);
        }
        
        .sidebar-header {
            padding: 0.65rem 0.85rem;
            border-bottom: 1px solid #e2e8f0;
            background: var(--gradient-primary);
            color: white;
        }
        
        .sidebar-header h2 {
            margin: 0;
            font-size: 0.92rem;
            font-weight: 800;
            letter-spacing: .01em;
        }
        
        .sidebar-nav {
            padding: 0.35rem 0 0.5rem;
        }
        
        .nav-item {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.42rem 0.85rem;
            color: var(--text-muted);
            text-decoration: none;
            transition: var(--transition-fast);
            border-left: 3px solid transparent;
            margin: 1px 6px 1px 0;
            border-radius: 0 8px 8px 0;
        }

        .nav-group-label {
            padding: 0.55rem 0.85rem 0.18rem;
            font-size: 0.92rem;
            font-weight: 700;
            letter-spacing: .01em;
            color: #334155;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .nav-group-label span:first-child {
            font-size: 1.35rem;
            line-height: 1;
        }
        
        .dark-theme .nav-group-label {
            color: #cbd5e1;
        }

        .nav-group-label {
            padding: .85rem 1.5rem .35rem;
            font-size: .68rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            color: #94a3b8;
            display: flex;
            align-items: center;
            gap: .4rem;
        }
        
        .nav-item:hover {
            background: rgba(79,70,229,.08);
            color: var(--primary-color);
            border-left-color: var(--primary-color);
        }
        
        .nav-item.active {
            background: linear-gradient(90deg, #f0f9ff 0%, #e0f2fe 100%);
            color: var(--primary-color);
            border-left-color: var(--primary-color);
            font-weight: 700;
        }
        
        .nav-item .flag {
            font-size: 0.95rem;
            width: 1.1rem;
            text-align: center;
            flex-shrink: 0;
        }
        
        .nav-item .country-name {
            font-weight: 600;
            font-size: 0.82rem;
            line-height: 1.25;
        }
        
        .nav-group-archived {
            margin-top: 0.75rem;
            padding-top: 0.6rem;
            border-top: 1px dashed rgba(148,163,184,.35);
        }
        .nav-item-archived {
            opacity: 0.85;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .nav-item-archived:hover {
            opacity: 1;
        }
        .nav-archived-tag {
            font-size: 0.62rem;
            font-weight: 700;
            padding: 1px 5px;
            border-radius: 4px;
            background: rgba(148,163,184,.2);
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: .04em;
        }
        .dark-theme .nav-archived-tag {
            color: #94a3b8;
            background: rgba(148,163,184,.15);
        }
        
        .sidebar-toggle {
            position: static;
            background: var(--gradient-primary);
            border: none;
            border-radius: 10px;
            width: 2.25rem;
            height: 2.25rem;
            color: white;
            cursor: pointer;
            box-shadow: var(--shadow-sm);
            transition: var(--transition-normal);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1rem;
            flex-shrink: 0;
        }
        
        .sidebar-toggle:hover {
            transform: scale(1.05);
            box-shadow: var(--shadow-xl);
        }
        
        .sidebar-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 999;
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transition: var(--transition-normal);
        }
        
        .sidebar-overlay.open {
            opacity: 1;
            visibility: visible;
            pointer-events: auto;
        }
        
        .main-content {
            transition: var(--transition-normal);
            margin-left: 0;
            padding-top: 52px;
        }
        
        .main-content.sidebar-open {
            margin-left: 220px;
        }
        
        /* Responsive */
        @media (max-width: 1024px) {
            :root {
                --container-padding: 1.25rem;
                --page-gutter: 1rem;
            }
            .header {
                padding: 2rem 1.25rem;
            }
            .header h1 {
                font-size: 2.25rem;
            }
            .metrics {
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            }
            .changes-section {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 768px) {
            :root {
                --section-gap: 1.25rem;
                --section-inner-x: 1rem;
                --panel-shell-radius: 12px;
                --table-block-max-width: 100%;
                --container-padding: 1rem;
                --page-gutter: .75rem;
            }
            .sidebar {
                width: 100%;
            }
            
            .main-content.sidebar-open {
                margin-left: 0;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .metrics {
                grid-template-columns: 1fr;
            }
            .metrics.metrics-compact {
                gap: .5rem;
            }
            .metrics.metrics-compact .metric {
                min-height: 50px;
            }
            .metric {
                padding: 1.25rem;
            }
            .metric-value {
                font-size: 2rem;
            }
            
            .table-filters {
                flex-direction: column;
                align-items: stretch;
            }
            .mobile-sort-bar {
                display: flex;
                flex-direction: column;
                gap: .45rem;
                margin: 0 0 1rem;
            }
            .mobile-sort-bar-label {
                font-size: .78rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: .03em;
                color: var(--text-muted);
            }
            .mobile-sort-controls {
                display: flex;
                gap: .5rem;
                align-items: stretch;
            }
            .mobile-sort-select {
                flex: 1;
                min-width: 0;
                min-height: 44px;
            }
            .mobile-sort-dir-btn {
                flex: 0 0 44px;
                min-height: 44px;
                padding: 0;
                border: 1px solid #e2e8f0;
                border-radius: var(--radius-md);
                background: white;
                font-size: 1.1rem;
                font-weight: 700;
                line-height: 1;
                cursor: pointer;
                color: var(--primary-color);
                transition: var(--transition-fast);
            }
            .mobile-sort-dir-btn:disabled {
                opacity: .45;
                cursor: default;
            }
            .mobile-sort-dir-btn:not(:disabled):hover {
                border-color: var(--primary-color);
                background: rgba(79,70,229,.06);
            }
            .dark-theme .mobile-sort-dir-btn {
                background: rgba(30,41,59,.85);
                border-color: rgba(148,163,184,.35);
                color: #93c5fd;
            }
            
            .filter-input, .filter-select {
                min-width: auto;
            }
            .hotels-section, .avg-top10-section, .trend-index-section, .alerts-section {
                padding: 1rem;
                border-radius: 14px;
            }
            .hotels-section.full-width-table-section {
                padding: 1rem;
            }
            .hotels-section.full-width-table-section h3,
            .hotels-section.full-width-table-section .deal-legend,
            .hotels-section.full-width-table-section .table-filters,
            .hotels-section.full-width-table-section .pagination,
            .hotels-section.full-width-table-section .pagination-info {
                margin-left: 0;
                margin-right: 0;
            }
            .hotels-table th, .hotels-table td {
                padding: .7rem .55rem;
                font-size: .82rem;
            }
            .table-container--hotels {
                overflow: visible;
                background: transparent;
                border: none;
                box-shadow: none;
            }
            #hotelsTable {
                width: 100%;
                min-width: 0;
                table-layout: auto;
            }
            #hotelsTable thead,
            #hotelsTable colgroup {
                display: none;
            }
            #hotelsTable tbody tr {
                display: block;
                background: rgba(255,255,255,.96);
                border: 1px solid var(--border-soft);
                border-radius: 12px;
                margin-bottom: .65rem;
                padding: .55rem .75rem;
                box-shadow: var(--shadow-sm);
            }
            #hotelsTable tbody tr:hover {
                transform: none;
                box-shadow: var(--shadow-md);
            }
            #hotelsTable tbody td {
                display: grid;
                grid-template-columns: minmax(5.2rem, 32%) 1fr;
                gap: .25rem .55rem;
                align-items: start;
                padding: .4rem 0;
                border: none;
                white-space: normal;
                text-align: left;
            }
            #hotelsTable tbody td::before {
                content: attr(data-label);
                font-size: .7rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: .03em;
                color: var(--text-muted);
                line-height: 1.35;
            }
            #hotelsTable tbody td.col-hide-sm {
                display: none;
            }
            #hotelsTable tbody td.col-hotel {
                display: block;
                padding: 0 0 .5rem;
                margin-bottom: .4rem;
                border-bottom: 1px solid rgba(226,232,240,.95);
            }
            #hotelsTable tbody td.col-hotel::before {
                display: none;
            }
            #hotelsTable tbody td.col-hotel .hotel-hover-link {
                font-size: 1rem;
                font-weight: 700;
                line-height: 1.25;
            }
            #hotelsTable tbody td.price .price-main {
                font-size: 1.05rem;
            }
            #hotelsTable tbody td.offer-link-cell {
                padding-top: .15rem;
            }
            #hotelsTable tbody td.offer-link-cell::before {
                align-self: center;
            }
            .hover-thumb {
                display: none !important;
            }
            .table-scroll-hint {
                display: none;
            }
            .table-container {
                border-radius: var(--panel-shell-radius);
            }
            .footer {
                font-size: .84rem;
                padding: 14px;
            }
            .alert-card-actions {
                flex-direction: column;
            }
            .alert-history-row {
                grid-template-columns: auto minmax(0, 1fr);
                grid-template-rows: auto auto;
                gap: .25rem .45rem;
            }
            .alert-history-price {
                grid-column: 2;
                text-align: left;
            }
            .alert-history-links {
                grid-column: 2;
                justify-content: flex-start;
            }
            .alerts-header {
                flex-direction: column;
                align-items: stretch;
            }
            .alerts-grid {
                grid-template-columns: 1fr;
            }
            .hero {
                min-height: 180px;
            }
            details.dashboard-fold > summary {
                padding: .72rem .85rem;
                font-size: .94rem;
            }
            .fold-title-meta {
                display: none;
            }
            .fold-content {
                padding: 0 .85rem .8rem;
            }
            .hero-kpis {
                grid-template-columns: repeat(2, minmax(0,1fr));
            }
            .cards-grid {
                grid-template-columns: 1fr;
            }
            .hotel-card-img {
                height: 106px;
            }
            .mode-switch {
                width: 100%;
                justify-content: space-between;
            }
            #modeSwitchRow.table-toolbar {
                flex-direction: column;
                align-items: stretch;
                gap: .45rem;
            }
            #modeSwitchRow .table-mode-switch {
                transform: none;
                width: 100%;
            }
            #modeSwitchRow .mode-btn {
                min-height: 44px;
                padding: .5rem 1rem;
            }
            .table-header-row {
                flex-direction: column;
                align-items: stretch;
                gap: .55rem;
            }
            .table-toolbar {
                margin-left: 0;
                width: 100%;
                justify-content: space-between;
            }
            .departure-modal {
                padding: .5rem;
                align-items: flex-end;
            }
            .departure-modal-dialog {
                width: 100%;
                max-height: 92vh;
                border-radius: 16px 16px 0 0;
            }
            .departure-modal-chart {
                width: calc(100% - 1.4rem);
                height: 240px;
                min-height: 240px;
                margin: 0 .7rem 10px;
            }
            .departure-offers-table {
                min-width: 460px;
            }
            .mode-btn {
                flex: 1;
            }
        }

        @media (max-width: 480px) {
            :root {
                --container-padding: .75rem;
                --page-gutter: .5rem;
            }
            .container {
                border-radius: 14px;
            }
            .header {
                border-radius: 14px;
                margin-bottom: 1.25rem;
            }
            .header h1 {
                font-size: 1.45rem;
                line-height: 1.2;
            }
            .header p {
                font-size: .9rem;
            }
            .hero-content {
                padding: 1rem .9rem;
            }
            .hero-kpis {
                grid-template-columns: 1fr;
            }
            .pagination {
                flex-wrap: wrap;
                gap: .35rem;
                padding: .75rem .5rem;
            }
            .pagination button {
                padding: .45rem .75rem;
                font-size: .82rem;
            }
            .country-flag {
                font-size: 1.35rem;
                margin-right: .35rem;
            }
            .hover-thumb {
                width: 180px;
                height: 118px;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            * {
                animation: none !important;
                transition: none !important;
            }
        }
        
        /* Country Flags */
        .country-flag {
            font-size: 2rem;
            margin-right: 0.5rem;
            display: inline-block;
            vertical-align: middle;
        }
        
        .header .country-flag {
            font-size: 3rem;
            margin-right: 1rem;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        /* Hover preview */
        .hover-thumb { position: absolute; display: none; width: 240px; height: 160px; background: #fff; border: 1px solid #ddd; box-shadow: 0 2px 8px rgba(0,0,0,.15); border-radius: 6px; padding: 4px; z-index: 9999; }
        .hover-thumb img { width: 100%; height: 100%; object-fit: cover; border-radius: 4px; }
        
        /* Watchlist Star Button */
        .watchlist-star-btn {
            background: none;
            border: none;
            color: #94a3b8;
            font-size: 1.25rem;
            cursor: pointer;
            padding: 0 4px;
            transition: transform 0.2s ease, color 0.2s ease;
            vertical-align: middle;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            outline: none;
        }
        .watchlist-star-btn:hover {
            transform: scale(1.25);
            color: #f59e0b;
        }
        .watchlist-star-btn.starred {
            color: #f59e0b;
        }
        
        .hotel-card-img {
            position: relative;
        }
        .watchlist-star-btn.card-star {
            position: absolute;
            top: 8px;
            right: 8px;
            background: rgba(255, 255, 255, 0.75);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            border-radius: 50%;
            width: 32px;
            height: 32px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            z-index: 10;
            padding: 0;
            color: #94a3b8;
        }
        .watchlist-star-btn.card-star.starred {
            color: #f59e0b;
            background: rgba(255, 255, 255, 0.9);
        }
        .dark-theme .watchlist-star-btn.card-star {
            background: rgba(15, 23, 42, 0.75);
            color: #64748b;
        }
        .dark-theme .watchlist-star-btn.card-star.starred {
            background: rgba(15, 23, 42, 0.9);
            color: #f59e0b;
        }

        /* Price Forecast Pills */
        .forecast-pill {
            display: inline-flex;
            align-items: center;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 12px;
            text-transform: uppercase;
            letter-spacing: 0.025em;
            white-space: nowrap;
            width: fit-content;
        }
        .forecast-buy {
            background-color: #dcfce7;
            color: #15803d;
        }
        .forecast-wait {
            background-color: #fef9c3;
            color: #a16207;
        }
        .forecast-expensive {
            background-color: #fee2e2;
            color: #b91c1c;
        }
        .forecast-nodata {
            background-color: #f1f5f9;
            color: #475569;
        }
        
        .dark-theme .forecast-buy {
            background-color: rgba(21, 128, 61, 0.2);
            color: #4ade80;
        }
        .dark-theme .forecast-wait {
            background-color: rgba(161, 98, 7, 0.2);
            color: #facc15;
        }
        .dark-theme .forecast-expensive {
            background-color: rgba(185, 28, 28, 0.2);
            color: #f87171;
        }
        .dark-theme .forecast-nodata {
            background-color: rgba(71, 85, 105, 0.2);
            color: #94a3b8;
        }

        /* Calendar Heatmap Section */
        .calendar-section h3 {
            margin-top: 0;
            margin-bottom: 0.25rem;
            font-size: 1.1rem;
            color: var(--text-primary);
        }
        .calendar-month-container {
            margin-bottom: 1.5rem;
            background: rgba(255,255,255,0.7);
            border-radius: var(--radius-md);
            padding: 1rem;
            border: 1px solid var(--border-soft);
        }
        .dark-theme .calendar-month-container {
            background: rgba(15, 23, 42, 0.4);
        }
        .calendar-month-title {
            font-size: 0.95rem;
            font-weight: 700;
            margin-bottom: 0.75rem;
            text-transform: capitalize;
            color: var(--text-primary);
            border-left: 3px solid var(--color-primary);
            padding-left: 8px;
        }
        .calendar-grid-container {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 6px;
            min-width: 280px;
        }
        .calendar-day-header {
            text-align: center;
            font-weight: 700;
            font-size: 0.75rem;
            color: var(--text-secondary);
            padding: 4px 0;
            text-transform: uppercase;
        }
        .calendar-day-cell {
            aspect-ratio: 1.25;
            border-radius: var(--radius-sm);
            padding: 6px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            font-size: 0.7rem;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid var(--border-soft);
            position: relative;
            background-color: var(--panel-bg);
            color: var(--text-primary);
        }
        @media (max-width: 600px) {
            .calendar-day-cell {
                aspect-ratio: 1;
                padding: 4px;
            }
        }
        .calendar-day-cell:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            border-color: var(--color-primary);
        }
        .calendar-day-cell.empty {
            background: rgba(241, 245, 249, 0.5) !important;
            color: #cbd5e1;
            cursor: default;
            border: 1px dashed var(--border-soft);
        }
        .dark-theme .calendar-day-cell.empty {
            background: rgba(30, 41, 59, 0.3) !important;
            color: #475569;
        }
        .calendar-day-cell.empty:hover {
            transform: none;
            box-shadow: none;
            border-color: var(--border-soft);
        }
        .calendar-day-number {
            font-weight: 700;
        }
        .calendar-day-price {
            font-weight: 800;
            align-self: flex-end;
            font-size: 0.75rem;
        }
        .calendar-day-cell.selected {
            box-shadow: 0 0 0 3px var(--color-primary) !important;
            border-color: var(--color-primary) !important;
        }
        {passport_css}
"""
    return f"""    <style>
{css_content}
        {passport_css}
    </style>"""
