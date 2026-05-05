#!/usr/bin/env python3
"""Test the season_sequence offset logic in isolation."""

def select_series_videos(flat, video_count, start_season, start_episode, day_offset):
    """Mirror the season_sequence branch from _select_series_videos."""
    # Find start_idx in flat list based on start_season/start_episode
    start_idx = 0
    found = False
    for i, v in enumerate(flat):
        s = v['season']
        e = v['episode']
        if s is None:
            continue
        if s > start_season or (s == start_season and e >= start_episode):
            start_idx = i
            found = True
            break
    if not found:
        return []
    effective_idx = start_idx + day_offset * video_count
    if effective_idx >= len(flat):
        return []
    take = min(video_count, len(flat) - effective_idx)
    return flat[effective_idx : effective_idx + take]

# Build test data: seasons 0,1,2,3 with episodes
flat = []
for s in range(4):
    for e in range(1, 6):  # 5 episodes each season
        flat.append({'season': s, 'episode': e, 'video': f'S{s}E{e}'})
# flat length 20

# Test case 1: start_season=0, start_episode=1, video_count=1
print("Case 1: start 0,1 vc1")
for day in range(5):
    sel = select_series_videos(flat, 1, 0, 1, day)
    print(f" day {day}: {sel}")

# Test case 2: start_season=2, start_episode=1, video_count=3
print("\nCase 2: start 2,1 vc3")
for day in range(5):
    sel = select_series_videos(flat, 3, 2, 1, day)
    print(f" day {day}: {[v['season']*10+v['episode'] for v in sel]}")

# Test case 3: start_season=1, start_episode=3, video_count=2
print("\nCase 3: start 1,3 vc2")
for day in range(5):
    sel = select_series_videos(flat, 2, 1, 3, day)
    print(f" day {day}: {[v['season']*10+v['episode'] for v in sel]}")
