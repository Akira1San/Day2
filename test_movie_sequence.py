#!/usr/bin/env python3
"""Test suite for Movie Sequence Mode feature."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime
from utils import extract_movie_sequence_key, group_videos_by_movie
from scheduler import ScheduleGenerator
from data_models import Tag, TagManager

def test_extract_movie_sequence_key():
    """Test filename parsing for movie sequence grouping."""
    print("\n=== Testing extract_movie_sequence_key ===")
    
    test_cases = [
        ({'name': 'Movie 1 Part 1', 'path': 'Movie 1 Part 1.mp4'}, (1, 1)),
        ({'name': 'Movie 1 Part 2', 'path': 'Movie 1 Part 2.mp4'}, (1, 2)),
        ({'name': 'Movie 2 Part 1', 'path': 'Movie 2 Part 1.mp4'}, (2, 1)),
        ({'name': 'Film 3 x1',      'path': 'Film 3 x1.mp4'},      (3, 1)),
        ({'name': '1 - Video Name', 'path': '1 - Video Name.mp4'}, (1, 0)),
        ({'name': '2x03 - Episode', 'path': '2x03 - Episode.mp4'}, (2, 3)),
        ({'name': 'S01E02',         'path': 'S01E02.mp4'},         (1, 2)),
        ({'name': 'NoNumbersHere',  'path': 'NoNumbersHere.mkv'},  (1, 0)),
        ({'name': 'Movie 10 Part 5','path': 'Movie 10 Part 5.mp4'},(10, 5)),
        ({'name': 'Part 7',         'path': 'Part 7.mp4'},         (7, 0)),
    ]
    
    for video, expected in test_cases:
        result = extract_movie_sequence_key(video)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {video['name']:30s} -> {result} (expected {expected})")
        assert result == expected, f"Failed for {video['name']}: got {result}, expected {expected}"
    
    print("All extract_movie_sequence_key tests passed!")


def test_group_videos_by_movie():
    """Test grouping videos into movie buckets."""
    print("\n=== Testing group_videos_by_movie ===")
    
    videos = [
        {'id': 1, 'name': 'Movie 1 Part 1', 'path': '/movies/Movie 1 Part 1.mp4', 'duration': 90},
        {'id': 2, 'name': 'Movie 1 Part 2', 'path': '/movies/Movie 1 Part 2.mp4', 'duration': 95},
        {'id': 3, 'name': 'Movie 2 Part 1', 'path': '/movies/Movie 2 Part 1.mp4', 'duration': 100},
        {'id': 4, 'name': 'Movie 2 Part 2', 'path': '/movies/Movie 2 Part 2.mp4', 'duration': 105},
        {'id': 5, 'name': 'Movie 2 Part 3', 'path': '/movies/Movie 2 Part 3.mp4', 'duration': 110},
        {'id': 6, 'name': 'Movie 3',        'path': '/movies/Movie 3.mp4',       'duration': 120},
        # Duplicate by id (id=1) - should be filtered out
        {'id': 1, 'name': 'Movie 1 Part 1 copy', 'path': '/movies/Movie 1 Part 1 (copy).mp4', 'duration': 90},
    ]
    
    groups = group_videos_by_movie(videos)
    
    print(f"  Groups formed: {list(groups.keys())}")
    for movie_num, group_videos in groups.items():
        print(f"    Movie {movie_num}: {len(group_videos)} videos")
        for v in group_videos:
            print(f"      - id={v.get('id')} name={v.get('name')}")
    
    assert len(groups) == 3, f"Expected 3 movie groups, got {len(groups)}"
    assert 1 in groups and len(groups[1]) == 2, "Movie 1 should have 2 unique parts"
    assert 2 in groups and len(groups[2]) == 3, "Movie 2 should have 3 parts"
    assert 3 in groups and len(groups[3]) == 1, "Movie 3 should have 1 video"
    
    # Verify duplicate by id was removed
    all_ids = []
    for grp in groups.values():
        for v in grp:
            all_ids.append(v.get('id'))
    assert len(all_ids) == len(set(all_ids)), "Duplicate IDs should be removed"
    
    print("Deduplication by id: verified")
    print("All group_videos_by_movie tests passed!")


def test_get_videos_for_day():
    """Test _get_videos_for_day behavior for random vs movie_sequence modes."""
    print("\n=== Testing _get_videos_for_day ===")
    
    videos = [
        {'id': 1, 'name': 'Movie 1 Part 1', 'path': '/movies/Movie 1 Part 1.mp4', 'duration': 90},
        {'id': 2, 'name': 'Movie 1 Part 2', 'path': '/movies/Movie 1 Part 2.mp4', 'duration': 95},
        {'id': 3, 'name': 'Movie 2 Part 1', 'path': '/movies/Movie 2 Part 1.mp4', 'duration': 100},
        {'id': 4, 'name': 'Movie 2 Part 2', 'path': '/movies/Movie 2 Part 2.mp4', 'duration': 105},
        {'id': 5, 'name': 'Movie 3 Part 1', 'path': '/movies/Movie 3 Part 1.mp4', 'duration': 120},
    ]
    
    tag_manager = TagManager()
    gen = ScheduleGenerator(tag_manager)
    
    # Test Random mode
    gen.video_order_mode = 'random'
    random_results = []
    for day in range(3):
        vids = gen._get_videos_for_day(videos, day)
        random_results.append(vids)
        print(f"  Random mode, day {day}: {len(vids)} videos, shuffled")
    
    # All should have all 5 videos (shuffled differently)
    for i, res in enumerate(random_results):
        assert len(res) == 5, f"Random mode day {i} should have all 5 videos"
    
    # Test Movie Sequence mode
    gen.video_order_mode = 'movie_sequence'
    seq_results = []
    for day in range(5):
        vids = gen._get_videos_for_day(videos, day)
        seq_results.append(vids)
        movie_nums = [extract_movie_sequence_key(v)[0] for v in vids]
        print(f"  Movie Sequence, day {day}: movies={movie_nums}")
    
    # Day 0 -> Movie 1 (all parts)
    assert all(extract_movie_sequence_key(v)[0] == 1 for v in seq_results[0])
    # Day 1 -> Movie 2
    assert all(extract_movie_sequence_key(v)[0] == 2 for v in seq_results[1])
    # Day 2 -> Movie 3
    assert all(extract_movie_sequence_key(v)[0] == 3 for v in seq_results[2])
    # Day 3 -> wraps to Movie 1
    assert all(extract_movie_sequence_key(v)[0] == 1 for v in seq_results[3])
    # Day 4 -> wraps to Movie 2
    assert all(extract_movie_sequence_key(v)[0] == 2 for v in seq_results[4])
    
    print("All _get_videos_for_day tests passed!")


def test_build_random_entries_movie_sequence():
    """Test _build_random_entries correctly handles multi-day movie sequence."""
    print("\n=== Testing _build_random_entries (movie_sequence) ===")
    
    videos = [
        {'id': 1, 'name': 'Movie 1 Part 1', 'path': '/movies/Movie 1 Part 1.mp4', 'duration': 90},
        {'id': 2, 'name': 'Movie 1 Part 2', 'path': '/movies/Movie 1 Part 2.mp4', 'duration': 90},
        {'id': 3, 'name': 'Movie 2 Part 1', 'path': '/movies/Movie 2 Part 1.mp4', 'duration': 90},
        {'id': 4, 'name': 'Movie 2 Part 2', 'path': '/movies/Movie 2 Part 2.mp4', 'duration': 90},
        {'id': 5, 'name': 'Movie 2 Part 3', 'path': '/movies/Movie 2 Part 3.mp4', 'duration': 90},
        {'id': 6, 'name': 'Movie 3 Part 1', 'path': '/movies/Movie 3 Part 1.mp4', 'duration': 90},
    ]
    
    tag_manager = TagManager()
    gen = ScheduleGenerator(tag_manager)
    gen.video_order_mode = 'movie_sequence'
    
    # Test 2-day random fill (simulating 48h schedule)
    # Start at 0, end at 2*86400
    entries = gen._build_random_entries(videos, 0, 2 * 86400, "RandomFill")
    
    # Group entries by day
    day0_entries = [e for e in entries if e.start_seconds < 86400]
    day1_entries = [e for e in entries if 86400 <= e.start_seconds < 2*86400]
    
    print(f"  Day 0 entries: {len(day0_entries)}")
    for e in day0_entries:
        print(f"    {e.video_name}")
    
    print(f"  Day 1 entries: {len(day1_entries)}")
    for e in day1_entries:
        print(f"    {e.video_name}")
    
    # Check that Day 0 only contains Movie 1 parts
    day0_movies = set()
    for e in day0_entries:
        name = e.video_name
        # Extract from "RandomFill - Movie 1 Part 1.mp4"
        if "Movie 1" in name:
            day0_movies.add(1)
        elif "Movie 2" in name:
            day0_movies.add(2)
        elif "Movie 3" in name:
            day0_movies.add(3)
    
    print(f"  Day 0 unique movie numbers: {day0_movies}")
    assert len(day0_movies) == 1, f"Day 0 should contain only 1 movie group, found {day0_movies}"
    
    # Day 1 should contain exactly 1 movie group (Movie 2)
    day1_movies = set()
    for e in day1_entries:
        name = e.video_name
        if "Movie 1" in name:
            day1_movies.add(1)
        elif "Movie 2" in name:
            day1_movies.add(2)
        elif "Movie 3" in name:
            day1_movies.add(3)
    
    print(f"  Day 1 unique movie numbers: {day1_movies}")
    assert len(day1_movies) == 1, f"Day 1 should contain only 1 movie group, found {day1_movies}"
    
    print("All _build_random_entries tests passed!")


def test_custom_tag_movie_sequence():
    """Test custom tag with movie_sequence mode."""
    print("\n=== Testing custom tag with movie_sequence ===")
    
    videos = [
        {'id': 1, 'name': 'Movie 1 Part 1', 'path': '/movies/Movie 1 Part 1.mp4', 'duration': 90},
        {'id': 2, 'name': 'Movie 1 Part 2', 'path': '/movies/Movie 1 Part 2.mp4', 'duration': 90},
        {'id': 3, 'name': 'Movie 2 Part 1', 'path': '/movies/Movie 2 Part 1.mp4', 'duration': 90},
        {'id': 4, 'name': 'Movie 2 Part 2', 'path': '/movies/Movie 2 Part 2.mp4', 'duration': 90},
    ]
    
    tag_manager = TagManager()
    gen = ScheduleGenerator(tag_manager)
    gen.video_order_mode = 'movie_sequence'
    
    # Create a custom tag from 00:00 to 02:00 (2 hours = 120 minutes = 7200 seconds)
    custom_tag = Tag(
        name="Movies",
        tag_type="custom",
        start_time="00:00",
        end_time="02:00",
        collection_videos=videos,
        video_count=4  # Want to show 4 videos
    )
    
    # Convert to QTime objects (as used by the scheduler)
    custom_tag.start_time = QTime(0, 0)
    custom_tag.end_time = QTime(2, 0)
    
    entries = []
    gen._process_custom_tag(custom_tag, entries, set(), start_offset=0)
    
    print(f"  Generated {len(entries)} entries:")
    for e in entries:
        print(f"    {e.video_name}")
    
    # Should contain only Movie 1 parts (since day_offset=0 picks movie 1)
    movie_nums = set()
    for e in entries:
        # Entry created via _create_video_entry includes tag name prefix: "Movies - ..."
        vid_name = e.video_name.split(" - ")[-1] if " - " in e.video_name else e.video_name
        movie_num = extract_movie_sequence_key({'name': vid_name, 'path': vid_name})[0]
        movie_nums.add(movie_num)
    
    print(f"  Movie numbers used: {movie_nums}")
    assert len(movie_nums) == 1, f"Custom tag should use only 1 movie group, got {movie_nums}"
    
    print("All custom tag tests passed!")


if __name__ == "__main__":
    try:
        test_extract_movie_sequence_key()
        test_group_videos_by_movie()
        test_get_videos_for_day()
        test_build_random_entries_movie_sequence()
        test_custom_tag_movie_sequence()
        print("\n" + "="*50)
        print("ALL TESTS PASSED!")
        print("="*50)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
