#!/usr/bin/env python3
"""Quick test to verify collection_id is attached to videos when loading."""
from utils import load_collection_json, load_collection_videos_only
import json

# Test with Cyber Legends.json which has multiple collections with same id 'cyber_legends'
print("Testing load_collection_json on Cyber Legends.json")
videos, info = load_collection_json('Cyber Legends.json')
print(f"Total videos loaded: {len(videos)}")
if videos:
    print(f"First few videos:")
    for v in videos[:3]:
        print(f"  path={v.get('path','')}, collection_id={v.get('collection_id','NOT SET')}")
print()

# Test with Akiratv collection (should have different collection_id per video from different collections)
print("Testing load_collection_videos_only on a sample collection file")
# We'll check the Akiratv collection if accessible
try:
    vids = load_collection_videos_only('/home/akira/akira/AkiraTV_NEW/user/collections/collections_akiratv.json')
    print(f"Total videos: {len(vids)}")
    # Show unique collection_ids
    ids = set(v.get('collection_id','') for v in vids)
    print(f"Unique collection_ids count: {len(ids)}")
    print(f"Sample collection_ids: {list(ids)[:5]}")
except Exception as e:
    print(f"Error: {e}")

print("\nTest completed.")
