# Refactor dialogs.py - Split into Modular Package

## Problem Statement

The `dialogs.py` file has grown to **2104 lines** with 9 dialog classes, making it:
- Hard to navigate and maintain
- Difficult to test individual components
- High cognitive load when working on any single dialog
- Significant code duplication (especially between `TagDialog` and `RandomFillDialog`)

## Current State Analysis

### File Statistics
- **Total lines**: 2104
- **Largest classes**:
  - `RandomFillDialog`: ~692 lines
  - `TagDialog`: ~557 lines
  - `SeriesDialog`: ~295 lines

### Code Duplication Issues
1. **TagDialog vs RandomFillDialog**: ~80% identical code
   - Both have identical `_create_video_list_section()` methods (lines 195-244 vs 798-847)
   - Both have identical `_create_blacklist_section()` methods (lines 246-280 vs 849-883)
   - Both duplicate `load_available_profiles()` (lines 471-512 vs 893-934)
   - Both duplicate profile selection handlers (lines 514-541 vs 936-965)
   - Both duplicate blacklist selection handlers (lines 543-554 vs 967-979)
   - Both duplicate `load_collection()` with minor variations (lines 390-469 vs 981-1061)
   - Both duplicate video list management methods (select_all, clear_selection, add_selected_videos, etc.)
   - Both duplicate `auto_calc_end_time()` with minor differences

2. **SeriesDialog duplicates profile/blacklist logic**: 
   - `load_available_profiles()` duplicated (lines 1581-1622)
   - `collection_profile_selected()` duplicated (lines 1624-1652)
   - `blacklist_profile_selected()` duplicated (lines 1654-1666)
   - `load_blacklist_file()` duplicated (lines 1668-1675)

3. **Scattered debug statements**: Multiple `print("[DEBUG]...")` calls that should be removed or converted to proper logging

### Structural Issues
- Mixing UI construction, business logic, and data transformation in single methods
- No separation of concerns between video list management, profile handling, and collection loading
- Helper functions like `_create_video_list_section()` return ad-hoc objects using `type()` instead of proper classes
- Common functionality from `BaseTagDialog` is limited but could be expanded

## Proposed Solution: Package-Based Refactoring

### Target Structure

```
dialogs/
├── __init__.py                 # Re-export all dialogs for backward compatibility
├── base.py                     # BaseTagDialog, VideoListWidget, common UI helpers
├── collection_base.py          # CollectionDialogBase (refactored shared logic)
├── custom_tag_dialogs.py       # TagDialog, RandomFillDialog (thin subclasses)
├── series_dialogs.py           # SeriesDialog, SeriesConfigDialog, MultiSeriesDialog
├── config_dialog.py            # ConfigDialog
├── preview_dialog.py           # SchedulePreviewDialog
├── exceptions.py               # Dialog-specific exceptions (optional)
├── utils.py                    # Dialog utilities (optional)
└── widgets/
    ├── __init__.py
    ├── video_list.py           # VideoListWidget, VideoSection, BlacklistSection
    ├── info_panel.py           # CollectionInfoPanel, VideoInfoDisplay
    └── profile_selector.py     # ProfileSelectorWidget (reusable profile combo + load button)
```

### File Responsibilities

#### `dialogs/base.py`
- `BaseTagDialog`: Core dialog with time input setup (`_setup_time_inputs`)
- `VideoListWidget`: Custom QListWidget with ExtendedSelection
- Basic dialog utilities

#### `dialogs/widgets/video_list.py`
- `VideoSection` dataclass: holds `widget`, `videos_list`, `count_label`
- `BlacklistSection` dataclass: holds `widget`, `blacklist_list`, `count_label`
- Functions to create these sections (formerly `_create_video_list_section` and `_create_blacklist_section`)

#### `dialogs/widgets/info_panel.py`
- `CollectionInfoPanel`: Displays collection name, description, genre, year, cover image
- `VideoInfoDisplay`: Displays selected video details (name, path, duration)
- Used by `RandomFillDialog` and `TagDialog`

#### `dialogs/collection_base.py`
**The core refactoring - eliminates 500+ lines of duplication**

```python
class CollectionDialogBase(BaseTagDialog):
    """
    Base class for dialogs that manage:
    - Collection loading (JSON with metadata)
    - Blacklist management (JSON/INI files)
    - Added videos list (selected from collection)
    - Profile selection (collection + blacklist profiles)
    
    Used by: TagDialog, RandomFillDialog
    """
    
    # Common UI components
    collection_path: QLineEdit
    collection_profile_combo: QComboBox
    blacklist_profile_combo: QComboBox
    videos_list: VideoListWidget
    added_list: VideoListWidget
    blacklist_list: VideoListWidget
    collection_videos: List[dict]
    added_videos: List[dict]
    blacklist: List[dict]
    
    # Abstract methods to be implemented by subclasses:
    # - get_tag() -> Tag
    # - load_collection_customizations() [optional]
    
    # Shared implementations:
    # - setup_common_ui()
    # - _create_video_sections() -> (collection_widget, added_widget, blacklist_widget)
    # - load_collection()
    # - refresh_added_list()
    # - refresh_blacklist_list()
    # - add_selected_videos()
    # - remove_selected_added()
    # - remove_all_added()
    # - add_to_blacklist()
    # - remove_from_blacklist()
    # - update_counts()
    # - load_available_profiles()
    # - profile_selected()
    # - blacklist_profile_selected()
    # - load_blacklist_file()
    # - save_blacklist_file() [modified in TagDialog]
    # - auto_calc_end_time() [overridden as needed]
    # - on_video_selected() [overridden for custom info display]
```

Key differences between TagDialog and RandomFillDialog handled via:
- `fill_24h_check`: Only in RandomFillDialog
- `video_count_spin`: Both have it, RandomFillDialog uses it for auto-calc differently
- Info panel: RandomFillDialog has detailed collection info + cover display
- `load_collection()`: RandomFillDialog sets up `collection_info_dict` and `covers_root`
- `get_tag()`: Returns different Tag types and fields

RandomFillDialog keeps:
- `CollectionInfoPanel` widget (cover image display)
- `fill_24h_check` checkbox
- Custom `on_added_video_selected()` and `on_blacklist_video_selected()` for cover display
- Custom `load_collection()` to populate info panel and covers_root

TagDialog keeps:
- Simple `video_info` QLabel
- `save_blacklist_file()` implementation
- `randomize_videos_check` checkbox
- `get_tag()` for custom tag fields

#### `dialogs/series_dialogs.py`
- `SeriesDialog`: Single series configuration
- `SeriesConfigDialog`: Sub-dialog for editing one series config
- `MultiSeriesDialog`: Container for multiple SeriesDialog configs
- Extract common profile/blacklist loading into a mixin or helper class `SeriesProfileMixin`

#### `dialogs/config_dialog.py`
- `ConfigDialog`: Standalone, no changes needed except extraction

#### `dialogs/preview_dialog.py`
- `SchedulePreviewDialog`: Standalone, no changes needed except extraction

## Implementation Phases

### Phase 1: Foundation (Low Risk)
**Goal**: Extract reusable widgets without changing behavior

1.1 Create `dialogs/widgets/video_list.py`
- Move `VideoListWidget` class
- Create `VideoSection` and `BlacklistSection` as proper dataclasses or namedtuples
- Move section creation functions as standalone: `create_video_section(...)` and `create_blacklist_section(...)`
- Update `TagDialog` and `RandomFillDialog` to use new functions

1.2 Create `dialogs/widgets/info_panel.py`
- Extract `CollectionInfoPanel` widget (currently inline in RandomFillDialog.setup_ui lines 682-711)
- Extract video info display logic into reusable component
- Make it pluggable so TagDialog can use simple QLabel, RandomFillDialog can use full panel

1.3 Create `dialogs/__init__.py`
- Re-export all dialog classes: `from .custom_tag_dialogs import TagDialog, RandomFillDialog`
- Ensure existing imports (`from dialogs import TagDialog`) continue to work

**Deliverable**: `dialogs/` package exists, all existing tests pass, no behavior changes

### Phase 2: Extract CollectionDialogBase (High Impact)
**Goal**: Eliminate Tag/RandomFill duplication

2.1 Create `dialogs/collection_base.py`
- Move duplicated methods from TagDialog to base class:
  - `_create_video_list_section` → `_create_video_sections()` (returns all 3 sections)
  - `_create_blacklist_section` → integrated into `_create_video_sections()`
  - `load_available_collection_profiles` → `load_available_profiles()`
  - `profile_selected`, `blacklist_profile_selected`
  - `load_collection()` common logic (split into `_load_collection_common()` and `_populate_video_lists()`)
  - `refresh_added_list()`, `refresh_blacklist_list()`
  - `add_selected_videos()`, `remove_selected_added()`, `remove_all_added()`
  - `add_to_blacklist()`, `remove_from_blacklist()`
  - `update_counts()`
  - `load_blacklist_file()`
  - `auto_calc_end_time()` (with hook for subclass modifications)

2.2 Refactor `TagDialog` into `custom_tag_dialogs.py`
- Subclass `CollectionDialogBase`
- Implement `get_tag()` returning `Tag`
- Override `save_blacklist_file()` (specific behavior)
- Keep `randomize_videos_check` and `video_count_spin`
- Add custom UI parts in `setup_ui()` calling `super().setup_common_ui()` then custom additions
- Remove all duplicated methods (now inherited)

2.3 Refactor `RandomFillDialog` into `custom_tag_dialogs.py`
- Subclass `CollectionDialogBase`
- Implement `get_tag()` returning `Tag` with `is_random_fill=True, fill_24h=...`
- Override `load_collection()` to populate `collection_info_dict` and `covers_root`
- Override `on_video_selected()` to show cover image
- Add info panel and `fill_24h_check` in `setup_ui()`
- Remove all duplicated methods (now inherited)

**Deliverable**: TagDialog and RandomFillDialog each ~80-120 lines; all existing functionality preserved

### Phase 3: Series Dialog Consolidation
**Goal**: Reduce duplication in series-related dialogs

3.1 Create `dialogs/series_dialogs.py`
- Move `SeriesDialog`, `SeriesConfigDialog`, `MultiSeriesDialog` to separate file
- Extract `SeriesProfileMixin` with shared profile/blacklist loading logic:
  - `load_available_profiles()`
  - `collection_profile_selected()`
  - `blacklist_profile_selected()`
  - `load_blacklist_file()`
- SeriesDialog and SeriesConfigDialog inherit from mixin
- MultiSeriesDialog uses mixin for profile handling

3.2 Remove duplicated `load_available_profiles` in SeriesDialog (use mixin method)
**Note**: SeriesDialog has different blacklist handling (just loads, doesn't manage added_videos), so careful to only extract common parts.

**Deliverable**: Series dialogs consolidated, ~150-200 lines saved

### Phase 4: Standalone Dialogs
**Goal**: Extract ConfigDialog and SchedulePreviewDialog

4.1 Move `ConfigDialog` to `dialogs/config_dialog.py`
4.2 Move `SchedulePreviewDialog` to `dialogs/preview_dialog.py`
4.3 Update import in `daypart_scheduler.py` if needed (should work via `dialogs/__init__.py`)

### Phase 5: Cleanup and Polish
**Goal**: Final cleanup

5.1 Remove all `print("[DEBUG]...")` statements, replace with `logger.debug()` where needed
5.2 Ensure all imports in `dialogs/__init__.py` are correct
5.3 Update any relative imports within dialogs package
5.4 Run full test suite to verify no regressions
5.5 Check for any circular import issues (dialogs imports utils, models; utils should not import dialogs)
5.6 Document public API in `dialogs/__init__.py` docstring

### Phase 6: Documentation and Validation
6.1 Update any documentation referencing `dialogs.py` as a single file
6.2 Run static analysis (pylint/flake8/mypy if used)
6.3 Ensure all dialog classes are properly exported
6.4 Create a mapping table showing old line numbers → new file locations for reference

## Testing Strategy

### Unit Tests
- Test each dialog in isolation (existing UI tests should still work)
- Test `CollectionDialogBase` through `TagDialog` and `RandomFillDialog` subclasses
- Verify profile loading, blacklist loading, video list operations
- Verify `get_tag()` returns correct Tag objects with proper fields

### Integration Tests
- Ensure `daypart_scheduler.py` can import all dialogs without changes
- Test full workflow: open dialog → load collection → add videos → save tag → use in schedule
- Test profile persistence and blacklist operations

### Manual QA
- Open each dialog in the application UI
- Verify all buttons, lists, and controls work as before
- Check that cover images display correctly in RandomFillDialog
- Verify time calculations work correctly
- Confirm blacklist save/load operations

## Migration Plan

### Backward Compatibility
The `dialogs/` package must maintain the same import surface:

```python
# dialogs/__init__.py
from .custom_tag_dialogs import TagDialog, RandomFillDialog
from .series_dialogs import SeriesDialog, SeriesConfigDialog, MultiSeriesDialog
from .config_dialog import ConfigDialog
from .preview_dialog import SchedulePreviewDialog
from .base import BaseTagDialog, VideoListWidget

__all__ = [
    'TagDialog',
    'RandomFillDialog',
    'SeriesDialog',
    'SeriesConfigDialog',
    'MultiSeriesDialog',
    'ConfigDialog',
    'SchedulePreviewDialog',
    'BaseTagDialog',
    'VideoListWidget',
]
```

This allows existing code to continue using:
```python
from dialogs import TagDialog  # Still works
```

### Gradual Migration (Optional)
If concerns about breaking changes, we can:
1. First move code to `dialogs/` but keep `dialogs.py` as a shim that imports from the package
2. Deprecate `dialogs.py` with warnings
3. Remove shim after one release cycle

But given this is an internal application, direct package migration is acceptable.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Circular imports between modules | High | Keep dialogs depends on utils/models, not vice versa. Use TYPE_CHECKING for type hints |
| Profile loading logic has subtle edge cases | Medium | Write tests for `load_available_profiles()` before refactoring; verify behavior matches exactly |
| UI state management breaks (signals/slots) | High | Run manual UI tests; ensure all signal connections are preserved |
| Missing re-exports cause ImportErrors | Medium | Comprehensive `__init__.py` and integration test importing all classes |
| Debug statements removed too early | Low | Remove only after verifying logging is adequate |

## Estimated Impact

### Lines of Code Reduction
- **Duplication eliminated**: ~500 lines (TagDialog vs RandomFillDialog shared logic)
- **SeriesDialog consolidation**: ~150 lines (profile loading dedup)
- **Total savings**: ~650 lines
- **New overhead** (package files, imports): ~50 lines
- **Net reduction**: ~600 lines

### Post-refactor file sizes (estimated):
- `custom_tag_dialogs.py`: 2 classes, ~150 lines each = ~300 lines
- `series_dialogs.py`: 3 classes = ~400 lines
- `collection_base.py`: ~400 lines
- `base.py`: ~100 lines
- `config_dialog.py`: ~110 lines
- `preview_dialog.py`: ~130 lines
- **Total**: ~1440 lines across 7 files (avg ~200 lines/file)

Maintainability improvement: Files are now focused, easier to locate specific dialog code, and duplication is eliminated.

## Success Criteria

1. All existing unit and integration tests pass
2. Application UI functions identically to pre-refactor
3. No import errors when importing from `dialogs` package
4. Code coverage stays the same or improves
5. No debug print statements remain in production code
6. All dialog classes can be imported from `dialogs` package
7. File count: 6-8 files in `dialogs/` package
8. Largest file under 500 lines (collection_base.py ~400 lines)
9. No circular dependencies
10. Static analysis passes (if configured)

## Dependencies and Prerequisites

- Python 3.8+ (for dataclasses if used, though can backport)
- PySide6 (already used)
- Project structure: Application is in `/day2/` directory; `dialogs.py` is at root
- No external dependencies beyond existing ones

## Open Questions

1. **Should we create a `ProfileLoader` utility class?**
   - Could be shared between CollectionDialogBase and SeriesProfileMixin
   - Might be over-engineering; simple mixin may suffice

2. **How to handle `collection_info_dict` and cover display logic?**
   - Currently RandomFillDialog has extensive cover image handling
   - Should that be extracted to `InfoPanelWidget`? Yes, planned in Phase 1

3. **What to do with `_display_cover_image` debug prints?**
   - Remove entirely or keep behind `if logger.isEnabledFor(logging.DEBUG)`?
   - Plan: Remove; use proper debug logging if needed

4. **Should SeriesDialog reuse any of CollectionDialogBase?**
   - SeriesDialog doesn't manage added_videos/blacklist same way
   - Only profile selection logic overlaps → use mixin, not inheritance

5. **Do we need `exceptions.py` or `utils.py` in dialogs package?**
   - Start without them; add only if needed during refactoring
   - Could hold `DialogException` base class or validation errors

## Related Files to Review

- `daypart_scheduler.py`: Imports all dialogs
- `models.py`: Tag, MultiSeriesTag definitions
- `utils.py`: Helper functions used by dialogs (load_collection_json, load_blacklist_json, get_config_paths, etc.)
- `scheduler.py`: Might create tags but doesn't import dialogs directly

## References

- Existing `models.py` shows pattern of splitting large file into submodules (data_models.py, scheduler.py, strategies.py)
- Follow similar convention: one class per file or group related classes
- Keep `__init__.py` minimal but complete for public API
