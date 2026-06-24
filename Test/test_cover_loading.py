#!/usr/bin/env python3
"""Test cover image loading for the TatkoTV collection.

Identifies which cover files exist at the expected path and which
exist at alternative locations, so we can fix the resolution logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, '/home/akira/akira/day2')
from utils import load_collection_json, get_covers_path

COLLECTION_FILE = '/home/akira/akira/AkiraTV_NEW/user/collections/collections_TatkoTV.json'
COVERS_ROOT = get_covers_path() or Path('/home/akira/akira/AkiraTV_NEW/')

videos, coll_dict = load_collection_json(COLLECTION_FILE)

# These directories mirror the fallback_dirs in CollectionInfoPanel
ALT_DIRS = [
    COVERS_ROOT / 'user' / 'collections' / 'covers' / 'tatkotv' / 'images',
    COVERS_ROOT / 'user' / 'covers' / 'tatkotv',
]


def resolve_cover(cover_rel: str) -> tuple[Path, str]:
    """Try to resolve a cover path. Returns (resolved_path, status)."""
    if not cover_rel:
        return (Path(), 'empty')

    p = Path(cover_rel)
    if not p.is_absolute():
        p = COVERS_ROOT / cover_rel

    if p.exists():
        return (p, 'exact')

    # Fallback: search by filename in alternative directories
    fname = Path(cover_rel).name
    for d in ALT_DIRS:
        candidate = d / fname
        if candidate.exists():
            return (candidate, f'alt:{d.name}')

    return (p, 'missing')


print(f"Total videos: {len(videos)}")
print(f"Collections:  {len(coll_dict)}")
print(f"Covers root:  {COVERS_ROOT}\n")

# Test all covers
exact = 0
alt_ok = 0
missing = 0
for cid, info in coll_dict.items():
    cover = info.get('cover', '')
    resolved, status = resolve_cover(cover)
    if status == 'exact':
        exact += 1
    elif status.startswith('alt:'):
        alt_ok += 1
    else:
        missing += 1

total = len(coll_dict)
print(f"Found at expected path:       {exact:3d} / {total}")
print(f"Found via fallback alt dirs:  {alt_ok:3d} / {total}")
print(f"Truly missing:                {missing:3d} / {total}")
print()

# Show a few examples at the top and bottom of the sorted list
sorted_videos = sorted(videos, key=lambda v: v.get('path', '').split('/')[-1])
print("--- Bottom of list (last 8) ---")
for v in sorted_videos[-8:]:
    fname = v.get('path', '').split('/')[-1]
    cid = v.get('collection_id', '')
    info = coll_dict.get(cid, {})
    cover = info.get('cover', '')
    resolved, status = resolve_cover(cover)
    cname = info.get('name', '?')
    print(f"  {fname:45s} status={status:10s} coll={cid}")

print()
print("--- Top of list (first 8) ---")
for v in sorted_videos[:8]:
    fname = v.get('path', '').split('/')[-1]
    cid = v.get('collection_id', '')
    info = coll_dict.get(cid, {})
    cover = info.get('cover', '')
    resolved, status = resolve_cover(cover)
    cname = info.get('name', '?')
    print(f"  {fname:45s} status={status:10s} coll={cid}")
