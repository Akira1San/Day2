#!/usr/bin/env python3
"""Regression test for back-to-back video placement by duration.

Reproduces the reported bug: when a schedule is generated from multiple
collection files (e.g. akiratv + animation), videos must be placed one
after the other using their real durations (no gaps, no overlaps). It also
reproduces the save_schedule collection-id resolution bug where substring
matching maps "Predator.mp4" onto "AVP Alien Vs Predator.mp4".
"""
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
random.seed(42)

from PySide6.QtCore import QTime
from scheduler import ScheduleGenerator
from data_models import Tag, TagManager
from utils import load_collection_json, get_video_display_name

AKIRATV_PATH = '/home/akira/akira/AkiraTV_NEW/user/collections/collections_akiratv.json'
ANIMATION_PATH = '/home/akira/akira/AkiraTV_NEW/user/collections/collections_animation.json'


def make_video(name: str, duration: int, collection_id: str = "") -> dict:
    return {"path": f"/p/{name}.mp4", "duration": duration, "collection_id": collection_id}


def load_real_collections():
    """Merge collection files exactly like RandomFillDialog._reload_all_collections."""
    videos = []
    for fp, source in [(AKIRATV_PATH, 'akiratv'), (ANIMATION_PATH, 'animation')]:
        if not os.path.exists(fp):
            continue
        vids, _ = load_collection_json(fp)
        for v in vids:
            v = dict(v)
            v['_source_name'] = source
            v['_rate'] = 50
            videos.append(v)
    return videos


def build_generator(videos):
    tg = TagManager()
    rf = Tag(
        tag_type="random_fill", name="fill",
        start_time=QTime(0, 0), end_time=QTime(23, 59),
        is_random_fill=True, fill_24h=True,
        collection_path=AKIRATV_PATH,
        collection_videos=videos,
    )
    tg.add_tag(rf)
    gen = ScheduleGenerator(tg)
    gen.video_order_mode = "movie_sequence"
    gen._generate_count = 0
    return gen


def test_back_to_back_placement_real_collections():
    """Videos placed one after the other must tile the day with no gaps/overlaps."""
    videos = load_real_collections()
    assert videos, "real collections should load"

    gen = build_generator(videos)
    entries = gen.generate_random_fill(remaining_seconds=86400)
    assert entries, "schedule should produce entries"

    prev_end = None
    for entry in entries:
        if prev_end is not None:
            assert entry.start_seconds == prev_end, (
                f"gap/overlap: entry starts {entry.start_seconds} but previous ended {prev_end}"
            )
        prev_end = entry.end_seconds


def test_scheduled_duration_matches_collection():
    """Each entry's span must match its collection video duration.

    The last entry of a day may be truncated at the 86400s day boundary,
    so only entries that do not touch the boundary are checked exactly.
    """
    videos = load_real_collections()
    gen = build_generator(videos)
    entries = gen.generate_random_fill(remaining_seconds=86400)

    dur_by_name = {}
    for v in videos:
        dur_by_name.setdefault(get_video_display_name(v), set()).add(v['duration'])

    for entry in entries:
        if entry.end_seconds >= 86400:
            continue  # truncated at day boundary
        name = entry.video_name
        if name not in dur_by_name:
            continue
        span = entry.end_seconds - entry.start_seconds
        assert any(abs(span - d) < 1.5 for d in dur_by_name[name]), (
            f"{name} scheduled {span}s but collection has {dur_by_name[name]}"
        )


def _save_schedule_resolve(videos, video_name):
    """Mirror the (fixed) matching loop from DaypartSchedulerWindow.save_schedule."""
    if " - " in video_name:
        video_name = video_name.split(" - ", 1)[1]
    for vid in videos:
        if get_video_display_name(vid) == video_name:
            return vid.get('collection_id', '')
    for vid in videos:
        vid_name = get_video_display_name(vid)
        if vid_name in video_name or video_name in vid_name:
            return vid.get('collection_id', '')
    return None


def test_save_schedule_substring_bug():
    """save_schedule must map 'Predator.mp4' to its own collection, not a substring hit.

    'Predator.mp4' is a substring of 'AVP Alien Vs Predator.mp4'. With plain
    substring matching the loop resolves the scheduled Predator entry to
    avp_alien_vs_predator (which is ~21 minutes shorter). This was the
    regression that pushed the next video too far ahead on the TV schedule.
    """
    videos = load_real_collections()
    assert _save_schedule_resolve(videos, 'Predator.mp4') == 'predator'
    assert _save_schedule_resolve(videos, 'AVP Alien Vs Predator.mp4') == 'avp_alien_vs_predator'
    assert _save_schedule_resolve(videos, 'fill - Predator.mp4') == 'predator'
    assert _save_schedule_resolve(videos, 'fill - AVP Alien Vs Predator.mp4') == 'avp_alien_vs_predator'


def test_back_to_back_placement_synthetic_collision():
    """Synthetic check that placement uses each video's own duration."""
    videos = [
        dict(make_video("AVP Alien Vs Predator", 5135, "avp_alien_vs_predator"), **{'_source_name': 'akiratv', '_rate': 50}),
        dict(make_video("Predator", 6395, "predator"), **{'_source_name': 'akiratv', '_rate': 50}),
        dict(make_video("Predators", 6059, "predators"), **{'_source_name': 'akiratv', '_rate': 50}),
    ]
    gen = build_generator(videos)
    entries = gen.generate_random_fill(remaining_seconds=86400)

    prev_end = None
    for entry in entries:
        if prev_end is not None:
            assert entry.start_seconds == prev_end
        if entry.end_seconds < 86400:  # skip day-boundary truncation
            span = entry.end_seconds - entry.start_seconds
            assert span in (5135, 6395, 6059)
        prev_end = entry.end_seconds
