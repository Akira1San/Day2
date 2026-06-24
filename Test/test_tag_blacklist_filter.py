#!/usr/bin/env python3
"""Test that blacklisted videos don't appear in added_videos when loading a tag.

Reproduces bug: when loading a tag with a blacklist, some blacklisted videos
were appearing in BOTH the 'Added Videos' and 'Blacklist' listboxes.
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTime
from models import Tag
from serialization import load_single_tag_from_ini, save_single_tag_to_ini
from utils import filter_videos_by_blacklist, is_video_in_blacklist, load_collection_videos_only, load_blacklist_json


def make_video(name: str, dur_sec: int = 3600) -> dict:
    return {"path": f"/videos/{name}.mp4", "duration": dur_sec, "name": f"{name}.mp4"}


def make_collection_json(path, videos):
    data = {"collections": [{"id": "test_coll", "name": "Test", "videos": videos}]}
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def make_blacklist_json(path, video_paths):
    data = {"blacklist": [{"path": p} for p in video_paths]}
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def make_tag_ini(path, collection_path, blacklist_path):
    tag = Tag(
        tag_type="random",
        name="Test Random Fill",
        start_time=QTime(0, 0),
        end_time=QTime(23, 59),
        collection_path=collection_path,
        blacklist_path=blacklist_path,
        is_random_fill=True,
        fill_24h=True,
    )
    save_single_tag_to_ini(tag, path)


# ── Tests ─────────────────────────────────────────────────────────────

def test_filter_videos_by_blacklist():
    videos = [make_video("a"), make_video("b"), make_video("c")]
    blacklist = [{"path": "/videos/b.mp4"}]
    filtered = filter_videos_by_blacklist(videos, blacklist)
    assert len(filtered) == 2, f"Expected 2, got {len(filtered)}"
    assert all(v['path'] != '/videos/b.mp4' for v in filtered)
    print("  PASS: filter_videos_by_blacklist works")


def test_tag_init_filters_blacklist():
    videos = [make_video("a"), make_video("b"), make_video("c")]
    blacklist = [{"path": "/videos/b.mp4"}]
    tag = Tag(
        tag_type="random", name="Test",
        collection_videos=videos,
        blacklist=blacklist,
        is_random_fill=True,
    )
    assert len(tag.collection_videos) == 2, f"Expected 2, got {len(tag.collection_videos)}"
    paths = [v['path'] for v in tag.collection_videos]
    assert "/videos/b.mp4" not in paths, "b.mp4 should be filtered out"
    print("  PASS: Tag.__init__ filters blacklisted videos")


def test_load_tag_from_ini_filters_blacklist():
    with tempfile.TemporaryDirectory() as tmp:
        videos = [make_video(f"movie_{c}", 7200) for c in "abc"]
        coll_path = os.path.join(tmp, "collection.json")
        make_collection_json(coll_path, videos)

        bl_path = os.path.join(tmp, "collection_blacklist.json")
        make_blacklist_json(bl_path, ["/videos/movie_b.mp4"])

        tag_ini = os.path.join(tmp, "tag.ini")
        make_tag_ini(tag_ini, coll_path, bl_path)

        tag = load_single_tag_from_ini(tag_ini, Tag, QTime.fromString)
        assert tag is not None, "Tag should load successfully"
        assert len(tag.blacklist) == 1, f"Expected 1 blacklist entry, got {len(tag.blacklist)}"

        added_paths = {v.get('path', '') for v in tag.collection_videos}
        bl_paths = {b.get('path', '') for b in tag.blacklist}
        overlap = added_paths & bl_paths
        assert len(overlap) == 0, \
            f"BUG: {len(overlap)} videos in both collection_videos and blacklist: {overlap}"
        assert "/videos/movie_b.mp4" not in added_paths

        print(f"  PASS: Tag loaded: {len(tag.collection_videos)} added, {len(tag.blacklist)} blacklisted")


def test_populate_dialog_state():
    """Simulate _populate_from_tag logic that the dialog uses."""
    with tempfile.TemporaryDirectory() as tmp:
        videos = [make_video(f"vid_{i}", 1800) for i in range(5)]
        coll_path = os.path.join(tmp, "collection.json")
        make_collection_json(coll_path, videos)

        bl_path = os.path.join(tmp, "collection_blacklist.json")
        make_blacklist_json(bl_path, ["/videos/vid_1.mp4", "/videos/vid_3.mp4"])

        tag_ini = os.path.join(tmp, "tag.ini")
        make_tag_ini(tag_ini, coll_path, bl_path)
        tag = load_single_tag_from_ini(tag_ini, Tag, QTime.fromString)

        # Simulate _populate_from_tag:
        blacklist = tag.blacklist.copy()
        all_videos = load_collection_videos_only(tag.collection_path)
        added_videos = tag.collection_videos.copy()
        added_videos = filter_videos_by_blacklist(added_videos, blacklist)

        bl_paths = {b.get('path', '') for b in blacklist}
        added_paths = {v.get('path', '') for v in added_videos}
        overlap = added_paths & bl_paths
        assert len(overlap) == 0, \
            f"BUG: {len(overlap)} videos in both added and blacklist: {overlap}"
        assert "/videos/vid_1.mp4" not in added_paths
        assert "/videos/vid_3.mp4" not in added_paths
        assert "/videos/vid_0.mp4" in added_paths
        assert "/videos/vid_2.mp4" in added_paths
        assert "/videos/vid_4.mp4" in added_paths

        print(f"  PASS: Dialog state correct: {len(added_videos)} added, {len(blacklist)} blacklisted")


def test_filter_by_basename_after_move():
    """Video moved to different dir: same basename, different path."""
    videos = [
        {"path": "/videos/old/movie_a.mp4", "duration": 3600, "name": "movie_a.mp4"},
        {"path": "/videos/old/movie_b.mp4", "duration": 5400, "name": "movie_b.mp4"},
    ]
    collection_videos = [
        {"path": "/videos/old/movie_a.mp4", "duration": 3600, "name": "movie_a.mp4"},
        {"path": "/videos/new/movie_b.mp4", "duration": 5400, "name": "movie_b.mp4"},
    ]
    blacklist = [{"path": "/videos/old/movie_b.mp4"}]

    # Exact path filtering would miss movie_b (different dirs)
    # Basename filtering should catch it
    filtered = filter_videos_by_blacklist(collection_videos, blacklist)
    assert len(filtered) == 1, f"Expected 1, got {len(filtered)}"
    assert filtered[0]['path'] == "/videos/old/movie_a.mp4", "movie_a should remain"
    print(f"  PASS: filter_by_basename_after_move catches moved file")


def test_is_video_in_blacklist_by_basename():
    """is_video_in_blacklist should match by basename when paths differ."""
    video = {"path": "/videos/new/same_name.mp4", "duration": 3600}
    blacklist = [{"path": "/videos/old/same_name.mp4"}]
    assert is_video_in_blacklist(video, blacklist), "Should match by basename"
    print("  PASS: is_video_in_blacklist matches by basename")


def test_is_video_in_blacklist_by_path():
    """is_video_in_blacklist should match exact paths too."""
    video = {"path": "/videos/exact.mp4", "duration": 3600}
    blacklist = [{"path": "/videos/exact.mp4"}, {"path": "/videos/other.mp4"}]
    assert is_video_in_blacklist(video, blacklist), "Should match by exact path"
    print("  PASS: is_video_in_blacklist matches by exact path")


def test_is_video_in_blacklist_no_match():
    """is_video_in_blacklist should return False when no match."""
    video = {"path": "/videos/unique.mp4", "duration": 3600}
    blacklist = [{"path": "/videos/different.mp4"}]
    assert not is_video_in_blacklist(video, blacklist), "Should not match"
    print("  PASS: is_video_in_blacklist no false positive")


def test_is_video_in_blacklist_by_collection_id():
    """Match by collection_id instead of path."""
    video = {"path": "/videos/new/path.mp4", "collection_id": "my_movie", "duration": 3600}
    blacklist = [{"path": "/videos/old/path.mp4", "collection_id": "my_movie"}]
    assert is_video_in_blacklist(video, blacklist), "Should match by collection_id"
    print("  PASS: is_video_in_blacklist matches by collection_id")


def test_is_video_in_blacklist_collection_id_no_match():
    """Different collection_ids should not match."""
    video = {"path": "/videos/movie_a.mp4", "collection_id": "movie_a", "duration": 3600}
    blacklist = [{"path": "/videos/movie_b.mp4", "collection_id": "movie_b"}]
    assert not is_video_in_blacklist(video, blacklist), "Different collection_ids should not match"
    print("  PASS: is_video_in_blacklist respects non-matching collection_ids")


def test_is_video_in_blacklist_collection_id_as_extra_identifier():
    """collection_id matched first, path matched as fallback."""
    video = {"path": "/videos/clash.mp4", "collection_id": "alpha", "duration": 3600}
    blacklist = [{"path": "/videos/clash.mp4", "collection_id": "beta"}]
    # Different collection_ids but same path -- still a match via path fallback
    assert is_video_in_blacklist(video, blacklist), "Same path should still match"
    print("  PASS: is_video_in_blacklist uses collection_id first, path as fallback")


def test_blacklist_profile_triggers_match_randomfill():
    """Verify TagDialog and RandomFillDialog handle profile combo the same way.

    The key fix: TagDialog._populate_from_tag must block signals when setting
    the collection_profile combo (just like RandomFillDialog does), otherwise
    profile_selected fires and re-loads the collection with load_blacklist=True,
    which replaces the tag's blacklist with auto-discovered data.
    """
    from PySide6.QtWidgets import QApplication
    from dialogs.custom_tag_dialogs import TagDialog

    # We need an app for QDialog
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp:
        videos = [make_video(f"x_{i}", 1800) for i in range(3)]
        coll_path = os.path.join(tmp, "collection.json")
        make_collection_json(coll_path, videos)

        bl_path = os.path.join(tmp, "collection_blacklist.json")
        make_blacklist_json(bl_path, ["/videos/x_1.mp4"])

        tag = Tag(
            tag_type="custom", name="Test",
            start_time=QTime(9, 0), end_time=QTime(17, 0),
            collection_videos=[v for v in videos if v['path'] != "/videos/x_1.mp4"],
            collection_path=coll_path,
            blacklist=[{"path": "/videos/x_1.mp4"}],
            collection_profile="collection.json",
            blacklist_profile="-- None --",
        )

        dialog = TagDialog(tag=tag)
        added_paths = {v.get('path', '') for v in dialog.added_videos}
        bl_paths = {b.get('path', '') for b in dialog.blacklist}
        overlap = added_paths & bl_paths
        assert len(overlap) == 0, \
            f"BUG: TagDialog shows {len(overlap)} videos in both added and blacklist: {overlap}"
        print(f"  PASS: TagDialog initialized without overlap ({len(dialog.added_videos)} added, {len(dialog.blacklist)} blacklisted)")


if __name__ == "__main__":
    print("=== Tag Blacklist Filter Tests ===\n")

    # Data-layer tests (no QApp needed)
    test_filter_videos_by_blacklist()
    test_tag_init_filters_blacklist()
    test_load_tag_from_ini_filters_blacklist()
    test_populate_dialog_state()
    test_filter_by_basename_after_move()
    test_is_video_in_blacklist_by_basename()
    test_is_video_in_blacklist_by_path()
    test_is_video_in_blacklist_no_match()
    test_is_video_in_blacklist_by_collection_id()
    test_is_video_in_blacklist_collection_id_no_match()
    test_is_video_in_blacklist_collection_id_as_extra_identifier()

    print("\n--- GUI-layer test (requires display) ---")
    # GUI test uses TagDialog which needs QApplication
    test_blacklist_profile_triggers_match_randomfill()

    print("\nAll tests passed!")
