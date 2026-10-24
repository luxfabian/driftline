"""All Dash component IDs (architecture §9.5). Never write an ID literal elsewhere."""

from __future__ import annotations

from dataclasses import dataclass

# --- shell -----------------------------------------------------------------------
URL = "url"
NEW_TASK_BUTTON = "new-task-button"

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

# --- filter bar (shown on the pages that filter tasks) -----------------------------------
FILTER_CTL = "filter-ctl"  # pattern: {"type": FILTER_CTL, "field": <store key>}
FILTER_BAR = "filter-bar"  # pattern: {"type": FILTER_BAR, "page": <page name>}
FILTER_MORE = "filter-more"
FILTER_MORE_PANEL = "filter-more-panel"
FILTER_RESET = "filter-reset"


def filter_ctl(field: str) -> dict[str, str]:
    """One filter control; ``field`` is its key in the FILTER store (state.filter_to_store)."""
    return {"type": FILTER_CTL, "field": field}


def filter_bar(page: str) -> dict[str, str]:
    return {"type": FILTER_BAR, "page": page}


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

# --- links that open the task detail (pattern-matching ID) ----------------------------
OPEN_TASK = "open-task"


def open_task(task_id: int, key: str) -> dict[str, object]:
    """``key`` keeps IDs unique when the same task is linked more than once."""
    return {"type": OPEN_TASK, "index": task_id, "key": key}


# --- dashboard ---------------------------------------------------------------------
DASH_FILTER_TEXT = "dash-filter-text"
DASH_KPIS = "dash-kpis"
DASH_DELAYED = "dash-delayed"
DASH_MS_WARNINGS = "dash-ms-warnings"
DASH_DEP_WARNINGS = "dash-dep-warnings"

# --- timeline ----------------------------------------------------------------------
TIMELINE_GRAPH = "timeline-graph"
TIMELINE_MILESTONES = "timeline-show-milestones"
TIMELINE_DEPENDENCIES = "timeline-show-dependencies"

# --- milestones page ---------------------------------------------------------------
MS_GRID = "ms-grid"
MS_FILTER_TEXT = "ms-filter-text"
MS_ARCHIVED = "ms-show-archived"
MS_NEW = "ms-new"
MS_EDIT = "ms-edit"
MS_ACHIEVE = "ms-achieve"
MS_REOPEN = "ms-reopen"
MS_REBASELINE = "ms-rebaseline"
MS_ARCHIVE = "ms-archive"
MS_DIALOG = "ms-dialog"
MS_DIALOG_TITLE = "ms-dialog-title"
MS_DIALOG_MODE = "ms-dialog-mode"  # store: {"mode": ..., "ids": [...]}
MS_ROW_NAME = "ms-row-name"
MS_ROW_DESCRIPTION = "ms-row-description"
MS_ROW_DATE = "ms-row-date"
MS_ROW_REASON = "ms-row-reason"
MS_DATE_LABEL = "ms-date-label"
MS_NAME = "ms-name"
MS_DESCRIPTION = "ms-description"
MS_DATE = "ms-date"
MS_REASON = "ms-reason"
MS_SAVE = "ms-save"
MS_CANCEL = "ms-cancel"
MTA_SELECT = "mta-select"
MTA_GRAPH = "mta-graph"

# --- workload ----------------------------------------------------------------------
WL_HORIZON = "wl-horizon"
WL_GROUP_BY = "wl-group-by"
WL_RATIO = "wl-ratio"
WL_CUMULATIVE = "wl-cumulative"
WL_WEEKLY = "wl-weekly"

# --- settings page -----------------------------------------------------------------
SET_WEEKLY_HOURS = "set-weekly-hours"
SET_WEEKDAYS = "set-weekdays"
SET_PLANNABLE_PCT = "set-plannable-pct"
SET_HORIZON = "set-horizon"
SET_GREEN_PCT = "set-green-pct"
SET_AMBER_PCT = "set-amber-pct"
SET_STALE_DAYS = "set-stale-days"
SET_BACKUP_KEEP = "set-backup-keep"
SET_TOP_N = "set-top-n"
SET_DAILY_NOTE = "set-daily-note"
SET_SAVE = "set-save"
ABS_START = "abs-start"
ABS_END = "abs-end"
ABS_NOTE = "abs-note"
ABS_ADD = "abs-add"
ABS_LIST = "abs-list"
HOL_DATE = "hol-date"
HOL_NAME = "hol-name"
HOL_ADD = "hol-add"
HOL_LIST = "hol-list"
EXPORT_EXCEL = "export-excel"
EXPORT_CSV = "export-csv"
EXPORT_DOWNLOAD = "export-download"
IMPORT_UPLOAD = "import-upload"
IMPORT_TEMPLATE = "import-template"
IMPORT_RESULT = "import-result"
ARCHIVED_TASKS = "archived-tasks"
ARCHIVED_MILESTONES = "archived-milestones"
ROW_ACTION = "row-action"


def row_action(action: str, index: int | str) -> dict[str, object]:
    """Buttons in settings lists, e.g. row_action("remove_absence", 3)."""
    return {"type": ROW_ACTION, "action": action, "index": index}
