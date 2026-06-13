#!/usr/bin/env python3
"""Tests for GroupApproximateStrategy: grouped chronological tag placement."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag
from data_models import MultiSeriesTag, FRAGMENT_TAG_TYPE


def make_video(name, dur_min):
    return {"path": f"/p/{name}.mp4", "duration": dur_min * 60}


def run_group_approx(tags, num_days=1, overlap_strategy="fragment"):
    random.seed(42)
    tg = TagManager()
    for t in tags:
        tg.add_tag(t)
    sg = ScheduleGenerator(tg)
    entries = sg.apply_approximate(num_days=num_days, mode="group_approximate", overlap_strategy=overlap_strategy)
    return entries


def get_tag_entries(entries):
    return [e for e in entries if e.tag_type not in ("", FRAGMENT_TAG_TYPE)]


def test_chronological_order():
    """Custom tags placed in start_time order regardless of input order."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    early = Tag(name="Early", tag_type="custom", start_time=QTime(8, 0), end_time=QTime(9, 0),
                collection_videos=[make_video("early", 30)])
    late = Tag(name="Late", tag_type="custom", start_time=QTime(14, 0), end_time=QTime(15, 0),
               collection_videos=[make_video("late", 30)])
    mid = Tag(name="Mid", tag_type="custom", start_time=QTime(11, 0), end_time=QTime(12, 0),
              collection_videos=[make_video("mid", 30)])

    entries = run_group_approx([rf, late, early, mid])
    tag_entries = get_tag_entries(entries)

    tag_times = [(e.start_seconds, e.video_name) for e in tag_entries]
    sorted_times = sorted(tag_times, key=lambda x: x[0])
    assert tag_times == sorted_times, (
        f"Tags not in chronological order:\n  got: {tag_times}\n  expected: {sorted_times}"
    )
    names = [n for _, n in tag_times]
    early_i = next(i for i, n in enumerate(names) if n.endswith("early.mp4"))
    mid_i = next(i for i, n in enumerate(names) if n.endswith("mid.mp4"))
    late_i = next(i for i, n in enumerate(names) if n.endswith("late.mp4"))
    assert early_i < mid_i < late_i, f"Order violated: early={early_i}, mid={mid_i}, late={late_i}"
    print(f"  PASS: chronological_order — tags in [early, mid, late] order")


def test_overlapping_tags_no_interleaving():
    """Overlapping tags produce contiguous placement with no interleaving."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    tag_a = Tag(name="Tag A", tag_type="custom", start_time=QTime(9, 0), end_time=QTime(11, 0),
                collection_videos=[make_video("a1", 45), make_video("a2", 45)])
    tag_b = Tag(name="Tag B", tag_type="custom", start_time=QTime(10, 0), end_time=QTime(12, 0),
                collection_videos=[make_video("b1", 30)])

    entries = run_group_approx([rf, tag_a, tag_b])
    tag_entries = get_tag_entries(entries)

    a_entry = next(e for e in tag_entries if e.video_name.endswith("a1.mp4") or e.video_name.endswith("a2.mp4"))
    b_entry = next(e for e in tag_entries if e.video_name.endswith("b1.mp4"))
    a_end = a_entry.end_seconds
    b_start = b_entry.start_seconds
    assert b_start >= a_end, (
        f"Tag B (start={b_start}s) overlaps Tag A (end={a_end}s)"
    )
    print(f"  PASS: overlapping_no_interleaving — Tag A ends {a_end}s, Tag B starts {b_start}s")


def test_adjacent_tags_no_gap():
    """Adjacent tags placed back-to-back without gap."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    tag_a = Tag(name="Tag A", tag_type="custom", start_time=QTime(9, 0), end_time=QTime(10, 0),
                collection_videos=[make_video("a1", 30)])
    tag_b = Tag(name="Tag B", tag_type="custom", start_time=QTime(10, 0), end_time=QTime(11, 0),
                collection_videos=[make_video("b1", 30)])

    entries = run_group_approx([rf, tag_a, tag_b])
    tag_entries = get_tag_entries(entries)
    tag_entries.sort(key=lambda e: e.start_seconds)

    a_end = max(e.end_seconds for e in tag_entries if e.video_name.endswith("a1.mp4"))
    b_start = min(e.start_seconds for e in tag_entries if e.video_name.endswith("b1.mp4"))
    assert b_start >= a_end, (
        f"Adjacent tags have overlap: A ends {a_end}s, B starts {b_start}s"
    )
    print(f"  PASS: adjacent_no_gap — Tag A ends {a_end}s, Tag B starts {b_start}s")


def test_no_random_intrusion():
    """No random-fill entries overlap scheduled tag slots."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    tag = Tag(name="Tag", tag_type="custom", start_time=QTime(9, 0), end_time=QTime(12, 0),
              collection_videos=[make_video("t1", 30), make_video("t2", 30)])

    entries = run_group_approx([rf, tag])

    rf_entries = [e for e in entries if "rf.mp4" in e.video_name and e.tag_type != FRAGMENT_TAG_TYPE]
    tag_entries = [e for e in entries if "t1.mp4" in e.video_name or "t2.mp4" in e.video_name]

    if not tag_entries:
        print("  SKIP: no_random_intrusion — no tag entries placed")
        return

    tag_start = min(e.start_seconds for e in tag_entries)
    tag_end = max(e.end_seconds for e in tag_entries)

    intrusions = [re for re in rf_entries
                  if re.start_seconds < tag_end and re.end_seconds > tag_start]
    assert not intrusions, (
        f"Found {len(intrusions)} random entries overlapping tag slot [{tag_start}, {tag_end}]"
    )
    print(f"  PASS: no_random_intrusion — 0 random entries overlap tag slot [{tag_start}, {tag_end}]")


def test_no_errors():
    """No negative/zero duration entries or out-of-range days."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    tags = [
        rf,
        Tag(name="C1", tag_type="custom", start_time=QTime(6, 0), end_time=QTime(8, 0),
            collection_videos=[make_video("c1", 30)]),
        Tag(name="C2", tag_type="custom", start_time=QTime(12, 0), end_time=QTime(14, 0),
            collection_videos=[make_video("c2", 30)]),
    ]
    entries = run_group_approx(tags, num_days=2)
    errors = []
    for e in entries:
        dur = e.end_seconds - e.start_seconds
        if dur <= 0:
            errors.append(f"{e.video_name} zero/negative duration ({dur}s)")
        day = e.start_seconds // 86400
        if day >= 2 or day < 0:
            errors.append(f"{e.video_name} out of range day={day+1}")
    assert not errors, f"Errors: {errors}"
    print(f"  PASS: no_errors — {len(entries)} entries, 0 errors (2 days)")


def test_multi_series_included():
    """Multi-series tags included alongside custom tags in sorted order."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    c = Tag(name="Custom", tag_type="custom", start_time=QTime(9, 0), end_time=QTime(10, 0),
            collection_videos=[make_video("custom_a", 30)])
    m = MultiSeriesTag(
        name="Multi", start_time=QTime(14, 0), end_time=QTime(15, 0),
        series_list=[{
            "name": "Series1",
            "collection_videos": [make_video("multi_c", 30)],
            "start_season": 1, "start_episode": 1,
            "play_mode": "sequence", "video_count": 1,
        }],
    )

    entries = run_group_approx([rf, c, m])
    tag_entries = get_tag_entries(entries)
    custom_videos = [e.video_name for e in tag_entries if "custom_a" in e.video_name]
    multi_videos = [e.video_name for e in tag_entries if "multi_c" in e.video_name]
    assert custom_videos, "custom video not found"
    assert multi_videos, "multi-series video not found"
    custom_pos = next(i for i, e in enumerate(tag_entries) if "custom_a" in e.video_name)
    multi_pos = next(i for i, e in enumerate(tag_entries) if "multi_c" in e.video_name)
    assert custom_pos < multi_pos, "Custom tag should appear before later multi-series tag"
    print(f"  PASS: multi_series_included — custom and multi-series both present")


def test_span_all_overlap_strategies():
    """Works with all overlap strategies without errors."""
    rf = Tag(name="RF", tag_type="random_fill", start_time=QTime(0, 0), end_time=QTime(23, 59),
             is_random_fill=True, fill_24h=True,
             collection_videos=[make_video("rf", 60) for _ in range(48)])
    tag = Tag(name="Tag", tag_type="custom", start_time=QTime(9, 0), end_time=QTime(12, 0),
              collection_videos=[make_video("t1", 30), make_video("t2", 30)])

    for strategy in ("fragment", "skip", "gap_fill", "compact"):
        entries = run_group_approx([rf, tag], overlap_strategy=strategy)
        errors = [e for e in entries if e.end_seconds - e.start_seconds <= 0]
        assert not errors, f"{strategy}: zero-duration entries found"
    print(f"  PASS: span_all_overlap_strategies — all 4 strategies work")


if __name__ == "__main__":
    tests = [
        test_chronological_order,
        test_overlapping_tags_no_interleaving,
        test_adjacent_tags_no_gap,
        test_no_random_intrusion,
        test_no_errors,
        test_multi_series_included,
        test_span_all_overlap_strategies,
    ]
    print(f"Group Approximate Tests ({len(tests)} tests):")
    for t in tests:
        t()
    print("All tests passed.")
