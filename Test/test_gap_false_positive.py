#!/usr/bin/env python3
"""Test: no gap entries appear in schedule when no gap tag is added.

The bug: mark_continuity_problems() sets problem="gap" on entries that
follow a time gap in the schedule.  _is_gap_entry() treated problem="gap"
the same as tag_type="gap_fill", causing normal entries to be displayed
as "Gap" groups in the preview tree even when the user never added a gap
filler tag.

Scenarios:
  1. random fill + series tag, apply_custom_tags  → 0 gap_fill entries
  2. random fill + series tag, apply_approximate  → 0 gap_fill entries
  3. random fill + custom tag, no gap tag         → 0 gap_fill entries
"""

import sys, logging, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
logging.basicConfig(level=logging.WARNING)

from data_models import Tag, TagManager, QTime, mark_continuity_problems
from scheduler import ScheduleGenerator


def _make_rf_tag(name: str, hour: int, duration_h: int = 2) -> Tag:
    return Tag(
        tag_type="random_fill", name=name,
        start_time=QTime(hour, 0), end_time=QTime((hour + duration_h) % 24, 0),
        collection_videos=[{'path': f'/tmp/rf_{i}.mp4', 'duration': 1800}
                          for i in range(4)],
        video_count=1, randomize_videos=False,
        is_random_fill=True, is_series=False,
    )


def _make_series_tag(name: str, hour: int) -> Tag:
    return Tag(
        tag_type="series", name=name,
        start_time=QTime(hour, 0), end_time=QTime(hour + 1, 0),
        collection_videos=[{'path': f'/tmp/{name}.mp4', 'duration': 3600,
                           'season': 1, 'episode': 1}],
        video_count=1, randomize_videos=False,
        is_random_fill=False, is_series=True,
    )


def _make_custom_tag(name: str, hour: int) -> Tag:
    return Tag(
        tag_type="custom", name=name,
        start_time=QTime(hour, 0), end_time=QTime(hour + 1, 0),
        collection_videos=[{'path': f'/tmp/{name}.mp4', 'duration': 3600}],
        video_count=1, randomize_videos=False,
        is_random_fill=False, is_series=False,
    )


def test_custom_tags_no_gap_tag():
    """Two custom tags with a gap → no gap_fill entries."""
    tm = TagManager()
    tm.add_tag(_make_custom_tag("Morning", 8))
    tm.add_tag(_make_custom_tag("Evening", 18))
    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(use_cache=False, num_days=1)
    mark_continuity_problems(entries)

    gap_fill = [e for e in entries if e.tag_type == "gap_fill"]
    assert len(gap_fill) == 0, f"Expected 0 gap_fill entries, got {len(gap_fill)}"

    problems = [e for e in entries if e.problem == "gap"]
    print(f"test_custom_tags_no_gap_tag: {len(problems)} entries have problem=gap (diagnostic only), "
          f"0 gap_fill entries — PASS")


def test_random_fill_and_series_no_gap_tag():
    """Random fill + series (no gap tag) → 0 gap_fill entries."""
    tm = TagManager()
    tm.add_tag(_make_rf_tag("RF", 0, 6))
    tm.add_tag(_make_series_tag("Series A", 12))
    sg = ScheduleGenerator(tm)
    entries = sg.apply_custom_tags(use_cache=False, num_days=1)
    mark_continuity_problems(entries)

    gap_fill = [e for e in entries if e.tag_type == "gap_fill"]
    assert len(gap_fill) == 0, f"Expected 0 gap_fill entries, got {len(gap_fill)}"

    problems = [e for e in entries if e.problem == "gap"]
    print(f"test_random_fill_and_series_no_gap_tag (custom): {len(problems)} entries have problem=gap, "
          f"0 gap_fill — PASS")


def test_random_fill_and_series_approximate_no_gap_tag():
    """Random fill + series in approximate mode (no gap tag) → 0 gap_fill."""
    for mode in ["find_replace", "linear"]:
        tm = TagManager()
        tm.add_tag(_make_rf_tag("RF", 0, 8))
        tm.add_tag(_make_series_tag("Series A", 14))
        sg = ScheduleGenerator(tm)
        entries = sg.apply_approximate(num_days=1, mode=mode)
        mark_continuity_problems(entries)

        gap_fill = [e for e in entries if e.tag_type == "gap_fill"]
        assert len(gap_fill) == 0, \
            f"[{mode}] Expected 0 gap_fill entries, got {len(gap_fill)}"

        print(f"test_random_fill_and_series_approximate_no_gap_tag ({mode}): "
              f"0 gap_fill — PASS")


if __name__ == "__main__":
    test_custom_tags_no_gap_tag()
    test_random_fill_and_series_no_gap_tag()
    test_random_fill_and_series_approximate_no_gap_tag()
    print("\nAll tests PASSED")
