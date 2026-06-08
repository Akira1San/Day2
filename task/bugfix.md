# Bugfix: Ghost Preview List (Items Invisible but Selectable)

## Status
In progress — debug instrumentation added, root cause not yet confirmed.

## Symptom
After loading tags and pressing **Generate** for a single-day schedule preview, the preview list appears visually empty. The items are still present in the model: they can be selected, and **Copy Preview Schedule** returns valid schedule text from the list.

This means the bug is in the **view/paint path**, not in schedule generation.

## Evidence Collected So Far

### 1. Schedule generation works
```
[REFRESH] entries=2 approximate=False mode=None
[REFRESH] list_count=2
```

### 2. Delegate sizeHint works and returns valid sizes
```
[DELEGATE] sizeHint text='Day 1\n20:00 - 20:51 - Sandokan 1976 - Sandokan E01.mp4' hint=293x42 avail=658
[DELEGATE] sizeHint text='Day 1\n20:51 - 21:51 - Sandokan 1976 - Sandokan E02.mp4' hint=293x42 avail=658
```

### 3. Preview list count matches entries
`self.preview_list.count()` equals the number of generated entries.

### 4. Copy path sees correct data
`copy_preview()` successfully reads item texts / `ScheduleEntry.to_copy_string()` from the list and copies them.

## Current Implementation Notes

### Preview list setup
- `preview_list` is a `QListWidget` inside a `QScrollArea`.
- Items are added as plain-text `QListWidgetItem(text)`.
- Each item also stores the `ScheduleEntry` via `Qt.UserRole` for the delegate.

### Tag name coloring
- A `TagNameColorDelegate(QStyledItemDelegate)` is installed on `preview_list`.
- `paint()` reads the entry, extracts the tag name, builds HTML with `<span style="color:...">`, and renders it with `QTextDocument`.
- `sizeHint()` also uses `QTextDocument` and a minimum width fallback (`_available_width()` returns `240` when `option.rect.width()` is `0`).
- Selected/hover styles are defined in `QListWidget::item` and `QListWidget::item:selected`.

### Logging added
- `refresh_preview()` logs entry count and list count.
- `generate_weekly_preview()` / `generate_monthly_preview()` log entry counts and added item counts.
- `TagNameColorDelegate.paint()` logs the text, tag name, and color before painting.
- `TagNameColorDelegate.sizeHint()` logs computed hints.
- `copy_preview()` logs the raw text it reads from the list.

## Likely Causes to Investigate Next

1. **`paint()` is not being called at all**
   - The view may believe items have zero height/width and skip painting.
   - Verify in the log whether `[DELEGATE] paint` ever appears.

2. **Painting happens but is clipped or drawn off-screen**
   - `option.rect` may be positioned outside the visible viewport.
   - Check `option.rect` coordinates in `paint()` logging.

3. **`QTextDocument` drawing fails silently inside the viewport**
   - `doc.drawContents(painter, option.rect)` may not align with widget coordinates.
   - Test with plain `painter.drawText(...)` fallback first.

4. **Item delegate or model mismatch**
   - Confirm the delegate is still installed after `clear()` / repopulate.
   - Verify no other code resets the delegate.

5. **Style/theme interference**
   - The dark theme stylesheet may set text color to the background color, making text invisible.
   - Check whether item text color matches background in the stylesheet.

## Next Debug Steps

1. Re-run the app, open the log, and confirm whether `[DELEGATE] paint` appears.
2. If `paint` is missing: add logging to `QListWidget.viewport().update()` and `QListView.paintEvent` to trace repaint events.
3. If `paint` runs but still invisible:
   - Temporarily replace `doc.drawContents(...)` with `painter.drawText(option.rect, 0, text)` to rule out `QTextDocument` issues.
   - Log `option.rect` coordinates and the viewport geometry.
4. Check the stylesheet for `QListWidget::item` color rules that could make text invisible on the dark background.
5. Inspect whether the preview list or scroll area is being obscured by another widget or layout issue.

## Housekeeping Task (Separate)
- The log file has grown too large.
- Rotate logs by creating a **new timestamped log file per run** in a dedicated `logs/` folder.
- Implemented: `logs/daypart_scheduler_YYYYMMDD_HHMMSS.log` with `RotatingFileHandler`.
