# Task: Exclude missing-on-disk videos from schedule preview

## Status: DONE — implemented 2026-09-18

Implementation notes (deviations from plan):
- Added `exclude_missing: bool = True` constructor flag on `ScheduleGenerator`
  (`scheduler.py`). Default ON = requested production behavior; tests with fake
  fixture paths opt out via `exclude_missing=False`. `_exclude_missing()` is a
  no-op (returns input unchanged, no counting) when the flag is off.
- 5 previously-passing test files used fake non-existent fixture paths and now
  opt out: `test_all_approximate_modes.py`, `test_custom_tag_no_videos_bug.py`,
  `test_group_approximation.py`, `test_marathon.py`, `test_standalone.py`.
- New `Test/test_missing_exclusion.py` (7 tests, real temp files) covers:
  custom/series-compact/random-fill exclusion, gap loader untouched,
  all-missing fallback, opt-out flag, non-mutating tags.
- Full suite parity verified: 15/31 pass (14 baseline + new file); failing set
  identical to pre-change baseline (all pre-existing import/CWD issues).

## Goal
When generating a schedule preview with missing videos (files listed in a
collection but no longer present on disk), the scheduler should automatically
exclude those videos instead of scheduling them. This saves the manual step of
adding each missing video to a blacklist.

Preview-only, non-mutating: `Tag.collection_videos` in memory must never be
rewritten; filtering applies to local copies during generation only.

## Decisions (confirmed)
- **Scope:** all video sources **except gap fillers** (custom, series,
  multi-series, random fill incl. marathon + 24h fill). Gap filler behavior
  unchanged (`_fill_gap_fillers` / `load_gap_collections` untouched).
- **Series numbering:** compact sequence — filter missing first, then
  `day_offset * video_count` indexes into the available list (days shift up to
  fill gaps).
- **Toggle:** always exclude, no new UI control / checkbox.
- **Feedback:** statusbar + log only, no placeholder entries for missing files.

## Implementation plan

### 1. `utils.py` — new helpers (single source of truth)
- Add `is_video_missing(video: dict) -> bool`: `not path or not Path(path).exists()`.
  Empty path counts as missing.
- Add `filter_available_videos(videos) -> list`: keep videos that are not missing.
- Must match `Path(path).exists()` semantics already used by
  `dialogs/collection_base.py:check_missing_videos` so dialog highlighting and
  preview agree (CWD-relative paths resolve the same way).

### 2. `scheduler.py` — `ScheduleGenerator` central filter
- Add `_exclude_missing(videos, context="")` helper: calls
  `filter_available_videos`, `logger.debug` with context + skipped count,
  increments `self._last_missing_excluded`. Returns a filtered copy.
- Init `self._last_missing_excluded = 0` in `__init__`; reset to 0 at entry of
  `apply_custom_tags()` and `apply_approximate()` (covers all strategies via
  shared helpers).
- Apply at these points (all on local copies):
  - `_select_series_videos()` — filter `collection_videos` at top AND filter the
    built `eligible` / `flat` lists before the existing `_rate != 0` filter.
    Required because `Tag._flat_ordered` (built in `data_models.py`) and
    multi-series config dicts (`_flat_ordered`) still contain missing entries.
    Filtering before `effective_idx = day_offset * video_count` gives the
    compact-sequence behavior.
  - `_get_videos_for_day()` — filter input before `_rate` filter and movie-group
    logic.
  - `_get_marathon_videos()` — filter before returning.
  - `_build_random_entries()`, `generate_random_fill()`, `_get_all_videos()`,
    `_process_random_fill_tag()` (both `fill_24h` gap loop and timed branch) —
    filter `rf_videos_base` after copy, before shuffle/group.
  - `_process_custom_tag()`, `_process_series_tag()`, `_place_tag_videos()` —
    covered via the helpers above; ensure the cold-load path
    (`_resolve_series_collection_path` -> `load_collection_videos_only`) flows
    through the `_select_series_videos` filter (no extra code needed).
- Fallbacks unchanged: empty-after-filter hits existing branches (`"No videos"`
  placeholder, series `stop` -> `[]`, custom tag with no videos ->
  `ScheduleEntry(ct.name)` block). All-missing collections must not crash.

### 3. `strategies.py` — no gap change
- Leave `CustomTagMergeStrategy._fill_gap_fillers()` untouched. All other
  strategies inherit the fix via `ScheduleGenerator` helpers.

### 4. `daypart_scheduler.py` — feedback only
- In `_show_issues_in_statusbar()`, after `compute_schedule_issues`, read
  `self.schedule_generator._last_missing_excluded`; if > 0 append
  `", {n} missing excluded"` to the statusbar text + `preview_log.info(...)`.
- No widget/layout changes.

## Edge cases / notes
- Relative vs absolute paths: same `Path.exists()` check as dialogs.
- Performance: one `exists()` syscall per video per selection call; acceptable
  for preview sizes. No caching layer in v1 (future optimization if collections
  are huge / network-mounted).
- Restoring a file makes it reappear on next Generate with no further action.

## Verification
- New `Test/test_missing_exclusion.py` (no GUI needed):
  1. Custom tag with 1 existing + 1 missing file -> preview contains only existing.
  2. Series tag `video_count=1`, ep1 missing -> day0 gets ep2, day1 gets ep3 (compact).
  3. Random-fill 24h with missing -> no missing basenames in entries.
  4. Gap tag with missing -> still scheduled (exclusion does NOT apply).
  5. All-missing collection -> placeholder/empty fallback, no exception.
- Regression: run `Test/test_series_tag_bugs.py` + approximate tests to confirm no
  change in sequencing/fragment logic.

## Files touched
- `utils.py` (add 2 helpers), `scheduler.py` (helper + ~7 call sites + counter),
  `daypart_scheduler.py` (statusbar line only). `strategies.py`,
  `data_models.py`: no edits.
