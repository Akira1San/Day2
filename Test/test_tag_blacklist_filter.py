#!/usr/bin/env python3
"""Test that blacklisted videos don't appear in added_videos when loading a tag.

New schema (2026-09): blacklist entries are {"video_id": <collections[].id>}
and rates keys are collection ids. Path/basename matching was removed.
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTime
from models import Tag
from serialization import load_single_tag_from_file, save_single_tag_to_file
from utils import filter_videos_by_blacklist, is_video_in_blacklist, load_collection_videos_only, load_blacklist_json


def make_video(name: str, dur_sec: int = 3600) -> dict:
    return {
        "path": f"/videos/{name}.mp4",
        "path_windows": f"C:\\videos\\{name}.mp4",
        "path_linux": f"/videos/{name}.mp4",
        "duration": dur_sec,
        "name": f"{name}.mp4",
        "collection_id": name,
    }


def make_collection_json(path, videos):
    # One collection per video so each has a distinct id (video_id).
    data = {"collections": [
        {"id": v["collection_id"], "name": v["collection_id"], "videos": [{
            "path": v["path"],
            "path_windows": v.get("path_windows", v["path"]),
            "path_linux": v.get("path_linux", ""),
            "duration": v.get("duration", 3600),
        }]}
        for v in videos
    ]}
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def make_blacklist_json(path, video_ids):
    data = {"blacklist": [{"video_id": i} for i in video_ids]}
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def make_tag_file(path, collection_path, blacklist_path):
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
    save_single_tag_to_file(tag, path)


# ── Tests ─────────────────────────────────────────────────────────────

def test_filter_videos_by_blacklist():
    videos = [make_video("a"), make_video("b"), make_video("c")]
    blacklist = [{"video_id": "b"}]
    filtered = filter_videos_by_blacklist(videos, blacklist)
    assert len(filtered) == 2, f"Expected 2, got {len(filtered)}"
    assert all(v['collection_id'] != 'b' for v in filtered)
    print("  PASS: filter_videos_by_blacklist works")


def test_tag_init_filters_blacklist():
    videos = [make_video("a"), make_video("b"), make_video("c")]
    blacklist = [{"video_id": "b"}]
    tag = Tag(
        tag_type="random", name="Test",
        collection_videos=videos,
        blacklist=blacklist,
        is_random_fill=True,
    )
    assert len(tag.collection_videos) == 2, f"Expected 2, got {len(tag.collection_videos)}"
    ids = [v['collection_id'] for v in tag.collection_videos]
    assert "b" not in ids, "b should be filtered out"
    print("  PASS: Tag.__init__ filters blacklisted videos")


def test_load_tag_from_file_filters_blacklist():
    with tempfile.TemporaryDirectory() as tmp:
        videos = [make_video(f"movie_{c}", 7200) for c in "abc"]
        coll_path = os.path.join(tmp, "collection.json")
        make_collection_json(coll_path, videos)

        bl_path = os.path.join(tmp, "collection_blacklist.json")
        make_blacklist_json(bl_path, ["movie_b"])

        tag_file = os.path.join(tmp, "tag.tag")
        make_tag_file(tag_file, coll_path, bl_path)

        tag = load_single_tag_from_file(tag_file, Tag, QTime.fromString)
        assert tag is not None, "Tag should load successfully"
        assert len(tag.blacklist) == 1, f"Expected 1 blacklist entry, got {len(tag.blacklist)}"

        added_ids = {v.get('collection_id', '') for v in tag.collection_videos}
        bl_ids = {b.get('video_id', '') for b in tag.blacklist}
        overlap = added_ids & bl_ids
        assert len(overlap) == 0, \
            f"BUG: {len(overlap)} videos in both collection_videos and blacklist: {overlap}"
        assert "movie_b" not in added_ids

        print(f"  PASS: Tag loaded: {len(tag.collection_videos)} added, {len(tag.blacklist)} blacklisted")


def test_populate_dialog_state():
    """Simulate _populate_from_tag logic that the dialog uses."""
    with tempfile.TemporaryDirectory() as tmp:
        videos = [make_video(f"vid_{i}", 1800) for i in range(5)]
        coll_path = os.path.join(tmp, "collection.json")
        make_collection_json(coll_path, videos)

        bl_path = os.path.join(tmp, "collection_blacklist.json")
        make_blacklist_json(bl_path, ["vid_1", "vid_3"])

        tag_file = os.path.join(tmp, "tag.tag")
        make_tag_file(tag_file, coll_path, bl_path)
        tag = load_single_tag_from_file(tag_file, Tag, QTime.fromString)

        # Simulate _populate_from_tag:
        blacklist = tag.blacklist.copy()
        all_videos = load_collection_videos_only(tag.collection_path)
        added_videos = tag.collection_videos.copy()
        added_videos = filter_videos_by_blacklist(added_videos, blacklist)

        bl_ids = {b.get('video_id', '') for b in blacklist}
        added_ids = {v.get('collection_id', '') for v in added_videos}
        overlap = added_ids & bl_ids
        assert len(overlap) == 0, \
            f"BUG: {len(overlap)} videos in both added and blacklist: {overlap}"
        assert "vid_1" not in added_ids
        assert "vid_3" not in added_ids
        assert "vid_0" in added_ids
        assert "vid_2" in added_ids
        assert "vid_4" in added_ids

        print(f"  PASS: Dialog state correct: {len(added_videos)} added, {len(blacklist)} blacklisted")


def test_path_alone_does_not_match():
    """New schema: path-only entries no longer blacklist anything."""
    videos = [
        {"path": "/videos/old/movie_a.mp4", "collection_id": "movie_a", "duration": 3600},
        {"path": "/videos/new/movie_b.mp4", "collection_id": "movie_b", "duration": 5400},
    ]
    blacklist = [{"path": "/videos/new/movie_b.mp4"}]
    filtered = filter_videos_by_blacklist(videos, blacklist)
    assert len(filtered) == 2, f"Expected 2 (no match), got {len(filtered)}"
    print("  PASS: path-only entries do not match (video_id required)")


def test_is_video_in_blacklist_by_video_id():
    video = {"path": "/videos/new/movie.mp4", "collection_id": "movie", "duration": 3600}
    assert is_video_in_blacklist(video, [{"video_id": "movie"}]), "Should match by video_id"
    print("  PASS: is_video_in_blacklist matches by video_id")


def test_is_video_in_blacklist_no_match():
    """is_video_in_blacklist should return False when no match."""
    video = {"path": "/videos/unique.mp4", "collection_id": "unique", "duration": 3600}
    blacklist = [{"video_id": "different"}]
    assert not is_video_in_blacklist(video, blacklist), "Should not match"
    print("  PASS: is_video_in_blacklist no false positive")


def test_is_video_in_blacklist_by_collection_id():
    """Match by collection_id instead of path."""
    video = {"path": "/videos/new/path.mp4", "collection_id": "my_movie", "duration": 3600}
    blacklist = [{"video_id": "my_movie"}]
    assert is_video_in_blacklist(video, blacklist), "Should match by video_id"
    print("  PASS: is_video_in_blacklist matches by video_id")


def test_is_video_in_blacklist_collection_id_no_match():
    """Different ids should not match."""
    video = {"path": "/videos/movie_a.mp4", "collection_id": "movie_a", "duration": 3600}
    blacklist = [{"video_id": "movie_b"}]
    assert not is_video_in_blacklist(video, blacklist), "Different ids should not match"
    print("  PASS: is_video_in_blacklist respects non-matching ids")


def test_effective_path_resolution():
    """Loader resolves path_windows on Windows, path_linux on Linux."""
    from utils import get_effective_path
    v = {"path": "C:\\videos\\a.mp4", "path_windows": "C:\\videos\\a.mp4",
         "path_linux": "/mnt/videos/a.mp4", "collection_id": "a"}
    eff = get_effective_path(v)
    import sys as _sys
    expected = v["path_windows"] if _sys.platform == "win32" else v["path_linux"]
    assert eff == expected, f"Expected {expected!r}, got {eff!r}"
    # Fallback when OS-specific path is empty
    v2 = {"path": "C:\\videos\\x.mp4", "path_windows": "C:\\videos\\x.mp4",
          "path_linux": "", "collection_id": "x"}
    eff2 = get_effective_path(v2)
    assert eff2 == "C:\\videos\\x.mp4", f"Fallback failed: {eff2!r}"
    print("  PASS: effective path resolution + fallback")


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
        make_blacklist_json(bl_path, ["x_1"])

        tag = Tag(
            tag_type="custom", name="Test",
            start_time=QTime(9, 0), end_time=QTime(17, 0),
            collection_videos=[v for v in videos if v['collection_id'] != "x_1"],
            collection_path=coll_path,
            blacklist=[{"video_id": "x_1"}],
            collection_profile="collection.json",
            blacklist_profile="-- None --",
        )

        dialog = TagDialog(tag=tag)
        added_ids = {v.get('collection_id', '') for v in dialog.added_videos}
        bl_ids = {b.get('video_id', b.get('collection_id', '')) for b in dialog.blacklist}
        overlap = added_ids & bl_ids
        assert len(overlap) == 0, \
            f"BUG: TagDialog shows {len(overlap)} videos in both added and blacklist: {overlap}"
        print(f"  PASS: TagDialog initialized without overlap ({len(dialog.added_videos)} added, {len(dialog.blacklist)} blacklisted)")


if __name__ == "__main__":
    print("=== Tag Blacklist Filter Tests ===\n")

    # Data-layer tests (no QApp needed)
    test_filter_videos_by_blacklist()
    test_tag_init_filters_blacklist()
    test_load_tag_from_file_filters_blacklist()
    test_populate_dialog_state()
    test_path_alone_does_not_match()
    test_is_video_in_blacklist_by_video_id()
    test_is_video_in_blacklist_no_match()
    test_is_video_in_blacklist_by_collection_id()
    test_is_video_in_blacklist_collection_id_no_match()
    test_effective_path_resolution()

    print("\n--- GUI-layer test (requires display) ---")
    # GUI test uses TagDialog which needs QApplication
    test_blacklist_profile_triggers_match_randomfill()

    print("\nAll tests passed!")
