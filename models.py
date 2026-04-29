#!/usr/bin/env python3
"""Backward-compatible re-exports for the daypart scheduler.

This module maintains the original import surface by re-exporting all
public classes from the refactored sub-modules.
"""

from data_models import (
    Tag,
    MultiSeriesTag,
    ScheduleEntry,
    TagManager,
)
from scheduler import ScheduleGenerator
from strategies import (
    CustomTagMergeStrategy,
    FindReplaceApproximateStrategy,
    LinearApproximateStrategy,
    EarlyFillApproximateStrategy,
    LateFillApproximateStrategy,
    PriorityApproximateStrategy,
    BestFitApproximateStrategy,
    RoundRobinApproximateStrategy,
    LinearSpanningApproximateStrategy,
    ExhaustiveApproximateStrategy,
)

__all__ = [
    "Tag",
    "MultiSeriesTag",
    "ScheduleEntry",
    "TagManager",
    "ScheduleGenerator",
    "CustomTagMergeStrategy",
    "FindReplaceApproximateStrategy",
    "LinearApproximateStrategy",
    "EarlyFillApproximateStrategy",
    "LateFillApproximateStrategy",
    "PriorityApproximateStrategy",
    "BestFitApproximateStrategy",
    "RoundRobinApproximateStrategy",
    "LinearSpanningApproximateStrategy",
    "ExhaustiveApproximateStrategy",
]
