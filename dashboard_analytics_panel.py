#!/usr/bin/env python3
"""Analytics panel, early booking, AI briefing, alerts, and hotel chart page renderers."""

from __future__ import annotations

import html as html_lib
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo

import pandas as pd

from dashboard_data_pipeline import (
    _break_series_at_data_gaps,
    _hotel_chart_viewer_href,
    _hotel_series_payload_hash,
    _load_hotel_series_manifest,
    _lowest_price_row,
    _parse_price_ceiling,
    _price_plateau_segments,
    _resolve_history_ceiling,
    _save_hotel_series_manifest,
    _table_deal_badge_compact,
    _time_weighted_price_baseline,
    _time_weighted_price_quantile,
    slugify,
)
from filter_registry import active_filter_id
from filter_trip import _duration_bucket_is_missing
from hotel_deal_score import comeback_from_premium

def render_ai_market_briefing_html(
    oracle_report: Optional[Dict[str, Any]],
    filter_title: str = "",
    hotel_meta_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Renders the Executive AI Market Intelligence Briefing fold."""
    if not oracle_report or "macro_briefing" not in oracle_report:
        return ""
    macro = oracle_report.get("macro_briefing", {})
    headline = html_lib.escape(str(macro.get("headline", "AI Market Intelligence")))
    phase = html_lib.escape(str(macro.get("market_phase", "")))
    dynamics = html_lib.escape(str(macro.get("charter_dynamics", "")))
    floor_status = html_lib.escape(str(macro.get("floor_status", "")))
    directive = html_lib.escape(str(macro.get("strategic_directive", "")))
    synthesized_by = html_lib.escape(str(macro.get("synthesized_by", "AI Engine")))
    display_title = html_lib.escape(str(filter_title or macro.get("filter_title", "")))

    anomalies_html = ""
    for a in macro.get("key_anomalies", []):
        t_title = html_lib.escape(str(a.get("title", "")))
        t_text = html_lib.escape(str(a.get("text", "")))
        anomalies_html += (
            f'<div class="ai-anomaly-tag">'
            f'<strong>{t_title}:</strong> <span>{t_text}</span>'
            f'</div>'
        )

    floor_badge_html = ""
    if floor_status:
        floor_badge_html = (
            f'<div class="ai-floor-badge">'
            f'<span>📊</span> <span>{floor_status}</span>'
            f'</div>'
        )

    phase_badge_html = ""
    if phase:
        phase_badge_html = f'<span class="ai-phase-badge">{phase}</span>'

    filter_info_html = ""
    if display_title:
        filter_info_html = f'<span class="ai-filter-title">{display_title}</span> • '

    # Feature: «Если покупать сейчас, то стоит выбрать из...»
    buy_rec = macro.get("buy_now_recommendation", {})
    buy_now_html = ""
    if buy_rec:
        has_deals = buy_rec.get("has_worthy_deals", False)
        rec_headline = html_lib.escape(str(buy_rec.get("headline", "")))
        rec_advice = html_lib.escape(str(buy_rec.get("advice", "")))
        rec_status = html_lib.escape(str(buy_rec.get("status_badge", "")))
        top_picks = buy_rec.get("top_picks", [])

        if has_deals and top_picks:
            picks_items_html = ""
            for p in top_picks:
                h_name = str(p.get("hotel_name", ""))
                meta = (hotel_meta_by_name or {}).get(h_name, {})
                h_price = float(p.get("price") or meta.get("price") or 0.0)

                # Fallback 1: case-insensitive or partial match in hotel_meta_by_name
                if h_price <= 0.0 and hotel_meta_by_name:
                    h_lower = h_name.strip().lower()
                    for k, v in hotel_meta_by_name.items():
                        k_lower = k.strip().lower()
                        if h_lower == k_lower or h_lower in k_lower or k_lower in h_lower:
                            cand_p = float(v.get("price") or 0.0)
                            if cand_p > 0.0:
                                h_price = cand_p
                                if not meta:
                                    meta = v
                                break

                # Fallback 2: parse price directly from why_buy text (e.g. "Цена 2,944 zł...")
                if h_price <= 0.0:
                    m_p = re.search(r"(?:цена|за|всего)?\s*([0-9][0-9\s,.]*)\s*zł", str(p.get("why_buy", "")), re.IGNORECASE)
                    if m_p:
                        try:
                            clean_str = m_p.group(1).replace(" ", "").replace("\xa0", "").replace(",", "")
                            if "." in clean_str and len(clean_str.split(".")[-1]) == 3:
                                clean_str = clean_str.replace(".", "")
                            val_p = float(clean_str)
                            if val_p >= 500.0:
                                h_price = val_p
                        except (ValueError, TypeError):
                            pass

                h_slug = slugify(h_name)
                h_badge = html_lib.escape(str(p.get("badge", "🟢 Выгодно")))
                h_why = html_lib.escape(str(p.get("why_buy", "")))
                offer_url = meta.get("offer_url") or p.get("offer_url", "")
                chart_href = meta.get("chart_href", "")

                chart_btn = f'<a href="{html_lib.escape(chart_href, quote=True)}" onclick="if(window.openHotelPassport){{window.openHotelPassport(\'{h_slug}\'); return false;}}" class="ai-pick-btn ai-pick-btn--chart">Паспорт отеля 📊</a>'
                offer_btn = f'<a href="{html_lib.escape(offer_url, quote=True)}" target="_blank" rel="noopener" class="ai-pick-btn ai-pick-btn--offer">Купить ↗</a>' if offer_url else ''
                price_badge_html = f'<span class="ai-pick-price">{h_price:,.0f} zł</span>' if h_price > 0.0 else ''

                picks_items_html += f"""
                    <div class="ai-pick-card" style="cursor:pointer;" onclick="if(event.target.tagName!=='A'&&event.target.tagName!=='BUTTON'&&window.openHotelPassport){{window.openHotelPassport('{h_slug}');}}">
                        <div class="ai-pick-header">
                            <span class="ai-pick-name">{html_lib.escape(h_name)}</span>
                            {price_badge_html}
                        </div>
                        <div class="ai-pick-meta">
                            <span class="ai-pick-badge">{h_badge}</span>
                            <span class="ai-pick-why">{h_why}</span>
                        </div>
                        <div class="ai-pick-actions">
                            {chart_btn}
                            {offer_btn}
                        </div>
                    </div>
                """

            buy_now_html = f"""
                <div class="ai-buy-now-box ai-buy-now--active">
                    <div class="ai-buy-now-header">
                        <div class="ai-buy-now-title-group">
                            <span class="ai-buy-now-icon">🛒</span>
                            <div class="ai-buy-now-titles">
                                <span class="ai-buy-now-kicker">Если покупать сейчас:</span>
                                <strong class="ai-buy-now-heading">{rec_headline}</strong>
                            </div>
                        </div>
                        <span class="ai-buy-now-pill pill--active">{rec_status or "🟢 ЕСТЬ ВЫГОДНЫЕ ВАРИАНТЫ"}</span>
                    </div>
                    {f'<div class="ai-buy-now-advice">{rec_advice}</div>' if rec_advice else ''}
                    <div class="ai-picks-grid">
                        {picks_items_html}
                    </div>
                </div>
            """
        else:
            buy_now_html = f"""
                <div class="ai-buy-now-box ai-buy-now--wait">
                    <div class="ai-buy-now-header">
                        <div class="ai-buy-now-title-group">
                            <span class="ai-buy-now-icon">✋</span>
                            <div class="ai-buy-now-titles">
                                <span class="ai-buy-now-kicker">Если покупать сейчас:</span>
                                <strong class="ai-buy-now-heading">{rec_headline or "Лучше ничего не покупать — подождите"}</strong>
                            </div>
                        </div>
                        <span class="ai-buy-now-pill pill--wait">{rec_status or "⏳ ВЫГОДНЫХ СДЕЛОК НЕТ"}</span>
                    </div>
                    <div class="ai-buy-now-advice">
                        {rec_advice or "Сейчас на рынке нет действительно выгодных предложений: отели продаются по базовым или завышенным ценам. Спешить с бронированием нет смысла — сохраните отели в «Избранное» (☆) и подождите приближения вылета (за 7–10 дней туроператоры обычно начинают снижать цены)."}
                    </div>
                </div>
            """

    return f"""
        <!-- --- AI Market Intelligence Briefing (Executive Dashboard Fold) --- -->
        <details class="dashboard-fold ai-oracle-fold" id="aiOracleFold" open>
            <summary>
                <div style="display: flex; align-items: center; gap: 0.85rem;">
                    <div class="ai-oracle-icon-box">
                        <span>🧠</span>
                    </div>
                    <div class="ai-oracle-title-wrap">
                        <div class="ai-oracle-title-row">
                            <span class="ai-oracle-main-title">AI-анализ рынка и прогноз цен</span>
                            {phase_badge_html}
                        </div>
                        <div class="ai-oracle-subtitle">
                            <strong class="ai-oracle-headline">{headline}</strong> • {filter_info_html}<span>{synthesized_by}</span>
                        </div>
                    </div>
                </div>
                <span class="fold-chevron" style="color: #7c3aed; font-size: 1.15rem; font-weight: 700;">⌄</span>
            </summary>
            <div class="fold-content" style="padding: 1.25rem;">
                <div class="ai-oracle-grid">
                    <div class="ai-card-pulse">
                        <div class="ai-card-header-purple">
                            <span>✈️</span> <span>Что происходит с рейсами и ценами</span>
                        </div>
                        <div class="ai-card-body">{dynamics}</div>
                        {floor_badge_html}
                    </div>
                    <div class="ai-card-directive">
                        <div class="ai-card-header-green">
                            <span>🎯</span> <span>Совет: брать сейчас или подождать</span>
                        </div>
                        <div class="ai-card-body-green">{directive}</div>
                    </div>
                </div>
                {buy_now_html}
                {f'<div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem;">{anomalies_html}</div>' if anomalies_html else ''}
            </div>
        </details>
    """


# Официальный logomark TripAdvisor (owl), cropped from TA_logo_primary.svg (tacdn.com).
TRIPADVISOR_HEADER_ICON_HTML = (
    '<span class="th-ta-icon" aria-hidden="true">'
    '<svg class="th-ta-svg" viewBox="0 0 50 30" xmlns="http://www.w3.org/2000/svg">'
    '<path fill="#FAC415" d="M8.69853,6.34985C13.42485,5.74015,26.834,5.32015,23.16029,24.69632l4.16692-.339C25.50191,12.41381,29.31986,6.324,41.25838,5.74015,21.45779-5.22456,10.18426,6.15809,8.69853,6.34985Z"/>'
    '<path fill="#fff" d="M27.13191,21.62794A11.34312,11.34312,0,1,0,33.84147,7.055,11.347,11.347,0,0,0,27.13191,21.62794Z"/>'
    '<circle fill="#fff" cx="12.62599" cy="17.65102" r="11.34537"/>'
    '<circle fill="#EE6946" cx="12.4632" cy="17.53993" r="2.0971"/>'
    '<circle fill="#00AF87" cx="37.74486" cy="17.53993" r="2.09618"/>'
    '<path fill="#000" d="M47.89824,10.18a16.25082,16.25082,0,0,1,2.48088-5.0444l-8.41926-.00647A30.65918,30.65918,0,0,0,25.14368.461,31.36745,31.36745,0,0,0,7.90015,5.18868L0,5.19309a16.3389,16.3389,0,0,1,2.46941,5.00044A12.60265,12.60265,0,0,0,22.46235,25.53426L25.14721,29.554l2.71074-4.05353A12.61369,12.61369,0,0,0,47.89824,10.18ZM37.37,5.094A12.57259,12.57259,0,0,0,25.19676,16.73368,12.6202,12.6202,0,0,0,12.87912,5.04515,31.17654,31.17654,0,0,1,25.14368,2.66044,29.67419,29.67419,0,0,1,37.37,5.094ZM12.62632,27.71926A10.06971,10.06971,0,1,1,22.695,17.652,10.08062,10.08062,0,0,1,12.62632,27.71926Zm28.63412-.57147a10.07577,10.07577,0,0,1-12.93515-5.96V21.185A10.07008,10.07008,0,1,1,41.26044,27.14779Z"/>'
    '<path fill="#000" d="M12.47059,11.3094a6.231,6.231,0,1,0,6.22191,6.23A6.24029,6.24029,0,0,0,12.47059,11.3094Zm0,10.31575a4.08509,4.08509,0,1,1,4.07706-4.08574A4.09513,4.09513,0,0,1,12.47059,21.62515Z"/>'
    '<path fill="#000" d="M37.74486,11.3094a6.231,6.231,0,1,0,6.22779,6.23A6.23822,6.23822,0,0,0,37.74486,11.3094Zm0,10.31575a4.08508,4.08508,0,1,1,4.08367-4.08574A4.091,4.091,0,0,1,37.74486,21.62515Z"/>'
    '</svg></span>'
)


def render_early_booking_section_html(eb_res: Optional[Dict[str, Any]]) -> Tuple[str, str, str]:
    """Renders the Early Booking fold with EBAS Score banner and Plotly chart slots."""
    if not eb_res or eb_res.get("error") or eb_res.get("summary", {}).get("verdict") == "INSUFFICIENT_DATA":
        empty_html = """
        <details class="dashboard-fold" id="earlyBookingFold">
            <summary>
                <span>🏷️ Анализ раннего бронирования (First Minute vs Last Minute)</span>
                <span class="fold-title-meta">Накопление данных</span>
                <span class="fold-chevron">⌄</span>
            </summary>
            <div class="fold-content" style="padding: 1rem 1.25rem;">
                <div class="timing-reco" style="background: rgba(59, 130, 246, 0.08); border-left: 4px solid #3b82f6; padding: 1rem; border-radius: 6px; margin: 0.5rem 0;">
                    💡 <strong>Накапливаем историю раннего бронирования для этого направления.</strong>
                    <p style="margin: 0.5rem 0 0 0; font-size: 0.88rem; color: #64748b;">
                        Графики когортной динамики и сравнение First Minute vs Last Minute появятся здесь автоматически при накоплении срезов цен за 60+ дней до вылета.
                    </p>
                </div>
            </div>
        </details>
        """
        return empty_html, "null", "null"

    summary = eb_res.get("summary", {})
    score = summary.get("ebas_score") or 50.0
    verdict = summary.get("verdict", "NEUTRAL")
    paired_traj = eb_res.get("paired_price_trajectory", {})
    survival = eb_res.get("survival_curve", [])

    if verdict == "EARLY_BOOKING_HIGHLY_FAVORABLE":
        v_icon = "🏆"
        v_title = "Раннее бронирование однозначно выгодно"
        v_color = "#059669"
        v_bg = "rgba(16, 185, 129, 0.08)"
        v_border = "#a7f3d0"
        badge_meta = f"Выгодно брать заранее (EBAS {score:.0f})"
        v_desc = "Цены большинства отелей растут по мере приближения к вылету, а популярные 4–5★ варианты раскупаются первыми. Ожидание горящих туров несет высокий риск распродажи."
    elif verdict == "EARLY_BOOKING_RECOMMENDED":
        v_icon = "🏷️"
        v_title = "Рекомендуется раннее бронирование"
        v_color = "#2563eb"
        v_bg = "rgba(59, 130, 246, 0.08)"
        v_border = "#bfdbfe"
        badge_meta = f"Рекомендуется FM (EBAS {score:.0f})"
        v_desc = "Умеренная экономия при бронировании в First Minute. Отели премиум-сегмента дорожают, базовый масс-маркет сохраняет стабильность."
    elif verdict == "WAIT_FOR_LAST_MINUTE":
        v_icon = "⚡"
        v_title = "Выгоднее ждать горящих туров (Last Minute)"
        v_color = "#ea580c"
        v_bg = "rgba(234, 88, 12, 0.08)"
        v_border = "#fed7aa"
        badge_meta = f"Ждать Last Minute (EBAS {score:.0f})"
        v_desc = "Направление характеризуется высокой емкостью чартеров. За 7–14 дней до вылета часто происходят масштабные сбросы цен от туроператоров."
    else:
        v_icon = "⚖️"
        v_title = "Нейтральная динамика цен"
        v_color = "#475569"
        v_bg = "rgba(100, 116, 139, 0.08)"
        v_border = "#cbd5e1"
        badge_meta = f"Нейтрально (EBAS {score:.0f})"
        v_desc = "Цены между ранним бронированием и вылетом колеблются незначительно. Покупка зависит от персональных дат отпуска."

    lm_delta = paired_traj.get("LM", {}).get("median_delta_pct")
    if lm_delta is None:
        lm_delta = paired_traj.get("LATE", {}).get("median_delta_pct")
    
    if lm_delta is not None:
        lm_text = f"+{lm_delta:.1f}%" if lm_delta > 0 else f"{lm_delta:.1f}%"
        lm_color = "#dc2626" if lm_delta > 0 else "#059669"
    else:
        lm_text = "—"
        lm_color = "#64748b"

    surv_14 = next((item["survival_rate"] for item in survival if item["d"] == 14), 0.5)
    sold_out_pct = max(0.0, min(100.0, (1.0 - surv_14) * 100.0))

    html = f"""
        <details class="dashboard-fold" id="earlyBookingFold">
            <summary>
                <span>🏷️ Анализ раннего бронирования (First Minute vs Last Minute)</span>
                <span class="fold-title-meta">{badge_meta}</span>
                <span class="fold-chevron">⌄</span>
            </summary>
            <div class="fold-content" style="padding: 1rem 1.25rem;">
                <div class="eb-score-banner" style="display:flex; flex-wrap:wrap; gap:1.25rem; align-items:center; background: {v_bg}; border: 1px solid {v_border}; padding:1.25rem; border-radius:10px; margin: 0.5rem 0 1.5rem 0;">
                    <div style="flex:1; min-width:280px;">
                        <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
                            <span style="font-size:1.75rem;">{v_icon}</span>
                            <div>
                                <div style="font-size:1.15rem; font-weight:700; color:{v_color};">{v_title}</div>
                                <div style="font-size:0.85rem; color:#64748b;">Индекс выгоды раннего бронирования (EBAS): <strong>{score:.1f} / 100</strong></div>
                            </div>
                        </div>
                        <p style="margin:0; font-size:0.9rem; line-height:1.5; color:#334155;">{v_desc}</p>
                    </div>
                    <div style="display:flex; gap:0.75rem; flex-wrap:wrap;">
                        <div style="background:rgba(255,255,255,0.85); border:1px solid rgba(0,0,0,0.06); padding:0.6rem 0.9rem; border-radius:8px; text-align:center; min-width:105px;">
                            <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase;">Когорт в базе</div>
                            <div style="font-size:1.25rem; font-weight:700; color:#1e293b;">{summary.get('total_cohorts', 0)}</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.85); border:1px solid rgba(0,0,0,0.06); padding:0.6rem 0.9rem; border-radius:8px; text-align:center; min-width:115px;">
                            <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase;">Δ к Last Minute</div>
                            <div style="font-size:1.25rem; font-weight:700; color:{lm_color};">{lm_text}</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.85); border:1px solid rgba(0,0,0,0.06); padding:0.6rem 0.9rem; border-radius:8px; text-align:center; min-width:115px;">
                            <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase;">Риск Sold Out</div>
                            <div style="font-size:1.25rem; font-weight:700; color:#e11d48;">{sold_out_pct:.0f}%</div>
                        </div>
                    </div>
                </div>

                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap:1.5rem;">
                    <div style="background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:1.25rem;">
                        <h4 style="margin:0 0 0.5rem 0; font-size:1rem; display:flex; align-items:center; gap:0.5rem;">
                            <span>📊 Парная динамика цен по горизонтам</span>
                        </h4>
                        <p style="margin:0 0 1rem 0; font-size:0.82rem; color:#64748b;">
                            Изменение цены одних и тех же отелей относительно First Minute (базис 0% на D 60–120 дней).
                        </p>
                        <div id="ebTrajectoryChart" style="height:290px;"></div>
                    </div>
                    <div style="background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:1.25rem;">
                        <h4 style="margin:0 0 0.5rem 0; font-size:1rem; display:flex; align-items:center; gap:0.5rem;">
                            <span>📉 Кривая доступности отелей (Survival Rate)</span>
                        </h4>
                        <p style="margin:0 0 1rem 0; font-size:0.82rem; color:#64748b;">
                            Доля отелей из раннего бронирования, оставшихся в наличии к моменту D дней до вылета.
                        </p>
                        <div id="ebSurvivalChart" style="height:290px;"></div>
                    </div>
                </div>
            </div>
        </details>
    """

    traj_x = []
    traj_y = []
    bucket_order = [
        ("EB", "Early Bird (>120d)"),
        ("FM", "First Minute (60-120d)"),
        ("STD", "Standard (30-60d)"),
        ("LATE", "Late (14-30d)"),
        ("LM", "Last Minute (7-14d)"),
        ("PANIC", "Panic Dump (≤7d)"),
    ]
    for b_code, b_label in bucket_order:
        b_info = paired_traj.get(b_code, {})
        val = b_info.get("median_delta_pct")
        if val is not None:
            traj_x.append(b_label)
            traj_y.append(float(val))
    
    surv_x = [int(item["d"]) for item in survival]
    surv_y = [round(float(item["survival_rate"]) * 100.0, 1) for item in survival]

    traj_json = json.dumps({"x": traj_x, "y": traj_y}, ensure_ascii=False) if traj_x else "null"
    surv_json = json.dumps({"x": surv_x, "y": surv_y}, ensure_ascii=False) if surv_x else "null"

    return html, traj_json, surv_json



def _should_show_alert(alert) -> bool:
    alert_type = alert.get('alert_type') or alert.get('type') or ''
    return alert_type != 'zone_entry'


def _hotel_base_name(name: str) -> str:
    text = str(name or "").strip()
    for marker in (" Grecja,", " Turcja,", " Grecja ", " Turcja "):
        if marker in text:
            return text.split(marker, 1)[0].strip()
    return text


def _register_chart_href(lookup: dict, hotel_name: str, href: str) -> None:
    name = str(hotel_name or "").strip()
    if not name or not href:
        return
    lookup[name] = href
    lookup[_hotel_base_name(name).lower()] = href
    slug = href.rsplit("/", 1)[-1]
    if slug.endswith(".html"):
        lookup[f"__slug__:{slug[:-5]}"] = href
    if "hotel=" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            hotel_slug = (qs.get("hotel") or [""])[0]
            if hotel_slug:
                lookup[f"__slug__:{hotel_slug}"] = href
        except Exception:
            pass


def _resolve_chart_href(hotel_name: str, lookup: dict, charts_subdir: str, slugify_fn) -> str:
    name = str(hotel_name or "").strip()
    if not name:
        return ""
    if name in lookup:
        return lookup[name]
    base = _hotel_base_name(name).lower()
    if base in lookup:
        return lookup[base]
    slug = slugify_fn(name)
    slug_key = f"__slug__:{slug}"
    if slug_key in lookup:
        return lookup[slug_key]
    sub = (charts_subdir or "").rstrip("/")
    data_id = sub.split("/")[-1] if sub else ""
    if data_id.startswith("filter_"):
        return _hotel_chart_viewer_href(data_id, slug)
    return _hotel_chart_viewer_href(active_filter_id(charts_subdir), slug)



def _alert_is_current(alert, table_prices, tolerance=2.0, scope_duration_bucket=None):
    """Alert is current if the hotel is in the last run at the alert's new price."""
    hotel_name = str(alert.get('hotel_name') or alert.get('hotel') or '')
    alert_type = alert.get('alert_type') or alert.get('type') or ''
    new_price = alert.get('new_price') if 'new_price' in alert else (alert.get('to') or alert.get('current_price'))
    if not hotel_name or alert_type == 'missing' or new_price in (None, '', 'null'):
        return False
    alert_bucket = str(alert.get('duration_bucket') or '').strip()
    if _duration_bucket_is_missing(alert_bucket):
        alert_bucket = ''
    scope_bucket = str(scope_duration_bucket or '').strip()
    if scope_bucket:
        if alert_bucket and alert_bucket != scope_bucket:
            return False
        if not alert_bucket:
            return False
    row_id = trip_row_key(hotel_name, alert_bucket or scope_bucket) if (alert_bucket or scope_bucket) else hotel_name
    candidates = []
    if row_id in table_prices:
        candidates.append(float(table_prices[row_id]))
    if not scope_bucket:
        if hotel_name in table_prices:
            candidates.append(float(table_prices[hotel_name]))
        prefix = f"{hotel_name}|"
        for key, value in table_prices.items():
            if str(key).startswith(prefix):
                candidates.append(float(value))
    if not candidates:
        return False
    try:
        target = float(new_price)
    except (TypeError, ValueError):
        return False
    return any(abs(current - target) <= tolerance for current in candidates)


def _alert_display_fields(alert, meta, slugify_fn, parse_iso_fn):
    hotel_name = str(alert.get('hotel_name') or alert.get('hotel') or 'Unknown')
    hotel_name_html = meta.get('hotel_name_html') or html_lib.escape(hotel_name)
    default_href = _hotel_chart_viewer_href(
        meta.get("filter_id") or "filter",
        slugify_fn(hotel_name),
    )
    chart_href = html_lib.escape(meta.get('chart_href') or default_href, quote=True)
    offer_url = meta.get('offer_url') or ''
    dates = meta.get('dates') or '—'
    duration = meta.get('duration') or '—'

    alert_type = alert.get('alert_type') or alert.get('type') or ''
    old_price = alert.get('old_price') or alert.get('from') or alert.get('previous_price')
    new_price = alert.get('new_price') if 'new_price' in alert else (alert.get('to') or alert.get('current_price'))
    ts_raw = alert.get('created_at') or alert.get('timestamp') or alert.get('time') or ''
    try:
        ts_fmt = parse_iso_fn(ts_raw).astimezone().strftime('%d.%m.%Y %H:%M')
    except Exception:
        ts_fmt = str(ts_raw)

    if alert_type == 'zone_entry':
        kind = 'drop'
        badge = '+'
        new_cls = 'drop'
        change_pct = float(alert.get('price_change_pct') or 0.0)
        try:
            new_fmt = f"{float(new_price):.0f}"
        except (TypeError, ValueError):
            new_fmt = str(new_price)
        try:
            old_f = float(old_price) if old_price is not None else None
            new_f = float(new_price)
            if old_f is not None and abs(old_f - new_f) > 1:
                old_fmt = f"{old_f:.0f}"
                pct_text = f'{change_pct:+.1f}%'
            else:
                old_fmt = '—'
                pct_text = ''
        except (TypeError, ValueError):
            old_fmt = '—'
            pct_text = ''
        note = 'Вошёл в зону отслеживания'
    elif alert_type == 'zone_exit':
        kind = 'up'
        badge = '↑'
        new_cls = 'up'
        change_pct = float(alert.get('price_change_pct') or 0.0)
        pct_text = f'{change_pct:+.1f}%' if change_pct else ''
        try:
            old_fmt = f"{float(old_price):.0f}"
            new_fmt = f"{float(new_price):.0f}"
        except (TypeError, ValueError):
            old_fmt = str(old_price)
            new_fmt = str(new_price)
        note = 'Вышел из зоны отслеживания'
    elif alert_type == 'missing' or new_price in (None, '', 'null'):
        kind = 'missing'
        badge = '—'
        pct_text = ''
        try:
            old_fmt = f"{float(old_price):.0f}" if old_price is not None else '—'
        except (TypeError, ValueError):
            old_fmt = str(old_price or '—')
        new_fmt = '—'
        new_cls = ''
        note = html_lib.escape(alert.get('message') or alert.get('note') or 'Исчез из выдачи')
    else:
        change_pct = float(alert.get('price_change_pct') or 0.0)
        price_change = float(alert.get('price_change') or 0.0)
        pct_text = f'{change_pct:+.1f}%'
        if alert_type == 'premium_comeback':
            pct_text = f'↩ {pct_text}'
        if price_change > 0:
            kind = 'up'
            badge = '↑'
            new_cls = 'up'
        elif price_change < 0:
            kind = 'drop'
            badge = '↓'
            new_cls = 'drop'
        else:
            kind = 'missing'
            badge = '→'
            new_cls = ''
        try:
            old_fmt = f"{float(old_price):.0f}"
            new_fmt = f"{float(new_price):.0f}"
        except (TypeError, ValueError):
            old_fmt = str(old_price)
            new_fmt = str(new_price)
        note = ''

    meta_line = f'{html_lib.escape(str(dates))} · {html_lib.escape(str(duration))}'
    return {
        'slug': slugify_fn(hotel_name),
        'alert_type': alert_type,
        'kind': kind,
        'badge': badge,
        'hotel_name_html': hotel_name_html,
        'chart_href': chart_href,
        'offer_url': offer_url,
        'old_fmt': old_fmt,
        'new_fmt': new_fmt,
        'new_cls': new_cls,
        'pct_text': pct_text,
        'ts_fmt': ts_fmt,
        'meta_line': meta_line,
        'note': note,
    }


def _render_note_price_block(d, *, as_history=False):
    """Price row for zone_entry / zone_exit alerts (with note, not plain price change)."""
    if d['alert_type'] == 'zone_entry':
        if d['old_fmt'] != '—' and d['pct_text']:
            if as_history:
                return (
                    f'<span class="alert-history-old">{d["old_fmt"]}</span>'
                    f'<span class="alert-history-arrow">→</span>'
                    f'<span class="alert-history-new {d["new_cls"]}">{d["new_fmt"]}</span>'
                ), f'<span class="alert-history-pct {d["new_cls"]}">{d["pct_text"]}</span>'
            pct_block = f'<span class="alert-change-pct {d["new_cls"]}">{d["pct_text"]}</span>'
            return (
                f'<div class="alert-price-row">'
                f'<span class="alert-price-old">{d["old_fmt"]}</span>'
                f'<span aria-hidden="true">→</span>'
                f'<span class="alert-price-new {d["new_cls"]}">{d["new_fmt"]}</span>'
                f'{pct_block}'
                f'</div>'
            ), None
        if as_history:
            return f'<span class="alert-history-new {d["new_cls"]}">{d["new_fmt"]} PLN</span>', None
        return f'<div class="alert-price-row"><span class="alert-price-new {d["new_cls"]}">{d["new_fmt"]} PLN</span></div>', None

    if as_history:
        return f'<span class="alert-history-new">{d["old_fmt"]} PLN</span>', None
    return f'<div class="alert-price-row"><span class="alert-price-new">{d["old_fmt"]} PLN</span></div>', None


def _render_alert_card(alert, meta, slugify_fn, parse_iso_fn):
    d = _alert_display_fields(alert, meta, slugify_fn, parse_iso_fn)
    image_url = meta.get('image_url') or ''
    if image_url:
        img_block = (
            f'<img src="{html_lib.escape(image_url, quote=True)}" alt="" loading="lazy" '
            f'onerror="this.onerror=null;this.parentElement.innerHTML=\'<div>🏨</div>\';" />'
        )
    else:
        img_block = '<div>🏨</div>'

    offer_btn = (
        f'<a class="card-btn" href="{html_lib.escape(d["offer_url"], quote=True)}" target="_blank" rel="noopener">Оффер</a>'
        if d['offer_url'] else
        '<span class="card-btn" style="opacity:.55;">—</span>'
    )

    if d['note']:
        price_block, _ = _render_note_price_block(d)
        sub_line = f'{d["note"]} · {d["meta_line"]}'
    else:
        pct_block = f'<span class="alert-change-pct {d["new_cls"]}">{d["pct_text"]}</span>' if d['pct_text'] else ''
        price_block = (
            f'<div class="alert-price-row">'
            f'<span class="alert-price-old">{d["old_fmt"]}</span>'
            f'<span aria-hidden="true">→</span>'
            f'<span class="alert-price-new {d["new_cls"]}">{d["new_fmt"]}</span>'
            f'{pct_block}'
            f'</div>'
        )
        sub_line = f'{d["ts_fmt"]} · {d["meta_line"]}'

    return f"""
                    <article class="alert-card {d["kind"]}">
                        <div class="alert-card-img">{img_block}</div>
                        <div class="alert-card-body">
                            <div class="alert-card-top">
                                <h4 class="alert-card-title"><a href="{d["chart_href"]}" onclick="if(window.openHotelPassport){{window.openHotelPassport('{d["slug"]}'); return false;}}">{d["hotel_name_html"]}</a></h4>
                                <span class="alert-badge {d["kind"]}">{d["badge"]}</span>
                            </div>
                            {price_block}
                            <div class="alert-card-meta">{sub_line}</div>
                            <div class="alert-card-actions">
                                <a class="card-btn primary" href="{d["chart_href"]}" onclick="if(window.openHotelPassport){{window.openHotelPassport('{d["slug"]}'); return false;}}">Паспорт и график</a>
                                {offer_btn}
                            </div>
                        </div>
                    </article>
"""


def _render_alert_history_row(alert, meta, slugify_fn, parse_iso_fn):
    d = _alert_display_fields(alert, meta, slugify_fn, parse_iso_fn)
    if d['note']:
        price_html, pct_html = _render_note_price_block(d, as_history=True)
        note_html = f'<span class="alert-history-pct">{html_lib.escape(d["note"])}</span>'
        pct_html = pct_html or note_html
    else:
        price_html = (
            f'<span class="alert-history-old">{d["old_fmt"]}</span>'
            f'<span class="alert-history-arrow">→</span>'
            f'<span class="alert-history-new {d["new_cls"]}">{d["new_fmt"]}</span>'
        )
        pct_html = f'<span class="alert-history-pct {d["new_cls"]}">{d["pct_text"]}</span>' if d['pct_text'] else ''

    offer_link = (
        f'<a class="alert-history-offer" href="{html_lib.escape(d["offer_url"], quote=True)}" target="_blank" rel="noopener" title="Оффер">🔗</a>'
        if d['offer_url'] else ''
    )
    return f"""
                        <div class="alert-history-row {d["kind"]}">
                            <span class="alert-history-badge {d["kind"]}" aria-hidden="true">{d["badge"]}</span>
                            <div class="alert-history-info">
                                <a class="alert-history-name" href="{d["chart_href"]}" onclick="if(window.openHotelPassport){{window.openHotelPassport('{d["slug"]}'); return false;}}">{d["hotel_name_html"]}</a>
                                <span class="alert-history-sub">{d["ts_fmt"]} · {d["meta_line"]}</span>
                            </div>
                            <div class="alert-history-price">{price_html}{pct_html}</div>
                            <div class="alert-history-links">
                                <a class="alert-history-chart" href="{d["chart_href"]}" onclick="if(window.openHotelPassport){{window.openHotelPassport('{d["slug"]}'); return false;}}">Паспорт</a>
                                {offer_link}
                            </div>
                        </div>
"""


def _alert_matches_scope(alert, scope_hotel_names: set, scope_duration_bucket: str = '') -> bool:
    hotel_name = str(alert.get('hotel_name') or alert.get('hotel') or '')
    if hotel_name not in scope_hotel_names:
        return False
    scope_bucket = str(scope_duration_bucket or '').strip()
    if not scope_bucket:
        return True
    alert_bucket = str(alert.get('duration_bucket') or '').strip()
    if _duration_bucket_is_missing(alert_bucket):
        return False
    return alert_bucket == scope_bucket


def _build_alerts_panel_html(
    *,
    alerts: list,
    table_prices: dict,
    premium_history_by_hotel: dict,
    scope_hotel_names: set,
    hotel_meta_by_name: dict,
    latest_run_ts,
    ceiling_val,
    alert_threshold_percent: float,
    parse_iso_fn,
    scope_duration_bucket: str = '',
) -> tuple[str, str]:
    """Build alert summary chips and inner content for one duration scope."""
    from price_alerts_v2 import ALERT_THRESHOLD_PERCENT

    threshold = float(alert_threshold_percent or ALERT_THRESHOLD_PERCENT)
    scoped_alerts = [
        a for a in alerts
        if _alert_matches_scope(a, scope_hotel_names, scope_duration_bucket)
    ]

    current_alerts = []
    current_keys = set()
    for alert in scoped_alerts:
        if not _alert_is_current(alert, table_prices, scope_duration_bucket=scope_duration_bucket):
            continue
        hotel_name = str(alert.get('hotel_name') or alert.get('hotel') or '')
        unique_key = alert.get('unique_key') or f"{hotel_name}:{alert.get('new_price')}"
        if unique_key in current_keys:
            continue
        current_keys.add(unique_key)
        current_alerts.append(alert)

    for row_id, price in table_prices.items():
        hotel_name = str(row_id).split('|', 1)[0] if '|' in str(row_id) else str(row_id)
        row_bucket = str(row_id).split('|', 1)[1] if '|' in str(row_id) else ''
        if hotel_name not in scope_hotel_names:
            continue
        if scope_duration_bucket and row_bucket != scope_duration_bucket:
            continue
        comeback_key = f"{row_id}_comeback"
        if comeback_key in current_keys:
            continue
        comeback = comeback_from_premium(
            price, premium_history_by_hotel.get(row_id), ceiling_val
        )
        if not comeback or comeback['drop_from_peak_pct'] < threshold:
            continue
        peak = float(comeback['peak_price'])
        curr = float(price)
        current_alerts.append({
            'hotel_name': hotel_name,
            'duration_bucket': row_bucket,
            'old_price': peak,
            'new_price': curr,
            'price_change': curr - peak,
            'price_change_pct': (curr - peak) / peak * 100.0 if peak else 0.0,
            'timestamp': latest_run_ts,
            'alert_type': 'premium_comeback',
            'created_at': latest_run_ts.isoformat() if latest_run_ts is not None else '',
            'threshold_percent': threshold,
            'unique_key': f"{row_id}_comeback_{peak:.0f}_to_{curr:.0f}",
        })
        current_keys.add(comeback_key)

    current_alert_keys = {a.get('unique_key') for a in current_alerts if a.get('unique_key')}
    history_alerts = [
        a for a in scoped_alerts
        if not a.get('unique_key') or a.get('unique_key') not in current_alert_keys
    ]

    def _count_alert_kinds(items):
        drops = sum(1 for a in items if float(a.get('price_change') or 0) < 0)
        ups = sum(1 for a in items if float(a.get('price_change') or 0) > 0)
        return drops, ups

    cur_drops, cur_ups = _count_alert_kinds(current_alerts)
    chips_html = ""
    if current_alerts:
        if cur_drops:
            chips_html += f'<span class="alert-chip drop">↓ {cur_drops} подешевело сейчас</span>'
        if cur_ups:
            chips_html += f'<span class="alert-chip up">↑ {cur_ups} подорожало сейчас</span>'
    if history_alerts:
        chips_html += f'<span class="alert-chip missing">🕘 {len(history_alerts)} в истории</span>'

    content_parts = []
    if scoped_alerts or current_alerts:
        if current_alerts:
            content_parts.append(
                f'<p class="alerts-section-label">Действует сейчас · {len(current_alerts)}</p>'
                '<div class="alerts-grid">'
            )
            for alert in current_alerts:
                hotel_name = str(alert.get('hotel_name') or alert.get('hotel') or 'Unknown')
                meta = hotel_meta_by_name.get(hotel_name, {})
                content_parts.append(_render_alert_card(alert, meta, slugify, parse_iso_fn))
            content_parts.append('</div>')
        else:
            content_parts.append(
                '<div class="alerts-empty">Сейчас нет отелей с актуальным изменением цены — '
                'зафиксированные сдвиги уже устарели. Смотрите «Историю» ниже.</div>'
            )
        if history_alerts:
            content_parts.append(
                f'<details class="alerts-history-fold" onclick="event.stopPropagation()">'
                f'<summary>🕘 Показать историю ({len(history_alerts)} прошлых изменений)</summary>'
                '<div class="alert-history-list">'
            )
            for alert in history_alerts:
                hotel_name = str(alert.get('hotel_name') or alert.get('hotel') or 'Unknown')
                meta = hotel_meta_by_name.get(hotel_name, {})
                content_parts.append(_render_alert_history_row(alert, meta, slugify, parse_iso_fn))
            content_parts.append('</div></details>')
    else:
        content_parts.append(
            f'<div class="alerts-empty">Пока нет изменений от {threshold:.0f}% — '
            'они появятся здесь после следующих проверок.</div>'
        )

    return chips_html, ''.join(content_parts)


def _compute_chart_point_meta(y_values, alert_threshold, ceiling_val=None):
    """Marker sizes/colors and step % for each price point."""
    sizes = []
    colors = []
    step_pcts = []
    prev_price = None
    for i, price in enumerate(y_values):
        if price is None:
            sizes.append(0)
            colors.append('rgba(0,0,0,0)')
            step_pcts.append(0.0)
            continue
        price = float(price)
        # После разрыва (None) сравниваем с последней реальной ценой до паузы.
        if prev_price is None and i > 0:
            for j in range(i - 1, -1, -1):
                if y_values[j] is not None:
                    prev_price = float(y_values[j])
                    break
        if prev_price is None:
            pct = 0.0
        else:
            pct = ((price - prev_price) / prev_price * 100.0) if prev_price else 0.0
        step_pcts.append(round(pct, 1))
        above_ceiling = ceiling_val is not None and price > float(ceiling_val)
        crossed_gap = i > 0 and y_values[i - 1] is None
        if prev_price is not None and abs(pct) >= alert_threshold:
            sizes.append(15 if crossed_gap else 14)
            colors.append('#ef4444' if pct > 0 else '#10b981')
        elif crossed_gap:
            sizes.append(12)
            colors.append('#6366f1')
        elif above_ceiling:
            sizes.append(9 if i == len(y_values) - 1 else 8)
            colors.append('#f59e0b')
        else:
            sizes.append(8 if i == len(y_values) - 1 else 7)
            colors.append('#6366f1' if i == len(y_values) - 1 else '#4f46e5')
        # Подсветить точку перед паузой, если после паузы цена заметно изменилась.
        if i < len(y_values) - 1:
            for j in range(i + 1, len(y_values)):
                if y_values[j] is None:
                    continue
                jump_pct = ((float(y_values[j]) - price) / price * 100.0) if price else 0.0
                if abs(jump_pct) >= alert_threshold:
                    sizes[-1] = max(sizes[-1], 13)
                    colors[-1] = '#ef4444' if jump_pct > 0 else '#10b981'
                break
        prev_price = price
    if sizes:
        for j in range(len(sizes) - 1, -1, -1):
            if y_values[j] is not None:
                sizes[j] = max(sizes[j], 10)
                break
    return sizes, colors, step_pcts


def _build_gap_jump_series(chart_x, chart_y, alert_threshold):
    """Пунктир через паузу в данных, если цена заметно изменилась."""
    jump_x, jump_y = [], []
    last_idx = None
    for i, y in enumerate(chart_y):
        if y is None:
            continue
        if last_idx is not None:
            gap_between = any(v is None for v in chart_y[last_idx + 1:i])
            if gap_between and last_idx + 1 < i:
                prev_y = float(chart_y[last_idx])
                pct = ((float(y) - prev_y) / prev_y * 100.0) if prev_y else 0.0
                if abs(pct) >= max(3.0, float(alert_threshold) * 0.5):
                    jump_x.extend([chart_x[last_idx], chart_x[i], None])
                    jump_y.extend([prev_y, float(y), None])
        last_idx = i
    return jump_x, jump_y


def _render_hotel_chart_page(
    hotel_name,
    hotel_name_html,
    x_values,
    y_values,
    hover_lines,
    meta,
    back_href,
    deal_score,
    deal_label,
    deal_class,
    delta48_str,
    delta_avg_str,
    confidence,
    median_p,
    min_p,
    max_p,
    samples,
    alert_threshold,
    trip_dates_label,
    display_price_ceiling=None,
    history_price_ceiling=None,
    favicon_href="favicon.svg",
):
    current_p = float(y_values[-1]) if y_values else 0.0
    has_drop = (max_p - min_p) >= 50.0 and max_p > 0 and ((max_p - min_p) / max_p) >= 0.02
    is_at_min = bool(y_values) and has_drop and current_p <= min_p + 2.0
    above_ceiling_now = (
        display_price_ceiling is not None
        and y_values
        and current_p > float(display_price_ceiling)
    )
    _, _, step_pcts_raw = _compute_chart_point_meta(
        y_values, alert_threshold, display_price_ceiling
    )
    chart_x = x_values
    chart_y = y_values
    chart_hover = hover_lines

    enriched_hover = []
    prev_price = None
    for i, base in enumerate(chart_hover):
        price = float(chart_y[i]) if i < len(chart_y) else 0.0
        if prev_price is not None and prev_price > 0:
            pct = (price - prev_price) / prev_price * 100.0
        else:
            pct = 0.0
        extra = f'<br>Δ к прошлому замеру: {pct:+.1f}%' if i > 0 else ''
        if i > 0 and abs(pct) >= alert_threshold:
            extra += '<br><b>Заметное изменение</b>'
        enriched_hover.append((base or '') + extra)
        prev_price = price

    image_url = meta.get('image_url') or ''
    offer_url = meta.get('offer_url') or ''
    dates = html_lib.escape(str(meta.get('dates') or '—'))
    duration = html_lib.escape(str(meta.get('duration') or '—'))

    if image_url:
        img_html = (
            f'<img src="{html_lib.escape(image_url, quote=True)}" alt="" loading="lazy" '
            f'onerror="this.onerror=null;this.parentElement.innerHTML=\'<div class=\\\'chart-hero-placeholder\\\'>🏨</div>\';" />'
        )
    else:
        img_html = '<div class="chart-hero-placeholder">🏨</div>'

    offer_btn = (
        f'<a class="chart-btn primary" href="{html_lib.escape(offer_url, quote=True)}" target="_blank" rel="noopener">Открыть оффер</a>'
        if offer_url else
        '<span class="chart-btn disabled">Оффер недоступен</span>'
    )
    min_badge = '<span class="chart-min-badge">🔥 Исторический минимум</span>' if is_at_min else ''
    ceiling_badge = (
        f'<span class="chart-ceiling-badge">Выше потолка показа (&gt;{display_price_ceiling:.0f})</span>'
        if above_ceiling_now else ''
    )

    recent_rows = ''
    for i in range(max(0, len(x_values) - 5), len(x_values)):
        step = step_pcts_raw[i] if i < len(step_pcts_raw) else 0.0
        step_cls = 'up' if step > 0 else ('drop' if step < 0 else 'flat')
        step_txt = f'{step:+.1f}%' if i > 0 else '—'
        try:
            x_label = pd.to_datetime(x_values[i]).strftime('%d.%m.%Y %H:%M')
        except Exception:
            x_label = str(x_values[i])
        recent_rows += (
            f'<tr><td>{html_lib.escape(x_label)}</td>'
            f'<td><strong>{float(y_values[i]):.0f}</strong> PLN</td>'
            f'<td class="{step_cls}">{step_txt}</td></tr>'
        )

    title_esc = html_lib.escape(str(hotel_name))
    back_href_esc = html_lib.escape(back_href, quote=True)
    meta_desc = html_lib.escape(
        f'{hotel_name}: {current_p:.0f} PLN. Deal Score {deal_score} {deal_label}.'
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{meta_desc}">
    <meta property="og:title" content="{title_esc} — {current_p:.0f} PLN">
    <meta property="og:description" content="{meta_desc}">
    <meta property="og:image" content="{html_lib.escape(image_url or '')}">
    <meta property="og:type" content="website">
    <title>{title_esc} — {current_p:.0f} PLN</title>
    <link rel="icon" href="{html_lib.escape(favicon_href)}" type="image/svg+xml">
    <link rel="apple-touch-icon" href="{html_lib.escape(favicon_href)}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        :root {{
            --gradient-primary: linear-gradient(135deg, #4f46e5 0%, #0ea5e9 100%);
            --border-soft: rgba(148, 163, 184, 0.28);
            --text-muted: #64748b;
            --radius-lg: 14px;
            --shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: 'Inter', sans-serif;
            background: #f3f6ff;
            color: #0f172a;
            line-height: 1.45;
        }}
        .page {{
            max-width: 980px;
            margin: 0 auto;
            padding: 1rem 1rem 2rem;
        }}
        .chart-topbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: .75rem;
            margin-bottom: .85rem;
        }}
        .chart-back {{
            color: #4f46e5;
            text-decoration: none;
            font-weight: 600;
            font-size: .88rem;
        }}
        .chart-back:hover {{ text-decoration: underline; }}
        .chart-topbar-actions {{
            display: flex;
            gap: .5rem;
            align-items: center;
        }}
        .chart-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: .45rem .85rem;
            border-radius: 10px;
            font-size: .82rem;
            font-weight: 700;
            text-decoration: none;
            border: 1px solid var(--border-soft);
            background: #fff;
            color: #1e293b;
            cursor: pointer;
            transition: all .15s ease;
        }}
        .chart-btn:hover {{ background: #f8fafc; border-color: #cbd5e1; }}
        .chart-btn.primary {{
            background: var(--gradient-primary);
            color: #fff;
            border-color: transparent;
        }}
        .chart-btn.disabled {{
            opacity: .55;
            cursor: default;
        }}
        .chart-hero {{
            display: grid;
            grid-template-columns: 140px minmax(0, 1fr);
            gap: 1rem;
            background: #fff;
            border: 1px solid var(--border-soft);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
            overflow: hidden;
            margin-bottom: .85rem;
        }}
        .chart-hero-img {{
            min-height: 120px;
            background: linear-gradient(135deg, rgba(79,70,229,.12), rgba(14,165,233,.12));
        }}
        .chart-hero-img img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            min-height: 120px;
        }}
        .chart-hero-placeholder {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 120px;
            font-size: 2rem;
            opacity: .55;
        }}
        .chart-hero-body {{
            padding: .85rem .95rem .9rem 0;
        }}
        .chart-hero-body h1 {{
            margin: 0 0 .35rem;
            font-size: 1.15rem;
            line-height: 1.25;
        }}
        .chart-hero-meta {{
            margin: 0 0 .55rem;
            font-size: .82rem;
            color: var(--text-muted);
        }}
        .chart-hero-price-row {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: .45rem;
        }}
        .chart-current-price {{
            font-size: 1.65rem;
            font-weight: 800;
            background: var(--gradient-primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .deal-pill {{
            border-radius: 999px;
            padding: .18rem .55rem;
            font-size: .72rem;
            font-weight: 700;
            border: 1px solid transparent;
        }}
        .deal-pill.hot {{ background: rgba(245,158,11,.18); color: #92400e; border-color: rgba(245,158,11,.32); }}
        .deal-pill.good {{ background: rgba(16,185,129,.17); color: #065f46; border-color: rgba(16,185,129,.32); }}
        .deal-pill.normal {{ background: rgba(148,163,184,.18); color: #334155; border-color: rgba(148,163,184,.35); }}
        .deal-pill.bad {{ background: rgba(239,68,68,.15); color: #991b1b; border-color: rgba(239,68,68,.32); }}
        .deal-pill.warm {{ background: rgba(14,165,233,.16); color: #0c4a6e; border-color: rgba(14,165,233,.35); }}
        .chart-min-badge {{
            font-size: .72rem;
            font-weight: 700;
            color: #b45309;
            background: rgba(245,158,11,.14);
            border: 1px solid rgba(245,158,11,.28);
            border-radius: 999px;
            padding: .15rem .5rem;
        }}
        .chart-ceiling-badge {{
            font-size: .72rem;
            font-weight: 700;
            color: #b45309;
            background: rgba(245,158,11,.14);
            border: 1px solid rgba(245,158,11,.28);
            border-radius: 999px;
            padding: .15rem .5rem;
        }}
        .chart-kpis {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: .55rem;
            margin-bottom: .85rem;
        }}
        .chart-kpi {{
            background: #fff;
            border: 1px solid var(--border-soft);
            border-radius: 12px;
            padding: .55rem .65rem;
            box-shadow: var(--shadow-md);
        }}
        .chart-kpi .v {{
            font-size: 1.02rem;
            font-weight: 800;
            color: #111827;
        }}
        .chart-kpi .l {{
            font-size: .72rem;
            color: var(--text-muted);
            font-weight: 600;
            margin-top: .12rem;
        }}
        .chart-kpi .v.drop {{ color: #047857; }}
        .chart-kpi .v.up {{ color: #b91c1c; }}
        .chart-panel {{
            background: #fff;
            border: 1px solid var(--border-soft);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
            padding: .65rem .45rem .25rem;
            margin-bottom: .85rem;
        }}
        .chart-panel h2 {{
            margin: 0 0 .35rem .55rem;
            font-size: .95rem;
            color: #334155;
        }}
        #chart {{ height: 420px; }}
        .chart-recent {{
            background: #fff;
            border: 1px solid var(--border-soft);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-md);
            padding: .65rem .75rem .75rem;
        }}
        .chart-recent h3 {{
            margin: 0 0 .45rem;
            font-size: .88rem;
            color: #334155;
        }}
        .chart-recent table {{
            width: 100%;
            border-collapse: collapse;
            font-size: .78rem;
        }}
        .chart-recent th, .chart-recent td {{
            padding: .35rem .25rem;
            border-bottom: 1px solid rgba(148,163,184,.18);
            text-align: left;
        }}
        .chart-recent td.drop {{ color: #047857; font-weight: 700; }}
        .chart-recent td.up {{ color: #b91c1c; font-weight: 700; }}
        .chart-recent td.flat {{ color: #64748b; }}
        .chart-legend-note {{
            margin: .35rem .55rem .5rem;
            font-size: .72rem;
            color: var(--text-muted);
        }}
        @media (max-width: 640px) {{
            .chart-hero {{ grid-template-columns: 1fr; }}
            .chart-hero-body {{ padding: .75rem; }}
            .chart-hero-img {{ max-height: 140px; }}
            .chart-topbar {{
                flex-wrap: wrap;
                align-items: flex-start;
            }}
            .chart-btn {{
                width: 100%;
            }}
            #chart {{ height: 320px; }}
        }}
    </style>
    <!-- Cloudflare Web Analytics --><script defer src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "1b9c3c0ee6164106a1cb5eda9e61a045"}}'></script><!-- End Cloudflare Web Analytics -->
</head>
<body>
    <div class="page">
        <div class="chart-topbar">
            <a class="chart-back" href="{back_href_esc}">← Назад к дашборду</a>
            <div class="chart-topbar-actions">
                <button type="button" class="chart-btn" id="copyLinkBtn" onclick="copyHotelLink()">📋 Скопировать ссылку</button>
                {offer_btn}
            </div>
        </div>
        <section class="chart-hero">
            <div class="chart-hero-img">{img_html}</div>
            <div class="chart-hero-body">
                <h1>{hotel_name_html}</h1>
                <p class="chart-hero-meta">🗓️ {dates} · ⏱️ {duration}</p>
                <div class="chart-hero-price-row">
                    <span class="chart-current-price">{current_p:.0f} PLN</span>
                    <span class="deal-pill {deal_class}">Deal {deal_score} · {html_lib.escape(deal_label)}</span>
                    {min_badge}
                    {ceiling_badge}
                    {offer_btn}
                </div>
            </div>
        </section>
        <section class="chart-kpis">
            <div class="chart-kpi" title="Изменение цены за последние 48 часов"><div class="v {'drop' if delta48_str.startswith('-') else ('up' if delta48_str.startswith('+') else '')}">{html_lib.escape(delta48_str)}</div><div class="l">Δ за 48ч</div></div>
            <div class="chart-kpi" title="Отклонение от средней цены этого отеля за всё время наблюдений"><div class="v {'drop' if delta_avg_str.startswith('-') else ('up' if delta_avg_str.startswith('+') else '')}">{html_lib.escape(delta_avg_str)}</div><div class="l">Δ к своей средней</div></div>
            <div class="chart-kpi" title="Самая низкая цена зафиксированная для этого отеля"><div class="v">{min_p:.0f} PLN</div><div class="l">Минимум истории</div></div>
            <div class="chart-kpi" title="Медианное значение цены за время мониторинга"><div class="v">{median_p:.0f} PLN</div><div class="l">Ср. по времени</div></div>
            <div class="chart-kpi" title="Самая высокая цена зафиксированная для этого отеля"><div class="v">{max_p:.0f} PLN</div><div class="l">Максимум</div></div>
            <div class="chart-kpi" title="Количество проверок и степень уверенности оценки (Low/Medium/High)"><div class="v">{samples}</div><div class="l">Замеров · {html_lib.escape(confidence)}</div></div>
        </section>
        <section class="chart-panel">
            <h2>История цен</h2>
            <p class="chart-legend-note">Сплошная линия — история цены отеля в этом фильтре. Зелёная зона снизу — область хорошей выгоды (ниже средней цены).</p>
            <div id="chart"></div>
        </section>
        <section class="chart-recent">
            <h3>Последние замеры</h3>
            <table>
                <thead><tr><th>Время</th><th>Цена</th><th>Δ к прошлому</th></tr></thead>
                <tbody>{recent_rows}</tbody>
            </table>
        </section>
    </div>
    <script>
      function copyHotelLink() {{
        const btn = document.getElementById('copyLinkBtn');
        navigator.clipboard.writeText(window.location.href).then(function() {{
          if (btn) {{
            const orig = btn.textContent;
            btn.textContent = '✅ Ссылка скопирована!';
            setTimeout(function() {{ btn.textContent = orig; }}, 2000);
          }}
        }}).catch(function(e) {{
          prompt('Скопируйте ссылку:', window.location.href);
        }});
      }}

      const x = {json.dumps(chart_x, ensure_ascii=False)};
      const y = {json.dumps(chart_y, ensure_ascii=False)};
      const text = {json.dumps(enriched_hover, ensure_ascii=False)};
      const mainTrace = {{
        x, y, text,
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Цена отеля',
        line: {{ color: '#4f46e5', width: 2.5 }},
        marker: {{ size: 6, color: '#4f46e5', line: {{ width: 1, color: '#fff' }} }},
        connectgaps: true,
        hovertemplate: '<b>%{{y:.0f}} PLN</b><br>%{{text}}<extra></extra>'
      }};
      const tripDatesLabel = {json.dumps(str(trip_dates_label or '—'), ensure_ascii=False)};
      const medianP = {median_p:.0f};
      const yDataMin = y.length ? Math.min(...y) : 0;
      const yDataMax = y.length ? Math.max(...y) : 0;
      const ySpan = Math.max(yDataMax - yDataMin, 1);
      const yPad = Math.max(ySpan * 0.08, 80);

      // Линия средней цены
      const medianTrace = {{
        x: x.length ? [x[0], x[x.length - 1]] : [],
        y: [medianP, medianP],
        type: 'scatter',
        mode: 'lines',
        name: 'Средняя цена',
        line: {{ color: 'rgba(148,163,184,0.7)', width: 1.5, dash: 'dot' }},
        hovertemplate: 'Средняя: <b>%{{y:.0f}} PLN</b><extra></extra>'
      }};

      // Зелёная зона хорошей выгоды (ниже средней цены)
      const shapes = [];
      if (y.length && medianP > yDataMin) {{
        shapes.push({{
          type: 'rect',
          xref: 'paper',
          yref: 'y',
          x0: 0,
          x1: 1,
          y0: yDataMin - yPad,
          y1: medianP,
          fillcolor: 'rgba(16, 185, 129, 0.08)',
          line: {{ width: 0 }}
        }});
      }}

      // Аннотация последней точки
      const annotations = [];
      if (y.length) {{
        const lastY = y[y.length - 1];
        const lastX = x[x.length - 1];
        annotations.push({{
          x: lastX,
          y: lastY,
          text: `<b>${{lastY.toFixed(0)}} PLN</b>`,
          showarrow: true,
          arrowhead: 2,
          arrowsize: 1,
          arrowwidth: 1.5,
          arrowcolor: '#4f46e5',
          ax: 0,
          ay: -32,
          font: {{ size: 12, color: '#4f46e5', family: 'Inter, sans-serif' }},
          bgcolor: 'rgba(255,255,255,0.85)',
          borderpad: 3,
          bordercolor: '#4f46e5',
          borderwidth: 1
        }});
      }}

      const layout = {{
        margin: {{ t: 24, r: 20, b: 75, l: 70 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        shapes: shapes,
        xaxis: {{
          title: {{ text: 'Время проверки (обновляется каждый час) · Даты поездки: ' + tripDatesLabel, standoff: 16, font: {{ size: 11, color: '#64748b' }} }},
          type: 'date',
          tickformat: '%d.%m',
          hoverformat: '%d.%m.%Y %H:%M',
          gridcolor: 'rgba(148,163,184,0.2)',
          tickangle: -20
        }},
        yaxis: {{
          title: {{ text: 'Цена (PLN) · 2 взрослых + 1 ребёнок', standoff: 10, font: {{ size: 11, color: '#64748b' }} }},
          gridcolor: 'rgba(148,163,184,0.2)',
          range: [yDataMin - yPad, yDataMax + yPad],
          fixedrange: false
        }},
        showlegend: true,
        legend: {{ orientation: 'h', x: 0, y: -0.22, font: {{ size: 11, color: '#64748b' }} }},
        hovermode: 'closest',
        annotations
      }};
      Plotly.newPlot('chart', [mainTrace, medianTrace], layout, {{ responsive: true, displayModeBar: true }});
    </script>
</body>
</html>"""


