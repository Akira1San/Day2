#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/akira/akira/day2')
from PySide6.QtCore import QTime
from models import TagManager, Tag, ScheduleGenerator
from datetime import date

DAY = 3600

def make_video(name, tags, duration=DAY):
    return {'name': name, 'path': f'/videos/{name}.mp4', '_meta_tags': tags, 'duration': duration}

def test_marathon_filtering():
    tm = TagManager()
    t = Tag('random', 'MarathonRF', QTime(0,0), QTime(23,59),
        collection_videos=[
            make_video('ep1', ['Episodic']),
            make_video('movie1', ['Movie']),
        ],
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='Episodic')
    sg = ScheduleGenerator(tm)
    filtered = sg._get_marathon_videos(t, 0)
    assert len(filtered) == 1, f'Expected 1, got {len(filtered)}'
    assert filtered[0]['name'] == 'ep1'
    print('  marathon_filtering OK')

def test_marathon_serialization():
    from serialization import serialize_tag_to_string, deserialize_tag_from_string
    t = Tag('random', 'RF', QTime(0,0), QTime(23,59),
        collection_videos=[make_video('v', ['Episodic'])],
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='Episodic')
    s = serialize_tag_to_string(t)
    assert 'marathon_mode = true' in s
    assert 'marathon_tag_name = Episodic' in s
    loaded = deserialize_tag_from_string(s, Tag, QTime.fromString)
    assert loaded.marathon_mode == True
    assert loaded.marathon_tag_name == 'Episodic'
    assert loaded.fill_24h == True
    print('  marathon_serialization OK')

def test_marathon_active_days_single_day():
    """Marathon only on Monday; verify Tue/Wed fall back to unfiltered fill."""
    tm = TagManager()
    tm.add_tag(Tag('random', 'M', QTime(0,0), QTime(23,59),
        collection_videos=[
            make_video('ep1', ['Episodic']),
            make_video('movie1', ['Movie']),
        ],
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='Episodic',
        active_days=[1]))  # Monday
    sg = ScheduleGenerator(tm)
    sg.schedule_start_weekday = 0  # Monday
    result = sg.apply_custom_tags(use_cache=False, num_days=3)

    from collections import defaultdict
    by_day = defaultdict(set)
    for e in result:
        day = (e.start_seconds // 86400) + 1
        name = e.video_name.split('/')[-1].split(' - ')[-1] if ' - ' in e.video_name else e.video_name
        by_day[day].add(name)

    assert by_day[1] == {'ep1.mp4'}, f'Day 1 expected only ep1, got {by_day[1]}'
    assert 'movie1.mp4' in by_day[2], f'Day 2 expected movie1, got {by_day[2]}'
    assert 'movie1.mp4' in by_day[3], f'Day 3 expected movie1, got {by_day[3]}'
    print('  marathon_active_days_single_day OK')

def test_marathon_no_custom_tags():
    """Only marathon RF tag, no custom tags - fast-path avoidance."""
    tm = TagManager()
    tm.add_tag(Tag('random', 'M', QTime(0,0), QTime(23,59),
        collection_videos=[
            make_video('ep1', ['Episodic']),
            make_video('movie1', ['Movie']),
        ],
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='Episodic',
        active_days=[1]))
    sg = ScheduleGenerator(tm)
    sg.schedule_start_weekday = 2  # Wednesday
    result = sg.apply_custom_tags(use_cache=False, num_days=2)
    from collections import defaultdict
    by_day = defaultdict(set)
    for e in result:
        day = (e.start_seconds // 86400) + 1
        name = e.video_name.split('/')[-1].split(' - ')[-1] if ' - ' in e.video_name else e.video_name
        by_day[day].add(name)
    # Day 1 = Wed (not active) -> both videos
    assert 'movie1.mp4' in by_day[1], f'Day 1 expected movie1, got {by_day[1]}'
    # Day 2 = Thu (not active) -> both videos
    assert 'movie1.mp4' in by_day[2], f'Day 2 expected movie1, got {by_day[2]}'
    print('  marathon_no_custom_tags OK')

def test_marathon_with_custom_tag():
    """Marathon RF + custom tag: custom tag placed, marathon handles days."""
    tm = TagManager()
    tm.add_tag(Tag('random', 'M', QTime(0,0), QTime(23,59),
        collection_videos=[
            make_video('ep1', ['Episodic']),
            make_video('movie1', ['Movie']),
        ],
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='Episodic',
        active_days=[1, 2]))  # Mon, Tue
    tm.add_tag(Tag('custom', 'Show', QTime(12,0), QTime(13,0),
        collection_videos=[make_video('show1', [])],
        video_count=1))
    sg = ScheduleGenerator(tm)
    sg.schedule_start_weekday = 0  # Monday
    result = sg.apply_custom_tags(use_cache=False, num_days=4)

    from collections import defaultdict
    by_day = defaultdict(set)
    for e in result:
        day = (e.start_seconds // 86400) + 1
        name = e.video_name.split('/')[-1].split(' - ')[-1] if ' - ' in e.video_name else e.video_name
        by_day[day].add(name)
    # Day 1 (Mon) active -> only ep1 or Show
    assert 'ep1.mp4' in by_day[1], f'Day 1 expected ep1, got {by_day[1]}'
    # Day 3 (Wed) inactive -> movie1 appears
    assert 'movie1.mp4' in by_day[3], f'Day 3 expected movie1, got {by_day[3]}'
    print('  marathon_with_custom_tag OK')

def test_marathon_all_days_default():
    """Marathon with no active_days (= all days) should filter on every day."""
    tm = TagManager()
    tm.add_tag(Tag('random', 'M', QTime(0,0), QTime(23,59),
        collection_videos=[
            make_video('ep1', ['Episodic']),
            make_video('movie1', ['Movie']),
        ],
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='Episodic'))
    sg = ScheduleGenerator(tm)
    result = sg.apply_custom_tags(use_cache=False, num_days=2)
    for e in result:
        name = e.video_name.split('/')[-1].split(' - ')[-1] if ' - ' in e.video_name else e.video_name
        assert 'ep1' in name, f'Expected only ep1, got {name}'
    print('  marathon_all_days_default OK')

def test_non_marathon_unaffected():
    """Regular random fill without marathon mode should play all videos."""
    tm = TagManager()
    tm.add_tag(Tag('random', 'RF', QTime(0,0), QTime(23,59),
        collection_videos=[
            make_video('ep1', ['Episodic']),
            make_video('movie1', ['Movie']),
        ],
        is_random_fill=True, fill_24h=True))
    sg = ScheduleGenerator(tm)
    result = sg.apply_custom_tags(use_cache=False, num_days=1)
    names = set(e.video_name for e in result)
    assert 'ep1.mp4' in names
    assert 'movie1.mp4' in names
    print('  non_marathon_unaffected OK')

def test_hero_collection():
    """Test marathon with real Hero test tag collection JSON."""
    from utils import load_collection_json, load_collection_videos_only

    # Load via dialog path (load_collection_json) — sets _meta_tags
    videos, info = load_collection_json('Hero test tag.json')
    assert len(videos) == 24
    for v in videos:
        assert '_meta_tags' in v, f'Missing _meta_tags'
        assert 'HIRO' in v['_meta_tags'], f'Expected HIRO tag'
    print(f'  hero_load_collection_json OK ({len(videos)} videos)')

    # Load via cold-load path (load_collection_videos_only) — used by serialization
    v2 = load_collection_videos_only('Hero test tag.json')
    assert len(v2) == 24
    for v in v2:
        assert '_meta_tags' in v, f'Missing _meta_tags in cold-load'
    print(f'  hero_load_collection_videos_only OK ({len(v2)} videos)')

    # Marathon filtering with real data
    tm = TagManager()
    sg = ScheduleGenerator(tm)
    t = Tag('random', 'Hero', QTime(0,0), QTime(23,59),
        collection_videos=videos,
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='HIRO')
    filtered = sg._get_marathon_videos(t, 0)
    assert len(filtered) == len(videos), f'Expected all {len(videos)}, got {len(filtered)}'
    print(f'  hero_marathon_filter OK ({len(filtered)} videos)')

    # Marathon on Monday only, start Tuesday — inactive day uses unfiltered videos
    tm2 = TagManager()
    tm2.add_tag(Tag('random', 'Hero', QTime(0,0), QTime(23,59),
        collection_videos=videos,
        is_random_fill=True, fill_24h=True,
        marathon_mode=True, marathon_tag_name='HIRO',
        active_days=[1]))  # Monday only
    sg2 = ScheduleGenerator(tm2)
    sg2.schedule_start_weekday = 1  # Tuesday → Day1 = Tue (inactive), Day2 = Wed (inactive)
    result = sg2.apply_custom_tags(use_cache=False, num_days=2)
    assert len(result) > 0
    print(f'  hero_active_days OK ({len(result)} entries across 2 inactive days)')


if __name__ == '__main__':
    tests = [
        test_marathon_filtering,
        test_marathon_serialization,
        test_marathon_active_days_single_day,
        test_marathon_no_custom_tags,
        test_marathon_with_custom_tag,
        test_marathon_all_days_default,
        test_non_marathon_unaffected,
        test_hero_collection,
    ]
    for t in tests:
        t()
    print(f'\nAll {len(tests)} tests passed.')
