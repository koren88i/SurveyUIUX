from __future__ import annotations

from pathlib import Path
from io import BytesIO
import json

import pandas as pd

REQUIRED_COLUMNS = [
    "segment_id", "answer_id", "response_id", "team", "tenure", "source_question_id",
    "source_question_label", "raw_text", "segment_text", "question_id", "relevance",
    "direction", "evidence_span", "explanation", "confidence", "coding_source",
    "model", "prompt_version", "run_id",
]


def load_evidence(source: str | Path | bytes) -> pd.DataFrame:
    records = []
    if isinstance(source, bytes):
        text = source.decode("utf-8-sig")
        lines = text.splitlines()
    else:
        path = Path(source)
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    for line in lines:
        if line.strip():
            records.append(json.loads(line))
    frame = pd.DataFrame.from_records(records)
    for column in REQUIRED_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    if not frame.empty:
        frame["response_id"] = pd.to_numeric(frame["response_id"], errors="coerce").astype("Int64")
    return frame[REQUIRED_COLUMNS]


def load_status(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"status": "missing", "message": "לא נטען קובץ evidence."}
    return json.loads(path.read_text(encoding="utf-8"))


def classify_relation(direction: str, numeric_direction: str) -> str:
    if numeric_direction == "neutral":
        return "חיובית" if direction == "positive" else (
            "ביקורתית" if direction == "negative" else "מעורבת/ניטרלית"
        )
    if direction == numeric_direction:
        return "תומכת"
    if direction in {"positive", "negative"} and direction != numeric_direction:
        return "סותרת/מסייגת"
    return "הקשר נוסף"



def relation_counts(
    evidence: pd.DataFrame,
    question_id: str,
    response_ids: set[int],
    numeric_direction: str,
) -> dict[str, int | None]:
    """Count atomic evidence statements supporting or contradicting a result.

    Counts unique ``segment_id`` values. When the numeric result is neutral,
    support/contradiction is intentionally undefined and returned as ``None``.
    """
    if numeric_direction == "neutral":
        return {"support": None, "contradict": None, "matched": 0}
    if evidence.empty or not response_ids:
        return {"support": 0, "contradict": 0, "matched": 0}

    selected = evidence[
        (evidence["question_id"] == question_id)
        & (evidence["response_id"].astype("Int64").isin(list(response_ids)))
    ].copy()
    if selected.empty:
        return {"support": 0, "contradict": 0, "matched": 0}

    selected["relation"] = selected["direction"].map(
        lambda value: classify_relation(str(value), numeric_direction)
    )
    id_column = "segment_id" if "segment_id" in selected.columns else None
    if id_column:
        support = int(selected.loc[selected["relation"] == "תומכת", id_column].nunique())
        contradict = int(selected.loc[selected["relation"] == "סותרת/מסייגת", id_column].nunique())
        matched = int(selected[id_column].nunique())
    else:
        support = int((selected["relation"] == "תומכת").sum())
        contradict = int((selected["relation"] == "סותרת/מסייגת").sum())
        matched = int(len(selected))
    return {"support": support, "contradict": contradict, "matched": matched}

def evidence_for_selection(
    evidence: pd.DataFrame,
    question_id: str,
    response_ids: set[int],
    numeric_direction: str,
    score_rows: pd.DataFrame,
) -> pd.DataFrame:
    if evidence.empty:
        return evidence.copy()
    selected = evidence[
        (evidence["question_id"] == question_id)
        & (evidence["response_id"].astype("Int64").isin(list(response_ids)))
    ].copy()
    if selected.empty:
        return selected
    selected["relation"] = selected["direction"].map(
        lambda value: classify_relation(str(value), numeric_direction)
    )
    score_map = score_rows.set_index("response_id")["score"].to_dict()
    selected["score"] = selected["response_id"].map(score_map)
    selected["personal_alignment"] = selected.apply(_personal_alignment, axis=1)
    order = pd.Categorical(selected["relation"], ["תומכת", "סותרת/מסייגת", "הקשר נוסף", "חיובית", "ביקורתית", "מעורבת/ניטרלית"])
    confidence_order = pd.Categorical(selected["confidence"], ["high", "medium", "low"], ordered=True)
    selected = (
        selected.assign(_order=order, _confidence_order=confidence_order)
        .sort_values(["_order", "_confidence_order"], ascending=[True, True])
        .drop(columns=["_order", "_confidence_order"])
    )
    return selected


def _personal_alignment(row: pd.Series) -> str:
    score = row.get("score")
    direction = row.get("direction")
    if pd.isna(score):
        return "אין ציון"
    if score >= 8:
        score_direction = "positive"
    elif score <= 5:
        score_direction = "negative"
    else:
        score_direction = "neutral"
    if direction in {"positive", "negative"} and direction == score_direction:
        return "המלל והציון האישיים מתיישבים"
    if direction in {"positive", "negative"} and score_direction in {"positive", "negative"}:
        return "פער בין המלל לציון האישי"
    return "הציון האישי ביניים"
