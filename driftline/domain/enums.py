"""Enumerations (data_model_spec §2). Values equal the stored database values."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class TaskStatus(StrEnum):  # [DAT-02]
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"

    @property
    def label(self) -> str:
        return {
            TaskStatus.PLANNED: "Planned",
            TaskStatus.IN_PROGRESS: "In progress",
            TaskStatus.BLOCKED: "Blocked",
            TaskStatus.DONE: "Done",
        }[self]


class Priority(IntEnum):  # [DAT-03]
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

    @property
    def label(self) -> str:
        return self.name.capitalize()


class MilestoneStatus(StrEnum):  # [DAT-05]
    OPEN = "open"
    ACHIEVED = "achieved"

    @property
    def label(self) -> str:
        return self.value.capitalize()


class CommentKind(StrEnum):
    NOTE = "note"
    RISK_SET = "risk_set"
    RISK_CLEARED = "risk_cleared"
    BLOCKED = "blocked"
    SYSTEM = "system"


class EntityType(StrEnum):
    TASK = "task"
    MILESTONE = "milestone"


class ChangeKind(StrEnum):
    CREATE = "create"
    EDIT = "edit"
    REBASELINE = "rebaseline"
    ARCHIVE = "archive"
    RESTORE = "restore"


DEFAULT_TASK_STATUS = TaskStatus.PLANNED
DEFAULT_PRIORITY = Priority.MEDIUM
DEFAULT_MILESTONE_STATUS = MilestoneStatus.OPEN
DEFAULT_COMMENT_KIND = CommentKind.NOTE
