# Collection JSON Tags for Movie Sequence

## Overview
Add support for reading movie sequence identifiers from the collection JSON file's `tags` field, so users can explicitly tag which movie group a video belongs to — instead of relying solely on filename parsing.

## User Story
As a user, I want to put tags like `"1"`, `"2"`, `"3"`, or `"movie 1"`, `"Movie 2"` in the collection JSON file's `tags` array to mark which movie sequence group each video belongs to. The movie sequence scheduler should read these tags and group videos accordingly.

## Requirements

### Functional
1. In the collection JSON (`_name.json`), each collection entry can have `tags` containing movie sequence identifiers
2. Supported tag formats:
   - Bare number: `"1"`, `"2"`, `"3"` → movie number
   - Named: `"movie 1"`, `"Movie 1"`, `"Movie: 1"` → movie number extracted
   - Part: `"part 2"`, `"Part 2"`, `"Part: 2"` → part number for ordering within a movie group
3. If a video dict has `_meta_movie` set from JSON tags, `extract_movie_sequence_key` uses it directly instead of parsing the filename
4. If no movie tag is found, fall back to existing filename-based parsing (backward compatible)
5. Both `load_collection_json` and `load_collection_videos_only` extract the tags
6. `group_videos_by_movie` automatically benefits — no changes needed

### Non-Functional
- No changes to existing collection files that lack movie tags
- No changes to scheduler, dialogs, serialization, or data models
- Tag matching is case-insensitive

## Tag Priority in `extract_movie_sequence_key`

```
1. _meta_movie / _meta_part from video dict (if present) → return immediately
2. Filename parsing (existing behavior) → fallback
```

## Technical Design

### New Helper in `utils.py`

```python
def _extract_movie_tag(tags: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """Scan tags for movie sequence identifiers.
    
    Returns: (movie_number, part_number) or (None, None) if no movie tag found.
    
    Tag formats matched:
    - Purely numeric: "3" → movie=3
    - "Movie: N", "Movie N", "movie N" → movie=N
    - "Part: N", "Part N", "part N" → part=N
    """
    movie = None
    part = None
    
    for tag in tags:
        tag_stripped = tag.strip()
        
        # Purely numeric tag → movie number
        if tag_stripped.isdigit():
            movie = int(tag_stripped)
            continue
        
        # Check for "Movie: N" or "movie N" etc.
        m = re.match(r'(?:movie|film)[:\s]*(\d+)', tag_stripped, re.IGNORECASE)
        if m:
            movie = int(m.group(1))
            continue
        
        # Check for "Part: N" or "part N" etc.
        m = re.match(r'part[:\s]*(\d+)', tag_stripped, re.IGNORECASE)
        if m:
            part = int(m.group(1))
            continue
    
    return (movie, part)  # either or both may be None
```

### Changes to `load_collection_json` and `load_collection_videos_only`

After the existing `_extract_tag_value` calls for `Series:` and `Season:`, add:

```python
movie_num, part_num = _extract_movie_tag(coll_tags)
```

Then on each video copy:

```python
video_copy['_meta_movie'] = movie_num      # int or None
video_copy['_meta_part'] = part_num         # int or None
```

### Changes to `extract_movie_sequence_key`

At the top of the function (before filename parsing), when given a dict:

```python
if isinstance(video_or_path, dict):
    meta_movie = video_or_path.get('_meta_movie')
    if meta_movie is not None:
        meta_part = video_or_path.get('_meta_part', 0) or 0
        return (meta_movie, meta_part)
    # fall through to existing filename parsing
```

If the dict has `_meta_movie`, return it immediately with `_meta_part` (default 0). Otherwise proceed to parse the filename as before.

## Example Collection JSON

```json
{
  "collections": [
    {
      "id": "star_wars_4",
      "name": "Star Wars: A New Hope",
      "videos": [{"path": "/vids/sw4.mp4", "duration": 7200}],
      "tags": ["1"]
    },
    {
      "id": "star_wars_5",
      "name": "Star Wars: Empire Strikes Back",
      "videos": [{"path": "/vids/sw5.mp4", "duration": 7800}],
      "tags": ["2"]
    },
    {
      "id": "star_wars_6",
      "name": "Star Wars: Return of the Jedi",
      "videos": [{"path": "/vids/sw6.mp4", "duration": 8000}],
      "tags": ["movie 3"]
    },
    {
      "id": "some_show",
      "name": "Normal Series",
      "videos": [{"path": "/vids/ep01.mp4", "duration": 1800}],
      "tags": ["Episodic"]
    }
  ]
}
```

With this, movie sequence mode would group:
- Group 1: Star Wars A New Hope
- Group 2: Star Wars Empire Strikes Back
- Group 3: Star Wars Return of the Jedi
- "Normal Series" has no movie tag → falls back to filename parsing

## Edge Cases

| Scenario | Behavior |
|---|---|
| Tag is `"3"` (purely numeric) | movie=3 |
| Tag is `"movie 7"` | movie=7 |
| Tag is `"Part 2"` | part=2; movie determined by another tag or filename |
| Tag is `"Episodic"` | ignored (no match) — falls back to filename |
| Tag is `"Series: Arcane"` | ignored — handled by existing `_extract_tag_value` |
| Multiple numbers in tags | First matching movie + first matching part used |
| No movie tag found | Existing filename parsing takes over |
| `_meta_movie` set but not `_meta_part` | part defaults to 0 |

## Implementation Order

1. Add `_extract_movie_tag()` helper function
2. Update `load_collection_json` — call helper, set `_meta_movie`/`_meta_part`
3. Update `load_collection_videos_only` — same
4. Update `extract_movie_sequence_key` — check `_meta_movie` first
5. Verify with existing collection files (no regression — no movie tags = filename parsing)

## Files Modified

```
utils.py     # _extract_movie_tag helper + 2 collection loaders + 1 check in extract_movie_sequence_key
```

## Testing Checklist

- [ ] Collection entry with `tags: ["3"]` → movie=3, no filename parsing
- [ ] Collection entry with `tags: ["movie 7"]` → movie=7
- [ ] Collection entry with `tags: ["Movie: 5", "Part: 2"]` → movie=5, part=2
- [ ] Collection entry with `tags: ["Episodic"]` → no movie tag, filename parsing used
- [ ] No tags at all → existing behavior (filename parsing)
- [ ] Mixed: some entries have movie tags, some don't → each resolved correctly
- [ ] `group_videos_by_movie` groups correctly with mixed sources
- [ ] Random fill tag with movie sequence mode works end-to-end

---

**Last Updated:** 2026-05-28  
**Status:** Draft for review  
**Owner:** Kilo (implementation agent)
