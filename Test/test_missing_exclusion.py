#!/usr/bin/env python3
"""Tests for missing-on-disk video exclusion in schedule previews.

Videos whose files no longer exist on disk are automatically excluded from
schedule previews (custom, series, multi-series, random fill) so users don't
have to blacklist them manually. Gap fillers are intentionally NOT filtered.

Real temp files stand in for "existing" videos; paths inside the same temp
dir that were never created stand in for "missing" videos.
"""
import os
import sys
import random
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTime
from models import ScheduleGenerator, TagManager, Tag
from utils import is_video_missing, filter_available_videos, load_gap_collections


def make_real_video(tmpdir, name, duration=1800, **kw):
    path = os.path.join(tmpdir, name)
    with open(path, "wb") as f:
        f.write(b"\0")
    video = {"path": path, "duration": duration}
    video.update(kw)
    return video


def make_missing_video(tmpdir, name, duration=1800, **kw):
    # Path inside tmpdir that is never created on disk.
    video = {"path": os.path.join(tmpdir, name), "duration": duration}
    video.update(kw)
    return video


def test_is_video_missing_and_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        real = make_real_video(tmpdir, "real.mp4")
        missing = make_missing_video(tmpdir, "gone.mp4")
        assert not is_video_missing(real)
        assert is_video_missing(missing)
        assert is_video_missing({"path": ""})
        assert is_video_missing({"duration": 90})  # no path key
        assert is_video_missing("not-a-dict")
        kept = filter_available_videos([real, missing])
        assert kept == [real], f"expected only real video, got {kept}"
    print("  is_video_missing_and_filter OK")


def test_custom_tag_excludes_missing():
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmpdir:
        a = make_real_video(tmpdir, "A.mp4")
        b = make_missing_video(tmpdir, "B.mp4")
        c = make_real_video(tmpdir, "C.mp4")
        tm = TagManager()
        tag = Tag(tag_type="custom", name="Block",
                  start_time=QTime(8, 0), end_time=QTime(9, 0),
                  collection_videos=[a, b, c], video_count=2)
        tm.add_tag(tag)
        sg = ScheduleGenerator(tm)
        assert sg.exclude_missing is True  # default ON
        entries = sg.apply_custom_tags(use_cache=False, num_days=1)
        names = [e.video_name for e in entries]
        assert any("A.mp4" in n for n in names), f"A.mp4 missing from {names}"
        assert any("C.mp4" in n for n in names), f"C.mp4 missing from {names}"
        assert not any("B.mp4" in n for n in names), f"B.mp4 should be excluded: {names}"
        assert sg._last_missing_excluded >= 1
        # Non-mutating: the tag still holds all 3 videos afterwards.
        assert len(tag.collection_videos) == 3
    print("  custom_tag_excludes_missing OK")


def test_series_compact_sequence():
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmpdir:
        ep1 = make_missing_video(tmpdir, "Show.S01E01.mp4")
        ep2 = make_real_video(tmpdir, "Show.S01E02.mp4")
        ep3 = make_real_video(tmpdir, "Show.S01E03.mp4")
        tm = TagManager()
        tm.add_tag(Tag(tag_type="custom", name="Series", is_series=True,
                       start_time=QTime(10, 0), end_time=QTime(11, 0),
                       collection_videos=[ep1, ep2, ep3],
                       video_count=1, play_mode="sequence",
                       start_season=1, start_episode=1))
        sg = ScheduleGenerator(tm)
        entries = sg.apply_custom_tags(use_cache=False, num_days=2)
        by_day = {}
        for e in entries:
            if e.tag_type == "series":
                by_day[e.start_seconds // 86400] = e.video_name
        # Compact: day 0 takes first AVAILABLE episode (E02), day 1 takes E03.
        assert "S01E02" in by_day.get(0, ""), f"day0 should be E02: {by_day}"
        assert "S01E03" in by_day.get(1, ""), f"day1 should be E03: {by_day}"
    print("  series_compact_sequence OK")


def test_random_fill_excludes_missing():
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmpdir:
        real = make_real_video(tmpdir, "real.mp4", duration=3600)
        missing = make_missing_video(tmpdir, "gone.mp4", duration=3600)
        tm = TagManager()
        tm.add_tag(Tag("random", "RF", QTime(0, 0), QTime(23, 59),
                       collection_videos=[real, missing],
                       is_random_fill=True, fill_24h=True))
        sg = ScheduleGenerator(tm)
        entries = sg.apply_custom_tags(use_cache=False, num_days=1)
        assert entries, "expected fill entries"
        assert not any("gone.mp4" in e.video_name for e in entries)
        assert any("real.mp4" in e.video_name for e in entries)
    print("  random_fill_excludes_missing OK")


def test_gap_filler_not_excluded():
    # Gap collections load verbatim, even if files are missing on disk.
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        coll_path = os.path.join(tmpdir, "trailers.json")
        with open(coll_path, "w", encoding="utf-8") as f:
            json.dump({"collections": [{"id": "t1", "tags": [], "videos": [
                {"path": os.path.join(tmpdir, "missing_trailer.mp4"), "duration": 60},
            ]}]}, f)
        videos = load_gap_collections([{"path": coll_path, "type": "trailer"}])
        assert len(videos) == 1, f"gap videos must not be filtered: {videos}"
    print("  gap_filler_not_excluded OK")


def test_all_missing_fallback_no_crash():
    random.seed(1)
    with tempfile.TemporaryDirectory() as tmpdir:
        missing = make_missing_video(tmpdir, "gone.mp4")
        tm = TagManager()
        tag = Tag(tag_type="custom", name="Block",
                  start_time=QTime(8, 0), end_time=QTime(9, 0),
                  collection_videos=[missing], video_count=1)
        tm.add_tag(tag)
        sg = ScheduleGenerator(tm)
        entries = sg.apply_custom_tags(use_cache=False, num_days=1)  # must not crash
        assert not any("gone.mp4" in e.video_name for e in entries)
        assert len(tag.collection_videos) == 1  # non-mutating
    print("  all_missing_fallback_no_crash OK")


def test_exclude_missing_opt_out():
    # Tests with fake fixture paths can disable the filesystem check.
    tm = TagManager()
    tm.add_tag(Tag(tag_type="custom", name="Block",
                   start_time=QTime(8, 0), end_time=QTime(9, 0),
                   collection_videos=[{"path": "/videos/fake.mp4", "duration": 1800}],
                   video_count=1))
    sg = ScheduleGenerator(tm, exclude_missing=False)
    entries = sg.apply_custom_tags(use_cache=False, num_days=1)
    assert any("fake.mp4" in e.video_name for e in entries), entries
    assert sg._last_missing_excluded == 0
    print("  exclude_missing_opt_out OK")


if __name__ == "__main__":
    test_is_video_missing_and_filter()
    test_custom_tag_excludes_missing()
    test_series_compact_sequence()
    test_random_fill_excludes_missing()
    test_gap_filler_not_excluded()
    test_all_missing_fallback_no_crash()
    test_exclude_missing_opt_out()
    print("All missing-exclusion tests PASSED")
