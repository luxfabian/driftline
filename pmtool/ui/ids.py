"""All Dash component IDs (architecture §9.5). Never write an ID literal elsewhere."""

from __future__ import annotations

from dataclasses import dataclass

# --- shell -----------------------------------------------------------------------
URL = "url"
NEW_TASK_BUTTON = "new-task-button"
SIDEBAR = "sidebar"

# --- global stores ---------------------------------------------------------------
FILTER = "filter-store"  # serialized Filter, storage="session"
DATA_VERSION = "data-version"  # int, incremented after every successful write
LOOKUPS = "lookups-store"  # labels, milestones, tasks for dropdowns
PENDING_ACTION = "pending-action"  # action waiting for confirmation (R-05, R-11)
SELECTED_TASK = "selected-task"  # task id shown in the detail panel
DETAIL_STATE = "detail-state"  # {"task_id", "at_risk", "archived"} of the shown task

# --- feedback --------------------------------------------------------------------
TOAST = "toast"
CONFIRM_MODAL = "confirm-modal"
CONFIRM_TEXT = "confirm-text"
CONFIRM_YES = "confirm-yes"
CONFIRM_NO = "confirm-no"

# --- filter panel ----------------------------------------------------------------
FILTER_LABELS = "filter-labels"
FILTER_LABEL_MODE = "filter-label-mode"
FILTER_PRIORITIES = "filter-priorities"
FILTER_STATUSES = "filter-statuses"
FILTER_AT_RISK = "filter-at-risk"
FILTER_MILESTONES = "filter-milestones"
FILTER_DATE_FROM = "filter-date-from"
FILTER_DATE_TO = "filter-date-to"
FILTER_ARCHIVED = "filter-archived"
FILTER_RESET = "filter-reset"


# --- task forms ------------------------------------------------------------------
@dataclass(frozen=True)
class TaskFormIds:
    """IDs of one task form; ``prefix`` keeps the create and edit forms apart."""

    prefix: str

    def __getattr__(self, name: str) -> str:  # e.g. NEW_FORM.title -> "new-task-title"
        if name not in TASK_FORM_FIELDS:
            raise AttributeError(name)
        return f"{self.prefix}-{name.replace('_', '-')}"


TASK_FORM_FIELDS = (
    "title", "description", "start", "end", "estimated", "remaining", "status",
    "status_reason", "priority", "labels", "milestone", "predecessors", "reason",
)  # fmt: skip

NEW_FORM = TaskFormIds("new-task")
EDIT_FORM = TaskFormIds("detail")

NEW_TASK_MODAL = "new-task-modal"
NEW_TASK_SAVE = "new-task-save"
NEW_TASK_CANCEL = "new-task-cancel"

# --- task detail -----------------------------------------------------------------
DETAIL = "task-detail"
DETAIL_BADGES = "detail-badges"
DETAIL_WARNINGS = "detail-warnings"
DETAIL_SAVE = "detail-save"
DETAIL_REVIEWED = "detail-reviewed"
DETAIL_ARCHIVE = "detail-archive"
DETAIL_RISK_TEXT = "detail-risk-text"
DETAIL_RISK_REASON = "detail-risk-reason"
DETAIL_RISK_BUTTON = "detail-risk-button"
DETAIL_DEPS_SAVE = "detail-deps-save"
DETAIL_SUCCESSORS = "detail-successors"
DETAIL_COMMENT_TEXT = "detail-comment-text"
DETAIL_COMMENT_ADD = "detail-comment-add"
DETAIL_COMMENTS = "detail-comments"
DETAIL_HISTORY = "detail-history"

# --- tasks page ------------------------------------------------------------------
TASK_GRID = "task-grid"
TASKS_FILTER_TEXT = "tasks-filter-text"
TASKS_COUNT = "tasks-count"
BULK_REVIEWED = "bulk-reviewed"
BULK_REBASELINE = "bulk-rebaseline"
BULK_ARCHIVE = "bulk-archive"
REBASELINE_MODAL = "rebaseline-modal"
REBASELINE_REASON = "rebaseline-reason"
REBASELINE_OK = "rebaseline-ok"
REBASELINE_CANCEL = "rebaseline-cancel"
