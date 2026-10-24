from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

METRICS = {
    "mean": "ממוצע",
    "delta": "פער מהממוצע הענפי",
    "high": "% ציוני 8–10",
    "low": "% ציוני 1–5",
    "std": "סטיית תקן",
    "n": "מספר משיבים",
}


def branch_stats(numeric: pd.DataFrame) -> pd.DataFrame:
    grouped = numeric.groupby("question_id")["score"]
    result = grouped.agg(branch_mean="mean", branch_n="count").reset_index()
    return result


def _group_columns(view: str) -> list[str]:
    if view == "general":
        return []
    if view == "team":
        return ["team"]
    if view == "tenure":
        return ["tenure"]
    if view == "team_tenure":
        return ["team", "tenure"]
    raise ValueError(f"Unknown view: {view}")


def compute_matrix(
    numeric: pd.DataFrame,
    catalog: pd.DataFrame,
    view: str,
    metric: str,
    selected_team: str | None = None,
    domain: str | None = None,
    min_group_size: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = numeric.copy()
    if domain and domain != "all":
        data = data[data["domain"] == domain]
    if view == "team_tenure" and selected_team:
        data = data[data["team"] == selected_team]

    group_cols = _group_columns(view)
    branch = branch_stats(numeric)
    if group_cols:
        grouped = data.groupby(group_cols + ["question_id"])["score"]
    else:
        data = data.assign(_all="כלל הענף")
        group_cols = ["_all"]
        grouped = data.groupby(group_cols + ["question_id"])["score"]

    stats = grouped.agg(
        mean="mean",
        n="count",
        std=lambda s: float(s.std(ddof=0)) if len(s) else np.nan,
        median="median",
        p25=lambda s: float(s.quantile(0.25)),
        p75=lambda s: float(s.quantile(0.75)),
        high=lambda s: float((s >= 8).mean()),
        low=lambda s: float((s <= 5).mean()),
    ).reset_index()
    stats = stats.merge(branch, on="question_id", how="left")
    stats["delta"] = stats["mean"] - stats["branch_mean"]
    stats["group"] = stats[group_cols].astype(str).agg(" · ".join, axis=1)
    stats["display_allowed"] = stats["n"] >= min_group_size
    stats["value"] = stats[metric]
    stats.loc[~stats["display_allowed"], "value"] = np.nan

    question_order = catalog["question_id"].tolist()
    group_order = stats["group"].drop_duplicates().tolist()
    matrix = stats.pivot(index="group", columns="question_id", values="value")
    matrix = matrix.reindex(index=group_order, columns=[q for q in question_order if q in matrix.columns])
    return matrix, stats


def score_distribution_counts(scores: Iterable[float], min_score: int = 1, max_score: int = 10) -> dict[int, int]:
    values = pd.to_numeric(pd.Series(list(scores)), errors="coerce").dropna().astype(int)
    counts = values.value_counts().to_dict()
    return {score: int(counts.get(score, 0)) for score in range(min_score, max_score + 1)}


def score_distribution_label(scores: Iterable[float]) -> str:
    counts = score_distribution_counts(scores)
    nonzero = [f"{score}: {count}" for score, count in counts.items() if count]
    return ", ".join(nonzero) if nonzero else "—"


def sort_matrix_rows(matrix: pd.DataFrame, sort_qid: str | None, descending: bool) -> pd.DataFrame:
    if not sort_qid or sort_qid not in matrix.columns:
        return matrix
    sort_data = pd.DataFrame({"group": matrix.index, "value": matrix[sort_qid].values})
    visible = sort_data[sort_data["value"].notna()].sort_values(
        ["value", "group"],
        ascending=[not descending, True],
        kind="mergesort",
    )
    hidden = sort_data[sort_data["value"].isna()]
    return matrix.reindex(index=visible["group"].tolist() + hidden["group"].tolist())


def selected_group_mask(numeric: pd.DataFrame, view: str, group: str, selected_team: str | None = None) -> pd.Series:
    if view == "general":
        return pd.Series(True, index=numeric.index)
    if view == "team":
        return numeric["team"].astype(str) == group
    if view == "tenure":
        return numeric["tenure"].astype(str) == group
    if view == "team_tenure":
        if " · " in group:
            team, tenure = group.split(" · ", 1)
        else:
            team, tenure = selected_team or "", group
        return (numeric["team"].astype(str) == team) & (numeric["tenure"].astype(str) == tenure)
    raise ValueError(view)


def drilldown(
    numeric: pd.DataFrame,
    question_id: str,
    view: str,
    group: str,
    selected_team: str | None = None,
) -> dict:
    qdata = numeric[numeric["question_id"] == question_id].copy()
    mask = selected_group_mask(qdata, view, group, selected_team)
    selected = qdata[mask].copy()
    branch = qdata["score"]
    values = selected["score"]
    stats = {
        "n": int(values.count()),
        "mean": float(values.mean()) if len(values) else None,
        "branch_mean": float(branch.mean()) if len(branch) else None,
        "delta": float(values.mean() - branch.mean()) if len(values) else None,
        "median": float(values.median()) if len(values) else None,
        "p25": float(values.quantile(0.25)) if len(values) else None,
        "p75": float(values.quantile(0.75)) if len(values) else None,
        "high": float((values >= 8).mean()) if len(values) else None,
        "low": float((values <= 5).mean()) if len(values) else None,
        "std": float(values.std(ddof=0)) if len(values) else None,
    }
    return {
        "stats": stats,
        "rows": selected[[
            "response_id", "source_excel_row", "team", "tenure", "score", "source_column",
            "question_label", "dimension", "domain",
        ]].sort_values(["team", "tenure", "response_id"]),
        "response_ids": set(selected["response_id"].astype(int)),
    }


def team_question_distribution(
    numeric: pd.DataFrame,
    question_id: str,
    min_group_size: int = 5,
) -> pd.DataFrame:
    """Return all teams' comparable results for one numeric question.

    This result is deliberately independent of the currently selected heatmap
    view. It lets the UI retain the full team comparison even when the user is
    drilling into one team or one tenure group.
    """
    qdata = numeric[numeric["question_id"] == question_id].copy()
    if qdata.empty:
        return pd.DataFrame(
            columns=["team", "n", "mean", "delta", "high", "low", "std", "display_allowed"]
        )

    branch_mean = float(qdata["score"].mean())
    grouped = qdata.groupby("team")["score"]
    result = grouped.agg(
        n="count",
        mean="mean",
        std=lambda s: float(s.std(ddof=0)) if len(s) else np.nan,
        high=lambda s: float((s >= 8).mean()),
        low=lambda s: float((s <= 5).mean()),
    ).reset_index()
    result["delta"] = result["mean"] - branch_mean
    result["display_allowed"] = result["n"] >= min_group_size
    return result.sort_values(["mean", "team"], ascending=[True, True]).reset_index(drop=True)


def result_direction(delta: float | None, threshold: float = 0.35) -> str:
    if delta is None:
        return "neutral"
    if delta >= threshold:
        return "positive"
    if delta <= -threshold:
        return "negative"
    return "neutral"
