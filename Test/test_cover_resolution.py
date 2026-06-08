#!/usr/bin/env python3
"""Test cover resolution logic."""
from pathlib import Path
import sys
sys.path.insert(0, '/home/akira/akira/myencoder/MyEncoder/PySide6/venv/lib/python3.13/site-packages')
from utils import get_config_paths, load_collection_json

collection_path, _ = get_config_paths()
print(f"Collection path from config: {collection_path}")
akiratv_root = Path(collection_path).parent.parent
print(f"AkiraTV root: {akiratv_root}")

videos, coll_dict = load_collection_json('movie_collection_001.json')
if videos:
    v = videos[0]
    cid = v.get('collection_id','')
    cover_rel = coll_dict.get(cid, {}).get('cover','')
    print(f"\nFirst video cover relative: '{cover_rel}'")
    cover_full = akiratv_root / cover_rel
    print(f"Resolved full: {cover_full}")
    print(f"Exists: {cover_full.exists()}")
