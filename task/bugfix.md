# Bugfix: Ghost Preview List (Items Invisible but Selectable)

## Status
**Resolved** — two root causes identified and fixed.

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

## Root Causes (both fixed at `daypart_scheduler.py`)

### 1. Text drawn at wrong position (primary)
- `doc.drawContents(painter, option.rect)` uses `option.rect` **only as a clip rect**, not a position.
- The painter is in viewport coordinates (NOT pre-translated to the item's position).
- Text is always drawn at viewport origin `(0,0)`, regardless of which item is being painted.
- **Item 1** (`rect.y`=0): text at y=0 may partially show.
- **Item 2+** (`rect.y`>0): clip rect starts below the text → **entire text clipped out**.
- **Fix:** Added `painter.translate(option.rect.topLeft())` before `drawContents`, with `QRectF(0, 0, option.rect.width(), option.rect.height())` as clip rect.

### 2. No default text color in QTextDocument (secondary)
- `QTextDocument` uses `QPalette::Text` (usually black `#000000`) for unstyled HTML text.
- Application stylesheet sets `QListWidget` background to `#2a2a3e` (dark).
- Black-on-dark text is invisible (~1.3:1 contrast).
- The `QWidget { color: #f8f8f2 }` stylesheet does **not** propagate into `QTextDocument`.
- **Fix:** Added `<body style="color:#f8f8f2">` to the HTML to set the default text color to theme foreground.

## Changes Made

| File | Line | Change |
|---|---|---|
| `daypart_scheduler.py` | 73 | Wrap HTML body in `style="color:#f8f8f2"` for default text color |
| `daypart_scheduler.py` | 79-82 | Translate painter to `option.rect.topLeft()` before `drawContents` |
| `daypart_scheduler.py` | 59 | Added `rect={option.rect}` to paint debug log |

## Housekeeping Task (Separate)
- The log file has grown too large.
- Rotate logs by creating a **new timestamped log file per run** in a dedicated `logs/` folder.
- Implemented: `logs/daypart_scheduler_YYYYMMDD_HHMMSS.log` with `RotatingFileHandler`.
