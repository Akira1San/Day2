# Daypart Scheduler — Code Review Action Items

> Generated from review on 2026-04-25. Last updated after commit `c4704a6`.

---

## 0. ✅ Completed (3/13)

- [x] **Extract `_place_tag_videos()`** — DRY up 3 duplicated blocks in `_apply_approximate_find_replace()` (`961c241`)
- [x] **Extract `_build_random_entries()`** — DRY up 3 random-fill generation loops (`827c785`)
- [x] **Extract `CustomTagMergeStrategy`** — Moved `apply_custom_tags()` and `_inject_custom_tags()` out of `ScheduleGenerator` (`c4704a6`)

---

## 1. 🐛 Bugs (3 items — 0 done)

- [ ] **1.1 Approximate Algorithm Truncation Bug**
  - **File:** `models.py`
  - **Method:** `_apply_approximate_find_replace()` (surrounding logic, not the video placement block)
  - **Problem:** When Approximate is ON, random fill videos before a custom/series tag get truncated. A random video that should span e.g. `12:30–13:00` gets cut to `12:55–13:00` (5 min).
  - **Evidence:** `Test/test_approximate.py` reproduces this.
  - **Root cause hypothesis:** The random-entry selection / partial-append logic around the custom tag placement (lines handling `best_rand`, `current_pos`, remaining portions) has an off-by-one or boundary condition when `current_pos` falls inside a random entry.
  - **Fix approach:** Trace `current_pos` through the `best_rand` selection branch. The truncation likely happens in the partial-append block that adds `ScheduleEntry(current_pos, rand_e.end_minutes, ...)`.

- [ ] **1.2 Dead Code in `utils.py`**
  - **File:** `utils.py`
  - **Lines:** 59–80
  - **Problem:** `load_collection_videos_only()` has unreachable code after `return []` on line 57. The entire duplicate try/except block below is never executed.
  - **Fix:** Remove lines 59–80.

- [ ] **1.3 Fragile Video Removal in RandomFillDialog**
  - **File:** `dialogs.py`
  - **Method:** `RandomFillDialog.remove_selected_added()`
  - **Problem:** Filters by splitting on `'/'` and comparing filenames. If two videos share the same filename in different directories, the wrong one gets removed.
  - **Fix:** Use the full video object or a stable identifier (e.g., `path`) for removal instead of filename string matching.

---

## 2. 🔧 Code Quality (3 items — 0 done)

- [ ] **2.1 Remove Debug Print Statements**
  - **File:** `dialogs.py`
  - **Lines:** 557, 572, 580, 590, 594, 596, 1098, 1108, 1111, 1113
  - **Problem:** `print(f"[DEBUG] ...")` statements left in production code.
  - **Fix:** Delete all debug prints or replace with a proper logging setup (e.g., `logging.debug()`).

- [ ] **2.2 Replace Inline `__import__('datetime')` Hack**
  - **File:** `daypart_scheduler.py`
  - **Lines:** 283, 311
  - **Problem:** Uses `__import__('datetime').timedelta(...)` inline instead of a normal import.
  - **Fix:** Add `from datetime import timedelta` at the top of the file and replace both occurrences.

- [ ] **2.3 Extract Magic Numbers to Constants**
  - **File:** `models.py`, `utils.py`
  - **Problem:** `90` (default video duration), `24 * 60` (minutes per day), `60` (seconds per minute) are scattered throughout.
  - **Fix:** Define module-level constants:
    ```python
    MINUTES_PER_DAY = 24 * 60
    DEFAULT_VIDEO_DURATION_SEC = 90
    DEFAULT_VIDEO_DURATION_MIN = 1  # fallback minimum
    ```

---

## 3. 🏗️ Architecture / Refactoring (4 items — 1 done)

- [ ] **3.1 Reduce `edit_tag()` Argument Count**
  - **File:** `daypart_scheduler.py`
  - **Method:** `edit_tag()` call at line 387
  - **Problem:** Passes 17 positional arguments. Extremely error-prone.
  - **Fix:** Pass a single `Tag` object instead, or use a dataclass/namespace for the parameters.

- [ ] **3.2 Extract Duplicated Dialog Logic**
  - **File:** `dialogs.py`
  - **Problem:** `load_available_profiles()` and `collection_profile_selected()` are duplicated almost identically across `TagDialog`, `RandomFillDialog`, and `SeriesDialog`.
  - **Fix:** Move these methods to `BaseTagDialog` so all subclasses inherit them.

- [ ] **3.3 Break Up `ScheduleGenerator` Responsibilities**
  - **File:** `models.py`
  - **Problem:** `ScheduleGenerator` handles random fill, custom tags, series parsing, 24h gap filling, and two different approximate algorithms.
  - **Fix:** Extract strategy classes:
    ```
    RandomFillStrategy
    LinearApproximateStrategy
    FindReplaceApproximateStrategy
    ```
  - **Status:** Steps 1–3 done (`_place_tag_videos()`, `_build_random_entries()`, `CustomTagMergeStrategy` extracted). Next: `LinearApproximateStrategy`, then `FindReplaceApproximateStrategy`.

- [ ] **3.4 Refactor `Tag` God Object**
  - **File:** `models.py`
  - **Problem:** `Tag.__init__` has ~20 parameters covering custom tags, series tags, and random fill tags. Many are irrelevant depending on `tag_type`.
  - **Fix:** Consider inheritance:
    ```python
    class BaseTag: ...
    class CustomTag(BaseTag): ...
    class SeriesTag(CustomTag): ...
    class RandomFillTag(BaseTag): ...
    ```

---

## 4. 📝 Missing Features (2 items — 0 done)

- [ ] **4.1 Add Overlap Validation**
  - **File:** `models.py` or `dialogs.py`
  - **Spec reference:** Section 3.1 — "No overlapping allowed (validation)"
  - **Problem:** Custom tags can overlap. The spec says this should be prevented.
  - **Fix:** In `TagManager.add_tag()` and `edit_tag()`, check new tag against existing tags and reject if any time ranges overlap.

- [ ] **4.2 Serialization Modernization**
  - **File:** `serialization.py`
  - **Problem:** Uses a mini-INI format embedded inside an INI value, plus a legacy `|` pipe-delimited fallback.
  - **Fix:** Consider JSON serialization for tags. It handles nested structures natively and is easier to parse.

---

## Progress Summary

| Category | Total | Done | Remaining |
|----------|-------|------|-----------|
| Bugs | 3 | 0 | 3 |
| Code Quality | 3 | 0 | 3 |
| Architecture | 4 | 0 | 4 |
| Missing Features | 2 | 0 | 2 |
| **Completed** | **3** | **3** | **0** |
| **Grand Total** | **14** | **3** | **11** |

---

## Priority Order (Suggested)

1. **Fix truncation bug** (1.1) — most critical functional issue
2. **Remove dead code & debug prints** (1.2, 2.1, 2.2) — quick wins
3. **Add overlap validation** (4.1) — spec requirement
4. **Extract duplicated dialog logic** (3.2) — medium effort, high maintainability
5. **Reduce `edit_tag()` args** (3.1) — reduces bug surface
6. **Magic numbers → constants** (2.3)
7. **Architecture refactoring** (3.3, 3.4, 4.2) — larger effort, schedule separately
