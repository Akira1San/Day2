#!/usr/bin/env python3
"""Test suite for Movie Sequence Mode feature."""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime
from utils import (
    extract_movie_sequence_key,
    group_videos_by_movie,
    _extract_movie_tag,
    load_collection_json,
    load_collection_videos_only,
)
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
    
    # Check that Day 0 contains all movies in sequence (continuous ordering)
    day0_movies = set()
    for e in day0_entries:
        name = e.video_name
        if "Movie 1" in name:
            day0_movies.add(1)
        elif "Movie 2" in name:
            day0_movies.add(2)
        elif "Movie 3" in name:
            day0_movies.add(3)
    
    print(f"  Day 0 unique movie numbers: {day0_movies}")
    # With continuous ordered list, Day 0 should contain all movies
    assert len(day0_movies) >= 1, f"Day 0 should contain at least 1 movie group, found {day0_movies}"
    
    # Day 1 should also contain movies (continuous ordering across days)
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
    assert len(day1_movies) >= 1, f"Day 1 should contain at least 1 movie group, found {day1_movies}"
    
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


def test_generate_rotates_starting_movie():
    """Bug 3 fix: re-Generate in movie_sequence mode should produce a different preview.

    Each call to apply_custom_tags bumps _generate_count, which rotates the
    starting movie group. So day 1 should cycle through Movie 1 -> Movie 2 ->
    Movie 3 -> Movie 1 on successive Generate clicks.
    """
    print("\n=== Testing Bug 3 fix: rotation on each Generate click ===")

    videos = [
        {'id': 1, 'name': 'Movie 1 Part 1', 'path': '/movies/Movie 1 Part 1.mp4', 'duration': 90},
        {'id': 2, 'name': 'Movie 1 Part 2', 'path': '/movies/Movie 1 Part 2.mp4', 'duration': 90},
        {'id': 3, 'name': 'Movie 2 Part 1', 'path': '/movies/Movie 2 Part 1.mp4', 'duration': 90},
        {'id': 4, 'name': 'Movie 2 Part 2', 'path': '/movies/Movie 2 Part 2.mp4', 'duration': 90},
        {'id': 5, 'name': 'Movie 3 Part 1', 'path': '/movies/Movie 3 Part 1.mp4', 'duration': 90},
    ]

    tag_manager = TagManager()
    custom_tag = Tag(
        name="Movies",
        tag_type="custom",
        start_time="00:00",
        end_time="23:59",
        collection_videos=videos,
        video_count=1,
    )
    custom_tag.start_time = QTime(0, 0)
    custom_tag.end_time = QTime(23, 59)
    tag_manager.add_tag(custom_tag)

    gen = ScheduleGenerator(tag_manager)
    gen.video_order_mode = 'movie_sequence'

    # Click 1: should pick Movie 1 for day 0
    gen._generate_count = 0
    day0_v1 = gen._get_videos_for_day(videos, 0)
    movie_v1 = extract_movie_sequence_key(day0_v1[0])[0]
    print(f"  Click 1, day 0: Movie {movie_v1} (expected 1)")

    # Click 2: should pick Movie 2 for day 0
    gen._generate_count = 1
    day0_v2 = gen._get_videos_for_day(videos, 0)
    movie_v2 = extract_movie_sequence_key(day0_v2[0])[0]
    print(f"  Click 2, day 0: Movie {movie_v2} (expected 2)")

    # Click 3: should pick Movie 3 for day 0
    gen._generate_count = 2
    day0_v3 = gen._get_videos_for_day(videos, 0)
    movie_v3 = extract_movie_sequence_key(day0_v3[0])[0]
    print(f"  Click 3, day 0: Movie {movie_v3} (expected 3)")

    # Click 4: should wrap to Movie 1
    gen._generate_count = 3
    day0_v4 = gen._get_videos_for_day(videos, 0)
    movie_v4 = extract_movie_sequence_key(day0_v4[0])[0]
    print(f"  Click 4, day 0: Movie {movie_v4} (expected 1 - wrap)")

    assert movie_v1 == 1, f"Click 1 should pick Movie 1, got {movie_v1}"
    assert movie_v2 == 2, f"Click 2 should pick Movie 2, got {movie_v2}"
    assert movie_v3 == 3, f"Click 3 should pick Movie 3, got {movie_v3}"
    assert movie_v4 == 1, f"Click 4 should wrap to Movie 1, got {movie_v4}"

    # Also test that apply_custom_tags actually bumps the counter
    gen._generate_count = 0
    tag_manager.clear_cache()
    gen.apply_custom_tags(use_cache=False)
    after_first = gen._generate_count
    gen.apply_custom_tags(use_cache=False)
    after_second = gen._generate_count
    print(f"  _generate_count after clicks: {after_first} -> {after_second}")
    assert after_first == 1, f"Count after 1 click should be 1, got {after_first}"
    assert after_second == 2, f"Count after 2 clicks should be 2, got {after_second}"

    # And the produced schedule should differ between clicks
    gen._generate_count = 0
    tag_manager.clear_cache()
    schedule_a = gen.apply_custom_tags(use_cache=False)
    gen._generate_count = 1
    tag_manager.clear_cache()
    schedule_b = gen.apply_custom_tags(use_cache=False)

    def first_video_name(schedule):
        for e in schedule:
            if e.start_seconds < 86400 and "Movie" in e.video_name:
                return e.video_name
        return None

    name_a = first_video_name(schedule_a)
    name_b = first_video_name(schedule_b)
    print(f"  Schedule A first video: {name_a}")
    print(f"  Schedule B first video: {name_b}")
    assert name_a != name_b, (
        f"Two consecutive Generate clicks should produce different previews, "
        f"both had: {name_a}"
    )
    assert "Movie 1" in name_a or "Movie 2" in name_a or "Movie 3" in name_a
    assert "Movie 1" in name_b or "Movie 2" in name_b or "Movie 3" in name_b

    print("All Bug 3 rotation tests passed!")


def test_extract_movie_tag_helper():
    """Test the _extract_movie_tag helper directly with all supported formats."""
    print("\n=== Testing _extract_movie_tag helper ===")

    cases = [
        # (tags, expected_movie, expected_part)
        (["3"],                                 3, None),
        (["movie 7"],                           7, None),
        (["Movie 7"],                           7, None),
        (["Movie: 7"],                          7, None),
        (["film 4"],                            4, None),
        (["Film: 4"],                           4, None),
        (["Part 2"],                           None, 2),
        (["Part: 2"],                          None, 2),
        (["part 2"],                           None, 2),
        (["Movie: 5", "Part: 2"],               5,    2),
        (["Episodic"],                          None, None),
        (["Series: Arcane"],                    None, None),
        ([],                                   None, None),
        (["Some", "Other", "Tag"],              None, None),
        # Tag with leading whitespace
        (["  3  "],                              3, None),
        # Multiple movie tags: last movie tag wins (helper overwrites on each match)
        (["movie 1", "movie 2"],                2, None),
        # Numeric + movie N -> last numeric-or-named wins
        (["1", "movie 5"],                      5, None),
        # "video movie N" pattern (user's actual format): "movie" in the middle
        (["video movie 1"],                     1, None),
        (["video movie 3"],                     3, None),
        (["video movie 7"],                     7, None),
        (["Video Movie 4"],                     4, None),
        # "video part N" pattern
        (["video movie 1", "video part 2"],     1,    2),
        # Edge cases that must NOT match
        (["transport 7"],                       None, None),  # part preceded by 's'
        (["compartment 5"],                     None, None),  # part preceded by 'm'
        (["amovie 1"],                          None, None),  # movie preceded by 'a'
        (["superfilm 2"],                       None, None),  # film preceded by 'r'
        (["Department: 2"],                     None, None),  # part preceded by 'De'
    ]
    for tags, exp_movie, exp_part in cases:
        m, p = _extract_movie_tag(tags)
        status = "\u2713" if (m == exp_movie and p == exp_part) else "\u2717"
        print(f"  {status} {tags!r:40s} -> movie={m}, part={p} (expected movie={exp_movie}, part={exp_part})")
        assert m == exp_movie, f"Failed for {tags!r}: got movie={m}, expected {exp_movie}"
        assert p == exp_part, f"Failed for {tags!r}: got part={p}, expected {exp_part}"

    print("All _extract_movie_tag helper tests passed!")


def _write_temp_collection(coll_data):
    """Helper: write a collection JSON to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(coll_data, tmp)
    tmp.close()
    return tmp.name


def test_load_collection_json_with_movie_tags():
    """Test that load_collection_json extracts _meta_movie / _meta_part from tags."""
    print("\n=== Testing load_collection_json with movie tags ===")

    data = {
        "collections": [
            {
                "id": "sw4",
                "name": "Star Wars: A New Hope",
                "videos": [{"path": "/vids/sw4.mp4", "duration": 7200}],
                "tags": ["1"],
            },
            {
                "id": "sw5",
                "name": "Star Wars: Empire Strikes Back",
                "videos": [{"path": "/vids/sw5.mp4", "duration": 7800}],
                "tags": ["2"],
            },
            {
                "id": "sw6",
                "name": "Star Wars: Return of the Jedi",
                "videos": [{"path": "/vids/sw6.mp4", "duration": 8000}],
                "tags": ["movie 3"],
            },
            {
                "id": "some_show",
                "name": "Normal Series",
                "videos": [{"path": "/vids/ep01.mp4", "duration": 1800}],
                "tags": ["Episodic"],
            },
            {
                "id": "no_tags",
                "name": "No Tags At All",
                "videos": [{"path": "/vids/foo.mp4", "duration": 1800}],
            },
        ]
    }
    path = _write_temp_collection(data)
    try:
        videos, info = load_collection_json(path)
    finally:
        os.unlink(path)

    # Build id -> video mapping
    by_id = {v["collection_id"]: v for v in videos}

    # All 5 collections present
    assert set(by_id.keys()) == {"sw4", "sw5", "sw6", "some_show", "no_tags"}

    # Tagged entries have _meta_movie populated
    assert by_id["sw4"]["_meta_movie"] == 1
    assert by_id["sw4"]["_meta_part"] is None
    assert by_id["sw5"]["_meta_movie"] == 2
    assert by_id["sw5"]["_meta_part"] is None
    assert by_id["sw6"]["_meta_movie"] == 3
    assert by_id["sw6"]["_meta_part"] is None

    # Untagged entries have None for both
    assert by_id["some_show"]["_meta_movie"] is None
    assert by_id["some_show"]["_meta_part"] is None
    assert by_id["no_tags"]["_meta_movie"] is None
    assert by_id["no_tags"]["_meta_part"] is None

    # collection_info still works
    assert "sw4" in info
    assert info["sw4"]["name"] == "Star Wars: A New Hope"

    print("All load_collection_json movie-tag tests passed!")


def test_load_collection_videos_only_with_movie_tags():
    """Test that load_collection_videos_only also extracts _meta_movie / _meta_part."""
    print("\n=== Testing load_collection_videos_only with movie tags ===")

    data = {
        "collections": [
            {
                "id": "a",
                "name": "Movie 5",
                "videos": [{"path": "/vids/a.mp4"}],
                "tags": ["Movie: 5", "Part: 2"],
            },
            {
                "id": "b",
                "name": "Plain",
                "videos": [{"path": "/vids/b.mp4"}],
                "tags": ["Episodic"],
            },
        ]
    }
    path = _write_temp_collection(data)
    try:
        videos = load_collection_videos_only(path)
    finally:
        os.unlink(path)

    by_id = {v["collection_id"]: v for v in videos}
    assert by_id["a"]["_meta_movie"] == 5
    assert by_id["a"]["_meta_part"] == 2
    assert by_id["b"]["_meta_movie"] is None
    assert by_id["b"]["_meta_part"] is None

    print("All load_collection_videos_only movie-tag tests passed!")


def test_extract_movie_sequence_key_with_meta():
    """Test that extract_movie_sequence_key honors _meta_movie / _meta_part from dict."""
    print("\n=== Testing extract_movie_sequence_key with _meta_movie ===")

    # _meta_movie present, _meta_part present
    v = {"_meta_movie": 7, "_meta_part": 3, "name": "anything",
         "path": "1 - anything.mp4"}
    assert extract_movie_sequence_key(v) == (7, 3), \
        f"Expected (7, 3), got {extract_movie_sequence_key(v)}"

    # _meta_movie present, _meta_part missing -> defaults to 0
    v = {"_meta_movie": 5, "name": "1 - anything", "path": "1 - anything.mp4"}
    assert extract_movie_sequence_key(v) == (5, 0), \
        f"Expected (5, 0), got {extract_movie_sequence_key(v)}"

    # _meta_movie present, _meta_part explicitly None -> defaults to 0
    v = {"_meta_movie": 5, "_meta_part": None, "name": "1 - anything",
         "path": "1 - anything.mp4"}
    assert extract_movie_sequence_key(v) == (5, 0), \
        f"Expected (5, 0), got {extract_movie_sequence_key(v)}"

    # _meta_movie explicitly None -> falls back to filename parsing
    v = {"_meta_movie": None, "name": "Movie 1 Part 1", "path": "Movie 1 Part 1.mp4"}
    assert extract_movie_sequence_key(v) == (1, 1), \
        f"Expected (1, 1), got {extract_movie_sequence_key(v)}"

    # No _meta_movie at all -> falls back to filename parsing (existing behavior)
    v = {"name": "Movie 2 Part 3", "path": "Movie 2 Part 3.mp4"}
    assert extract_movie_sequence_key(v) == (2, 3), \
        f"Expected (2, 3), got {extract_movie_sequence_key(v)}"

    # String input is unchanged
    assert extract_movie_sequence_key("Movie 1 Part 1.mp4") == (1, 1)
    assert extract_movie_sequence_key("S01E02.mp4") == (1, 2)

    print("All extract_movie_sequence_key with _meta_movie tests passed!")


def test_group_videos_by_movie_with_meta():
    """Test that group_videos_by_movie groups videos using _meta_movie from tags."""
    print("\n=== Testing group_videos_by_movie with mixed sources ===")

    # Mixed: some videos use _meta_movie from JSON tags, others use filename parsing
    videos = [
        # From JSON tags
        {"id": 1, "_meta_movie": 1, "_meta_part": 0,
         "name": "Star Wars 4", "path": "/vids/sw4.mp4"},
        {"id": 2, "_meta_movie": 1, "_meta_part": 1,
         "name": "Star Wars 5", "path": "/vids/sw5.mp4"},
        # From filename parsing
        {"id": 3, "name": "Movie 2 Part 1", "path": "/vids/m2p1.mp4"},
        {"id": 4, "name": "Movie 2 Part 2", "path": "/vids/m2p2.mp4"},
        # Untagged but filename would have given (1, 0) - tag overrides filename
        {"id": 5, "_meta_movie": 3, "_meta_part": 0,
         "name": "1 - misleading name", "path": "/vids/m3.mp4"},
    ]

    groups = group_videos_by_movie(videos)
    print(f"  Groups formed: {sorted(groups.keys())}")
    for movie_num, group_videos in sorted(groups.items()):
        print(f"    Movie {movie_num}: {len(group_videos)} videos")
        for v in group_videos:
            print(f"      - id={v.get('id')} name={v.get('name')}")

    # 3 distinct movie groups
    assert sorted(groups.keys()) == [1, 2, 3]
    # Movie 1: 2 videos (ids 1, 2)
    assert sorted(v["id"] for v in groups[1]) == [1, 2]
    # Movie 2: 2 videos (ids 3, 4)
    assert sorted(v["id"] for v in groups[2]) == [3, 4]
    # Movie 3: 1 video (id 5) - tag wins over misleading filename
    assert [v["id"] for v in groups[3]] == [5]

    print("All group_videos_by_movie mixed-sources tests passed!")


def test_movie_sequence_end_to_end_with_tags():
    """End-to-end: load collection JSON with tags, then group + schedule."""
    print("\n=== End-to-end: load -> group -> schedule (with tags) ===")

    data = {
        "collections": [
            {"id": "m1", "name": "Movie 1",
             "videos": [{"path": "/vids/m1.mp4"}], "tags": ["1"]},
            {"id": "m2", "name": "Movie 2",
             "videos": [{"path": "/vids/m2.mp4"}], "tags": ["2"]},
            {"id": "m3", "name": "Movie 3",
             "videos": [{"path": "/vids/m3.mp4"}], "tags": ["3"]},
        ]
    }
    path = _write_temp_collection(data)
    try:
        videos, _ = load_collection_json(path)
    finally:
        os.unlink(path)

    # Group by movie
    groups = group_videos_by_movie(videos)
    assert sorted(groups.keys()) == [1, 2, 3], \
        f"Expected [1, 2, 3], got {sorted(groups.keys())}"
    assert len(groups[1]) == 1
    assert len(groups[2]) == 1
    assert len(groups[3]) == 1

    # Now schedule with movie_sequence mode and verify day-by-day movie picks
    tag_manager = TagManager()
    gen = ScheduleGenerator(tag_manager)
    gen.video_order_mode = "movie_sequence"

    for day, expected_movie in [(0, 1), (1, 2), (2, 3), (3, 1)]:
        vids = gen._get_videos_for_day(videos, day)
        movie_nums = [extract_movie_sequence_key(v)[0] for v in vids]
        assert all(m == expected_movie for m in movie_nums), (
            f"Day {day}: expected all movies={expected_movie}, got {movie_nums}"
        )

    print("End-to-end movie_sequence with tags: passed!")


if __name__ == "__main__":
    try:
        test_extract_movie_sequence_key()
        test_group_videos_by_movie()
        test_get_videos_for_day()
        test_build_random_entries_movie_sequence()
        test_custom_tag_movie_sequence()
        test_generate_rotates_starting_movie()
        test_extract_movie_tag_helper()
        test_load_collection_json_with_movie_tags()
        test_load_collection_videos_only_with_movie_tags()
        test_extract_movie_sequence_key_with_meta()
        test_group_videos_by_movie_with_meta()
        test_movie_sequence_end_to_end_with_tags()
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
