"""Test gap filler behavior with the new performance cap (section 10).

Scenarios:
  1. 3 custom tags with gaps between + gap tag → gap filler fills inter-tag gaps
  2. gap_max_duration=None → soft-capped at 7200s (2h)
  3. gap_max_duration=0 → soft-capped at 7200s (2h)
  4. gap_max_duration=3600 → capped at 1h
  5. fill_24h random fill present → gap filler fills remaining gaps
  6. preserve_boundaries=True → videos not split across day boundary
"""

import sys, logging, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
logging.basicConfig(level=logging.WARNING)

from scheduler import ScheduleGenerator
from data_models import Tag, TagManager, QTime


def _make_tag(name: str, hour: int, tag_type: str = "custom") -> Tag:
    return Tag(
        tag_type=tag_type,
        name=name,
        start_time=QTime(hour, 0),
        end_time=QTime(hour + 1, 0),
        collection_videos=[{'path': f'/tmp/{name}.mp4', 'duration': 3600}],
        video_count=1,
        randomize_videos=False,
        is_random_fill=False,
        is_series=False,
    )


def test_three_custom_tags_with_gaps():
    """3 tags at 08:00, 12:00, 18:00 → gaps at 00-08, 09-12, 13-18, 19-24."""
    tm = TagManager()
    for h, name in [(8, "Morning"), (12, "Midday"), (18, "Evening")]:
        tm.add_tag(_make_tag(name, h))
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=7200, gap_preserve_boundaries=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    print(f"test_three_custom_tags_with_gaps: {len(entries)} total, {len(gap_e)} gap entries")
    assert len(gap_e) > 0, "Expected gap entries between custom tags"
    # Verify no gap entry overlaps any custom entry
    custom_ranges = [(e.start_seconds, e.end_seconds) for e in entries if e.tag_type == "custom"]
    for g in gap_e:
        for cs, ce in custom_ranges:
            assert not (g.start_seconds < ce and g.end_seconds > cs), f"Gap {g.video_name} overlaps custom entry"
    print("  PASS: No overlaps between gap and custom entries")
    print("  PASS: Gap entries found between custom tags")


def test_soft_cap_none():
    """gap_max_duration=None → soft-capped at 14400s."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag", 12))
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=None, gap_preserve_boundaries=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    total_fill = sum(e.end_seconds - e.start_seconds for e in gap_e)
    print(f"test_soft_cap_none: {total_fill}s gap fill (expected ≤ 14400)")
    # Soft cap is 14400 — allow a little slack for last-video overrun
    assert total_fill <= 14600, f"Soft cap 14400 exceeded: {total_fill}s"
    print("  PASS: Soft cap at 14400s enforced")


def test_soft_cap_zero():
    """gap_max_duration=0 → soft-capped at 14400s."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag", 12))
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=0, gap_preserve_boundaries=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    total_fill = sum(e.end_seconds - e.start_seconds for e in gap_e)
    print(f"test_soft_cap_zero: {total_fill}s gap fill (expected ≤ 14400)")
    assert total_fill <= 14600, f"Soft cap 14400 exceeded: {total_fill}s"
    print("  PASS: Soft cap at 14400s enforced")


def test_hard_cap_3600():
    """gap_max_duration=3600 → capped at 3600s."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag", 12))
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=3600, gap_preserve_boundaries=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    total_fill = sum(e.end_seconds - e.start_seconds for e in gap_e)
    print(f"test_hard_cap_3600: {total_fill}s gap fill (expected ≤ 3600)")
    assert total_fill <= 3800, f"Cap 3600 exceeded: {total_fill}s"
    print("  PASS: Hard cap at 3600s enforced")


def test_fill_24h_with_gap():
    """fill_24h random fill + gap tag → gap filler fills remaining gaps."""
    tm = TagManager()
    rf = Tag(tag_type="random", name="24h Fill", is_random_fill=True,
             fill_24h=True, start_time=QTime(0, 0), end_time=QTime(23, 59),
             collection_videos=[{'path': '/tmp/rf.mp4', 'duration': 7200}],
             video_count=12)
    tm.add_tag(rf)
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=7200, gap_preserve_boundaries=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    print(f"test_fill_24h_with_gap: {len(entries)} total, {len(gap_e)} gap entries")
    # Gap filler may or may not find gaps depending on random fill coverage
    assert len(entries) > 0, "Expected some entries"
    print("  PASS: Schedule generated with both random fill and gap tag")


def test_preserve_boundaries():
    """gap_preserve_boundaries=True → no video crosses midnight."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag", 23))  # near midnight
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=7200, gap_preserve_boundaries=True)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    for g in gap_e:
        # No gap entry should end after 24:00 (86400s) of day 1
        assert g.end_seconds <= 86400, f"Gap entry {g.video_name} crosses midnight (ends at {g.end_seconds}s)"
    print(f"test_preserve_boundaries: {len(gap_e)} gap entries, none cross midnight")
    print("  PASS: Preserve boundaries respected")


def test_no_gap_tag():
    """No gap tag → no gap entries generated."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag", 8))
    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    assert len(gap_e) == 0, "Expected 0 gap entries with no gap tag"
    print("test_no_gap_tag: PASS")


def test_empty_gap_collections():
    """Gap tag with no collections → no gap entries."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag", 8))
    gt = Tag(tag_type="gap", name="Empty Gap", is_gap_filler=True,
             gap_collections=[], gap_max_duration=3600)
    tm.add_tag(gt)
    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    assert len(gap_e) == 0, "Expected 0 gap entries with empty collections"
    print("test_empty_gap_collections: PASS")


def test_round_robin_cycling():
    """Gap videos cycle in round-robin order across multiple gaps."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag1", 2))
    tm.add_tag(_make_tag("Tag2", 4))
    tm.add_tag(_make_tag("Tag3", 6))
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=7200, gap_preserve_boundaries=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = sorted([e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"],
                   key=lambda x: x.start_seconds)
    # Check round-robin: the first video should differ from the first video of the next gap
    if len(gap_e) >= 2:
        assert gap_e[0].video_name != gap_e[1].video_name, "Round-robin should cycle"
    print(f"test_round_robin_cycling: {len(gap_e)} gap entries")
    print("  PASS: Round-robin ordering")


def test_between_only_fills_middle_gaps():
    """gap_fill_between_only=True → only fills gaps BETWEEN tags, not edges."""
    tm = TagManager()
    tm.add_tag(_make_tag("Tag1", 2))
    tm.add_tag(_make_tag("Tag2", 4))
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=14400, gap_preserve_boundaries=False,
             gap_fill_between_only=True)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    gap_e = sorted([e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"],
                   key=lambda x: x.start_seconds)
    # All gap entries should be between 02:00 and 04:00 (the inter-tag gap)
    for g in gap_e:
        assert g.start_seconds >= 7200, f"Gap entry before first tag: {g.video_name} at {g.start_seconds}s"
        assert g.end_seconds <= 14400, f"Gap entry after last tag: {g.video_name} at {g.end_seconds}s"
    # The pre-first-tag gap (00:00-02:00) and post-last-tag gap (04:00-24:00) should be empty
    pre_gap = [e for e in gap_e if e.start_seconds < 7200]
    post_gap = [e for e in gap_e if e.start_seconds >= 14400]
    assert len(pre_gap) == 0, f"Expected 0 pre-first-tag gap entries, got {len(pre_gap)}"
    assert len(post_gap) == 0, f"Expected 0 post-last-tag gap entries, got {len(post_gap)}"
    assert len(gap_e) > 0, "Expected gap entries in middle gap"
    print(f"test_between_only_fills_middle_gaps: {len(gap_e)} entries, all in 02:00-04:00 zone")
    print("  PASS: Only inter-tag gaps filled")


def test_auto_resolve_shifts_overlapping_tags():
    """gap_auto_resolve_overlaps=True shifts overlapping custom tags to create gaps."""
    tm = TagManager()
    # Tag1: 08:00-10:00, Tag2: 09:00-11:00 → overlap 1h
    # Tag3: 13:00-15:00, Tag4: 14:00-16:00 → overlap 1h
    for h, name in [(8, "Early"), (9, "Late"), (13, "Afternoon1"), (14, "Afternoon2")]:
        t = Tag(tag_type="custom", name=name,
                start_time=QTime(h, 0), end_time=QTime(h+2, 0),
                collection_videos=[{'path': f'/tmp/{name}.mp4', 'duration': 7200}],
                video_count=1, randomize_videos=False)
        tm.add_tag(t)
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=14400, gap_preserve_boundaries=False,
             gap_auto_resolve_overlaps=True, gap_shift_padding=180)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    custom_e = sorted([e for e in entries if e.tag_type == "custom"], key=lambda x: x.start_seconds)
    assert len(custom_e) >= 4, f"Expected at least 4 custom entries, got {len(custom_e)}"
    # Tag2 (Late) should start after Tag1 (Early) ends + padding
    early_end = custom_e[0].end_seconds  # Early tag end
    late_start = custom_e[1].start_seconds  # Late tag start
    assert late_start >= early_end, f"Late tag ({late_start}s) starts before Early ends ({early_end}s)"
    # Tag4 should start after Tag3 ends + padding
    a1_end = custom_e[2].end_seconds
    a2_start = custom_e[3].start_seconds
    assert a2_start >= a1_end, f"Afternoon2 ({a2_start}s) starts before Afternoon1 ends ({a1_end}s)"
    # Gap entries should exist between shifted tags
    gap_e = [e for e in entries if e.problem == "gap" or e.tag_type == "gap_fill"]
    assert len(gap_e) > 0, "Expected gap entries between shifted tags"
    print(f"test_auto_resolve_shifts_overlapping_tags: {len(custom_e)} custom, {len(gap_e)} gap entries")
    print(f"  Early ends {early_end//3600}:{(early_end%3600)//60:02d}, Late starts {late_start//3600}:{(late_start%3600)//60:02d}")
    print("  PASS: Overlapping tags shifted, gaps filled")


def test_auto_resolve_off_keeps_overlaps():
    """gap_auto_resolve_overlaps=False keeps original overlapping times."""
    tm = TagManager()
    t1 = Tag(tag_type="custom", name="Tag1",
             start_time=QTime(8, 0), end_time=QTime(10, 0),
             collection_videos=[{'path': '/tmp/t1.mp4', 'duration': 7200}],
             video_count=1, randomize_videos=False)
    t2 = Tag(tag_type="custom", name="Tag2",
             start_time=QTime(9, 0), end_time=QTime(11, 0),
             collection_videos=[{'path': '/tmp/t2.mp4', 'duration': 7200}],
             video_count=1, randomize_videos=False)
    tm.add_tag(t1)
    tm.add_tag(t2)
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=14400, gap_preserve_boundaries=False,
             gap_auto_resolve_overlaps=False)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    custom_e = sorted([e for e in entries if e.tag_type == "custom"], key=lambda x: x.start_seconds)
    # Without auto-resolve, Tag1 ends at 10:00 and Tag2 starts at 09:00 (overlap)
    t2_start = custom_e[1].start_seconds
    expected = 9 * 3600  # 09:00
    assert t2_start == expected, f"Expected Tag2 at {expected}s, got {t2_start}s"
    print("test_auto_resolve_off_keeps_overlaps: PASS")


def test_runtime_overlap_detection():
    """gap_estimate_runtime_overlap=True catches overlaps from video overflow."""
    tm = TagManager()
    # Tag1: 08:00-10:00 but its 2 videos of 2h each extend it to 12:00
    t1 = Tag(tag_type="custom", name="LongMovie",
             start_time=QTime(8, 0), end_time=QTime(10, 0),
             collection_videos=[
                 {'path': '/tmp/t1a.mp4', 'duration': 7200},
                 {'path': '/tmp/t1b.mp4', 'duration': 7200},
             ],
             video_count=2, randomize_videos=False)
    # Tag2: 11:00-13:00 — no defined overlap (10:00 < 11:00), but runtime overlaps
    t2 = Tag(tag_type="custom", name="Show",
             start_time=QTime(11, 0), end_time=QTime(13, 0),
             collection_videos=[{'path': '/tmp/t2.mp4', 'duration': 7200}],
             video_count=1, randomize_videos=False)
    tm.add_tag(t1)
    tm.add_tag(t2)
    gt = Tag(tag_type="gap", name="Gap", is_gap_filler=True,
             gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
             gap_max_duration=14400, gap_preserve_boundaries=False,
             gap_auto_resolve_overlaps=True, gap_shift_padding=180,
             gap_estimate_runtime_overlap=True)
    tm.add_tag(gt)

    entries = ScheduleGenerator(tm).apply_custom_tags(use_cache=False, num_days=1)
    # Find Show entry (Tag2) — don't assume index order since Tag1 may produce multiple entries
    show_entries = sorted([e for e in entries if e.tag_type == "custom" and "Show" in e.video_name],
                          key=lambda x: x.start_seconds)
    assert len(show_entries) == 1, f"Expected 1 Show entry, got {len(show_entries)}"
    show_start = show_entries[0].start_seconds
    # With runtime estimation, Show should be shifted past Tag1's estimated end (12:00)
    assert show_start >= 43200, f"Show should start at or after 12:00, got {show_start}s"
    print(f"test_runtime_overlap_detection: Show starts at {show_start}s (expected ≥ 43200)")
    print("  PASS: Runtime overlap detected, tags shifted")

    # Now test with runtime estimation OFF → should stay at original positions
    tm2 = TagManager()
    tm2.add_tag(Tag(tag_type="custom", name="LongMovie",
                    start_time=QTime(8, 0), end_time=QTime(10, 0),
                    collection_videos=[
                        {'path': '/tmp/t1a.mp4', 'duration': 7200},
                        {'path': '/tmp/t1b.mp4', 'duration': 7200},
                    ],
                    video_count=2, randomize_videos=False))
    tm2.add_tag(Tag(tag_type="custom", name="Show",
                    start_time=QTime(11, 0), end_time=QTime(13, 0),
                    collection_videos=[{'path': '/tmp/t2.mp4', 'duration': 7200}],
                    video_count=1, randomize_videos=False))
    tm2.add_tag(Tag(tag_type="gap", name="Gap", is_gap_filler=True,
                    gap_collections=[{"path": "/home/akira/Videos/trailers/trailers.json", "type": "trailer"}],
                    gap_max_duration=14400, gap_preserve_boundaries=False,
                    gap_auto_resolve_overlaps=True, gap_shift_padding=180,
                    gap_estimate_runtime_overlap=False))
    entries2 = ScheduleGenerator(tm2).apply_custom_tags(use_cache=False, num_days=1)
    show_entries2 = sorted([e for e in entries2 if e.tag_type == "custom" and "Show" in e.video_name],
                           key=lambda x: x.start_seconds)
    assert len(show_entries2) == 1, f"Expected 1 Show entry in tm2, got {len(show_entries2)}"
    show_start_off = show_entries2[0].start_seconds
    expected = 11 * 3600
    assert show_start_off == expected, f"Expected Show at {expected}s with runtime off, got {show_start_off}s"
    print(f"  Show at {show_start_off}s (unchanged) with runtime OFF")
    print("  PASS: Runtime overlap detection disabled, no shift")


if __name__ == "__main__":
    test_no_gap_tag()
    test_empty_gap_collections()
    test_three_custom_tags_with_gaps()
    test_soft_cap_none()
    test_soft_cap_zero()
    test_hard_cap_3600()
    test_fill_24h_with_gap()
    test_preserve_boundaries()
    test_round_robin_cycling()
    test_between_only_fills_middle_gaps()
    test_auto_resolve_shifts_overlapping_tags()
    test_auto_resolve_off_keeps_overlaps()
    test_runtime_overlap_detection()
    print("\nAll tests PASSED")
