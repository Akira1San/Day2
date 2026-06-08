#!/usr/bin/env python3
"""Test collection_id attachment."""
import sys
sys.path.insert(0, '/home/akira/akira/day2')
from utils import load_collection_json

videos, coll_dict = load_collection_json('/home/akira/akira/AkiraTV_NEW/user/collections/collections_akiratv.json')
print(f"Total videos: {len(videos)}")
print(f"Collection IDs count: {len(coll_dict)}")
if videos:
    v = videos[0]
    print(f"\nFirst video keys: {list(v.keys())}")
    print(f"collection_id: '{v.get('collection_id')}'")
    print(f"path: {v.get('path')}")
# Find avatar
avatar_vids = [v for v in videos if 'avatar' in v.get('path','').lower()]
print(f"\nVideos with 'avatar' in path: {len(avatar_vids)}")
for av in avatar_vids[:2]:
    print(f"  path={av.get('path')}, collection_id={av.get('collection_id')}")
