# Movie Sequence Mode — Bug Fixes (One By One)

## Status: ALL 3 user-reported bugs FIXED. Deferred: Bugs A–E.

## Context

The Movie Sequence feature (`video_order_mode = "movie_sequence"`) was implemented
in `scheduler.py` and `utils.py` to group videos by numeric identifier in the
filename (e.g., "Movie 1", "Part 1") and assign each group to a specific day.
A prior attempt at a global refactor (day-aware loop in `generate_random_fill`)
broke things in production and was reverted via `git checkout`. We then fixed
bugs individually, validating each before moving on.

**Rule:** Fix one bug at a time. Run the existing test suite after every
change. Do not bundle multiple bugs in a single commit.

---

## User-Reported Bugs

### Bug 1 — Every day starts at 00:00  ✅ FIXED
**Reported:** Schedule preview restarts from 00:00 at the start of each day
instead of continuing from the previous day's end.

**Resolution:** Reverted prior `generate_random_fill` change via
`git checkout scheduler.py test_movie_sequence.py`. The on-disk code
now matches the version that was in place before the day-aware loop
regression, and the user has confirmed Bug 1 is gone.

**Validation:** `python3 test_no_approximate_continuous.py` — all 4
regression tests pass (1-day, 3-day, 7-day, no-reset-at-boundary).

**Status:** ✅ Fixed (2026-06-06 by revert)

---

### Bug 2 — From day 3 onwards, only 1 single video plays for a day  ✅ FIXED
**Reported:** Day 1 and 2 look correct, but from day 3 onwards a single
video consumed most of the day.

**Resolution:** Same revert as Bug 1. The day-aware loop in
`generate_random_fill` was leaving `pos` short of the day boundary, so
later days exited after one entry. Reverting restored the flat-list
cycle behavior, and the user has confirmed Bug 2 is gone.

**Validation:** `python3 test_movie_sequence.py` — all tests pass
including the existing 2-day `_build_random_entries` coverage.

**Status:** ✅ Fixed (2026-06-06 by revert)

---

### Bug 3 — Generate button only works once in Movie Sequence mode  ✅ FIXED
**Reported:** Pressing Generate a second time in Movie Sequence mode does
NOT produce a new preview. In Random mode, repeated Generate presses
correctly produce different previews (because of the random shuffle).

**Root cause:** Movie-sequence output is fully deterministic
(`group_videos_by_movie` returns videos in the same order every call,
no `random.shuffle` involved) so subsequent generations look identical
and the user perceives Generate as broken.

**Fix applied — Option (B) rotate the starting movie on each Generate click:**

1. `ScheduleGenerator.__init__` added `self._generate_count = 0`.
2. `apply_custom_tags()` and `apply_approximate()` (the two entry points
   invoked by the Generate button via `refresh_preview`) do
   `self._generate_count += 1` at the top.
3. `_get_videos_for_day(videos, day_offset)` now uses:
   ```python
   effective_day = (day_offset + self._generate_count) % num_movies
   selected_movie = movie_numbers[effective_day]
   ```
   So Day 1 cycles through M1 → M2 → M3 → M1 ... on each Generate click.
4. `_build_random_entries` and `generate_random_fill` movie_sequence
   branches rotate the flat list by `self._generate_count % len(ordered)`
   so random-fill cycles also rotate visibly.

**Result with 3 movies:**
- Click 1: Day 1 = M1, Day 2 = M2, Day 3 = M3
- Click 2: Day 1 = M2, Day 2 = M3, Day 3 = M1
- Click 3: Day 1 = M3, Day 2 = M1, Day 3 = M2
- Click 4: Day 1 = M1, ... (wraps)

Part-order within each movie group is preserved (no shuffling inside
groups). Day→movie mapping semantics are preserved (each day still
shows exactly one movie's parts). The change is purely a rotation of
where the cycle starts.

**Validation — `Test/test_generate_rotates_starting_movie` (new test):**
- Click 1, day 0: Movie 1 ✓
- Click 2, day 0: Movie 2 ✓
- Click 3, day 0: Movie 3 ✓
- Click 4, day 0: Movie 1 (wrap) ✓
- `_generate_count` bumps 0 → 1 → 2 on successive `apply_custom_tags()` calls ✓
- `apply_custom_tags()` produces different first-video on consecutive clicks ✓
- All 5 pre-existing tests still pass ✓
- `Test/test_no_approximate_continuous.py` — all 4 regression tests still pass ✓

**Files modified:**
- `scheduler.py` — ~12 lines added: counter init, two `+=1` increments,
  one rotation in `_get_videos_for_day`, two rotations in
  `_build_random_entries` / `generate_random_fill` movie_sequence branches.
- `Test/test_movie_sequence.py` — added `Test/test_generate_rotates_starting_movie` (~80 lines).

**Status:** ✅ Fixed (2026-06-06 by adding rotation counter)

---

## Already-Identified Implementation Bugs (from prior code review, NOT yet validated against the live system)

### Bug A — strategies.py ignores video_order_mode for random fill
All approximate strategies do `random.shuffle(rf_videos)` directly,
bypassing `_get_videos_for_day`. So in any approximate mode, movie_sequence
silently degrades to random.

**Status:** ⏸ TODO — defer

---

### Bug B — Inconsistent day-aware behavior in _build_random_entries and generate_random_fill
The spec says "Day 1 = Movie 1, Day 2 = Movie 2" but the implementations
build a flat list and cycle, mixing movies within a single day.

**Note:** The prior attempt to fix this caused the regressions reported
in Bug 1 and Bug 2. Re-investigate carefully. Bug 3's rotation counter
now masks the visual problem (you see different cycles on each click)
but the underlying "all movies in one stream" issue remains.

**Status:** ⏸ TODO — defer; needs a different approach

---

### Bug C — Redundant conditional in _process_random_fill_tag
Lines ~539-542:
```python
if continuation_pos > rf_start:
    pos = continuation_pos
elif continuation_pos > 0:
    pos = continuation_pos
```
Both branches do the same thing.

**Status:** ⏸ TODO — defer (cosmetic, low priority)

---

### Bug D — _place_tag_videos shadows its day_offset parameter
Line ~247: `day_offset = start // 86400` overwrites the parameter passed
by the caller. The caller's intent is lost.

**Status:** ⏸ TODO — defer (cosmetic, but could mask other issues)

---

### Bug E — Inconsistency between fill_24h and non-fill_24h branches in _process_random_fill_tag
fill_24h uses `_get_videos_for_day` (day-aware); non-fill_24h builds a
flat list. Two paths produce different ordering for the same data.

**Status:** ⏸ TODO — defer

---

## Workflow

1. Pick ONE bug.
2. Read the relevant code paths fully.
3. Add a failing test that reproduces the bug.
4. Implement the fix.
5. Re-run ALL existing tests:
   - `python3 test_movie_sequence.py`
   - `python3 test_no_approximate_continuous.py`
   - `python3 test_all_modes.py` (if applicable)
6. If everything passes, commit the fix and update this file (mark ✅).
7. Move to the next bug.

## Files to Inspect (when starting each bug)

- `scheduler.py` — core scheduling logic
- `strategies.py` — approximate-mode strategies
- `daypart_scheduler.py` — UI, video_order_combo wiring
- `utils.py` — `extract_movie_sequence_key`, `group_videos_by_movie`
- `Test/test_movie_sequence.py` — existing tests
- `Test/test_no_approximate_continuous.py` — continuous-schedule regression

---

**Last Updated:** 2026-06-06
**Owner:** Kilo (implementation agent)
**Reverted Commit Range:** see `git log --oneline` (revert via `git checkout`)
