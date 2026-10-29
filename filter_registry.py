"""Shared filter list for landing page and dashboard sidebar."""

from __future__ import annotations

import copy
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
META_FILE = ROOT / 'configs' / 'filters_registry_meta.json'

KNOWN_GROUPS = {
    'trips': {'id': 'trips', 'label': 'Поездки', 'icon': '🎯'},
    'egypt': {'id': 'egypt', 'label': 'Египет', 'icon': '🇪🇬'},
    'turkey': {'id': 'turkey', 'label': 'Турция', 'icon': '🇹🇷'},
    'greece': {'id': 'greece', 'label': 'Греция', 'icon': '🇬🇷'},
    'cyprus': {'id': 'cyprus', 'label': 'Кипр', 'icon': '🇨🇾'},
    'spain': {'id': 'spain', 'label': 'Испания', 'icon': '🇪🇸'},
    'italy': {'id': 'italy', 'label': 'Италия', 'icon': '🇮🇹'},
    'bulgaria': {'id': 'bulgaria', 'label': 'Болгария', 'icon': '🇧🇬'},
    'tunisia': {'id': 'tunisia', 'label': 'Тунис', 'icon': '🇹🇳'},
    'uae': {'id': 'uae', 'label': 'ОАЭ', 'icon': '🇦🇪'},
    'malta': {'id': 'malta', 'label': 'Мальта', 'icon': '🇲🇹'},
    'early_booking': {'id': 'early_booking', 'label': 'Раннее бронирование', 'icon': '🏷️'},
    'custom': {'id': 'custom', 'label': 'Мои поездки', 'icon': '✨'},
}


def load_filters_meta() -> Dict[str, Any]:
    """Loads central metadata overrides (status, custom groups, ordering, pinning)."""
    if not META_FILE.is_file():
        return {'version': 1, 'filters': {}, 'custom_groups': {}}
    try:
        with META_FILE.open('r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {'version': 1, 'filters': {}, 'custom_groups': {}}
            data.setdefault('filters', {})
            data.setdefault('custom_groups', {})
            return data
    except Exception:
        return {'version': 1, 'filters': {}, 'custom_groups': {}}


def save_filters_meta(meta: Dict[str, Any]) -> None:
    """Saves central metadata overrides."""
    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    with META_FILE.open('w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def get_known_groups() -> Dict[str, Dict[str, Any]]:
    """Returns KNOWN_GROUPS merged with any dynamic custom_groups from metadata."""
    groups = copy.deepcopy(KNOWN_GROUPS)
    meta = load_filters_meta()
    for gid, ginfo in meta.get('custom_groups', {}).items():
        if isinstance(ginfo, dict) and 'label' in ginfo:
            groups[gid] = {
                'id': gid,
                'label': ginfo.get('label', gid.capitalize()),
                'icon': ginfo.get('icon', '✨'),
            }
    return groups


def detect_group_for_config(cfg: Dict[str, Any], known: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """Detects destination group category from config metadata, URL, and required strings."""
    known_groups = known if known is not None else get_known_groups()
    if cfg.get('group'):
        g = str(cfg['group']).lower()
        if g in known_groups:
            return g

    if bool(cfg.get('early_booking_tracking')):
        return 'early_booking'

    haystack = " ".join([
        str(cfg.get('title', '')),
        str(cfg.get('description', '')),
        str(cfg.get('url', '')),
        str(cfg.get('data_dir', '')),
        " ".join(cfg.get('required_offer_url_contains', [])),
    ]).lower()

    if any(k in haystack for k in ['cypr', 'cyprus', 'кипр', 'paphos', 'larnaca', 'protaras', 'destinationlocation=6']):
        return 'cyprus'
    if any(k in haystack for k in ['spain', 'hiszpania', 'испания', 'mallorca', 'tenerife', 'canary', 'destinationlocation=15']):
        return 'spain'
    if any(k in haystack for k in ['italy', 'wlochy', 'италия', 'sicily', 'sardinia', 'destinationlocation=44']):
        return 'italy'
    if any(k in haystack for k in ['bulgaria', 'bułgaria', 'болгария', 'burgas', 'varna', 'destinationlocation=3']):
        return 'bulgaria'
    if any(k in haystack for k in ['turkey', 'turcja', 'турция', 'antalya', 'belek', 'side', 'kemer', 'alanya', 'destinationlocation=39']):
        return 'turkey'
    if any(k in haystack for k in ['egypt', 'egipt', 'египет', 'hurghada', 'sharm', 'marsa', 'destinationlocation=11']):
        return 'egypt'
    if any(k in haystack for k in ['greece', 'grecja', 'греция', 'crete', 'kreta', 'rhodes', 'rodos', 'corfu', 'destinationlocation=14']):
        return 'greece'
    if any(k in haystack for k in ['tunisia', 'tunezja', 'тунис', 'djerba', 'destinationlocation=38']):
        return 'tunisia'
    if any(k in haystack for k in ['uae', 'emiraty', 'оаэ', 'dubai', 'destinationlocation=372']):
        return 'uae'
    if any(k in haystack for k in ['malta', 'мальта', 'destinationlocation=26']):
        return 'malta'

    return 'custom'


def discover_filter_groups(*, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Dynamically discovers all filter configs in the workspace (config_ci_*.json and configs/filters/*.json),
    merging them with FILTER_GROUPS and applying any central metadata overrides (status, group reassignment, pinning).
    """
    meta_data = load_filters_meta()
    meta_filters = meta_data.get('filters', {})
    known_groups = get_known_groups()

    base_flts: List[Dict[str, Any]] = []
    for g in FILTER_GROUPS:
        orig_gid = g['id']
        for flt in g['filters']:
            item = copy.deepcopy(flt)
            item['origin_group_id'] = orig_gid
            base_flts.append(item)

    candidates = sorted(
        list(ROOT.glob('config_ci_*.json')) + list(ROOT.glob('configs/filters/*.json'))
    )

    registered_by_config = {
        flt['config']: flt for flt in base_flts if flt.get('config')
    }
    discovered_flts: Dict[str, Dict[str, Any]] = {}
    for flt in base_flts:
        discovered_flts[flt['id']] = flt

    for c_path in candidates:
        rel = str(c_path.relative_to(ROOT))
        try:
            with c_path.open('r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            continue

        out_file = str(cfg.get('output_data_file') or '')
        if 'any_airports' in rel and out_file != 'travel_prices.csv':
            continue

        data_dir = str(cfg.get('data_dir') or f"data/filters/{c_path.stem.replace('config_ci_', '')}")
        folder_name = Path(data_dir).name
        slug = folder_name.replace('filter_', '')
        flt_id = str(cfg.get('id') or slug)

        if rel in registered_by_config:
            existing = registered_by_config[rel]
            if cfg.get('modules') and 'modules' not in existing:
                existing['modules'] = cfg['modules']
            if cfg.get('germany_params') and 'germany_params' not in existing:
                existing['germany_params'] = cfg['germany_params']
            if not existing.get('data_dir'):
                existing['data_dir'] = data_dir
            if cfg.get('group') and 'origin_group_id' in existing:
                existing['origin_group_id'] = cfg['group']
            continue

        desc = str(cfg.get('description') or '')
        title = str(cfg.get('title') or (desc.split('•')[0].strip() if '•' in desc else flt_id))
        subtitle = str(cfg.get('subtitle') or desc)

        href = str(cfg.get('href') or f"index_{folder_name}.html")
        charts_subdir = str(cfg.get('charts_subdir') or f"hotel-charts/{folder_name}")

        detected_group = detect_group_for_config(cfg, known=known_groups)

        discovered_flts[flt_id] = {
            'id': flt_id,
            'title': title,
            'subtitle': subtitle,
            'href': href,
            'charts_subdir': charts_subdir,
            'config': rel,
            'data_dir': data_dir,
            'modules': cfg.get('modules', {}),
            'germany_params': cfg.get('germany_params', {}),
            'origin_group_id': detected_group,
        }

    active_items: List[Dict[str, Any]] = []
    for flt_id, flt in discovered_flts.items():
        ovr = meta_filters.get(flt_id) or meta_filters.get(flt.get('config', '')) or {}

        # Status: active, paused, archived, deleted
        flt['status'] = str(ovr.get('status') or flt.get('status') or 'active').lower()
        if flt['status'] == 'deleted':
            continue

        if ovr.get('title'):
            flt['title'] = ovr['title']
        if ovr.get('subtitle'):
            flt['subtitle'] = ovr['subtitle']
        if ovr.get('pinned') is not None:
            flt['pinned'] = bool(ovr['pinned'])
        if ovr.get('order') is not None:
            flt['order'] = int(ovr['order'])

        assigned_group = str(ovr.get('group') or flt.get('origin_group_id') or 'custom').lower()
        if assigned_group not in known_groups:
            known_groups[assigned_group] = {
                'id': assigned_group,
                'label': assigned_group.capitalize(),
                'icon': '✨',
            }
        flt['group_id'] = assigned_group
        active_items.append(flt)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for flt in active_items:
        gid = flt['group_id']
        grouped.setdefault(gid, []).append(flt)

    final_groups: List[Dict[str, Any]] = []
    all_group_ids = list(known_groups.keys())
    for gid in grouped.keys():
        if gid not in all_group_ids:
            all_group_ids.append(gid)

    for gid in all_group_ids:
        if gid not in grouped or not grouped[gid]:
            continue
        g_meta = known_groups.get(gid, {'id': gid, 'label': gid.capitalize(), 'icon': '✨'})
        items = grouped[gid]
        items.sort(key=lambda x: (not x.get('pinned', False), x.get('order', 999), x.get('title', '')))
        final_groups.append({
            'id': g_meta['id'],
            'label': g_meta['label'],
            'icon': g_meta['icon'],
            'filters': items,
        })

    return final_groups


def is_filter_paused(flt: Dict[str, Any]) -> bool:
    """True if filter monitoring is paused by admin."""
    status = str(flt.get('status') or '').lower()
    return status == 'paused' or flt.get('paused') is True or flt.get('enabled') is False


def is_filter_deleted(flt: Dict[str, Any]) -> bool:
    """True if filter was soft-deleted."""
    return str(flt.get('status') or '').lower() == 'deleted'


def is_filter_archived(flt: Dict[str, Any], *, today: Optional[date] = None) -> bool:
    """Return True if filter is retired, expired, or marked as archived."""
    if str(flt.get('status') or '').lower() == 'archived' or bool(flt.get('archived')):
        return True
    config_path = str(flt.get('config') or '').strip()
    if not config_path:
        return False
    return should_skip_monitor_config(config_path, today=today)


def should_scrape_filter(flt: Dict[str, Any], *, today: Optional[date] = None) -> bool:
    """Returns True if filter should be scraped by hourly cron monitoring."""
    if is_filter_paused(flt):
        return False
    if is_filter_archived(flt, today=today):
        return False
    if is_filter_deleted(flt):
        return False
    return True


def is_filter_active(flt: Dict[str, Any], *, today: Optional[date] = None) -> bool:
    """True for active/visible filters on the landing page (not archived/deleted)."""
    if is_filter_archived(flt, today=today):
        return False
    if is_filter_deleted(flt):
        return False
    return True


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
    """Returns list of all active config file paths to be monitored in parallel."""
    configs = []
    for _, flt in iter_filters():
        if not should_scrape_filter(flt):
            continue
        cfg_path = flt.get('config')
        if cfg_path and (ROOT / cfg_path).is_file():
            configs.append(cfg_path)

    for any_cfg in ROOT.glob('config_ci_*_any_airports.json'):
        rel = str(any_cfg.relative_to(ROOT))
        parent_rel = rel.replace('_any_airports.json', '.json')
        if parent_rel in configs and rel not in configs:
            configs.append(rel)

    return sorted(list(set(configs)))


def get_all_dashboard_configs() -> List[Dict[str, Any]]:
    """Returns list of dashboard definitions for run_dashboards_parallel.py."""
    dashboards = []
    for _, flt in iter_filters():
        if is_filter_deleted(flt):
            continue
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
            "status": flt.get('status', 'active'),
        }
        if c_data.get('display_price_ceiling'):
            d_item['display_price_ceiling'] = str(c_data['display_price_ceiling'])
        if c_data.get('history_price_ceiling'):
            d_item['history_price_ceiling'] = str(c_data['history_price_ceiling'])

        any_ap_csv = f"{data_dir}/travel_prices_any_airports.csv"
        if not (ROOT / any_ap_csv).is_file():
            candidates = []
            haystack = f"{data_dir} {flt.get('title', '')} {flt.get('href', '')}".lower()
            if any(k in haystack for k in ["egypt", "egipt", "египет", "7_10", "13_16"]):
                candidates.extend([
                    "data/filters/filter_egypt_autumn_2026_7_10_days/travel_prices_any_airports.csv",
                    "data/filters/filter_egypt_autumn_2026_13_16_days/travel_prices_any_airports.csv",
                    "data/egypt_travel_prices_any_airports.csv",
                ])
            if any(k in haystack for k in ["turkey", "turcja", "турция"]):
                candidates.append("data/turkey_travel_prices_any_airports.csv")
            candidates.append("data/travel_prices_any_airports.csv")

            for c in candidates:
                if (ROOT / c).is_file():
                    any_ap_csv = c
                    break

        if (ROOT / any_ap_csv).is_file():
            d_item['all_airports_data'] = any_ap_csv

        dashboards.append(d_item)
    return dashboards


def get_all_germany_configs() -> List[str]:
    """Returns list of config paths that should have Check24 German packages scraped."""
    configs = []
    for _, flt in iter_filters():
        if not should_scrape_filter(flt):
            continue
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


def get_filters_admin_manifest() -> Dict[str, Any]:
    """
    Returns rich manifest of all filters with metrics for admin dashboard.
    """
    discovered = discover_filter_groups()
    known = get_known_groups()

    items = []
    for group in discovered:
        for flt in group['filters']:
            flt_id = flt['id']
            data_dir_path = ROOT / flt.get('data_dir', f"data/filters/{flt_id}")
            csv_path = data_dir_path / 'travel_prices.csv'
            dashboard_path = ROOT / flt.get('href', '')

            offers_count = 0
            min_price = None
            csv_size_kb = 0.0
            last_scraped_iso = None

            if csv_path.is_file():
                try:
                    stat = csv_path.stat()
                    csv_size_kb = round(stat.st_size / 1024.0, 1)
                    last_scraped_iso = datetime.fromtimestamp(stat.st_mtime).isoformat()
                    with csv_path.open('r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    if len(lines) > 1:
                        offers_count = len(lines) - 1
                        prices = []
                        for line in lines[-100:]:
                            parts = line.split(',')
                            if len(parts) >= 2:
                                try:
                                    p = float(parts[1])
                                    if p > 0:
                                        prices.append(p)
                                except (ValueError, IndexError):
                                    pass
                        if prices:
                            min_price = round(min(prices), 2)
                except Exception:
                    pass

            status = 'paused' if is_filter_paused(flt) else ('archived' if is_filter_archived(flt) else 'active')

            items.append({
                'id': flt_id,
                'title': flt.get('title', flt_id),
                'subtitle': flt.get('subtitle', ''),
                'href': flt.get('href', ''),
                'charts_subdir': flt.get('charts_subdir', ''),
                'config': flt.get('config', ''),
                'group_id': group['id'],
                'group_label': group['label'],
                'group_icon': group['icon'],
                'status': status,
                'pinned': bool(flt.get('pinned', False)),
                'order': flt.get('order', 999),
                'data_dir': str(flt.get('data_dir', '')),
                'offers_count': offers_count,
                'min_price': min_price,
                'csv_size_kb': csv_size_kb,
                'last_scraped_iso': last_scraped_iso,
                'has_dashboard': dashboard_path.is_file(),
            })

    return {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'groups': known,
        'filters': items,
        'counts': {
            'total': len(items),
            'active': sum(1 for x in items if x['status'] == 'active'),
            'paused': sum(1 for x in items if x['status'] == 'paused'),
            'archived': sum(1 for x in items if x['status'] == 'archived'),
        }
    }

