#!/usr/bin/env python3
"""Helpers for marathon schedules (per-day / rotating collection tags).

A marathon schedule is an ordered list of rules:
    {"tag_name": str, "active_days": [1..7] | None}
where 1=Monday .. 7=Sunday, None means all days. Table order defines the
rotation order when several rules match the same weekday.
"""

from __future__ import annotations
from typing import List, Optional

DAY_NAMES_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def normalize_marathon_schedule(schedule) -> List[dict]:
    """Return a clean list of {tag_name, active_days} dicts."""
    cleaned: List[dict] = []
    if not schedule:
        return cleaned
    for entry in schedule:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("tag_name", "") or "").strip()
        if not name:
            continue
        days = entry.get("active_days", None)
        if days is None:
            norm_days = None
        else:
            try:
                vals = sorted({int(d) for d in days if 1 <= int(d) <= 7})
            except (TypeError, ValueError):
                vals = []
            norm_days = vals or []
            if len(norm_days) == 7:
                norm_days = None
        cleaned.append({"tag_name": name, "active_days": norm_days})
    return cleaned


def migrate_legacy_marathon(marathon_tag_name: str = "",
                            active_days: Optional[List[int]] = None,
                            schedule: Optional[List[dict]] = None) -> List[dict]:
    """Migrate legacy single tag + days to a schedule list."""
    sched = normalize_marathon_schedule(schedule)
    if sched:
        return sched
    name = str(marathon_tag_name or "").strip()
    if not name:
        return []
    if active_days:
        try:
            vals = sorted({int(d) for d in active_days if 1 <= int(d) <= 7})
        except (TypeError, ValueError):
            vals = []
        days = vals or None
        if days is not None and len(days) == 7:
            days = None
    else:
        days = None
    return [{"tag_name": name, "active_days": days}]


def marathon_entries_for_weekday(schedule: Optional[List[dict]],
                                 weekday_1mon: int) -> List[dict]:
    """Return schedule entries covering the given 1-based weekday, in order."""
    result = []
    for entry in normalize_marathon_schedule(schedule):
        days = entry.get("active_days", None)
        if days is None or weekday_1mon in days:
            result.append(entry)
    return result


def is_marathon_active_on_weekday(schedule: Optional[List[dict]],
                                 weekday_1mon: int) -> bool:
    return len(marathon_entries_for_weekday(schedule, weekday_1mon)) > 0


def resolve_marathon_tag_name(schedule: Optional[List[dict]],
                              weekday_1mon: int,
                              occurrence_index: int = 0) -> str:
    """Pick the tag for one weekday occurrence (rotation by table order)."""
    matches = marathon_entries_for_weekday(schedule, weekday_1mon)
    if not matches:
        return ""
    return matches[occurrence_index % len(matches)].get("tag_name", "")


def summarize_marathon_schedule(schedule: Optional[List[dict]],
                                legacy_tag: str = "",
                                legacy_days: Optional[List[int]] = None) -> str:
    """Compact summary e.g. 'Marathon: 2 rules (Sun: A/B rotation, Mon: C)'."""
    sched = normalize_marathon_schedule(schedule)
    if not sched and legacy_tag:
        sched = migrate_legacy_marathon(legacy_tag, legacy_days)
    if not sched:
        return "Marathon"
    if len(sched) == 1:
        e = sched[0]
        days = e.get("active_days", None)
        suffix = "" if days is None else f" ({','.join(DAY_NAMES_SHORT[d - 1] for d in days)})"
        return f"Marathon: {e.get('tag_name', '')}{suffix}"
    # Group tags per weekday to show rotations.
    parts = []
    for wd in range(1, 8):
        tags = [e.get("tag_name", "") for e in marathon_entries_for_weekday(sched, wd)]
        if not tags:
            continue
        label = DAY_NAMES_SHORT[wd - 1]
        if len(tags) == 1:
            parts.append(f"{label}: {tags[0]}")
        else:
            parts.append(f"{label}: {'/'.join(tags)} rotation")
    detail = ", ".join(parts) if parts else f"{len(sched)} rules"
    return f"Marathon: {len(sched)} rules ({detail})"
