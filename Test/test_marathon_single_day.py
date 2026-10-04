#!/usr/bin/env python3
"""Marathon single-day semantics (no repeat) + video-pool validation.

Agreed behavior: a checked weekday fires only on its FIRST occurrence in
the generated preview (e.g. Monday-only rule -> first Monday only, later
Mondays fall back to normal unfiltered fill). Rotation is removed.

Bug context (TatkoTV): `collections_TatkoTV_blacklist.json` excludes 14 of
the 15 'Sylvester Stallone' videos, so the marathon pool collapses to a
single video repeated all day. These tests lock in both the schedule
semantics and the pool-size validation.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import defaultdict
from PySide6.QtCore import QTime
from models import TagManager, Tag, ScheduleGenerator

DAY = 3600


def make_video(name, tags, duration=DAY, collection_id=""):
    v = {'name': name, 'path': f'/videos/{name}.mp4', '_meta_tags': tags,
         'duration': duration}
    if collection_id:
        v['collection_id'] = collection_id
    return v


def marathon_tag(videos, schedule, marathon_tag_name="", active_days=None):
    return Tag('random', 'M', QTime(0, 0), QTime(23, 59),
               collection_videos=videos,
               is_random_fill=True, fill_24h=True,
               marathon_mode=True,
               marathon_tag_name=marathon_tag_name,
               marathon_schedule=schedule,
               active_days=active_days)


def distinct_by_day(entries):
    by_day = defaultdict(set)
    for e in entries:
        day = (e.start_seconds // 86400) + 1
        name = e.video_name.split('/')[-1].split(' - ')[-1] if ' - ' in e.video_name else e.video_name
        by_day[day].add(name)
    return by_day


def test_first_monday_only_30d():
    """Monday-only rule: only the first Monday is marathon, later Mondays are normal fill."""
    tm = TagManager()
    tm.add_tag(marathon_tag(
        [make_video('ep1', ['Stallone']), make_video('movie1', ['Other'])],
        [{'tag_name': 'Stallone', 'active_days': [1]}],
        marathon_tag_name='Stallone', active_days=[1]))
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 6  # Sunday; Mondays at offsets 1, 8, 15, 22, 29
    result = sg.apply_custom_tags(use_cache=False, num_days=30)
    by_day = distinct_by_day(result)
    # Day 2 = first Monday -> only Stallone
    assert by_day[2] == {'ep1.mp4'}, f'Day 2 (Mon1) expected only ep1, got {by_day[2]}'
    # Later Mondays (days 9, 16, 23, 30) -> normal fill, must include non-Stallone
    for day in (9, 16, 23, 30):
        assert 'movie1.mp4' in by_day[day], f'Day {day} (later Mon) expected normal fill, got {by_day[day]}'
    print('  first_monday_only_30d OK')


def test_mon_tue_each_once():
    """Mon+Tue rule: first Mon and first Tue each marathon once, then never again."""
    tm = TagManager()
    tm.add_tag(marathon_tag(
        [make_video('ep1', ['Stallone']), make_video('movie1', ['Other'])],
        [{'tag_name': 'Stallone', 'active_days': [1, 2]}],
        marathon_tag_name='Stallone', active_days=[1, 2]))
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 6  # Sunday; Mon=1, Tue=2, next Mon=8, next Tue=9
    result = sg.apply_custom_tags(use_cache=False, num_days=14)
    by_day = distinct_by_day(result)
    assert by_day[2] == {'ep1.mp4'}, f'Day 2 (Mon1) expected only ep1, got {by_day[2]}'
    assert by_day[3] == {'ep1.mp4'}, f'Day 3 (Tue1) expected only ep1, got {by_day[3]}'
    assert 'movie1.mp4' in by_day[9], f'Day 9 (Mon2) expected normal fill, got {by_day[9]}'
    assert 'movie1.mp4' in by_day[10], f'Day 10 (Tue2) expected normal fill, got {by_day[10]}'
    print('  mon_tue_each_once OK')


def test_all_days_first_week_only():
    """All-days rule: first 7 preview days marathon, day 8+ normal fill (no repeat)."""
    tm = TagManager()
    tm.add_tag(marathon_tag(
        [make_video('ep1', ['Stallone']), make_video('movie1', ['Other'])],
        [{'tag_name': 'Stallone', 'active_days': None}]))
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 0  # Monday
    result = sg.apply_custom_tags(use_cache=False, num_days=10)
    by_day = distinct_by_day(result)
    for day in range(1, 8):
        assert by_day[day] == {'ep1.mp4'}, f'Day {day} expected only ep1, got {by_day[day]}'
    assert 'movie1.mp4' in by_day[8], f'Day 8 expected normal fill, got {by_day[8]}'
    print('  all_days_first_week_only OK')


def test_no_rotation_first_row_wins():
    """Two rows on the same weekday: no rotation, first row always wins (single firing)."""
    tm = TagManager()
    t = marathon_tag(
        [make_video('a1', ['EpA']), make_video('b1', ['EpB'])],
        [{'tag_name': 'EpA', 'active_days': [7]},
         {'tag_name': 'EpB', 'active_days': [7]}])
    tm.add_tag(t)
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 0  # Monday; Sunday at offset 6 only within 7 days
    assert sg._resolve_marathon_tag_name(t, 6) == 'EpA'
    assert sg._is_marathon_active_on_day(t, 6) is True
    print('  no_rotation_first_row_wins OK')


def test_normalized_tag_match():
    """Tag matching is case/whitespace-insensitive ('sylvester stallone' == 'Sylvester Stallone')."""
    tm = TagManager()
    t = marathon_tag(
        [make_video('ep1', ['Sylvester Stallone']), make_video('movie1', ['Other'])],
        [{'tag_name': '  sylvester stallone ', 'active_days': [1]}])
    tm.add_tag(t)
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 0  # Monday
    filtered = sg._get_marathon_videos(t, 0)
    assert len(filtered) == 1 and filtered[0]['name'] == 'ep1', f'Expected [ep1], got {[v["name"] for v in filtered]}'
    print('  normalized_tag_match OK')


def test_blacklist_collapse_repro():
    """Repro of the TatkoTV report: blacklist leaves 1 Stallone video -> repeated all day."""
    from utils import filter_videos_by_blacklist
    vids = [make_video(f's{i}', ['Stallone'], collection_id=f'stall_{i}') for i in range(15)]
    vids += [make_video('movie1', ['Other'], collection_id='other_1')]
    blacklist = [{'video_id': f'stall_{i}'} for i in range(14)]  # as in collections_TatkoTV_blacklist.json
    remaining = filter_videos_by_blacklist(vids, blacklist)
    stall_left = [v for v in remaining if 'Stallone' in v.get('_meta_tags', [])]
    assert len(stall_left) == 1, f'Expected pool collapse to 1, got {len(stall_left)}'
    # Scheduler consequence: marathon day contains only that video
    tm = TagManager()
    tm.add_tag(marathon_tag(remaining,
                            [{'tag_name': 'Stallone', 'active_days': [1]}],
                            marathon_tag_name='Stallone', active_days=[1]))
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 0  # Monday
    result = sg.apply_custom_tags(use_cache=False, num_days=1)
    by_day = distinct_by_day(result)
    assert by_day[1] == {'s14.mp4'}, f'Expected single-video day, got {by_day[1]}'
    print('  blacklist_collapse_repro OK (documents Bug 1 mechanism)')


def test_validate_marathon_schedule():
    """Pool-size validation: 0 matches -> error, 1 match -> warning, 2+ -> clean."""
    from utils_marathon import validate_marathon_schedule
    vids = [make_video('a', ['TagA']), make_video('b', ['TagA']), make_video('c', ['TagC'])]
    errors, warnings = validate_marathon_schedule(
        [{'tag_name': 'Missing', 'active_days': [1]},
         {'tag_name': 'TagC', 'active_days': [1]},
         {'tag_name': 'TagA', 'active_days': [1]}], vids)
    assert any('Missing' in e for e in errors), f'Expected error for Missing, got {errors}'
    assert any('TagC' in w for w in warnings), f'Expected warning for TagC, got {warnings}'
    assert not any('TagA' in e for e in errors), f'Unexpected error for TagA: {errors}'
    print('  validate_marathon_schedule OK')


def test_marathon_ignores_blacklist():
    """Marathon day plays blacklisted-tag videos; normal days still exclude them."""
    vids = [make_video(f's{i}', ['Stallone'], collection_id=f'stall_{i}') for i in range(15)]
    vids += [make_video('movie1', ['Other'], collection_id='other_1')]
    blacklist = [{'video_id': f'stall_{i}'} for i in range(14)]
    # Constructor must NOT pre-filter marathon tags (full pool kept).
    t = Tag('random', 'M', QTime(0, 0), QTime(23, 59),
            collection_videos=list(vids), blacklist=list(blacklist),
            is_random_fill=True, fill_24h=True,
            marathon_mode=True, marathon_tag_name='Stallone',
            marathon_schedule=[{'tag_name': 'Stallone', 'active_days': [1]}],
            active_days=[1])
    assert len(t.collection_videos) == 16, f'Marathon pool must stay full, got {len(t.collection_videos)}'
    tm = TagManager()
    tm.add_tag(t)
    sg = ScheduleGenerator(tm, exclude_missing=False)
    sg.schedule_start_weekday = 0  # Monday; offset 0 = marathon, 7+ = normal
    result = sg.apply_custom_tags(use_cache=False, num_days=8)
    by_day = distinct_by_day(result)
    assert len(by_day[1]) == 15, f'Marathon Monday expected 15 Stallone, got {by_day[1]}'
    assert 's0.mp4' not in by_day[8], f'Normal day must exclude blacklisted s0, got {by_day[8]}'
    assert 's14.mp4' in by_day[1] and 'movie1.mp4' in by_day[8]
    print('  marathon_ignores_blacklist OK')


def test_build_marathon_pool():
    """Helper: re-includes blacklist-excluded videos, no dupes, manual removals stay out."""
    from utils_marathon import build_marathon_pool
    full = [make_video(f's{i}', ['Stallone'], collection_id=f'stall_{i}') for i in range(15)]
    full += [make_video('other', ['Other'], collection_id='other_1')]
    blacklist = [{'video_id': f'stall_{i}'} for i in range(14)]
    # Added: user kept s14 but manually removed other_1 (not blacklisted).
    added = [v for v in full if v['collection_id'] == 'stall_14']
    pool = build_marathon_pool(added, full, blacklist)
    ids = {v.get('collection_id') for v in pool}
    assert len(pool) == 15, f'Expected 15 (14 re-included + s14), got {len(pool)}'
    assert 'stall_0' in ids and 'stall_14' in ids
    assert 'other_1' not in ids, 'Manually removed video must stay out of marathon pool'
    # Empty blacklist -> pool == added.
    pool2 = build_marathon_pool(added, full, [])
    assert len(pool2) == 1
    print('  build_marathon_pool OK')


def test_validate_uses_full_pool():
    """Validation against the effective (blacklist-exempt) pool reports no warning."""
    from utils_marathon import build_marathon_pool, validate_marathon_schedule
    full = [make_video(f's{i}', ['Stallone'], collection_id=f'stall_{i}') for i in range(15)]
    blacklist = [{'video_id': f'stall_{i}'} for i in range(14)]
    added = [v for v in full if v['collection_id'] == 'stall_14']
    pool = build_marathon_pool(added, full, blacklist)
    errors, warnings = validate_marathon_schedule(
        [{'tag_name': 'Stallone', 'active_days': [1]}], pool)
    assert errors == [] and warnings == [], f'Expected clean, got {errors} {warnings}'
    print('  validate_uses_full_pool OK')


if __name__ == '__main__':
    tests = [
        test_first_monday_only_30d,
        test_mon_tue_each_once,
        test_all_days_first_week_only,
        test_no_rotation_first_row_wins,
        test_normalized_tag_match,
        test_blacklist_collapse_repro,
        test_validate_marathon_schedule,
        test_marathon_ignores_blacklist,
        test_build_marathon_pool,
        test_validate_uses_full_pool,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f'  FAIL {t.__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed.')
    sys.exit(1 if failed else 0)
