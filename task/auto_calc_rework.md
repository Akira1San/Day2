# Auto Calc End Time + Randomize Checkbox Rework

## Goal
Simplify the custom tag dialog by:
1. Removing the "Auto Calc End Time" button — end_time auto-calculates live as inputs change
2. Removing the "Randomize Videos" checkbox — always randomize, hidden from UI

## Files affected
- `dialogs/custom_tag_dialogs.py` — TagDialog and RandomFillDialog

## Changes

### Auto Calc End Time (read-only, always auto)

**TagDialog (`dialogs/custom_tag_dialogs.py`):**

1. Remove the Auto Calc button (`self.auto_calc_btn`) and its layout row (`calc_layout`), plus the `auto_calc_end_time` method entirely.

2. Make `end_time_edit` read-only so the user cannot type into it:
   ```python
   self.end_time_edit.setReadOnly(True)
   ```

3. Add a private recalculation method:
   ```python
   def _recalc_end_time(self):
       if not self.added_videos:
           return
       count = self.video_count_spin.value()
       total_duration = sum(
           self.added_videos[i].get('duration', 0)
           for i in range(min(count, len(self.added_videos)))
       )
       start_mins = qtime_to_minutes(self.start_time_edit.time())
       end_mins = (start_mins + int(total_duration // 60)) % (24 * 60)
       self.end_time_edit.setTime(QTime(end_mins // 60, end_mins % 60))
   ```

4. Connect signals to call `_recalc_end_time`:
   - `self.video_count_spin.valueChanged.connect(self._recalc_end_time)`
   - `self.start_time_edit.timeChanged.connect(self._recalc_end_time)`
   - After any add/remove of videos that changes `self.added_videos`, call `_recalc_end_time()` explicitly (signals won't cover `refresh_added_list`).

5. In `_populate_from_tag`: after populating all fields, call `_recalc_end_time()` to sync the end_time with the loaded tag state.

**RandomFillDialog (`dialogs/custom_tag_dialogs.py`):**

Same changes — remove `auto_calc_end_time`, make `end_time_edit` read-only, connect signals, add `_recalc_end_time`.

### Randomize Videos checkbox (remove entirely)

**TagDialog (`dialogs/custom_tag_dialogs.py`):**

1. Remove `self.randomize_videos_check` and its layout row (`rand_layout`).

2. In `_populate_from_tag`: remove the `hasattr(tag, 'randomize_videos')` block (currently lines 123-124).

3. In `get_tag()`: hardcode `randomize_videos=True` instead of reading from checkbox:
   ```python
   return Tag(..., randomize_videos=True, ...)
   ```

**RandomFillDialog:** no randomize checkbox exists here, so no changes.

## Testing

- [ ] Create a new custom tag — verify end_time auto-updates when changing video_count or start_time
- [ ] Edit an existing custom tag — verify end_time matches after loading
- [ ] Verify end_time field is grayed out / not editable
- [ ] Verify schedule preview shows randomized videos (as before, since randomize was already default)
- [ ] Edit a random fill tag — verify same auto-calc behavior works
- [ ] Run existing regression tests (`test_series_tag_bugs.py`, `test_movie_sequence.py`)
