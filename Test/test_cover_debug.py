#!/usr/bin/env python3
"""Test cover image loading logic without GUI."""
from pathlib import Path
from utils import load_collection_json

# Test loading movie_collection_001.json
videos, coll_dict = load_collection_json('movie_collection_001.json')

print(f"Total videos: {len(videos)}")
print(f"Collections dict size: {len(coll_dict)}")

# Show collection info
for cid, info in coll_dict.items():
    print(f"\nCollection ID: {cid}")
    print(f"  Name: {info.get('name')}")
    print(f"  Cover: {info.get('cover')}")

# Check first video
if videos:
    v = videos[0]
    print(f"\nFirst video:")
    print(f"  Name: {v.get('name')}")
    print(f"  collection_id: {v.get('collection_id')}")

    # Simulate cover display
    coll_id = v.get('collection_id', '')
    coll_info = coll_dict.get(coll_id, {})
    cover_rel = coll_info.get('cover', '')
    print(f"\nFor first video, cover relative path: '{cover_rel}'")

    collection_dir = Path('movie_collection_001.json').parent
    cover_full = collection_dir / cover_rel if cover_rel else None
    print(f"Resolved full path: {cover_full}")
    print(f"Exists: {cover_full.exists() if cover_full else 'N/A'}")
