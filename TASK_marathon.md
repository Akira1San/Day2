# Task: Marathon mode — per-day / rotating collection tags

## Problem
Marathon mode currently supports only a single `collection tag` + `active day/s`:
- `Tag.marathon_mode: bool + marathon_tag_name: str + active_days` (`data_models.py:46-47`)
- UI: `Marathon Mode` checkbox + `Active Days` checkboxes + `Collection Tag` combo (`dialogs/custom_tag_dialogs.py:427-457`)
- Scheduler: `_get_marathon_videos()` filters by the one `marathon_tag_name` (`scheduler.py:142-156`)

Cannot express: "this Sunday = TagA, next Sunday = TagB, then repeat".

## Decision (agreed with user)
- Weekday map + rotation (not explicit calendar dates).
- Inactive day = keep current unfiltered 24h-fill fallback (`scheduler.py:750-753`).
- UI: compact row `[x] Marathon checkbox + summary label + [Configure...]` opening a dedicated `MarathonScheduleDialog`.

## Design
- New model: `Tag.marathon_schedule: List[{"tag_name": str, "active_days": [1..7] | None}]`.
  - Table order = rotation order.
  - Resolution for `day_offset`: `weekday = (schedule_start_weekday + day_offset) % 7 + 1`; matches = entries covering weekday.
  - 0 matches -> inactive -> unfiltered fallback. 1 match -> use it. N matches -> `idx = occurrence_of_this_weekday_so_far % N` (e.g. Sun1=A, Sun2=B, Sun3=A...).
- Keep `marathon_mode`, `marathon_tag_name`, `active_days` as legacy/migration fields.

## Steps
1. `data_models.py`: add `marathon_schedule` to `Tag.__init__`; extend `TagManager.edit_tag`; update `Tag.to_display_string()` summary.
2. New `dialogs/marathon_dialog.py:MarathonScheduleDialog`: table `Tag combo | Mon..Sun + All` per row, Add/Remove/Up-Down, validation, `get/set_schedule()`.
3. `dialogs/custom_tag_dialogs.py:RandomFillDialog`: replace inline tag combo + day checkboxes with checkbox + summary + Configure button; reuse `_populate_marathon_tag_combo()` as tag source; migrate legacy tag on populate; emit new schedule on `get_tag()`.
4. `scheduler.py`: add `_resolve_marathon_tag_name(tag, day_offset)`; rewire `_get_marathon_videos()` + `_process_random_fill_tag()` active check to use schedule.
5. `serialization.py` + `daypart_scheduler.py:851-853`: persist `marathon_schedule` as JSON, migrate legacy `marathon_tag_name/active_days` on load; also persist `active_days` for random type.
6. Tests: extend `Test/test_marathon.py` — weekday map, Sunday rotation over 3 weeks, fallback day, legacy migration; run `test_marathon.py` + `test_all_modes.py`.

## Acceptance
- [x] Sunday rotation works in 21-day preview (`test_marathon_schedule_sunday_rotation`).
- [x] Inactive days fall back to unfiltered fill (kept + covered by existing tests).
- [x] Old `.tag` files load (migrated to 1-entry schedule) and re-save (`test_marathon_schedule_serialization`).
- [x] All marathon tests pass (10/10, except pre-existing `test_hero_collection` fixture failure — missing `Hero test tag.json`, fails on clean tree too).

## Notes
- Out of scope: explicit calendar-date overrides; approximate modes reuse day-0 tag pool (rotation applies on the main custom-merge path).
- Pre-existing failures (clean tree too): `test_hero_collection` (missing fixture), `test_new_modes` linear ZeroDivisionError.

## Change: single-day, no repeat (2026-10-04, user-confirmed)
- A checked weekday fires only on its FIRST occurrence in the preview
  (`_is_marathon_active_on_day`: inactive when `day_offset >= 7`); later
  same weekdays fall back to unfiltered fill. Mon+Tue checked = first Mon
  once + first Tue once.
- Rotation removed: several rows on one weekday -> first row wins
  (`_resolve_marathon_tag_name`, `utils_marathon.resolve_marathon_tag_name`).
- Tag matching is case/whitespace-insensitive (`video_matches_marathon_tag`).
- `RandomFillDialog.get_tag()` validates each rule via
  `validate_marathon_schedule`: 0 matches -> error (abort save), 1 match ->
  warning (confirm save); summary label shows per-rule video counts.
- Root cause of the TatkoTV report: `collections_TatkoTV_blacklist.json`
  excludes 14/15 Stallone videos, collapsing the pool to 1 video repeated
  all day. Covered by `Test/test_marathon_single_day.py`
  (`test_blacklist_collapse_repro`, `test_first_monday_only_30d`, ...).

## Change: marathon ignores blacklist (2026-10-04, user-confirmed)
- Blacklist applies to normal generation only. Marathon tags keep the full
  pool (`Tag.__init__`/`edit_tag` skip pre-filtering when `marathon_mode`;
  `RandomFillDialog.get_tag()` saves Added + blacklist-excluded videos via
  `build_marathon_pool`; extra-collections load skips blacklist for marathon).
- Non-marathon days filter by blacklist at schedule time
  (`_blacklist_filtered_pool` in `_process_random_fill_tag` inactive branch).
- To keep a movie out of a marathon, remove it from the Added list
  (dialog tooltip). Validation/summary use the effective marathon pool.

## Change: marathon continuous flow (2026-10-04, user-confirmed)
- With marathon, every preview day reset to 00:00 with trailing gaps. Now a
  single marathon `fill_24h` tag (no fixed-time tags) builds one continuous
  stream like normal generation (`generate_marathon_continuous_fill`;
  pool switches at midnight: marathon pool on the active day, normal pool
  otherwise; videos may span midnight, attributed by start time).
- Unchanged: per-day packing with custom/series/multi tags, series paths,
  Approximate strategies, non-marathon fast path.

## Notes
- Out of scope: explicit calendar-date overrides.
- Rotation is per-weekday occurrence count, deterministic (no RNG).
