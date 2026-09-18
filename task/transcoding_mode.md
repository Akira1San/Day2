# Task: Transcoding Mode per Video (transcode / copy)

## Concept
Add per-video `transcoding_mode` flag (`transcode` or `copy`) selectable from the
**Added Videos** section bottom row. The flag is written into the saved schedule
JSON only when set; otherwise the key is omitted.

Example saved schedule entry:
```json
{
  "time": "00:00:00",
  "collection_id": "phantasm_iv_oblivion",
  "channel": "horror",
  "source": "random",
  "collection_source": "horror",
  "transcoding_mode": "transcode"
}
```

## User decisions
- Buttons in **all dialogs** (shared Added Videos section: Custom + Random Fill).
- **Session only** — no `.tag` file persistence.
- Buttons: **Transcode / Copy + Clear** (set/overwrite on selected videos).
- Visual indicator: **suffix label** in Added Videos list (e.g. `Movie.mp4 [transcode]`).

## UX flow
1. Select 1+ videos in Added Videos list.
2. Press Transcode -> mark selected as `transcode`; Copy -> mark as `copy`; Clear -> remove mark.
3. List shows suffix label.
4. Save Schedule emits `transcoding_mode` key only for marked videos.

## Implementation TODO

### 1. Storage (transient, no serialization change)
- [x] Use `video["_transcoding_mode"] = "transcode" | "copy"` on in-memory video dicts
  (same pattern as `_rate`, `_source_name`).
- [x] `Tag.collection_videos` carries dicts via `added_videos` copies — no `data_models.py`
  Tag field change, no `serialization.py` change.
- [x] Document that reload from `.tag` / collection JSON drops marks (session-only).

### 2. `dialogs/widgets/video_list.py` — `create_video_section`
- [x] Add optional params `on_transcode, on_copy, on_clear_transcoding`.
- [x] In Added-Videos branch (`with_buttons=False`), add bottom-row buttons
  Transcode / Copy / Clear wired to callbacks. Skip when callbacks not supplied
  (blacklist section unaffected).

### 3. `dialogs/collection_base.py`
- [x] Pass new callbacks when creating `self.added_section`.
- [x] Implement `_set_transcoding_mode(mode)`:
  selected rows from `added_list` via `_selected_table_rows`,
  map `Qt.UserRole` path -> `added_videos`, set key, `refresh_added_list()`.
- [x] Implement `_clear_transcoding_mode()`: pop key on selected, refresh.
- [x] Update `refresh_added_list()` name rendering with suffix label,
  keep `UserRole=path` unchanged.
- [x] Ensure `add_selected_videos()`, `remove_from_blacklist()` restore,
  `_on_rate_changed` preserve the key (copy whole dict).

### 4. `dialogs/custom_tag_dialogs.py`
- [x] `TagDialog._populate_from_tag` already copies `tag.collection_videos` -> marks
  survive edit in-session automatically; verify.
- [x] `RandomFillDialog._populate_from_tag` currently resets
  `added_videos = collection_videos.copy()`; re-apply marks from
  `tag.collection_videos` by path lookup so Edit preserves session marks.
- [x] `get_tag()` in both dialogs: verify copy carries key (no logic change expected).

### 5. `daypart_scheduler.py` — `save_schedule` / `get_schedule_entries_for_day`
- [x] After `matched_vid` found (primary tag loop + gap loop), add:
  ```python
  mode = matched_vid.get("_transcoding_mode", "")
  if mode in ("transcode", "copy"):
      video_info["transcoding_mode"] = mode
  ```
- [x] Keep `source` / `collection_source` logic untouched.
- [x] Applies uniformly (random/custom/series/gap) since buttons are in all dialogs.

### Edge cases
- [ ] Identity key = video `path` (matches `UserRole`); display prefix `_source_name` stays.
- [ ] Sort/search filtering must not break set/clear (operate on `added_videos` by path).
- [ ] Overwrite semantics: Transcode over Copy overwrites; Clear removes.
- [ ] Rate spinbox column unaffected (dict-level key, not widget-level).

## Verification
- [x] Manual: Random Fill -> Add Collection -> Add >> -> select video -> Transcode ->
  check suffix -> Generate -> Save Schedule -> JSON has key only on marked videos;
  Clear -> key gone; Edit tag in-session keeps marks; reload `.tag` drops marks.
- [x] `pytest Test/` passes (serialization format untouched).
