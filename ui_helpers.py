from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    try:
        return value.to_dict()
    except Exception:
        return None


def _selection_points(state: Any) -> list[Mapping[str, Any]]:
    """Return Plotly selection points from Streamlit's dict or object state."""
    if state is None:
        return []

    mapping = _as_mapping(state)
    if mapping is not None:
        selection = mapping.get("selection", {})
    else:
        selection = getattr(state, "selection", None)

    selection_mapping = _as_mapping(selection)
    if selection_mapping is not None:
        points = selection_mapping.get("points", [])
    else:
        points = getattr(selection, "points", []) if selection is not None else []

    output: list[Mapping[str, Any]] = []
    for point in points or []:
        point_mapping = _as_mapping(point)
        if point_mapping is not None:
            output.append(point_mapping)
    return output


def extract_selected_cell(
    *states: Any,
    x_ids: Sequence[str],
    x_labels: Sequence[str],
    y_labels: Sequence[str],
) -> tuple[str | None, str | None]:
    """Extract ``(group, question_id)`` from a Plotly heatmap selection.

    Supports Streamlit event objects, plain dictionaries, customdata, x/y values,
    and Plotly heatmap ``point_number=[row, column]`` as fallbacks.
    """
    for state in states:
        points = _selection_points(state)
        if not points:
            continue
        point = points[-1]

        custom = point.get("customdata")
        if isinstance(custom, Sequence) and not isinstance(custom, (str, bytes)):
            # app.py stores question_id and group at positions 5 and 6.
            if len(custom) >= 7:
                qid = str(custom[5]) if custom[5] is not None else None
                group = str(custom[6]) if custom[6] is not None else None
                if qid in x_ids and group in y_labels:
                    return group, qid

        x_value = point.get("x")
        y_value = point.get("y")
        if y_value in y_labels and x_value in x_labels:
            return str(y_value), str(x_ids[x_labels.index(x_value)])

        point_number = point.get("point_number", point.get("pointNumber"))
        if (
            isinstance(point_number, Sequence)
            and not isinstance(point_number, (str, bytes))
            and len(point_number) >= 2
        ):
            row_index, column_index = int(point_number[0]), int(point_number[1])
            if 0 <= row_index < len(y_labels) and 0 <= column_index < len(x_ids):
                return str(y_labels[row_index]), str(x_ids[column_index])

    return None, None
