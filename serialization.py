import configparser
from typing import List, Any, Optional, Dict
from pathlib import Path

from utils import load_collection_videos_only, load_blacklist_json


def serialize_tag_to_string(tag) -> str:
    if getattr(tag, 'is_series', False):
        tag_type = "series"
        start_season = str(getattr(tag, 'start_season', 1))
        start_episode = str(getattr(tag, 'start_episode', 1))
        play_mode = getattr(tag, 'play_mode', 'sequence')
        video_count = str(getattr(tag, 'video_count', 1))
        return f"{tag_type}|{tag.name}|{tag.start_time.toString('HH:mm')}|{tag.end_time.toString('HH:mm')}|{start_season}|{start_episode}|{play_mode}|{video_count}"
    
    elif getattr(tag, 'is_random_fill', False):
        tag_type = "random"
        blacklist_path = getattr(tag, 'blacklist_path', '')
        fill_24h = "1" if getattr(tag, 'fill_24h', False) else "0"
        return f"{tag_type}|{tag.name}|{tag.start_time.toString('HH:mm')}|{tag.end_time.toString('HH:mm')}|{getattr(tag, 'collection_path', '')}|{blacklist_path}|{fill_24h}"
    
    else:
        tag_type = "custom"
        is_random = "1" if getattr(tag, 'randomize_videos', False) else "0"
        video_count = str(getattr(tag, 'video_count', 1))
        return f"{tag_type}|{tag.name}|{tag.start_time.toString('HH:mm')}|{tag.end_time.toString('HH:mm')}|{is_random}|{video_count}|{getattr(tag, 'collection_path', '')}"


def save_tags_to_ini(tags: List[Any], filepath: str = "tags.ini"):
    config = configparser.ConfigParser()
    config['Tags'] = {}
    
    for i, tag in enumerate(tags):
        key = f"tag{i}"
        config['Tags'][key] = serialize_tag_to_string(tag)
    
    with open(filepath, 'w') as f:
        config.write(f)


def deserialize_tag_from_string(data: str, tag_class, qtime_from_string):
    parts = data.split('|')
    if len(parts) < 4:
        return None
    
    tag_type = parts[0]
    name = parts[1]
    start = parts[2]
    end = parts[3]
    
    collection_videos = []
    collection_path = ""
    blacklist = []
    blacklist_path = ""
    
    if tag_type == 'series':
        start_season = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else 1
        start_episode = int(parts[5]) if len(parts) >= 6 and parts[5].isdigit() else 1
        play_mode = parts[6] if len(parts) >= 7 else "sequence"
        video_count = int(parts[7]) if len(parts) >= 8 and parts[7].isdigit() else 1
        collection_path = parts[8] if len(parts) >= 9 else ""
        
        if collection_path:
            collection_videos = load_collection_videos_only(collection_path)
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'), 
                        collection_videos, collection_path, video_count=video_count, 
                        is_series=True, start_season=start_season, start_episode=start_episode, 
                        play_mode=play_mode)
    
    elif tag_type == 'random':
        collection_path = parts[4] if len(parts) >= 5 else ""
        blacklist_path = parts[5] if len(parts) >= 6 else ""
        fill_24h = len(parts) >= 7 and parts[6] == "1"
        
        if collection_path:
            collection_videos = load_collection_videos_only(collection_path)
        
        if blacklist_path:
            blacklist = load_blacklist_json(blacklist_path)
        
        return tag_class('random', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_fill=True,
                        blacklist=blacklist, blacklist_path=blacklist_path, fill_24h=fill_24h)
    
    else:
        is_random_videos = len(parts) >= 5 and parts[4] == "1"
        video_count = int(parts[5]) if len(parts) >= 6 and parts[5].isdigit() else 1
        collection_path = parts[6] if len(parts) >= 7 else ""
        
        if collection_path:
            collection_videos = load_collection_videos_only(collection_path)
        
        return tag_class('custom', name, qtime_from_string(start, 'HH:mm'), qtime_from_string(end, 'HH:mm'),
                        collection_videos, collection_path, is_random_videos, video_count)


def load_tags_from_ini(filepath: str, tag_class, qtime_from_string) -> List[Any]:
    if not Path(filepath).exists():
        return []
    
    config = configparser.ConfigParser()
    config.read(filepath)
    
    if 'Tags' not in config:
        return []
    
    tags = []
    for key in config['Tags']:
        tag = deserialize_tag_from_string(config['Tags'][key], tag_class, qtime_from_string)
        if tag:
            tags.append(tag)
    
    return tags


def save_single_tag_to_ini(tag, filepath: str):
    config = configparser.ConfigParser()
    config['Tag'] = {'data': serialize_tag_to_string(tag)}
    
    with open(filepath, 'w') as f:
        config.write(f)


def load_single_tag_from_ini(filepath: str, tag_class, qtime_from_string) -> Optional[Any]:
    if not Path(filepath).exists():
        return None
    
    config = configparser.ConfigParser()
    config.read(filepath)
    
    if 'Tag' not in config:
        return None
    
    return deserialize_tag_from_string(config['Tag']['data'], tag_class, qtime_from_string)
