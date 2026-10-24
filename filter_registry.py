"""Shared filter list for landing page and dashboard sidebar."""

from __future__ import annotations

import copy
from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from filter_trip import should_skip_monitor_config

FILTER_GROUPS = [
    {
        'id': 'trips',
        'label': 'Поездки',
        'icon': '🎯',
        'filters': [
            {
                'id': 'turkey_vacation_jul18_2026',
                'title': 'Турция • отпуск 18 июля',
                'subtitle': '7–9 / 9–11 дн. • один фильтр, переключатель на странице',
                'href': 'index_filter_turkey_vacation_jul18.html',
                'charts_subdir': 'hotel-charts/filter_turkey_vacation_jul18_2026',
                'config': 'config_ci_filter_turkey_vacation_jul18.json',
            },
            {
                'id': 'egypt_autumn_2026_7_10',
                'title': 'Египет • осень 2026 • 7–10 дн.',
                'subtitle': '10.10–05.11.2026 • WAW/WMI/RDO • 2+1 • показ ≤11k',
                'href': 'index_filter_egypt_autumn_2026_7_10_days.html',
                'charts_subdir': 'hotel-charts/filter_egypt_autumn_2026_7_10_days',
                'config': 'config_ci_filter_egypt_autumn_7_10.json',
            },
            {
                'id': 'egypt_autumn_2026_13_16',
                'title': 'Египет • осень 2026 • 13–16 дн.',
                'subtitle': '10.10–05.11.2026 • WAW/WMI/RDO • 2+1 • показ ≤11k',
                'href': 'index_filter_egypt_autumn_2026_13_16_days.html',
                'charts_subdir': 'hotel-charts/filter_egypt_autumn_2026_13_16_days',
                'config': 'config_ci_filter_egypt_autumn_13_16.json',
            },
            {
                'id': 'egypt_ny_dec24_2026_7_10',
                'title': 'Египет • НГ 24.12–06.01 • 7–10 дн.',
                'subtitle': '24.12.2026–06.01.2027 • WAW/WMI/RDO • 2+1 • показ ≤11k',
                'href': 'index_filter_egypt_ny_dec24_2026_7_10_days.html',
                'charts_subdir': 'hotel-charts/filter_egypt_ny_dec24_2026_7_10_days',
                'config': 'config_ci_filter_egypt_ny_dec24_7_10.json',
            },
            {
                'id': 'egypt_ny_dec28_2026_7_10',
                'title': 'Египет • НГ 28.12–06.01 • 7–10 дн.',
                'subtitle': '28.12.2026–06.01.2027 • WAW/WMI/RDO • 2+1 • показ ≤11k',
                'href': 'index_filter_egypt_ny_dec28_2026_7_10_days.html',
                'charts_subdir': 'hotel-charts/filter_egypt_ny_dec28_2026_7_10_days',
                'config': 'config_ci_filter_egypt_ny_dec28_7_10.json',
            },
            {
                'id': 'egypt_sharm_dec20_29_1p',
                'title': 'Египет • Шарм 20–29 дек • 7–15 дн. • 1 взр.',
                'subtitle': '20.12–29.12.2026 • 7–15 дн. • любой аэропорт • 1 чел. • Шарм-эль-Шейх',
                'href': 'index_filter_egypt_sharm_dec20_29_1p.html',
                'charts_subdir': 'hotel-charts/filter_egypt_sharm_dec20_29_1p',
                'config': 'config_ci_filter_egypt_sharm_dec20_29_1p.json',
            },
        ],
    },
    {
        'id': 'egypt',
        'label': 'Египет',
        'icon': '🇪🇬',
        'filters': [
            {
                'id': 'egypt_7_10',
                'title': '7–10 дней',
                'subtitle': 'сбор 4–20k PLN • показ ≤10k • WAW/WMI/RDO',
                'href': 'index_filter_7_10_days.html',
                'charts_subdir': 'hotel-charts/filter_7_10_days',
                'config': 'config_ci_filter_7_10.json',
            },
            {
                'id': 'egypt_13_16',
                'title': '13–16 дней',
                'subtitle': 'сбор 4–20k PLN • показ ≤10k • WAW/WMI/RDO',
                'href': 'index_filter_13_16_days.html',
                'charts_subdir': 'hotel-charts/filter_13_16_days',
                'config': 'config_ci_filter_13_16.json',
            },
        ],
    },
    {
        'id': 'turkey',
        'label': 'Турция',
        'icon': '🇹🇷',
        'filters': [
            {
                'id': 'turkey_7_10',
                'title': '7–10 дней',
                'subtitle': 'сбор 4–20k PLN • показ ≤10k • WAW/RDO',
                'href': 'index_filter_turkey_7_10_days.html',
                'charts_subdir': 'hotel-charts/filter_turkey_7_10_days',
                'config': 'config_ci_filter_turkey_7_10.json',
            },
            {
                'id': 'turkey_9_11',
                'title': '9–11 дней',
                'subtitle': 'сбор 4.6–20k PLN • показ ≤10k • WAW/WMI/RDO • с питанием',
                'href': 'index_filter_turkey_9_11_days.html',
                'charts_subdir': 'hotel-charts/filter_turkey_9_11_days',
                'config': 'config_ci_filter_turkey_9_11.json',
            },
            {
                'id': 'turkey_13_16',
                'title': '13–16 дней',
                'subtitle': 'сбор 4–20k PLN • показ ≤10k • WAW/RDO',
                'href': 'index_filter_turkey_13_16_days.html',
                'charts_subdir': 'hotel-charts/filter_turkey_13_16_days',
                'config': 'config_ci_filter_turkey_13_16.json',
            },
        ],
    },
    {
        'id': 'greece',
        'label': 'Греция',
        'icon': '🇬🇷',
        'filters': [
            {
                'id': 'greece_7_10',
                'title': '7–10 дней',
                'subtitle': 'сбор 4–20k PLN • показ ≤10k • любой аэропорт',
                'href': 'index_filter_greece_7_10_days.html',
                'charts_subdir': 'hotel-charts/filter_greece_7_10_days',
                'config': 'config_ci_filter_greece_7_10.json',
            },
            {
                'id': 'greece_13_16',
                'title': '13–16 дней',
                'subtitle': 'сбор 4–20k PLN • показ ≤10k • любой аэропорт',
                'href': 'index_filter_greece_13_16_days.html',
                'charts_subdir': 'hotel-charts/filter_greece_13_16_days',
                'config': 'config_ci_filter_greece_13_16.json',
            },
        ],
    },
]


ARCHIVED_GROUP_ID = 'archived'

ROOT = Path(__file__).resolve().parent

KNOWN_GROUPS = {
    'trips': {'id': 'trips', 'label': 'Поездки', 'icon': '🎯'},
    'egypt': {'id': 'egypt', 'label': 'Египет', 'icon': '🇪🇬'},
    'turkey': {'id': 'turkey', 'label': 'Турция', 'icon': '🇹🇷'},
    'greece': {'id': 'greece', 'label': 'Греция', 'icon': '🇬🇷'},
    'cyprus': {'id': 'cyprus', 'label': 'Кипр', 'icon': '🇨🇾'},
    'spain': {'id': 'spain', 'label': 'Испания', 'icon': '🇪🇸'},
    'italy': {'id': 'italy', 'label': 'Италия', 'icon': '🇮🇹'},
    'bulgaria': {'id': 'bulgaria', 'label': 'Болгария', 'icon': '🇧🇬'},
    'custom': {'id': 'custom', 'label': 'Мои поездки', 'icon': '✨'},
}


def detect_group_for_config(cfg: Dict[str, Any]) -> str:
    """Detects destination group category from config metadata, URL, and required strings."""
    if cfg.get('group'):
        g = str(cfg['group']).lower()
        if g in KNOWN_GROUPS:
            return g

    haystack = " ".join([
        str(cfg.get('title', '')),
        str(cfg.get('description', '')),
        str(cfg.get('url', '')),
        str(cfg.get('data_dir', '')),
        " ".join(cfg.get('required_offer_url_contains', [])),
    ]).lower()

    if any(k in haystack for k in ['cypr', 'cyprus', 'кипр', 'paphos', 'larnaca', 'protaras', 'destinationlocation=12']):
        return 'cyprus'
    if any(k in haystack for k in ['spain', 'hiszpania', 'испания', 'mallorca', 'tenerife', 'canary', 'destinationlocation=13']):
        return 'spain'
    if any(k in haystack for k in ['italy', 'wlochy', 'италия', 'sicily', 'sardinia', 'destinationlocation=17']):
        return 'italy'
    if any(k in haystack for k in ['bulgaria', 'bułgaria', 'болгария', 'burgas', 'varna', 'destinationlocation=15']):
        return 'bulgaria'
    if any(k in haystack for k in ['turkey', 'turcja', 'турция', 'antalya', 'belek', 'side', 'kemer', 'alanya', 'destinationlocation=39']):
        return 'turkey'
    if any(k in haystack for k in ['egypt', 'egipt', 'египет', 'hurghada', 'sharm', 'marsa', 'destinationlocation=11']):
        return 'egypt'
    if any(k in haystack for k in ['greece', 'grecja', 'греция', 'crete', 'kreta', 'rhodes', 'rodos', 'corfu', 'destinationlocation=14']):
        return 'greece'

    return 'custom'


def discover_filter_groups(*, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Dynamically discovers all filter configs in the workspace (config_ci_*.json and configs/filters/*.json),
    merging them with FILTER_GROUPS so that any newly created user filter is automatically registered
    without manual code edits.
    """
    groups = copy.deepcopy(FILTER_GROUPS)
    registered_configs = {
        flt['config']: flt
        for g in groups
        for flt in g['filters']
        if flt.get('config')
    }
    group_map = {g['id']: g for g in groups}

    # Discover candidate configs
    candidates = sorted(
        list(ROOT.glob('config_ci_*.json')) + list(ROOT.glob('configs/filters/*.json'))
    )

    for c_path in candidates:
        rel = str(c_path.relative_to(ROOT))

        try:
            with c_path.open('r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            continue

        if rel in registered_configs:
            # Enrich existing registration with modules/metadata if present
            flt = registered_configs[rel]
            if cfg.get('modules') and 'modules' not in flt:
                flt['modules'] = cfg['modules']
            if cfg.get('germany_params') and 'germany_params' not in flt:
                flt['germany_params'] = cfg['germany_params']
            continue

        # Skip companion any_airports sub-monitors from standalone dashboard cards
        out_file = str(cfg.get('output_data_file') or '')
        if 'any_airports' in rel and out_file != 'travel_prices.csv':
            continue

        data_dir = str(cfg.get('data_dir') or f"data/filters/{c_path.stem.replace('config_ci_', '')}")
        folder_name = Path(data_dir).name
        slug = folder_name.replace('filter_', '')
        flt_id = str(cfg.get('id') or slug)

        desc = str(cfg.get('description') or '')
        title = str(cfg.get('title') or (desc.split('•')[0].strip() if '•' in desc else flt_id))
        subtitle = str(cfg.get('subtitle') or desc)

        href = str(cfg.get('href') or f"index_{folder_name}.html")
        charts_subdir = str(cfg.get('charts_subdir') or f"hotel-charts/{folder_name}")

        group_id = detect_group_for_config(cfg)

        new_flt = {
            'id': flt_id,
            'title': title,
            'subtitle': subtitle,
            'href': href,
            'charts_subdir': charts_subdir,
            'config': rel,
            'data_dir': data_dir,
            'modules': cfg.get('modules', {}),
            'germany_params': cfg.get('germany_params', {}),
        }

        if group_id in group_map:
            group_map[group_id]['filters'].append(new_flt)
        else:
            meta = KNOWN_GROUPS.get(group_id, {'id': group_id, 'label': group_id.capitalize(), 'icon': '✨'})
            new_group = {
                'id': meta['id'],
                'label': meta['label'],
                'icon': meta['icon'],
                'filters': [new_flt],
            }
            groups.append(new_group)
            group_map[group_id] = new_group

    return groups


def is_filter_archived(flt: Dict[str, Any], *, today: Optional[date] = None) -> bool:
    """Return True if filter is retired, expired, or marked as archived."""
    if bool(flt.get('archived')):
        return True
    config_path = str(flt.get('config') or '').strip()
    if not config_path:
        return False
    return should_skip_monitor_config(config_path, today=today)


def is_filter_active(flt: Dict[str, Any], *, today: Optional[date] = None) -> bool:
    """True for active filters (not archived/retired/expired)."""
    return not is_filter_archived(flt, today=today)


def archived_filters(*, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Return all filters across discovered groups that are currently archived."""
    discovered = discover_filter_groups(today=today)
    archived: List[Dict[str, Any]] = []
    for group in discovered:
        for flt in group['filters']:
            if is_filter_archived(flt, today=today):
                item = copy.deepcopy(flt)
                item['origin_group_id'] = group['id']
                item['origin_group_label'] = group['label']
                item['is_archived'] = True
                archived.append(item)
    return archived


def archived_filter_group(*, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Synthetic group for archived trip/tour filters."""
    archived = archived_filters(today=today)
    if not archived:
        return None
    return {
        'id': ARCHIVED_GROUP_ID,
        'label': 'Архив туров',
        'icon': '📦',
        'subtitle': 'Завершённые поездки и архивные мониторинги',
        'filters': archived,
    }


def active_filter_groups(*, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Discovered groups without retired / expired / archived filters."""
    discovered = discover_filter_groups(today=today)
    groups: List[Dict[str, Any]] = []
    for group in discovered:
        active = [flt for flt in group['filters'] if is_filter_active(flt, today=today)]
        if not active:
            continue
        item = copy.deepcopy(group)
        item['filters'] = copy.deepcopy(active)
        groups.append(item)
    return groups


def all_filter_groups_with_archive(*, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Active groups followed by the archived group at the bottom."""
    groups = active_filter_groups(today=today)
    arch_group = archived_filter_group(today=today)
    if arch_group:
        groups.append(arch_group)
    return groups


def iter_filters(groups: Optional[List[Dict[str, Any]]] = None):
    source = groups if groups is not None else discover_filter_groups()
    for group in source:
        for flt in group['filters']:
            yield group, flt


def filter_href_by_charts_subdir(charts_subdir: str) -> str:
    sub = (charts_subdir or '').rstrip('/')
    for _, flt in iter_filters():
        if flt['charts_subdir'].rstrip('/') == sub:
            return flt['href']
    return 'index.html'


def active_filter_id(charts_subdir: str) -> str:
    sub = (charts_subdir or '').rstrip('/')
    for _, flt in iter_filters():
        if flt['charts_subdir'].rstrip('/') == sub:
            return flt['id']
    return ''


def get_all_monitor_configs() -> List[str]:
    """Returns list of all config file paths to be monitored in parallel."""
    configs = []
    for _, flt in iter_filters():
        cfg_path = flt.get('config')
        if cfg_path and (ROOT / cfg_path).is_file():
            configs.append(cfg_path)

    # Include companion any_airports configs if they exist
    for any_cfg in ROOT.glob('config_ci_*_any_airports.json'):
        rel = str(any_cfg.relative_to(ROOT))
        if rel not in configs:
            configs.append(rel)

    return sorted(list(set(configs)))


def get_all_dashboard_configs() -> List[Dict[str, Any]]:
    """Returns list of dashboard definitions for run_dashboards_parallel.py."""
    dashboards = []
    for _, flt in iter_filters():
        cfg_path = flt.get('config')
        if not cfg_path:
            continue
        full_cfg = ROOT / cfg_path
        if not full_cfg.is_file():
            continue

        try:
            with full_cfg.open('r', encoding='utf-8') as f:
                c_data = json.load(f)
        except Exception:
            c_data = {}

        data_dir = flt.get('data_dir') or c_data.get('data_dir') or f"data/filters/{Path(flt['href']).stem.replace('index_', '')}"

        d_item = {
            "data": f"{data_dir}/travel_prices.csv",
            "output": flt.get('href'),
            "title": flt.get('title'),
            "charts": flt.get('charts_subdir'),
            "alerts": f"{data_dir}/travel_prices_alerts.json",
            "config": cfg_path,
        }
        if c_data.get('display_price_ceiling'):
            d_item['display_price_ceiling'] = str(c_data['display_price_ceiling'])
        if c_data.get('history_price_ceiling'):
            d_item['history_price_ceiling'] = str(c_data['history_price_ceiling'])

        any_ap_csv = f"{data_dir}/travel_prices_any_airports.csv"
        if (ROOT / any_ap_csv).is_file():
            d_item['all_airports_data'] = any_ap_csv

        dashboards.append(d_item)
    return dashboards


def get_all_germany_configs() -> List[str]:
    """Returns list of config paths that should have Check24 German packages scraped."""
    configs = []
    for _, flt in iter_filters():
        cfg_path = flt.get('config')
        if not cfg_path or not (ROOT / cfg_path).is_file():
            continue

        modules = flt.get('modules') or {}
        if modules.get('arbitrage_germany') is False:
            continue
        germany_params = flt.get('germany_params') or {}
        if germany_params.get('enabled') is False:
            continue

        configs.append(cfg_path)
    return configs
