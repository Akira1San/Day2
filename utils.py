import json
import re
import configparser
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from PySide6.QtCore import QTime


def load_collection_json(file_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    collection_videos = []
    collection_info = {}
    
    if not file_path or not Path(file_path).exists():
        return collection_videos, collection_info
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        collections = data.get('collections', [])
        for collection in collections:
            collection_info = collection
            for video in collection.get('videos', []):
                collection_videos.append(video)
    except Exception:
        pass
    
    return collection_videos, collection_info


def load_collection_videos_only(file_path: str) -> List[Dict[str, Any]]:
    videos, _ = load_collection_json(file_path)
    return videos


def parse_series_episode(path: str) -> Tuple[int, int]:
    name = path.split('/')[-1] if '/' in path else path
    season, episode = 1, 1
    
    match = re.search(r'[Ss](\d+)[Ee](\d+)', name)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
    else:
        match = re.search(r'Season\s*(\d+)\s*Episode\s*(\d+)', name, re.IGNORECASE)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
    
    return season, episode


def parse_videos_for_series(videos: List[Dict[str, Any]], start_season: int = 1, 
                            start_episode: int = 1, play_mode: str = "sequence",
                            video_count: int = 1) -> Tuple[List[Dict[str, Any]], int]:
    parsed_videos = []
    for vid in videos:
        path = vid.get('path', '')
        season, episode = parse_series_episode(path)
        parsed_videos.append({
            'video': vid,
            'season': season,
            'episode': episode,
            'path': path,
            'name': path.split('/')[-1] if '/' in path else path
        })
    
    filtered = [v for v in parsed_videos 
                if v['season'] > start_season or (v['season'] == start_season and v['episode'] >= start_episode)]
    
    if play_mode == 'random':
        import random
        random.shuffle(filtered)
    else:
        filtered.sort(key=lambda v: (v['season'], v['episode']))
    
    return filtered[:video_count], len(filtered)


def load_blacklist_json(file_path: str) -> List[Dict[str, Any]]:
    blacklist = []
    
    if not file_path or not Path(file_path).exists():
        return blacklist
    
    try:
        if file_path.endswith('.ini'):
            bc = configparser.ConfigParser()
            bc.read(file_path)
            if 'Blacklist' in bc:
                for key in bc['Blacklist']:
                    value = bc['Blacklist'][key]
                    paths = [p.strip() for p in value.split('\n') if p.strip()]
                    for path in paths:
                        blacklist.append({'path': path})
        else:
            with open(file_path, 'r') as f:
                blacklist = json.load(f).get('blacklist', [])
    except Exception:
        pass
    
    return blacklist


def qtime_to_minutes(qtime: QTime) -> int:
    return qtime.hour() * 60 + qtime.minute()


def minutes_to_qtime(minutes: int) -> QTime:
    return QTime(minutes // 60, minutes % 60)


def get_video_display_name(video: Dict[str, Any]) -> str:
    path = video.get('path', '')
    return path.split('/')[-1] if '/' in path else path


def format_duration(duration_seconds: int) -> str:
    return f"{int(duration_seconds)}s"


def get_config_paths(config_file: str = "config.ini") -> Tuple[str, str]:
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        collection_path = config.get('Paths', 'collection_path', fallback='/home/akira/akira/AkiraTV_NEW/user/collections')
        blacklist_path = config.get('Paths', 'blacklist_path', fallback='/home/akira/akira/AkiraTV_NEW/user/collections')
    except Exception:
        collection_path = '/home/akira/akira/AkiraTV_NEW/user/collections'
        blacklist_path = '/home/akira/akira/AkiraTV_NEW/user/collections'
    
    return collection_path, blacklist_path


def filter_videos_by_blacklist(videos: List[Dict[str, Any]], blacklist: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blacklist_paths = {b.get('path', '') for b in blacklist}
    return [v for v in videos if v.get('path', '') not in blacklist_paths]
