#!/usr/bin/env python3
"""
CLI and Automation Engine for Filter & Dashboard Management.
Supports:
- pause / resume monitoring
- move filter to different category (group)
- archive / unarchive filter
- soft delete / restore filter
- pin / unpin filter
- update title / subtitle
- export frontend manifest (filters_manifest.json)
- process IssueOps payloads
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import filter_registry

AUTH_KEY_HASH = "e7bbd2753119f63d1bab83262e7cf7835286942712dd1caacd25d57f24b84a56"


def load_meta() -> Dict[str, Any]:
    return filter_registry.load_filters_meta()


def save_meta(meta: Dict[str, Any]) -> None:
    filter_registry.save_filters_meta(meta)


def resolve_filter_id(target: str) -> str:
    """Normalizes filter identifier from id, config path, or slug."""
    clean = target.strip()
    clean = clean.replace("config_ci_", "").replace("filter_", "").replace(".json", "")
    manifest = filter_registry.get_filters_admin_manifest()
    
    # Exact match on id
    for flt in manifest['filters']:
        if flt['id'] == target:
            return flt['id']
    # Match on config filename
    for flt in manifest['filters']:
        if target in flt.get('config', ''):
            return flt['id']
    # Match on stripped slug
    for flt in manifest['filters']:
        flt_slug = flt['id'].replace("filter_", "")
        if flt_slug == clean or flt['id'] == f"filter_{clean}":
            return flt['id']

    # Fallback to normalized target
    return target


def set_filter_status(filter_id: str, status: str) -> Dict[str, Any]:
    """Sets status for filter ('active', 'paused', 'archived', 'deleted')."""
    fid = resolve_filter_id(filter_id)
    valid_statuses = {'active', 'paused', 'archived', 'deleted'}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")

    meta = load_meta()
    flt_meta = meta['filters'].setdefault(fid, {})
    flt_meta['status'] = status
    flt_meta['updated_at'] = datetime.utcnow().isoformat() + "Z"
    save_meta(meta)
    return {'id': fid, 'status': status, 'updated_at': flt_meta['updated_at']}


def set_filter_group(
    filter_id: str,
    group_id: str,
    group_label: Optional[str] = None,
    group_icon: Optional[str] = None,
) -> Dict[str, Any]:
    """Reassigns filter to a category group, creating custom group if needed."""
    fid = resolve_filter_id(filter_id)
    gid = group_id.strip().lower()
    if not gid:
        raise ValueError("group_id cannot be empty")

    meta = load_meta()
    flt_meta = meta['filters'].setdefault(fid, {})
    flt_meta['group'] = gid
    flt_meta['updated_at'] = datetime.utcnow().isoformat() + "Z"

    # If new custom group definition provided
    if group_label:
        meta['custom_groups'][gid] = {
            'id': gid,
            'label': group_label,
            'icon': group_icon or "✨",
        }

    save_meta(meta)
    return {'id': fid, 'group': gid, 'updated_at': flt_meta['updated_at']}


def set_filter_pinned(filter_id: str, pinned: bool) -> Dict[str, Any]:
    """Pins or unpins filter to top of its group."""
    fid = resolve_filter_id(filter_id)
    meta = load_meta()
    flt_meta = meta['filters'].setdefault(fid, {})
    flt_meta['pinned'] = bool(pinned)
    flt_meta['updated_at'] = datetime.utcnow().isoformat() + "Z"
    save_meta(meta)
    return {'id': fid, 'pinned': flt_meta['pinned']}


def rename_filter(filter_id: str, title: Optional[str] = None, subtitle: Optional[str] = None) -> Dict[str, Any]:
    """Renames filter title and/or subtitle."""
    fid = resolve_filter_id(filter_id)
    meta = load_meta()
    flt_meta = meta['filters'].setdefault(fid, {})
    if title is not None and title.strip():
        flt_meta['title'] = title.strip()
    if subtitle is not None:
        flt_meta['subtitle'] = subtitle.strip()
    flt_meta['updated_at'] = datetime.utcnow().isoformat() + "Z"
    save_meta(meta)
    return {'id': fid, 'title': flt_meta.get('title'), 'subtitle': flt_meta.get('subtitle')}


def export_manifest(output_path: Path) -> Dict[str, Any]:
    """Exports filters manifest JSON to file."""
    manifest = filter_registry.get_filters_admin_manifest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def print_filter_table() -> None:
    """Prints a terminal-friendly table of all filters."""
    manifest = filter_registry.get_filters_admin_manifest()
    counts = manifest['counts']
    print(f"\n📊 Total: {counts['total']} | 🟢 Active: {counts['active']} | ⏸️ Paused: {counts['paused']} | 📦 Archived: {counts['archived']}\n")
    print(f"{'STATUS':<10} {'ID':<30} {'GROUP':<15} {'OFFERS':<8} {'MIN PLN':<10} {'TITLE'}")
    print("-" * 105)
    for flt in manifest['filters']:
        status_icon = "🟢 ACTIVE" if flt['status'] == 'active' else ("⏸️ PAUSED" if flt['status'] == 'paused' else "📦 ARCHIVED")
        min_p = f"{flt['min_price']} zł" if flt.get('min_price') else "—"
        offers = str(flt.get('offers_count') or 0)
        print(f"{status_icon:<10} {flt['id']:<30} {flt['group_label']:<15} {offers:<8} {min_p:<10} {flt['title'][:35]}")
    print()


def process_payload(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Processes an action payload (e.g. from IssueOps or API)."""
    # Security check: verify signature
    sig = str(payload_dict.get('signature') or payload_dict.get('auth_hash') or '')
    if sig != AUTH_KEY_HASH:
        raise PermissionError("Access denied: invalid or missing cryptographic signature.")

    action = str(payload_dict.get('action') or '').strip().lower()
    target = str(payload_dict.get('filter_id') or '').strip()

    if not action:
        raise ValueError("Missing 'action' in payload")
    if not target and action not in {'export_manifest', 'list'}:
        raise ValueError("Missing 'filter_id' in payload")

    if action in {'pause', 'stop'}:
        res = set_filter_status(target, 'paused')
        msg = f"⏸️ Мониторинг фильтра '{res['id']}' успешно приостановлен."
    elif action in {'resume', 'start', 'unpause', 'activate'}:
        res = set_filter_status(target, 'active')
        msg = f"▶️ Мониторинг фильтра '{res['id']}' возобновлён."
    elif action in {'archive'}:
        res = set_filter_status(target, 'archived')
        msg = f"📦 Фильтр '{res['id']}' перемещён в архив туров."
    elif action in {'delete', 'remove'}:
        res = set_filter_status(target, 'deleted')
        msg = f"🗑️ Фильтр '{res['id']}' удалён из мониторинга."
    elif action in {'set_group', 'move_group'}:
        group = str(payload_dict.get('group') or payload_dict.get('group_id') or '').strip()
        g_label = payload_dict.get('group_label')
        g_icon = payload_dict.get('group_icon')
        res = set_filter_group(target, group, g_label, g_icon)
        msg = f"🗂️ Фильтр '{res['id']}' перемещён в категорию '{res['group']}'."
    elif action in {'rename'}:
        title = payload_dict.get('title')
        subtitle = payload_dict.get('subtitle')
        res = rename_filter(target, title, subtitle)
        msg = f"✏️ Фильтр '{res['id']}' успешно переименован."
    elif action in {'pin'}:
        res = set_filter_pinned(target, True)
        msg = f"📌 Фильтр '{res['id']}' закреплён вверху категории."
    elif action in {'unpin'}:
        res = set_filter_pinned(target, False)
        msg = f"Фильтр '{res['id']}' откреплён."
    else:
        raise ValueError(f"Unknown action: '{action}'")

    return {
        'success': True,
        'action': action,
        'message': msg,
        'result': res,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter and Dashboard Management Tool")
    parser.add_argument("--filter", "-f", help="Target filter ID or config path")
    parser.add_argument(
        "--action", "-a",
        choices=["pause", "resume", "archive", "delete", "pin", "unpin", "set-group", "rename", "list"],
        help="Action to perform on target filter"
    )
    parser.add_argument("--set-group", "-g", help="Assign filter to category group ID")
    parser.add_argument("--group-label", help="Optional label for custom category")
    parser.add_argument("--group-icon", help="Optional icon emoji for custom category")
    parser.add_argument("--title", help="New title for rename action")
    parser.add_argument("--subtitle", help="New subtitle for rename action")
    parser.add_argument("--export-manifest", help="Export frontend manifest JSON to given path")
    parser.add_argument("--payload-file", help="Execute JSON payload from file (IssueOps)")
    parser.add_argument("--payload-json", help="Execute raw JSON payload string")
    parser.add_argument("--output-json", help="Write result as JSON to given file")

    args = parser.parse_args()
    result: Dict[str, Any] = {}

    try:
        if args.payload_file:
            with open(args.payload_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # Extract JSON block if inside markdown
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            raw = m.group(1).strip() if m else content.strip()
            data = json.loads(raw)
            result = process_payload(data)
            print(result.get('message', 'Payload executed successfully'))

        elif args.payload_json:
            data = json.loads(args.payload_json)
            result = process_payload(data)
            print(result.get('message', 'Payload executed successfully'))

        elif args.export_manifest:
            out_p = Path(args.export_manifest)
            manifest = export_manifest(out_p)
            print(f"✅ Manifest exported to {out_p} ({manifest['counts']['total']} filters)")

        elif args.action == "list" or (not args.action and not args.filter and not args.export_manifest):
            print_filter_table()

        elif args.filter:
            target = args.filter
            act = args.action

            if act == "pause":
                res = set_filter_status(target, "paused")
                print(f"⏸️ Filter '{res['id']}' set to PAUSED")
            elif act == "resume":
                res = set_filter_status(target, "active")
                print(f"▶️ Filter '{res['id']}' set to ACTIVE")
            elif act == "archive":
                res = set_filter_status(target, "archived")
                print(f"📦 Filter '{res['id']}' set to ARCHIVED")
            elif act == "delete":
                res = set_filter_status(target, "deleted")
                print(f"🗑️ Filter '{res['id']}' set to DELETED")
            elif act == "pin":
                res = set_filter_pinned(target, True)
                print(f"📌 Filter '{res['id']}' pinned")
            elif act == "unpin":
                res = set_filter_pinned(target, False)
                print(f"Filter '{res['id']}' unpinned")
            elif act == "set-group" or args.set_group:
                grp = args.set_group or ""
                res = set_filter_group(target, grp, args.group_label, args.group_icon)
                print(f"🗂️ Filter '{res['id']}' moved to group '{res['group']}'")
            elif act == "rename":
                res = rename_filter(target, args.title, args.subtitle)
                print(f"✏️ Filter '{res['id']}' renamed")
            else:
                parser.print_help()
                sys.exit(1)

        else:
            parser.print_help()
            sys.exit(0)

    except Exception as err:
        print(f"❌ Error: {err}", file=sys.stderr)
        if args.output_json:
            with open(args.output_json, 'w', encoding='utf-8') as f:
                json.dump({'success': False, 'error': str(err)}, f)
        sys.exit(1)

    if args.output_json and result:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
