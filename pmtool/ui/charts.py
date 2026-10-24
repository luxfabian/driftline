"""Pure figure builders: data in -> ``go.Figure`` out (architecture P6, §9.4).

No data loading or calculation happens here. Every builder puts the active
filter text in the chart subtitle [FUN-10].

Colors follow the job they do (reference palette of the dataviz method):
task status is a state -> reserved status colors; priority is ordered -> one
blue ramp, darkest = Critical; labels and milestones are identities -> the
categorical slots in fixed order, keyed by entity so a filter never repaints
the survivors. Red (blocked) vs. green (done) is not CVD-safe on its own, so
blocked bars also carry a 45° hatch and every series has a legend entry.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

from pmtool.calc.schedule import milestone_variance, task_variance
from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.models import Milestone, Task

# --- palette ------------------------------------------------------------------------

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

CATEGORICAL = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
)
OTHER = "Other"
OTHER_COLOR = MUTED

STATUS_GOOD, STATUS_WARNING, STATUS_CRITICAL = "#0ca30c", "#fab219", "#d03b3b"
TASK_STATUS_COLORS = {
    TaskStatus.PLANNED: MUTED,
    TaskStatus.IN_PROGRESS: CATEGORICAL[0],
    TaskStatus.BLOCKED: STATUS_CRITICAL,
    TaskStatus.DONE: STATUS_GOOD,
}
# Ordinal ramp (validated with --ordinal): Critical darkest.
PRIORITY_COLORS = {
    Priority.CRITICAL.label: "#104281",
    Priority.HIGH.label: "#256abf",
    Priority.MEDIUM.label: "#5598e7",
    Priority.LOW.label: "#86b6ef",
}
TODAY_COLOR = CATEGORICAL[1]
DEMAND_COLOR = CATEGORICAL[0]
CAPACITY_COLOR = INK_2

DAY_MS = 24 * 60 * 60 * 1000
ROW_PX = 30
MULTI_LABEL_NOTE = "tasks with several labels appear in each"


def categorical_colors(keys: Iterable) -> dict:
    """Fixed-order slots for entities in a stable order (e.g. all ids sorted).

    Up to eight entities get one slot each; with more, the first seven keep a
    slot and the rest share the "Other" gray (never a generated ninth hue).
    """
    ordered = list(dict.fromkeys(keys))
    slots = CATEGORICAL if len(ordered) <= len(CATEGORICAL) else CATEGORICAL[:-1]
    return {k: (slots[i] if i < len(slots) else OTHER_COLOR) for i, k in enumerate(ordered)}


# --- shared layout ----------------------------------------------------------------------


def _layout(fig: go.Figure, title: str, filter_text: str, height: int = 420) -> go.Figure:
    fig.update_layout(
        title={
            "text": title,
            "subtitle": {"text": f"Filter: {filter_text}"},
            "x": 0,
            "xanchor": "left",
            "font": {"size": 16, "color": INK},
        },
        font={"family": FONT, "color": INK_2, "size": 12},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        height=height,
        margin={"l": 10, "r": 20, "t": 80, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1},
        hoverlabel={"bgcolor": "white", "font": {"family": FONT, "color": INK}},
    )
    axis = {
        "gridcolor": GRID,
        "gridwidth": 1,
        "linecolor": AXIS,
        "zeroline": False,
        "tickfont": {"color": MUTED},
        "title": {"font": {"color": INK_2}},
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def _today_line(fig: go.Figure, today: date) -> None:
    fig.add_shape(
        type="line",
        x0=today,
        x1=today,
        y0=0,
        y1=1,
        yref="paper",
        line={"color": TODAY_COLOR, "width": 2},
    )
    fig.add_annotation(  # inside the plot, so it never collides with the legend
        x=today,
        y=1,
        yref="paper",
        text="Today",
        showarrow=False,
        xanchor="left",
        yanchor="top",
        xshift=4,
        bgcolor=SURFACE,
        font={"color": INK_2, "size": 11},
    )


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def empty_figure(title: str, filter_text: str, message: str) -> go.Figure:
    fig = _layout(go.Figure(), title, filter_text, height=260)
    fig.add_annotation(
        text=message,
        showarrow=False,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        font={"color": MUTED, "size": 14},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# --- Gantt [FUN-11] ---------------------------------------------------------------------


def build_gantt(
    tasks: Sequence[Task],
    milestones: Sequence[Milestone],
    today: date,
    filter_text: str,
    risk_ids: Iterable[int],
    overdue_ids: Iterable[int] = (),
) -> go.Figure:
    """Forecast bars by status inside baseline outlines; milestones as diamonds.

    Task bars carry ``customdata[0]`` = task id (for click-to-open).
    """
    title = "Timeline"
    if not tasks and not milestones:
        return empty_figure(title, filter_text, "No tasks or milestones match the filter.")
    risk, overdue = set(risk_ids), set(overdue_ids)
    ordered = sorted(tasks, key=lambda t: (t.forecast_start, t.forecast_end, t.id))
    ms_rows = sorted(milestones, key=lambda m: (m.forecast_date, m.id))
    row = {t.id: f"#{t.id} {_short(t.title)}" for t in ordered}
    ms_row = {m.id: f"◆ {_short(m.name)}" for m in ms_rows}
    categories = [ms_row[m.id] for m in ms_rows] + [row[t.id] for t in ordered]

    fig = go.Figure()
    if ordered:
        fig.add_trace(
            go.Bar(
                name="Baseline",
                orientation="h",
                y=[row[t.id] for t in ordered],
                base=[t.baseline_start.isoformat() for t in ordered],
                x=[_span_ms(t.baseline_start, t.baseline_end) for t in ordered],
                width=0.72,
                marker={"color": "rgba(0,0,0,0)", "line": {"color": INK_2, "width": 1}},
                hoverinfo="skip",
            )
        )
    for status in TaskStatus:
        group = [t for t in ordered if t.status is status]
        if not group:
            continue
        fig.add_trace(
            go.Bar(
                name=status.label,
                orientation="h",
                y=[row[t.id] for t in group],
                base=[t.forecast_start.isoformat() for t in group],
                x=[_span_ms(t.forecast_start, t.forecast_end) for t in group],
                width=0.42,
                marker={
                    "color": TASK_STATUS_COLORS[status],
                    "line": {
                        "color": [STATUS_CRITICAL if t.id in overdue else SURFACE for t in group],
                        "width": [2.5 if t.id in overdue else 0 for t in group],
                    },
                    "pattern": {
                        "shape": "/" if status is TaskStatus.BLOCKED else "",
                        "fgcolor": SURFACE,
                        "size": 6,
                    },
                },
                customdata=[_task_hover(t, t.id in overdue, t.id in risk) for t in group],
                hovertemplate=(
                    "<b>%{customdata[1]}</b><br>Forecast %{customdata[2]} – %{customdata[3]}"
                    "<br>Baseline %{customdata[4]} – %{customdata[5]}"
                    "<br>End variance %{customdata[6]} d · Remaining %{customdata[7]} h"
                    "<br>%{customdata[8]}<extra>" + status.label + "</extra>"
                ),
            )
        )
    at_risk = [t for t in ordered if t.id in risk]
    if at_risk:
        fig.add_trace(
            go.Scatter(
                name="⚠ At risk",
                mode="markers",
                y=[row[t.id] for t in at_risk],
                x=[(t.forecast_end + timedelta(days=1, hours=12)).isoformat() for t in at_risk],
                marker={
                    "symbol": "triangle-up",
                    "size": 12,
                    "color": STATUS_WARNING,
                    "line": {"color": INK, "width": 1},
                },
                customdata=[[t.id] for t in at_risk],
                hovertemplate="⚠ At risk<extra></extra>",
            )
        )
    if overdue & {t.id for t in ordered}:
        fig.add_trace(
            go.Scatter(
                name="Overdue (red outline)",
                x=[None],
                y=[None],
                mode="markers",
                marker={
                    "symbol": "square-open",
                    "size": 12,
                    "color": STATUS_CRITICAL,
                    "line": {"width": 2.5},
                },
            )
        )
    if ms_rows:
        fig.add_trace(
            go.Scatter(
                name="Milestone baseline",
                mode="markers",
                y=[ms_row[m.id] for m in ms_rows],
                x=[m.baseline_date.isoformat() for m in ms_rows],
                marker={"symbol": "diamond-open", "size": 13, "color": INK_2, "line": {"width": 2}},
                hovertemplate="Baseline %{x|%Y-%m-%d}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                name="Milestone forecast",
                mode="markers",
                y=[ms_row[m.id] for m in ms_rows],
                x=[m.forecast_date.isoformat() for m in ms_rows],
                marker={
                    "symbol": "diamond",
                    "size": 13,
                    "color": INK,
                    "line": {"color": SURFACE, "width": 2},
                },
                customdata=[
                    [-m.id, m.name, m.status.label, milestone_variance(m)] for m in ms_rows
                ],
                hovertemplate="<b>%{customdata[1]}</b> (%{customdata[2]})<br>"
                "Forecast %{x|%Y-%m-%d} · variance %{customdata[3]} d"
                "<extra></extra>",
            )
        )

    _layout(fig, title, filter_text, height=max(320, ROW_PX * len(categories) + 150))
    _today_line(fig, today)
    fig.update_layout(barmode="overlay", bargap=0.2)
    fig.update_xaxes(type="date", tickformat="%d %b", showgrid=True)
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=categories,
        autorange="reversed",
        showgrid=False,
        tickfont={"color": INK_2},
    )
    return fig


def _span_ms(start: date, end: date) -> int:
    """Bar length for an inclusive date range (end day is part of the bar)."""
    return ((end - start).days + 1) * DAY_MS


def _task_hover(t: Task, overdue: bool, at_risk: bool) -> list:
    notes = [n for n, on in (("Overdue", overdue), ("⚠ At risk", at_risk)) if on]
    return [
        t.id,
        f"#{t.id} {t.title}",
        t.forecast_start.isoformat(),
        t.forecast_end.isoformat(),
        t.baseline_start.isoformat(),
        t.baseline_end.isoformat(),
        f"{task_variance(t).end_d:+d}",
        f"{t.remaining_effort_h:g}",
        " · ".join(notes),
    ]


# --- milestone trend analysis [SCH-04] ----------------------------------------------------


def build_mta(
    series: Mapping[str, list[tuple[date, date]]],
    today: date,
    filter_text: str,
    colors: Mapping[str, str] | None = None,
) -> go.Figure:
    """One staircase line per milestone plus the diagonal (reporting = forecast).

    ``colors`` maps series name -> color, chosen by the caller per milestone id
    so a milestone keeps its color when others are hidden.
    """
    title = "Milestone trend analysis"
    series = {name: pts for name, pts in series.items() if pts}
    if not series:
        return empty_figure(title, filter_text, "No milestone history to show.")
    palette = colors or categorical_colors(series)
    all_dates = [d for pts in series.values() for p in pts for d in p] + [today]
    lo, hi = min(all_dates) - timedelta(days=3), max(all_dates) + timedelta(days=3)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            name="Reporting date = forecast",
            x=[lo, hi],
            y=[lo, hi],
            mode="lines",
            line={"color": AXIS, "width": 1},
            hoverinfo="skip",
        )
    )
    for name, pts in series.items():
        color = palette.get(name, OTHER_COLOR)
        fig.add_trace(
            go.Scatter(
                name=name,
                x=[p[0] for p in pts],
                y=[p[1] for p in pts],
                mode="lines+markers",
                line={"color": color, "width": 2},
                marker={"size": 8, "color": color, "line": {"color": SURFACE, "width": 2}},
                hovertemplate=f"<b>{name}</b><br>Reported %{{x|%Y-%m-%d}}"
                "<br>Forecast %{y|%Y-%m-%d}<extra></extra>",
            )
        )
    if len(series) <= 4:  # direct end labels supplement the legend
        for name, pts in series.items():
            fig.add_annotation(
                x=pts[-1][0],
                y=pts[-1][1],
                text=name,
                showarrow=False,
                xanchor="left",
                xshift=8,
                font={"color": INK_2, "size": 11},
            )

    _layout(fig, title, filter_text, height=460)
    _today_line(fig, today)
    fig.update_xaxes(type="date", range=[lo, hi], title="Reporting date", tickformat="%d %b")
    fig.update_yaxes(type="date", range=[lo, hi], title="Forecast date", tickformat="%d %b")
    return fig


# --- workload [WL-03, WL-06] ---------------------------------------------------------------


def build_cumulative(curves: pd.DataFrame, filter_text: str) -> go.Figure:
    """Cumulative demand vs. capacity; the gap where demand is higher is shaded."""
    title = "Cumulative demand vs. plannable capacity"
    if curves.empty:
        return empty_figure(title, filter_text, "No days in the horizon.")
    x = [d.isoformat() for d in curves["date"]]
    upper = curves[["demand_h", "capacity_h"]].max(axis=1)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            name="Capacity",
            x=x,
            y=curves["capacity_h"],
            mode="lines",
            line={"color": CAPACITY_COLOR, "width": 2, "shape": "hv"},
            hovertemplate="Capacity %{y:.1f} h<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Shortfall",
            x=x,
            y=upper,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(208,59,59,0.18)",
            line={"width": 0, "shape": "hv"},
            customdata=curves["shortfall_h"],
            hovertemplate="Shortfall %{customdata:.1f} h<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Demand",
            x=x,
            y=curves["demand_h"],
            mode="lines",
            line={"color": DEMAND_COLOR, "width": 2, "shape": "hv"},
            hovertemplate="Demand %{y:.1f} h<extra></extra>",
        )
    )
    worst = curves.loc[curves["shortfall_h"].idxmax()]
    if worst["shortfall_h"] > 0:
        fig.add_annotation(
            x=worst["date"].isoformat(),
            y=worst["demand_h"],
            text=f"Max shortfall {worst['shortfall_h']:.1f} h",
            showarrow=True,
            arrowcolor=AXIS,
            ax=0,
            ay=-30,
            font={"color": INK, "size": 11},
        )
    _layout(fig, title, filter_text)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(type="date", tickformat="%d %b")
    fig.update_yaxes(title="Hours (cumulative)", rangemode="tozero")
    return fig


def build_weekly_load(
    weekly: pd.DataFrame,
    capacity: pd.DataFrame,
    group_label: str,
    filter_text: str,
    colors: Mapping[str, str] | None = None,
) -> go.Figure:
    """Stacked weekly hours per group with the weekly capacity as a marker per week.

    ``group_label`` is "Priority" or "Label"; for labels the subtitle notes that
    a task with several labels counts in each. ``colors`` maps group -> color.
    """
    title = f"Weekly load by {group_label.lower()}"
    subtitle = filter_text
    if group_label.lower() == "label":
        subtitle += f" · {MULTI_LABEL_NOTE}"
    if capacity.empty:
        return empty_figure(title, subtitle, "No weeks in the horizon.")
    if colors is None:
        colors = (
            PRIORITY_COLORS
            if group_label.lower() == "priority"
            else categorical_colors(weekly["group"].unique() if len(weekly) else [])
        )
    fig = go.Figure()
    for group in dict.fromkeys(weekly["group"]) if len(weekly) else []:
        part = weekly[weekly["group"] == group]
        fig.add_trace(
            go.Bar(
                name=group,
                x=[week_label(w) for w in part["week_start"]],
                y=part["hours"],
                marker={
                    "color": colors.get(group, OTHER_COLOR),
                    "line": {"color": SURFACE, "width": 2},
                },
                hovertemplate=f"<b>{group}</b><br>%{{x}}: %{{y:.1f}} h<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            name="Capacity",
            x=[week_label(w) for w in capacity["week_start"]],
            y=capacity["capacity_h"],
            mode="markers",
            marker={
                "symbol": "line-ew",
                "size": 60,
                "line": {"color": CAPACITY_COLOR, "width": 2.5},
            },
            hovertemplate="Capacity %{y:.1f} h<extra></extra>",
        )
    )
    _layout(fig, title, subtitle)
    fig.update_layout(barmode="stack", bargap=0.55)
    weeks = [week_label(w) for w in capacity["week_start"]]
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=weeks)
    fig.update_yaxes(title="Hours per week", rangemode="tozero")
    return fig


def week_label(monday: date) -> str:
    return f"Wk of {monday:%d %b}"


def fold_groups(weekly: pd.DataFrame, keep: Iterable[str]) -> pd.DataFrame:
    """Merge groups not in ``keep`` into "Other" (for more labels than color slots)."""
    keep = set(keep)
    if weekly.empty or set(weekly["group"]) <= keep:
        return weekly
    folded = weekly.assign(group=weekly["group"].where(weekly["group"].isin(keep), OTHER))
    return folded.groupby(["week_start", "group"], as_index=False, sort=False).agg(
        hours=("hours", "sum"), capacity_h=("capacity_h", "first")
    )
