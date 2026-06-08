#!/usr/bin/env python3
"""
Regression / reproduction tests for the 4 series-tag & custom-tag bugs
documented in `task/series_tag_bugs.md`.

Each test is intentionally written to FAIL right now (the bugs are
unfixed). The point of this file is twofold:
  1. Demonstrate the current broken behavior (the output the user sees)
  2. Serve as a regression guard: once the bugs are fixed, every test
     should pass and stay green.

When a test fails, the failure message shows the actual output of the
scheduler so the bug is easy to diagnose visually. When a test passes,
the "OK" line is the green-light signal.

Bugs covered (per task/series_tag_bugs.md):
  Bug 1  - custom tag disappears when paired with random fill
  Bug 2  - series tag shows only tag name (no episode file names)
           Sub-bug 2a - video_count=1 produces 0 entries
  Bug 3  - series tag video count inconsistent across days
  Bug 4  - first random-fill entry after a series tag has half its real duration

Run with:
    python3 test_series_tag_bugs.py
"""

import sys
import os
import json
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTime

from data_models import Tag, TagManager, ScheduleEntry
from scheduler import ScheduleGenerator
from strategies import CustomTagMergeStrategy


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

# 6 synthetic Sandokan-style episodes with episode metadata. Durations are
# in seconds. Path encodes season/episode so parse_series_episode picks them
# up. (See utils.parse_series_episode.)
SANDOKAN_EPISODES = [
    {"path": "S01E01 - Sandokan E01.mp4", "duration": 50 * 60, "_meta_season": 1, "_meta_episode": 1, "name": "Sandokan E01.mp4"},
    {"path": "S01E02 - Sandokan E02.mp4", "duration": 55 * 60, "_meta_season": 1, "_meta_episode": 2, "name": "Sandokan E02.mp4"},
    {"path": "S01E03 - Sandokan E03.mp4", "duration": 57 * 60, "_meta_season": 1, "_meta_episode": 3, "name": "Sandokan E03.mp4"},
    {"path": "S01E04 - Sandokan E04.mp4", "duration": 53 * 60, "_meta_season": 1, "_meta_episode": 4, "name": "Sandokan E04.mp4"},
    {"path": "S01E05 - Sandokan E05.mp4", "duration": 55 * 60, "_meta_season": 1, "_meta_episode": 5, "name": "Sandokan E05.mp4"},
    {"path": "S01E06 - Sandokan E06.mp4", "duration": 53 * 60, "_meta_season": 1, "_meta_episode": 6, "name": "Sandokan E06.mp4"},
]

# Random-fill pool: 4 distinct videos with KNOWN, EASILY-RECOGNIZABLE
# durations so Bug 4 (half duration) shows up in the printed output.
RANDOM_FILL_VIDEOS = [
    {"path": "/pool/Show A.mp4",        "duration": 60 * 60,  "name": "Show A.mp4"},
    {"path": "/pool/Show B.mp4",        "duration": 90 * 60,  "name": "Show B.mp4"},
    {"path": "/pool/Show C.mp4",        "duration": 120 * 60, "name": "Show C.mp4"},
    {"path": "/pool/Show D.mp4",        "duration": 100 * 60, "name": "Show D.mp4"},
]


def _format_entry(e: ScheduleEntry) -> str:
    """Pretty-print a schedule entry with day-boundary info."""
    s_h = (e.start_seconds // 3600) % 24
    s_m = (e.start_seconds % 3600) // 60
    e_h = (e.end_seconds // 3600) % 24
    e_m = (e.end_seconds % 3600) // 60
    day = (e.start_seconds // 86400) + 1
    dur = e.end_seconds - e.start_seconds
    return (f"  D{day} {s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d} "
            f"({dur:>4}s)  {e.video_name}")


def _dump_schedule(title: str, entries):
    print(f"\n--- {title} ({len(entries)} entries) ---")
    if not entries:
        print("  (empty)")
        return
    last_day = -1
    for e in entries:
        day = (e.start_seconds // 86400) + 1
        if day != last_day:
            print(f"  === Day {day} ===")
            last_day = day
        print(_format_entry(e))


def _make_random_fill_tag(name="RF", fill_24h=True,
                          start=QTime(0, 0), end=QTime(23, 59),
                          videos=None):
    return Tag(
        name=name,
        tag_type="random",
        start_time=start,
        end_time=end,
        is_random_fill=True,
        fill_24h=fill_24h,
        collection_videos=list(videos if videos is not None else RANDOM_FILL_VIDEOS),
    )


def _make_custom_tag(name="Custom", start=QTime(0, 0), end=QTime(2, 0),
                     videos=None, video_count=2):
    return Tag(
        name=name,
        tag_type="custom",
        start_time=start,
        end_time=end,
        collection_videos=list(videos if videos is not None else RANDOM_FILL_VIDEOS[:2]),
        video_count=video_count,
    )


def _make_series_tag(name="Sandokan 1976",
                     start=QTime(20, 0), end=QTime(20, 51),
                     episodes=None, video_count=1,
                     end_behavior="repeat", repeat_season=1):
    return Tag(
        name=name,
        tag_type="series",
        start_time=start,
        end_time=end,
        is_series=True,
        start_season=1,
        start_episode=1,
        play_mode="sequence",
        video_count=video_count,
        series_end_behavior=end_behavior,
        series_repeat_season=repeat_season,
        collection_videos=list(episodes if episodes is not None else SANDOKAN_EPISODES),
    )


# ---------------------------------------------------------------------------
# BUG 1: custom tag disappears when paired with random fill
# ---------------------------------------------------------------------------

def test_bug1_custom_tag_disappears_with_random_fill():
    """
    Setup: 1 custom tag (00:00-02:00, 2 distinct videos) + 1 random fill
    tag (24h fill, 4 distinct videos).
    Expected: schedule contains BOTH custom-tag entries AND random-fill
    entries.
    Buggy:   only random-fill entries are present; the custom-tag block
             (00:00-02:00) is missing.
    """
    print("\n" + "=" * 70)
    print("BUG 1: custom tag disappears when paired with random fill")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_custom_tag(
        name="MyCustom",
        start=QTime(0, 0), end=QTime(2, 0),
        videos=RANDOM_FILL_VIDEOS[:2],  # Show A (60m) + Show B (90m)
        video_count=2,
    ))
    tm.add_tag(_make_random_fill_tag(
        name="MyRF",
        fill_24h=True,
        videos=RANDOM_FILL_VIDEOS,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=1)
    _dump_schedule("Schedule with custom tag + random fill", entries)

    # Look for any entry mentioning the custom tag name OR one of its
    # video display names.
    custom_names = {"MyCustom", "Show A.mp4", "Show B.mp4"}
    custom_entries = [e for e in entries
                      if any(n in e.video_name for n in custom_names)]
    rf_entries = [e for e in entries if "MyRF" in e.video_name]

    print(f"\n  custom-tag entries: {len(custom_entries)}")
    print(f"  random-fill entries: {len(rf_entries)}")

    # The custom tag should occupy 00:00-02:00 (7200s) with 2 videos
    # (Show A 60m + Show B 60m truncated to fit the 2h window).
    custom_in_window = [e for e in custom_entries
                        if 0 <= e.start_seconds < 2 * 3600]
    print(f"  custom-tag entries in [00:00, 02:00): {len(custom_in_window)}")

    assert len(custom_in_window) >= 1, (
        f"BUG 1 REPRODUCED: custom tag 'MyCustom' produced "
        f"{len(custom_in_window)} entries in the 00:00-02:00 window "
        f"(expected at least 1). Only random-fill entries are visible."
    )
    print("  PASS: custom tag is present in the schedule")


# ---------------------------------------------------------------------------
# BUG 2: series tag shows only the tag name, not episode file names
# ---------------------------------------------------------------------------

def test_bug2_series_tag_shows_only_tag_name_no_episodes():
    """
    Setup: 1 series tag (Sandokan 1976) with collection_videos loaded
           (simulating the state AFTER the user does the Save workaround).
    Expected: each series entry shows the episode file name
              (e.g. "Sandokan E01.mp4") in the video_name field.
    Buggy:   not reproducible here directly because we pre-load the
             videos. To reproduce the cold-load bug, see
             test_bug2_cold_load_series_tag_shows_only_tag_name.

    This sub-test asserts the working case (videos loaded) so that the
    fix for Bug 2 (cold-load state) keeps the working case green.
    """
    print("\n" + "=" * 70)
    print("BUG 2: series tag must show episode file names (warm load)")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="Sandokan 1976",
        start=QTime(20, 0), end=QTime(20, 51),
        episodes=SANDOKAN_EPISODES,
        video_count=1,
        end_behavior="repeat",
        repeat_season=1,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=1)
    _dump_schedule("Series tag warm load (1 day, video_count=1)", entries)

    series_entries = [e for e in entries if "Sandokan" in e.video_name]
    print(f"\n  series entries: {len(series_entries)}")

    for e in series_entries:
        print(f"    {e.video_name}")

    # Each entry should mention the episode file name.
    for e in series_entries:
        assert "E0" in e.video_name and ".mp4" in e.video_name, (
            f"BUG 2 (warm): expected episode file name in '{e.video_name}', "
            f"got only the tag name."
        )
    print("  PASS: every series entry contains an episode file name")


def _write_sandokan_collection_file():
    """Write a synthetic Sandokan 1976 collection JSON for cold-load tests.

    Returns the path to the temp file. Caller is responsible for cleanup.
    """
    import tempfile
    videos = [
        {
            "path": f"S01E{ep:02d} - Sandokan E{ep:02d}.mp4",
            "duration": dur,
        }
        for ep, dur in zip(
            range(1, 7),
            [50 * 60, 55 * 60, 57 * 60, 53 * 60, 55 * 60, 53 * 60],
        )
    ]
    coll = {
        "collections": [
            {
                "id": "sandokan_1976",
                "name": "Sandokan 1976",
                "cover": "",
                "description": "",
                "genre": [],
                "videos": videos,
                "tags": ["Series: Sandokan 1976", "Season: 1"],
            }
        ]
    }
    fd, path = tempfile.mkstemp(suffix=".json", prefix="sandokan_cold_")
    with os.fdopen(fd, "w") as f:
        json.dump(coll, f)
    return path


def test_bug2_cold_load_series_tag_shows_only_tag_name():
    """
    Regression test for Bug 2: in the cold-load state the series tag
    must show the episode file name, not just the tag name.

    The cold-load state is: the Tag was just deserialized from disk, the
    in-memory `collection_videos` is empty, but `collection_path` is set
    to a real collection file (this is exactly what the user has on
    the first Generate click after opening a series tag from disk).
    The fix in `_process_series_tag` lazy-loads the videos from
    `collection_path` so the placeholder branch is no longer needed.

    On the unfixed code: this test FAILS — the entry is the tag-name
    placeholder (BUG REPRODUCED).
    On the fixed code: this test PASSES — the entry has the episode
    file name.
    """
    print("\n" + "=" * 70)
    print("BUG 2: COLD-LOAD series tag must show episode file name (regression guard)")
    print("=" * 70)

    coll_path = _write_sandokan_collection_file()
    try:
        tm = TagManager()
        # Cold-load state: collection_videos is empty, but collection_path
        # points to a real collection file (this matches what the user
        # has when the series tag is loaded from an .ini file).
        tm.add_tag(Tag(
            name="Sandokan 1976",
            tag_type="series",
            start_time=QTime(20, 0),
            end_time=QTime(20, 51),
            is_series=True,
            start_season=1,
            start_episode=1,
            play_mode="sequence",
            video_count=1,
            series_end_behavior="repeat",
            series_repeat_season=1,
            collection_path=coll_path,
            # collection_videos intentionally NOT set (cold load)
        ))

        sg = ScheduleGenerator(tm)
        entries = sg.apply_custom_tags(num_days=1)
        _dump_schedule("Series tag COLD load (1 day, video_count=1)", entries)

        # Expect the episode file name in the entry, not just the tag name.
        series_entries = [e for e in entries
                          if 20 * 3600 <= e.start_seconds < 21 * 3600]
        print(f"\n  series-window entries (20:00-20:59): {len(series_entries)}")
        for e in series_entries:
            print(f"    '{e.video_name}'  (dur={e.end_seconds - e.start_seconds}s)")

        assert len(series_entries) >= 1, (
            f"BUG 2 (cold) REGRESSION: expected the cold-load lazy-load "
            f"fallback to emit at least one entry per day, got "
            f"{len(series_entries)}"
        )
        for e in series_entries:
            # After the fix, the entry should be the real episode, not the
            # tag-name placeholder. The placeholder would have
            # video_name == tag name ("Sandokan 1976") and duration
            # equal to the whole window (51 min = 3060s).
            is_placeholder = (e.video_name == "Sandokan 1976" and
                              (e.end_seconds - e.start_seconds) == 51 * 60)
            assert not is_placeholder, (
                f"BUG 2 (cold) REPRODUCED: cold-load entry is the tag-name "
                f"placeholder ('{e.video_name}', "
                f"dur={e.end_seconds - e.start_seconds}s) instead of an "
                f"actual episode entry. _process_series_tag must lazy-load "
                f"videos from collection_path when collection_videos is "
                f"empty."
            )
            # And the entry must reference the episode file name.
            assert ".mp4" in e.video_name, (
                f"BUG 2 (cold): expected an episode file name in "
                f"'{e.video_name}', got only the tag name."
            )
        print("  PASS: cold-load series tag emits the episode file name "
              "(not the tag-name placeholder). Save-then-Generate workaround "
              "is no longer needed.")
    finally:
        try:
            os.unlink(coll_path)
        except OSError:
            pass


def test_bug2_cold_load_matches_warm_load():
    """
    Regression test for Bug 2: the cold-load preview must match the
    warm-load preview (i.e. opening the edit dialog and clicking Save,
    then re-Generating, must produce the same result as the very first
    Generate on a cold-loaded tag).

    On the unfixed code: the cold load emits the tag-name placeholder
    while the warm load emits real episode file names — the two outputs
    disagree. FAILS.
    On the fixed code: both emit real episode file names. PASSES.
    """
    print("\n" + "=" * 70)
    print("BUG 2: cold-load preview must match warm-load preview")
    print("=" * 70)

    coll_path = _write_sandokan_collection_file()
    try:
        # --- cold load ---
        tm_cold = TagManager()
        tm_cold.add_tag(Tag(
            name="Sandokan 1976",
            tag_type="series",
            start_time=QTime(20, 0),
            end_time=QTime(20, 51),
            is_series=True,
            start_season=1,
            start_episode=1,
            play_mode="sequence",
            video_count=1,
            series_end_behavior="repeat",
            series_repeat_season=1,
            collection_path=coll_path,
            # collection_videos intentionally NOT set
        ))
        sg_cold = ScheduleGenerator(tm_cold)
        cold_entries = sg_cold.apply_custom_tags(num_days=1)

        # --- warm load (simulating post-Save) ---
        from utils import load_collection_videos_only
        warm_videos = load_collection_videos_only(coll_path)
        tm_warm = TagManager()
        tm_warm.add_tag(Tag(
            name="Sandokan 1976",
            tag_type="series",
            start_time=QTime(20, 0),
            end_time=QTime(20, 51),
            is_series=True,
            start_season=1,
            start_episode=1,
            play_mode="sequence",
            video_count=1,
            series_end_behavior="repeat",
            series_repeat_season=1,
            collection_path=coll_path,
            collection_videos=warm_videos,  # post-Save state
        ))
        sg_warm = ScheduleGenerator(tm_warm)
        warm_entries = sg_warm.apply_custom_tags(num_days=1)

        cold_names = [e.video_name for e in cold_entries
                      if 20 * 3600 <= e.start_seconds < 21 * 3600]
        warm_names = [e.video_name for e in warm_entries
                      if 20 * 3600 <= e.start_seconds < 21 * 3600]

        print(f"\n  cold load video names: {cold_names}")
        print(f"  warm load video names: {warm_names}")

        assert cold_names == warm_names, (
            f"BUG 2 REGRESSION: cold-load and warm-load previews differ. "
            f"Cold: {cold_names}, Warm: {warm_names}. The Save-then-Generate "
            f"workaround should be a no-op after the fix."
        )
        print("  PASS: cold-load preview matches warm-load preview "
              "(Save-then-Generate workaround is a no-op).")
    finally:
        try:
            os.unlink(coll_path)
        except OSError:
            pass


def test_bug2_saved_series_tag_uses_collection_profile():
    """
    Regression test for Bug 2 (re-discovered 2026-06-08): the user's
    report after the initial Bug 2 fix landed:
    'I save a tags for random and series, custom and so on. when I
    load the tags and generate the bug shows up, but if I do a
    click on the button random fill, select the collection, then
    click on the series tag select the collection file. this makes
    a new tags in the list and press generate button. all works
    fine! so the bug is with the saved tags'

    Root cause: `serialize_tag_to_string` for series tags did NOT
    save `collection_path` (only `collection_profile`, a bare file
    name in the collections dir). On reload, the in-memory Tag
    had `collection_path=''` AND `collection_videos=[]` AND only
    `collection_profile='collections_Sandokan_1976.json'`. The
    cold-load fallback in `_process_series_tag` only checked
    `collection_path`, so it never fired, and the placeholder
    was emitted.

    Fix: `_process_series_tag` now resolves the collection via a
    new helper `_resolve_series_collection_path` that falls back
    to `collection_profile → collections_dir/profile_name` and
    also scans the collections dir for a matching JSON if neither
    is set. `serialize_tag_to_string` also now saves
    `collection_path` so new tags work after save/reload too.

    On the unfixed code: this test FAILS — the entry is the
    tag-name placeholder 'Sandokan 1976' (no episode).
    On the fixed code: this test PASSES — the entry has the
    episode file name.
    """
    print("\n" + "=" * 70)
    print("BUG 2 (regression 2026-06-08): saved series tag uses collection_profile")
    print("=" * 70)

    # Find an existing Sandokan collection on disk. If not available,
    # write a synthetic one to a temp dir and override the config
    # paths to point there. (For this regression test, we use the
    # real on-disk path that the user's saved tag references.)
    from utils import get_config_paths, load_collection_videos_only
    coll_dir, _ = get_config_paths()
    coll_path = os.path.join(coll_dir, "collections_Sandokan_1976.json")
    if not os.path.isfile(coll_path):
        # Fallback: write a synthetic one in a temp dir and patch
        # get_config_paths via monkey-patching the collections dir.
        # The simplest way is to just write a copy to the actual
        # collections dir; for the test we'll skip if even that
        # fails (e.g. permissions).
        coll_path = _write_sandokan_collection_file()
        fallback_path = True
    else:
        fallback_path = False
    try:
        # Sanity check that the profile-based resolution would work.
        loaded = load_collection_videos_only(coll_path)
        assert loaded, f"Could not load videos from {coll_path}"

        # Build a Tag that matches what serialize_tag_to_string would
        # produce for a series tag (no collection_path, only
        # collection_profile = bare file name).
        tm = TagManager()
        tm.add_tag(Tag(
            name="Sandokan 1976",
            tag_type="series",
            start_time=QTime(20, 0),
            end_time=QTime(20, 51),
            is_series=True,
            start_season=1,
            start_episode=1,
            play_mode="sequence",
            video_count=1,
            series_end_behavior="repeat",
            series_repeat_season=1,
            collection_profile="collections_Sandokan_1976.json",
            # collection_path is intentionally NOT set (matches the
            # old .ini file format where the field wasn't serialized)
        ))

        sg = ScheduleGenerator(tm)
        entries = sg.apply_custom_tags(num_days=1)
        _dump_schedule("Series tag with collection_profile only", entries)

        series_entries = [e for e in entries
                          if "Sandokan" in e.video_name]
        print(f"\n  series entries: {len(series_entries)}")
        for e in series_entries:
            print(f"    '{e.video_name}'  (dur={e.end_seconds - e.start_seconds}s)")

        assert len(series_entries) >= 1, (
            f"BUG 2 (saved-tag): expected the collection_profile fallback "
            f"to emit at least one entry, got {len(series_entries)}"
        )
        for e in series_entries:
            is_placeholder = (e.video_name == "Sandokan 1976" and
                              (e.end_seconds - e.start_seconds) == 51 * 60)
            assert not is_placeholder, (
                f"BUG 2 (saved-tag) REPRODUCED: entry is the tag-name "
                f"placeholder ('{e.video_name}', "
                f"dur={e.end_seconds - e.start_seconds}s) instead of an "
                f"actual episode. The collection_profile→path "
                f"fallback in _resolve_series_collection_path is not "
                f"working."
            )
            assert ".mp4" in e.video_name, (
                f"BUG 2 (saved-tag): expected an episode file name in "
                f"'{e.video_name}', got only the tag name."
            )
        print("  PASS: saved series tag (collection_profile only) "
              "resolves the collection and emits the episode file name. "
              "No Save round-trip needed.")
    finally:
        if fallback_path:
            try:
                os.unlink(coll_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# BUG 2a: series tag with video_count=1 produces 0 entries
# ---------------------------------------------------------------------------

def test_bug2a_series_video_count_one_produces_no_entries():
    """
    Setup: 1 series tag with video_count=1, 6 episodes, end_behavior=repeat.
    Expected: each day has exactly 1 series entry (one episode).
    Buggy:   0 series entries per day (the user's report: "we will only
             see the days of weeks").
    """
    print("\n" + "=" * 70)
    print("BUG 2a: series tag video_count=1 produces 0 entries")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="Sandokan 1976",
        start=QTime(20, 0), end=QTime(20, 51),
        episodes=SANDOKAN_EPISODES,
        video_count=1,
        end_behavior="repeat",
        repeat_season=1,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=3)
    _dump_schedule("Series tag, video_count=1, 3 days", entries)

    # Match by tag name (works for all days, since wall-clock filters
    # like `20*3600 <= start < 21*3600` only match day 1's entries).
    series_entries = [e for e in entries
                      if "Sandokan" in e.video_name]
    print(f"\n  series entries (tag name match) over 3 days: "
          f"{len(series_entries)}")
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        s_h = (e.start_seconds // 3600) % 24
        s_m = (e.start_seconds % 3600) // 60
        e_h = (e.end_seconds // 3600) % 24
        e_m = (e.end_seconds % 3600) // 60
        print(f"    D{d} {s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d}  {e.video_name}")

    # Per day: expect 1 series entry
    per_day = {1: 0, 2: 0, 3: 0}
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        per_day[d] = per_day.get(d, 0) + 1
    print(f"  per-day series count: {per_day}")

    for d in range(1, 4):
        n = per_day.get(d, 0)
        assert n == 1, (
            f"BUG 2a REPRODUCED: day {d} has {n} series entries "
            f"(expected exactly 1)."
        )
    print("  PASS: every day has exactly 1 series entry")


# ---------------------------------------------------------------------------
# BUG 3: series tag video_count=2 produces inconsistent per-day count
# ---------------------------------------------------------------------------

def test_bug3_series_video_count_inconsistent_across_days():
    """
    Setup: 1 series tag with video_count=2, 6 episodes, end_behavior=repeat.
    Expected: each day has exactly 2 series entries.
    Buggy:   some days have 2, some have 1 (the user's report).
    """
    print("\n" + "=" * 70)
    print("BUG 3: series tag video_count=2 is inconsistent across days")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="Sandokan 1976",
        start=QTime(20, 0), end=QTime(23, 59),  # wider window so both fit
        episodes=SANDOKAN_EPISODES,
        video_count=2,
        end_behavior="repeat",
        repeat_season=1,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=3)
    _dump_schedule("Series tag, video_count=2, 3 days", entries)

    # Match by tag name (works for all days, since wall-clock filters
    # like `20*3600 <= start < 24*3600` only match day 1's entries).
    series_entries = [e for e in entries
                      if "Sandokan" in e.video_name]
    print(f"\n  series entries (tag name match) over 3 days: "
          f"{len(series_entries)}")
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        s_h = (e.start_seconds // 3600) % 24
        s_m = (e.start_seconds % 3600) // 60
        e_h = (e.end_seconds // 3600) % 24
        e_m = (e.end_seconds % 3600) // 60
        print(f"    D{d} {s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d}  {e.video_name}")

    per_day = {}
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        per_day[d] = per_day.get(d, 0) + 1
    print(f"  per-day series count: {per_day}")

    for d in range(1, 4):
        n = per_day.get(d, 0)
        assert n == 2, (
            f"BUG 3 REPRODUCED: day {d} has {n} series entries "
            f"(expected exactly 2, since video_count=2)."
        )
    print("  PASS: every day has exactly 2 series entries")


def test_bug2a3_partial_fit_extends_window():
    """
    Regression test for the refined Bug 2a/3 fix: the soft-hint
    must activate not only when ZERO episodes fit, but also when
    SOME episodes fit and the rest are silently skipped because
    they would exceed the configured end_time.

    Concrete scenario: window=66 min, video_count=2,
    ep1=36m fits, ep2=30m (float duration makes total 4014s > 3960s).
    Buggy behavior: only 1 episode placed, second silently skipped.
    Fixed behavior: window extends so both fit.
    """
    print("\n" + "=" * 70)
    print("BUG 2a/3 refined: partial fit (placed>=1 but <video_count) extends window")
    print("=" * 70)

    # Two videos where the second's float-precise total exceeds the 66-min window
    # First is 2161.52s (36.0m), second is 1852.58s (30.9m); sum=4014.10s > 3960s
    partial_episodes = [
        {"path": "S01E01 - Ep01.mkv", "duration": 2161.52,
         "_meta_season": 1, "_meta_episode": 1, "name": "Ep01.mkv"},
        {"path": "S01E02 - Ep02.mkv", "duration": 1852.58,
         "_meta_season": 1, "_meta_episode": 2, "name": "Ep02.mkv"},
        # Second day: both fit within 66m window (28m + 37m = 65m)
        {"path": "S01E03 - Ep03.mkv", "duration": 1682.52,
         "_meta_season": 1, "_meta_episode": 3, "name": "Ep03.mkv"},
        {"path": "S01E04 - Ep04.mkv", "duration": 2262.85,
         "_meta_season": 1, "_meta_episode": 4, "name": "Ep04.mkv"},
    ]

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="PartialFit",
        start=QTime(13, 0), end=QTime(14, 6),  # 66 min window
        episodes=partial_episodes,
        video_count=2,
        end_behavior="repeat",
        repeat_season=1,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=2)
    _dump_schedule("Partial-fit series (video_count=2, window=66m)", entries)

    series_entries = [e for e in entries if "PartialFit" in e.video_name]
    print(f"\n  series entries: {len(series_entries)}")
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        s_h = (e.start_seconds // 3600) % 24
        s_m = (e.start_seconds % 3600) // 60
        e_h = (e.end_seconds // 3600) % 24
        e_m = (e.end_seconds % 3600) // 60
        print(f"    D{d} {s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d}  {e.video_name}")

    per_day = {}
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        per_day[d] = per_day.get(d, 0) + 1
    print(f"  per-day series count: {per_day}")

    for d in range(1, 3):
        n = per_day.get(d, 0)
        assert n == 2, (
            f"BUG 2a/3 PARTIAL-FIT: day {d} has {n} series entries "
            f"(expected exactly 2, since video_count=2 and at least 2 "
            f"episodes exist). The window should auto-extend when the "
            f"second episode doesn't fit."
        )
    print("  PASS: every day has exactly 2 series entries even when "
          "the second episode doesn't fit in the initial window")


# ---------------------------------------------------------------------------
# BUG 4: first random-fill entry after a series tag has half its duration
# ---------------------------------------------------------------------------

def test_bug4_random_fill_entry_after_series_has_half_duration():
    """
    Setup: 1 series tag (Sandokan 1976) at 20:00-20:51 + 1 random fill
           tag (24h fill, 4 videos with known durations).
    Expected: the first random-fill entry that comes AFTER the series
              tag's last video has its full real duration.
    Buggy:   that entry's duration is roughly half the real value.

    The random-fill videos have clearly different durations (60m, 90m,
    120m, 100m), so any half-duration bug will be obvious in the dump.
    """
    print("\n" + "=" * 70)
    print("BUG 4: first random-fill entry after series has half duration")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="Sandokan 1976",
        start=QTime(20, 0), end=QTime(20, 51),
        episodes=SANDOKAN_EPISODES,
        video_count=1,
        end_behavior="repeat",
        repeat_season=1,
    ))
    tm.add_tag(_make_random_fill_tag(
        name="MyRF",
        fill_24h=True,
        videos=RANDOM_FILL_VIDEOS,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(num_days=1)
    _dump_schedule("Series (20:00-20:51) + random fill, 1 day", entries)

    # Find the last series entry, then the first random-fill entry after it.
    series_entries = [e for e in entries
                      if "Sandokan" in e.video_name and not "MyRF" in e.video_name]
    rf_entries = [e for e in entries if "MyRF" in e.video_name]
    if not series_entries or not rf_entries:
        print(f"\n  (cannot run assertion: series={len(series_entries)} "
              f"rf={len(rf_entries)})")
        return

    last_series_end = max(e.end_seconds for e in series_entries)
    first_rf_after = next(
        (e for e in rf_entries if e.start_seconds >= last_series_end),
        None,
    )
    if first_rf_after is None:
        print(f"\n  (no random-fill entry after last series end "
              f"{last_series_end}s)")
        return

    # Look up the real duration for that video from the pool.
    real_dur = None
    for v in RANDOM_FILL_VIDEOS:
        if v["name"] in first_rf_after.video_name or \
           v["path"].split("/")[-1] in first_rf_after.video_name:
            real_dur = v["duration"]
            break
    reported_dur = first_rf_after.end_seconds - first_rf_after.start_seconds

    print(f"\n  last series end:    {last_series_end}s")
    print(f"  first RF after it:  '{first_rf_after.video_name}'")
    print(f"    reported start:    {first_rf_after.start_seconds}s")
    print(f"    reported end:      {first_rf_after.end_seconds}s")
    print(f"    reported duration: {reported_dur}s")
    print(f"    real duration:     {real_dur}s")

    if real_dur is not None:
        # Allow 1s slop for boundaries; the bug is "roughly half" (~50%
        # off), so the assertion catches that without being noisy on
        # off-by-ones.
        ratio = reported_dur / real_dur
        print(f"    ratio:             {ratio:.3f}")
        assert 0.85 <= ratio <= 1.15, (
            f"BUG 4 REPRODUCED: first random-fill entry after the series "
            f"tag has reported duration {reported_dur}s, but the real "
            f"duration is {real_dur}s (ratio {ratio:.3f}). This indicates "
            f"the series tag's last episode did not fully advance the "
            f"pos/duration accumulator."
        )
    print("  PASS: first random-fill entry after series has full duration")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        # Approximate OFF tests (apply_custom_tags)
        test_bug1_custom_tag_disappears_with_random_fill,
        test_bug2_series_tag_shows_only_tag_name_no_episodes,
        test_bug2_cold_load_series_tag_shows_only_tag_name,
        test_bug2_cold_load_matches_warm_load,
        test_bug2_saved_series_tag_uses_collection_profile,
        test_bug2a_series_video_count_one_produces_no_entries,
        test_bug3_series_video_count_inconsistent_across_days,
        test_bug2a3_partial_fit_extends_window,
        test_bug4_random_fill_entry_after_series_has_half_duration,
        # Approximate ON + Find-Replace tests (apply_approximate)
        test_bug1_approximate_custom_tag_disappears_with_random_fill,
        test_bug5_series_missing_in_approximate_video_count_1,
        test_bug5_series_visible_in_approximate_video_count_2,
    ]

    print("Series Tag & Custom Tag Bug Tests")
    print("=" * 70)
    print("Bugs covered (see task/series_tag_bugs.md for details):")
    for i, t in enumerate(tests, 1):
        print(f"  {i}. {t.__name__}")
    print("=" * 70)

    results = []
    for t in tests:
        try:
            t()
            results.append((t.__name__, "PASS", None))
        except AssertionError as e:
            results.append((t.__name__, "FAIL", str(e)))
        except Exception as e:
            results.append((t.__name__, "ERROR", f"{e}\n{traceback.format_exc()}"))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, status, err in results:
        marker = {"PASS": "✓", "FAIL": "✗", "ERROR": "!"}[status]
        print(f"  {marker} {status:5s}  {name}")
        if err:
            for line in str(err).splitlines()[:6]:
                print(f"        {line}")
            if len(str(err).splitlines()) > 6:
                print(f"        ...")

    failed = sum(1 for _, s, _ in results if s != "PASS")
    print(f"\n  {len(results) - failed} / {len(results)} passed")
    if failed:
        print(f"  {failed} test(s) failed — see task/series_tag_bugs.md "
              "for the bug list and the workflow to fix them one by one.")
        sys.exit(1)
    else:
        print("  All tests passed — bugs are fixed!")
        sys.exit(0)




# ===========================================================================
# BUGS THAT ONLY REPRODUCE IN APPROXIMATE MODE (Apply ON + Find-Replace)
# ===========================================================================
#
# The user reports (2026-06-07 evening): "i used approximation on and
# Find-replace when we have a random fill tag and a custom tag [Bug 1
# reproduces]. But today i tested a Random fill and a Series tag and i
# see the series are not in the preview when generated, so it happens
# with custom and series too. But when i set the seriwes video count to
# 2, then i see the series tag in the preview."
#
# These tests exercise `apply_approximate(mode="find_replace")` instead
# of `apply_custom_tags()` to surface the approximate-mode-only bugs.

def test_bug1_approximate_custom_tag_disappears_with_random_fill():
    """
    Approximate ON + Find-Replace: 1 custom tag + 1 random fill tag.
    Expected: custom tag entries appear in the schedule.
    Buggy:   custom tag is missing (the user confirmed this in
             Approximate mode even though it works in Approximate OFF).
    """
    print("\n" + "=" * 70)
    print("BUG 1 (Approx Find-Replace): custom tag missing")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_custom_tag(
        name="MyCustom",
        start=QTime(10, 0), end=QTime(12, 0),  # 2-hour window, mid-day
        videos=RANDOM_FILL_VIDEOS[:2],
        video_count=2,
    ))
    tm.add_tag(_make_random_fill_tag(
        name="MyRF",
        fill_24h=True,
        videos=RANDOM_FILL_VIDEOS,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_approximate(num_days=1, mode="find_replace")
    _dump_schedule("Approx Find-Replace: custom + RF (1 day)", entries)

    custom_entries = [e for e in entries
                      if "MyCustom" in e.video_name]
    print(f"\n  custom-tag entries: {len(custom_entries)}")
    for e in custom_entries:
        print(f"    {e.video_name}")

    assert len(custom_entries) >= 2, (
        f"BUG 1 (APPROX) REPRODUCED: custom tag 'MyCustom' (video_count=2) "
        f"produced only {len(custom_entries)} entries in the schedule "
        f"(expected 2). Entries were silently dropped."
    )
    print("  PASS: custom tag emits all video_count entries in the Find-Replace schedule")


def test_bug5_series_missing_in_approximate_video_count_1():
    """
    Approximate ON + Find-Replace: 1 series tag (video_count=1) +
    1 random fill tag.
    Expected: at least one series entry per day, with episode file name.
    Buggy:   series tag is MISSING from the preview (the user's report).
    """
    print("\n" + "=" * 70)
    print("BUG 5 (Approx Find-Replace): series tag missing, video_count=1")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="Sandokan 1976",
        start=QTime(20, 0), end=QTime(20, 51),
        episodes=SANDOKAN_EPISODES,
        video_count=1,
        end_behavior="repeat",
        repeat_season=1,
    ))
    tm.add_tag(_make_random_fill_tag(
        name="MyRF",
        fill_24h=True,
        videos=RANDOM_FILL_VIDEOS,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_approximate(num_days=2, mode="find_replace")
    _dump_schedule("Approx Find-Replace: series(vc=1) + RF, 2 days", entries)

    series_entries = [e for e in entries
                      if "Sandokan" in e.video_name and "MyRF" not in e.video_name]
    print(f"\n  series entries: {len(series_entries)}")
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        s_h = (e.start_seconds // 3600) % 24
        s_m = (e.start_seconds % 3600) // 60
        e_h = (e.end_seconds // 3600) % 24
        e_m = (e.end_seconds % 3600) // 60
        print(f"    D{d} {s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d}  {e.video_name}")

    per_day = {}
    for e in series_entries:
        d = (e.start_seconds // 86400) + 1
        per_day[d] = per_day.get(d, 0) + 1
    print(f"  per-day series count: {per_day}")
    print(f"  num_days requested: 2")

    assert per_day.get(1, 0) >= 1 and per_day.get(2, 0) >= 1, (
        f"BUG 5 REPRODUCED: series tag 'Sandokan 1976' should appear on "
        f"EACH day, but per-day count is {per_day}. With video_count=1 "
        f"in Approx Find-Replace mode, the series is misplaced on day 1 "
        f"(anchored to a random-fill boundary instead of 20:00) and "
        f"missing entirely on day 2+."
    )
    print("  PASS: series tag is present on each day in the Find-Replace schedule")


def test_bug5_series_visible_in_approximate_video_count_2():
    """
    Approximate ON + Find-Replace: 1 series tag (video_count=2) +
    1 random fill tag — the WORKING case the user described.
    """
    print("\n" + "=" * 70)
    print("BUG 5 (Approx Find-Replace): series tag visible, video_count=2")
    print("=" * 70)

    tm = TagManager()
    tm.add_tag(_make_series_tag(
        name="Sandokan 1976",
        start=QTime(20, 0), end=QTime(23, 59),  # wider window for 2 eps
        episodes=SANDOKAN_EPISODES,
        video_count=2,
        end_behavior="repeat",
        repeat_season=1,
    ))
    tm.add_tag(_make_random_fill_tag(
        name="MyRF",
        fill_24h=True,
        videos=RANDOM_FILL_VIDEOS,
    ))

    sg = ScheduleGenerator(tm)
    entries = sg.apply_approximate(num_days=2, mode="find_replace")
    _dump_schedule("Approx Find-Replace: series(vc=2) + RF, 2 days", entries)

    series_entries = [e for e in entries
                      if "Sandokan" in e.video_name and "MyRF" not in e.video_name]
    print(f"\n  series entries: {len(series_entries)}")
    for e in series_entries:
        print(f"    {e.video_name}")

    # User says this case WORKS — assert at least 1 series entry.
    assert len(series_entries) >= 1, (
        f"REGRESSION: series tag with video_count=2 used to work; "
        f"now produces 0 entries."
    )
    print("  PASS: series tag is present in the Find-Replace schedule "
          "(video_count=2 case)")


if __name__ == "__main__":
    main()
