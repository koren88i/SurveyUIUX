from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
import hashlib
import json
import re

import pandas as pd

RAW_SHEET = "נתונים גולמיים"
MAPPING_SHEET = "מיפוי וחישובים"
COLUMN_MAP_PATH = Path(__file__).parent / "data" / "open_question_columns.json"

OPEN_QUESTION_META = {
    "manager_keep": {
        "column": "שאלה פתוחה - מה היית ממליץ למנהלת שלך להמשיך לעשות",
        "label": "מה היית ממליץ למנהלת שלך להמשיך לעשות",
        "domain": "manager",
    },
    "manager_change": {
        "column": "שאלה פתוחה - מה היית ממליץ למנהל שלך לשנות",
        "label": "מה היית ממליץ למנהל שלך לשנות",
        "domain": "manager",
    },
    "team_jump": {
        "column": "שאלה פתוחה - הצוות שלי יכול לעשות קפיצת מדרגה ב..",
        "label": "הצוות שלי יכול לעשות קפיצת מדרגה ב...",
        "domain": "team",
    },
    "team_keep": {
        "column": "שאלה פתוחה - הצוות שלי ממש מעולה ב.. ונכון לשמר..",
        "label": "הצוות שלי ממש מעולה ב... ונכון לשמר",
        "domain": "team",
    },
}

NON_INFORMATIVE = {
    "", ".", "-", "–", "—", "_", "/", "אין", "כלום", "לא יודע", "לא יודעת",
    "לא יודע עדיין", "לא יודעת עדיין", "אין לי משהו", "אין לי משהו ספציפי",
    "כרגע אין לי המלצה לשינוי", "לא לשנות שום דבר", "לא עולה לי משהו",
    "לא עולה לי משו", "כרגיל", "התקדמות", "מ",
}


def _slug(label: str) -> str:
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    return f"q_{digest}"


def _read_excel(source: str | Path | bytes | BinaryIO, sheet_name: str, **kwargs) -> pd.DataFrame:
    if isinstance(source, bytes):
        source = BytesIO(source)
    return pd.read_excel(source, sheet_name=sheet_name, engine="openpyxl", **kwargs)


def is_informative(value: object) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    text = re.sub(r"\s+", " ", str(value)).strip()
    if text in NON_INFORMATIVE or len(text) < 2:
        return False
    if "לא מספיק זמן" in text and len(text) < 80:
        return False
    return True


def load_question_catalog(source: str | Path | bytes | BinaryIO) -> pd.DataFrame:
    mapping = _read_excel(source, MAPPING_SHEET, header=None)
    header_row = None
    for idx, row in mapping.iterrows():
        if str(row.iloc[0]).strip() == "תחום" and str(row.iloc[2]).strip() == "תווית קצרה":
            header_row = idx
            break
    if header_row is None:
        raise ValueError("לא נמצאה טבלת מיפוי השאלות בגיליון 'מיפוי וחישובים'.")

    table = _read_excel(source, MAPPING_SHEET, header=header_row)
    table = table[["תחום", "ממד", "תווית קצרה", "נוסח מלא", "עמודת מקור"]].copy()
    table = table.dropna(subset=["תחום", "תווית קצרה", "נוסח מלא", "עמודת מקור"])
    table = table[table["תחום"].isin(["הערכת ראש צוות", "אפקטיביות צוות", "איכות המשוב"])]
    table = table[table["עמודת מקור"].astype(str).str.fullmatch(r"[A-Z]{1,2}")]
    table = table.rename(columns={
        "תחום": "domain_label",
        "ממד": "dimension",
        "תווית קצרה": "label",
        "נוסח מלא": "full_text",
        "עמודת מקור": "source_column",
    })
    table["question_id"] = table["label"].map(_slug)
    table["domain"] = table["domain_label"].map({
        "הערכת ראש צוות": "manager",
        "אפקטיביות צוות": "team",
        "איכות המשוב": "feedback_quality",
    }).fillna("other")
    table["positive_direction"] = table["full_text"].map(
        lambda text: f"ציון גבוה משמעו הסכמה חזקה יותר עם האמירה: {text}"
    )
    return table[[
        "question_id", "domain", "domain_label", "dimension", "label", "full_text",
        "source_column", "positive_direction",
    ]].reset_index(drop=True)


def load_responses(source: str | Path | bytes | BinaryIO) -> pd.DataFrame:
    raw = _read_excel(source, RAW_SHEET)
    raw = raw.copy()
    # Local column aliases support other workbook wording without hard-coding it.
    if COLUMN_MAP_PATH.exists():
        aliases = json.loads(COLUMN_MAP_PATH.read_text(encoding="utf-8"))
        if not isinstance(aliases, dict) or any(
            key not in OPEN_QUESTION_META or not isinstance(value, str) or not value
            for key, value in aliases.items()
        ):
            raise ValueError("Invalid local open-question column mapping")
        renames = {}
        for key, original in aliases.items():
            target = OPEN_QUESTION_META[key]["column"]
            if original in raw.columns and original != target:
                if target in raw.columns or target in renames.values():
                    raise ValueError("Ambiguous open-question column mapping")
                renames[original] = target
        raw = raw.rename(columns=renames)
    raw.insert(0, "response_id", range(1, len(raw) + 1))
    raw["source_excel_row"] = raw["response_id"] + 1
    raw = raw.rename(columns={"צוות": "team", "זמן בצוות": "tenure"})
    return raw


def build_numeric_long(responses: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for question in catalog.to_dict("records"):
        column = question["full_text"]
        if column not in responses.columns:
            raise ValueError(f"עמודת המקור של השאלה לא נמצאה בנתונים הגולמיים: {column}")
        values = pd.to_numeric(responses[column], errors="coerce")
        for response_id, team, tenure, source_row, score in zip(
            responses["response_id"], responses["team"], responses["tenure"],
            responses["source_excel_row"], values,
        ):
            if pd.isna(score):
                continue
            records.append({
                "response_id": int(response_id),
                "source_excel_row": int(source_row),
                "team": str(team),
                "tenure": str(tenure),
                "question_id": question["question_id"],
                "question_label": question["label"],
                "domain": question["domain"],
                "dimension": question["dimension"],
                "source_column": question["source_column"],
                "score": float(score),
            })
    return pd.DataFrame.from_records(records)


def build_open_answers(responses: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for row in responses.to_dict("records"):
        for source_question_id, meta in OPEN_QUESTION_META.items():
            raw_text = row.get(meta["column"], "")
            text = "" if pd.isna(raw_text) else str(raw_text).strip()
            records.append({
                "answer_id": f"r{int(row['response_id']):03d}_{source_question_id}",
                "response_id": int(row["response_id"]),
                "source_excel_row": int(row["source_excel_row"]),
                "team": str(row["team"]),
                "tenure": str(row["tenure"]),
                "source_question_id": source_question_id,
                "source_question_label": meta["label"],
                "domain": meta["domain"],
                "raw_text": text,
                "informative": is_informative(text),
            })
    return pd.DataFrame.from_records(records)


def load_model(source: str | Path | bytes | BinaryIO) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    catalog = load_question_catalog(source)
    responses = load_responses(source)
    numeric = build_numeric_long(responses, catalog)
    open_answers = build_open_answers(responses)
    return responses, catalog, numeric, open_answers
