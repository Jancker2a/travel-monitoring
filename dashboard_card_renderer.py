#!/usr/bin/env python3
"""Hotel cards, top movers, and metric card renderers for the travel dashboard."""

from __future__ import annotations

import html as html_lib
from typing import Any, Dict, List, Optional, Tuple

from dashboard_data_pipeline import _hotel_chart_viewer_href, slugify


def _metric_card(value_html: Any, label: str, tip: str = "") -> str:
    """Generates an HTML markup snippet for a KPI metric box."""
    tip_attr = f' title="{html_lib.escape(tip)}"' if tip else ""
    tip_cls = " metric-tip" if tip else ""
    return (
        f'<div class="metric{tip_cls}"{tip_attr}>'
        f'<div class="metric-value">{value_html}</div>'
        f'<div class="metric-label">{html_lib.escape(label)}</div>'
        f'</div>'
    )


def _render_top_movers_html(decreases_48h: list, increases_48h: list, slugify_fn, filter_data_id: str) -> str:
    """Генерирует виджет Top Movers (топ снижений и роста цен за 48 часов)."""
    if not decreases_48h and not increases_48h:
        return ""

    def _render_list(items, is_drop=True):
        if not items:
            return '<div class="top-mover-empty">За последние 48ч изменения цен не зафиксированы</div>'
        rows = []
        for item in items[:3]:
            hotel_name = html_lib.escape(str(item['hotel_name']))
            slug = slugify_fn(item['hotel_name'])
            href = _hotel_chart_viewer_href(filter_data_id, slug)
            old_p = float(item['old_price'])
            new_p = float(item['new_price'])
            pct = float(item['change_percent'])
            cls = 'drop' if is_drop else 'up'
            sign = '' if pct < 0 else '+'
            arrow = '↓' if is_drop else '↑'
            rows.append(
                f'<a href="{href}" onclick="if(window.openHotelPassport){{window.openHotelPassport(\'{slug}\'); return false;}}" class="top-mover-item" title="Открыть паспорт отеля">'
                f'<span class="top-mover-name" title="{hotel_name}">{hotel_name}</span>'
                f'<span class="top-mover-prices">{old_p:.0f} → <strong>{new_p:.0f} PLN</strong></span>'
                f'<span class="top-mover-badge {cls}">{arrow} {sign}{pct:.1f}%</span>'
                f'</a>'
            )
        return "".join(rows)

    drops_html = _render_list(decreases_48h, is_drop=True)
    rises_html = _render_list(increases_48h, is_drop=False)

    return f"""
        <div class="top-movers-section">
            <div class="top-movers-head">
                <h3>📊 Динамика цен за 48 часов (Top Movers)</h3>
                <span class="top-movers-sub">Отели с наибольшим изменением стоимости</span>
            </div>
            <div class="top-movers-grid">
                <div class="top-movers-card top-movers-card--drops">
                    <div class="top-movers-card-title">📉 Лидеры снижения цены</div>
                    <div class="top-movers-list">{drops_html}</div>
                </div>
                <div class="top-movers-card top-movers-card--rises">
                    <div class="top-movers-card-title">📈 Лидеры роста цены</div>
                    <div class="top-movers-list">{rises_html}</div>
                </div>
            </div>
        </div>
    """
