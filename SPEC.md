# Daypart Scheduler - Specification Document

## 1. Project Overview

**Project Name:** Daypart Scheduler  
**Type:** Desktop GUI Application (Python/PySide6)  
**Core Functionality:** A scheduling tool that generates a 24-hour day video playlist with random fills and custom tags, featuring an "approximate" algorithm to seamlessly integrate custom time slots into randomly generated schedules.  
**Target Users:** Video editors, content schedulers, media planners

---

## 2. UI/UX Specification

### 2.1 Window Structure

- **Main Window:** Single window application (800x600 minimum)
- **Layout:** Vertical split - tags panel (left) and preview panel (right)
- **Native window frame** with standard controls (close, minimize, maximize)

### 2.2 Visual Design

**Color Palette:**
- Primary Background: `#1e1e2e` (dark charcoal)
- Secondary Background: `#2a2a3e` (lighter panels)
- Accent Color: `#7c3aed` (vibrant purple)
- Accent Hover: `#8b5cf6` (lighter purple)
- Text Primary: `#f8f8f2` (off-white)
- Text Secondary: `#a0a0b0` (muted gray)
- Success: `#22c55e` (green)
- Warning: `#f59e0b` (amber)
- Error: `#ef4444` (red)
- Border: `#3a3a4e`

**Typography:**
- Font Family: "Segoe UI", system default
- Heading Size: 16px bold
- Body Size: 13px regular
- Small/Label Size: 11px

**Spacing:**
- Base unit: 8px
- Panel padding: 16px
- Component spacing: 12px
- Button padding: 8px 16px

**Visual Effects:**
- Rounded corners: 6px for buttons, 8px for panels
- Subtle shadow on panels: `0 2px 8px rgba(0,0,0,0.3)`
- Hover transitions: 150ms ease

### 2.3 Components

**Tags Panel (Left Side - 300px width):**
- Title: "Daypart Tags"
- ListBox: Displays all tags (random + custom)
  - Each row shows: type icon + name + time range
  - Selection highlight: accent color background
- Buttons below list:
  - "Add Custom Tag" (accent color)
  - "Edit Tag" (secondary)
  - "Delete Tag" (warning color)
- Add/Edit Dialog: Modal dialog for custom tag properties

**Preview Panel (Right Side - Flexible):**
- Title: "24-Hour Schedule Preview"
- ListWidget: Scrollable list showing generated schedule
  - Each row: `HH:MM - HH:MM - Video Name` format
  - Shows day transition as "Day 1", "Day 2" if spans midnight
- Buttons at bottom:
  - "Copy Preview" (secondary)
  - "Approximate" (accent color, prominent)

**Tag Editor Dialog:**
- Fields:
  - Video Name: Text input (for custom tags only)
  - Start Time: Time picker (HH:MM)
  - End Time: Time picker (HH:MM)
- Buttons: "Save", "Cancel"

**Component States:**
- Default: Standard colors
- Hover: Lighter shade, cursor pointer
- Active/Pressed: Darker shade
- Disabled: 50% opacity, no interactions
- Selected (ListBox): Accent background

---

## 3. Functional Specification

### 3.1 Core Features

**Random Fill Generation:**
- Generates continuous 24-hour schedule starting at 00:00 (Day 1)
- Uses 24 placeholder videos: Superman, Batman, Spiderman, Wonder Woman, Iron Man, Thor, Hulk, Captain America, Black Panther, Aquaman, Flash, Green Lantern, Cyborg, Supergirl, Batgirl, Robin, Nightwing, Joker, Loki, Thanos, Doctor Strange, Scarlet Witch, Ant-Man, Wonder Man
- Each random videoDuration: Random between 1h and 3h
- Shuffles video list before generating
- Recycles through list if needed to fill 24h
- Always starts at 00:00 (first day)

**Custom Tags:**
- User-defined time ranges with video name
- Properties:
  - name: str (video name)
  - start_time: HH:MM format
  - end_time: HH:MM format
- No overlapping allowed (validation)

**Approximate Algorithm:**
- Triggered by "Approximate" button
- For each custom tag:
  1. Find random-fill segment whose START time is closest to custom tag's start time
  2. Closeness threshold: 30-50 minutes (default: 40 min)
  3. If found within threshold:
     - Replace that random-fill segment entirely with custom tag
     - Recalculate all subsequent random-fill videos to start from custom tag's end time
     - Maintain continuous 24h schedule (no gaps)
  4. If no random segment within threshold, keep custom tag as-is (user error case)
- Auto-applies to ALL custom tags

**Tag Management:**
- Add new custom tag via dialog
- Edit existing custom tag (name, start_time, end_time)
- Delete custom tag
- Cannot delete the default random fill tag (it's always present)

**Preview Generation:**
- Displays continuous schedule from 00:00 to 24:00 (next day 00:00)
- Format per line: `Day X HH:MM - Day X HH:MM - Video Name`
- If video spans midnight, show day transition
- Always 24h total (no gaps)

**Copy Function:**
- Copies preview text to clipboard
- Format:
  ```
  Day 1 00:00 - Day 1 01:30 - Superman
  Day 1 01:30 - Day 1 03:00 - Batman
  ...
  ```

### 3.2 User Interactions and Flows

**Initial State (on startup):**
1. Random fill tag exists (fills 24h)
2. One sample custom tag: "My Custom Video" at 13:00-15:00
3. Preview shows random fill only (approximate NOT yet pressed)

**Adding Custom Tag:**
1. Click "Add Custom Tag"
2. Dialog opens with empty fields
3. Enter: name, start time, end time
4. Click "Save"
5. Tag added to list
6. Preview updates (random fill adjusts around custom tag - no gaps)

**Editing Custom Tag:**
1. Select tag in list
2. Click "Edit Tag"
3. Dialog opens with current values
4. Modify fields
5. Click "Save"
6. Preview updates

**Running Approximate:**
1. Click "Approximate" button
2. Algorithm processes all custom tags
3. Preview updates with seamless schedule

### 3.3 Data Flow & Key Modules

```
TagManager
├── tags: List[Tag] (mixed random + custom)
├── add_custom_tag(name, start, end)
├── edit_tag(index, name, start, end)
├── delete_tag(index)
└── generate_schedule() -> List[ScheduleEntry]

ScheduleGenerator
├── videos: List[str] (24 placeholder names)
├── generate_random_fill() -> List[ScheduleEntry]
├── apply_custom_tags(tags) -> List[ScheduleEntry]
└── approximate(custom_tags) -> List[ScheduleEntry]

PreviewDisplay
├── schedule: List[ScheduleEntry]
├── format_entry(entry) -> str
├── format_for_copy() -> str
└── to_clipboard()
```

### 3.4 Edge Cases

- Custom tag start time equals random tag start time: Replace that random segment exactly
- Custom tag times span beyond 24h: Wrap to next day (Day 2)
- All 24h filled by custom tags: No random fill needed
- Custom tags fill partial day: Random fill fills remaining
- Multiple custom tags: Process in order of start time

---

## 4. Acceptance Criteria

### 4.1 Success Conditions

1. **Startup:** App launches with random fill 24h + one custom tag (13:00-15:00 "My Custom Video")
2. **Preview Display:** Shows continuous 24h schedule in correct format
3. **Add Custom Tag:** Can add new custom tag with valid time range
4. **Edit Custom Tag:** Can modify existing custom tag properties
5. **Delete Custom Tag:** Can remove custom tag (random fill remains)
6. **Approximate Algorithm:**
   - Correctly replaces random segment near custom tag start
   - Recalculates subsequent times with no gaps
   - Auto-applies to all custom tags
7. **Copy:** Copies preview text to clipboard in correct format
8. **No Gaps:** Preview always shows continuous 24h schedule

### 4.2 Visual Checkpoints

- [ ] Dark theme UI with purple accents renders correctly
- [ ] Tags list shows both random and custom tags with different styling
- [ ] Preview list shows times with day transition when needed
- [ ] Approximate button is visually prominent
- [ ] All buttons have hover states
- [ ] Dialogs are modal and center on parent window

---

## 5. Technical Notes

- **Python Version:** 3.9+
- **GUI Framework:** PySide6
- **No external dependencies** beyond PySide6 (standard library only for other needs)
- **Single file implementation** for simplicity