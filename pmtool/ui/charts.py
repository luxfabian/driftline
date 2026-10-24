"""Pure figure builders: data in -> ``go.Figure`` out (architecture P6, §9.4).

No data loading or calculation happens here. Every builder puts the active
filter text in the chart subtitle [FUN-10].

Colors (``ui/theme.py``, Wada No. 309) follow the job they do: task status is
a state -> quiet tints for planned/done, Vandar Poel's Blue for work in
progress, Apricot for blocked (also hatched), Brick Red reserved for overdue;
priority is ordered -> one blue ramp, darkest = Critical; labels and
milestones are identities -> categorical slots in fixed order, keyed by the
entity so a filter never repaints the others.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

from pmtool.calc.schedule import milestone_variance, task_variance
from pmtool.domain.enums import Priority, TaskStatus
from pmtool.domain.models import Milestone, Task
from pmtool.ui import theme

# --- palette ------------------------------------------------------------------------

SURFACE = theme.SURFACE
INK = theme.INK
INK_2 = theme.INK_2
MUTED = theme.MUTED
GRID = theme.HAIRLINE
AXIS = theme.AXIS
FONT = theme.FONT_FAMILY

CATEGORICAL = theme.CATEGORICAL
OTHER = "Other"
OTHER_COLOR = "#a9a6b3"

STATUS_GOOD, STATUS_WARNING, STATUS_CRITICAL = theme.GOOD, theme.WARNING, theme.CRITICAL
TASK_STATUS_COLORS = {
    TaskStatus.PLANNED: "#8cb8d2",
    TaskStatus.IN_PROGRESS: "#006692",
    TaskStatus.BLOCKED: "#de6e28",
    TaskStatus.DONE: "#b9b6c4",
}
PRIORITY_COLORS = dict(zip([p.label for p in Priority], theme.PRIORITY_RAMP, strict=True))
TODAY_COLOR = theme.APRICOT_ORANGE
DEMAND_COLOR = "#006692"
SHORTFALL_COLOR = "#de6e28"
CAPACITY_COLOR = theme.VIOLET_BLUE
LINK_COLOR = theme.VIOLET_BLUE

DAY_MS = 24 * 60 * 60 * 1000
ROW_PX = 30
MULTI_LABEL_NOTE = "tasks with several labels appear in each"


def categorical_colors(keys: Iterable) -> dict:
    """Fixed-order slots for entities in a stable order (e.g. all ids sorted).

    Up to seven entities get one slot each; with more, the first six keep a
    slot and the rest share the "Other" gray (never a generated extra hue).
    """
    ordered = list(dict.fromkeys(keys))
    slots = CATEGORICAL if len(ordered) <= len(CATEGORICAL) else CATEGORICAL[:-1]
    return {k: (slots[i] if i < len(slots) else OTHER_COLOR) for i, k in enumerate(ordered)}


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


# --- shared layout ----------------------------------------------------------------------


def _layout(fig: go.Figure, title: str, filter_text: str, height: int = 400) -> go.Figure:
    fig.update_layout(
        title={
            "text": title,
            "subtitle": {"text": f"Filter: {filter_text}", "font": {"color": MUTED, "size": 12}},
            "x": 0.01,
            "xanchor": "left",
            "font": {"size": 15, "color": INK, "weight": 500},
        },
        font={"family": FONT, "color": INK_2, "size": 12},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        height=height,
        margin={"l": 12, "r": 24, "t": 84, "b": 36},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 12, "color": INK_2},
            "bgcolor": "rgba(0,0,0,0)",
        },
        hoverlabel={
            "bgcolor": SURFACE,
            "bordercolor": GRID,
            "font": {"family": FONT, "color": INK, "size": 12},
        },
    )
    axis = {
        "gridcolor": GRID,
        "gridwidth": 1,
        "linecolor": AXIS,
        "zeroline": False,
        "tickfont": {"color": MUTED},
        "title": {"font": {"color": INK_2, "size": 12}},
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def _today_line(fig: go.Figure, today: date, label_at: str = "top") -> None:
    """Vertical today line; the label sits inside the plot at the top or bottom."""
    fig.add_shape(
        type="line",
        x0=today,
        x1=today,
        y0=0,
        y1=1,
        yref="paper",
        line={"color": TODAY_COLOR, "width": 1.5},
        layer="below",
    )
    fig.add_annotation(  # inside the plot, so it never collides with the legend
        x=today,
        y=1 if label_at == "top" else 0,
        yref="paper",
        text="Today",
        showarrow=False,
        xanchor="left",
        yanchor="top" if label_at == "top" else "bottom",
        xshift=4,
        bgcolor=SURFACE,
        font={"color": INK_2, "size": 11},
    )


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def empty_figure(title: str, filter_text: str, message: str) -> go.Figure:
    fig = _layout(go.Figure(), title, filter_text, height=240)
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


# --- Gantt [FUN-11, FUN-06/07] ---------------------------------------------------------------


def build_gantt(
    tasks: Sequence[Task],
    milestones: Sequence[Milestone],
    today: date,
    filter_text: str,
    risk_ids: Iterable[int],
    overdue_ids: Iterable[int] = (),
    dependencies: Iterable[tuple[int, int, bool]] = (),
) -> go.Figure:
    """Forecast bars by status inside baseline outlines; milestones as diamonds.

    ``dependencies``: (predecessor id, successor id, late) to draw as connectors
    from the predecessor's end to the successor's start; ``late`` = the
    successor starts before the predecessor ends (FUN-07). Only links between
    shown tasks are drawn. Task bars carry ``customdata[0]`` = task id.
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
                width=0.7,
                marker={"color": "rgba(0,0,0,0)", "line": {"color": AXIS, "width": 1.2}},
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
                    "cornerradius": 3,
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
    _add_dependencies(fig, ordered, row, dependencies)
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
                    "size": 11,
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
                name="Overdue (outline)",
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
                marker={
                    "symbol": "diamond-open",
                    "size": 13,
                    "color": INK_2,
                    "line": {"width": 1.5},
                },
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
                    "color": theme.VIOLET_BLUE,
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


def _add_dependencies(
    fig: go.Figure,
    tasks: Sequence[Task],
    row: Mapping[int, str],
    dependencies: Iterable[tuple[int, int, bool]],
) -> None:
    """Elbow connectors: down from the predecessor's end, across to the successor's start."""
    by_id = {t.id: t for t in tasks}
    groups: dict[bool, list[tuple[Task, Task]]] = {False: [], True: []}
    for pred_id, succ_id, late in dependencies:
        if pred_id in by_id and succ_id in by_id:
            groups[bool(late)].append((by_id[pred_id], by_id[succ_id]))
    for late, links in groups.items():
        if not links:
            continue
        color = STATUS_CRITICAL if late else LINK_COLOR
        xs: list = []
        ys: list = []
        ends_x, ends_y, symbols, hover = [], [], [], []
        for pred, succ in links:
            x_from = _bar_end(pred.forecast_end)
            x_to = succ.forecast_start.isoformat()
            xs += [x_from, x_from, x_to, None]
            ys += [row[pred.id], row[succ.id], row[succ.id], None]
            ends_x.append(x_to)
            ends_y.append(row[succ.id])
            symbols.append("triangle-left" if late else "triangle-right")
            hover.append(f"#{pred.id} → #{succ.id}" + (" · starts before it ends" if late else ""))
        name = "Late dependency" if late else "Dependency"
        fig.add_trace(
            go.Scatter(
                name=name,
                x=xs,
                y=ys,
                mode="lines",
                legendgroup=name,
                line={"color": color, "width": 1.3},
                opacity=0.85,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                name=name,
                x=ends_x,
                y=ends_y,
                mode="markers",
                legendgroup=name,
                showlegend=False,
                text=hover,
                hovertemplate="%{text}<extra></extra>",
                marker={"symbol": symbols, "size": 8, "color": color},
            )
        )


def _bar_end(day: date) -> str:
    """x of a bar's right edge: the end day is inclusive."""
    return (day + timedelta(days=1)).isoformat()


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
    _today_line(fig, today, label_at="bottom")
    fig.update_xaxes(type="date", range=[lo, hi], title="Reporting date", tickformat="%d %b")
    fig.update_yaxes(type="date", range=[lo, hi], title="Forecast date", tickformat="%d %b")
    return fig


# --- workload [WL-03, WL-06] ---------------------------------------------------------------


def build_cumulative(curves: pd.DataFrame, filter_text: str) -> go.Figure:
    """Cumulative demand per day as bars; the part above capacity is shown in apricot.

    Bars soften the stepwise look of a cumulative line; the capacity is a
    smooth line on top, so the shortfall reads as the apricot cap of each bar.
    """
    title = "Cumulative demand vs. plannable capacity"
    if curves.empty:
        return empty_figure(title, filter_text, "No days in the horizon.")
    x = [d.isoformat() for d in curves["date"]]
    covered = curves[["demand_h", "capacity_h"]].min(axis=1)
    custom = list(zip(curves["demand_h"], curves["capacity_h"], curves["shortfall_h"], strict=True))
    hover = (
        "Demand %{customdata[0]:.1f} h<br>Capacity %{customdata[1]:.1f} h"
        "<br>Shortfall %{customdata[2]:.1f} h<extra></extra>"
    )
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Demand within capacity",
            x=x,
            y=covered,
            customdata=custom,
            marker={"color": _rgba(DEMAND_COLOR, 0.85), "cornerradius": 2},
            hovertemplate=hover,
        )
    )
    fig.add_trace(
        go.Bar(
            name="Demand above capacity",
            x=x,
            y=curves["shortfall_h"],
            customdata=custom,
            marker={"color": SHORTFALL_COLOR, "cornerradius": 2},
            hovertemplate=hover,
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Capacity",
            x=x,
            y=curves["capacity_h"],
            mode="lines",
            line={"color": CAPACITY_COLOR, "width": 2, "shape": "spline", "smoothing": 0.6},
            hoverinfo="skip",
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
            ay=-28,
            font={"color": INK, "size": 11},
        )
    _layout(fig, title, filter_text)
    fig.update_layout(barmode="stack", bargap=0.25, hovermode="x unified")
    fig.update_xaxes(type="date", tickformat="%d %b", showgrid=False)
    fig.update_yaxes(title="Hours (cumulative)", rangemode="tozero")
    return fig


def build_weekly_load(
    weekly: pd.DataFrame,
    capacity: pd.DataFrame,
    group_label: str,
    filter_text: str,
    colors: Mapping[str, str] | None = None,
) -> go.Figure:
    """Stacked lines (areas) of weekly hours per group, with the weekly capacity line.

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
    weeks = [week_label(w) for w in capacity["week_start"]]
    fig = go.Figure()
    for group in dict.fromkeys(weekly["group"]) if len(weekly) else []:
        part = weekly[weekly["group"] == group]
        hours = dict(zip(part["week_start"].map(week_label), part["hours"], strict=True))
        color = colors.get(group, OTHER_COLOR)
        fig.add_trace(
            go.Scatter(
                name=group,
                x=weeks,
                y=[hours.get(w, 0.0) for w in weeks],  # every week, so the stack is continuous
                mode="lines",
                stackgroup="load",
                # solid bands separated by a thin paper line (the 2px surface gap)
                line={"color": SURFACE, "width": 1.5, "shape": "spline", "smoothing": 0.45},
                fillcolor=color,
                hovertemplate=f"{group}: %{{y:.1f}} h<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            name="Capacity",
            x=weeks,
            y=capacity["capacity_h"],
            mode="lines+markers",
            line={"color": CAPACITY_COLOR, "width": 2},
            marker={"size": 6, "color": CAPACITY_COLOR},
            hovertemplate="Capacity %{y:.1f} h<extra></extra>",
        )
    )
    _layout(fig, title, subtitle)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=weeks, showgrid=False)
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
