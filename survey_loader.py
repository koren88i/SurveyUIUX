from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
import hashlib
import json
import re

import pandas as pd
from openpyxl.utils import column_index_from_string

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
    profile = find_profile(source)
    if profile is not None:
        return load_profile_model(source, profile)
    catalog = load_question_catalog(source)
    responses = load_responses(source)
    numeric = build_numeric_long(responses, catalog)
    open_answers = build_open_answers(responses)
    return responses, catalog, numeric, open_answers


def header_fingerprint(columns) -> str:
    """Match a locally configured form without embedding private questions in code."""
    return hashlib.sha256(json.dumps(list(columns), ensure_ascii=False).encode("utf-8")).hexdigest()


def workbook_fingerprint(source) -> str:
    if isinstance(source, (str, Path)):
        content = Path(source).read_bytes()
    elif isinstance(source, bytes):
        content = source
    else:
        position = source.tell()
        source.seek(0)
        content = source.read()
        source.seek(position)
    return hashlib.sha256(content).hexdigest()


def find_profile(source) -> dict | None:
    candidates = []
    if isinstance(source, (str, Path)):
        sidecar = Path(source).resolve().with_suffix(".profile.json")
        if sidecar.exists():
            candidates.append(sidecar)
    candidates.extend(path for path in sorted(COLUMN_MAP_PATH.parent.glob("*.profile.json")) if path not in candidates)
    excel_source = BytesIO(source) if isinstance(source, bytes) else source
    book = pd.ExcelFile(excel_source, engine="openpyxl")
    matches = []
    for path in candidates:
        profile = json.loads(path.read_text(encoding="utf-8"))
        if profile["sheet"] not in book.sheet_names:
            continue
        columns = pd.read_excel(book, sheet_name=profile["sheet"], nrows=0).columns
        if header_fingerprint(columns) == profile["header_fingerprint"]:
            matches.append(profile)
        elif isinstance(source, (str, Path)) and path == Path(source).resolve().with_suffix(".profile.json"):
            raise ValueError("Workbook headers no longer match its local survey profile.")
    if len(matches) > 1:
        raise ValueError("Multiple local survey profiles match this workbook.")
    return matches[0] if matches else None


def load_profile_model(source, profile: dict):
    """Load a branched form using a private, explicit column/role mapping.

    The original response rows and physical source columns remain authoritative.
    Zeros are excluded only when the profile explicitly declares that rule.
    """
    raw = _read_excel(source, profile["sheet"])
    if header_fingerprint(raw.columns) != profile["header_fingerprint"]:
        raise ValueError("Workbook headers do not match the survey profile.")
    responses = raw.copy()
    responses.insert(0, "response_id", range(1, len(raw) + 1))
    responses["source_excel_row"] = responses["response_id"] + 1
    responses["team"] = raw[profile["group_column"]]
    # Keep the existing engine's split field, with the actual meaning in metadata.
    responses["tenure"] = raw[profile["split_column"]]
    if responses[["team", "tenure"]].isna().any().any():
        raise ValueError("Missing survey group or role values.")
    survey_id = workbook_fingerprint(source)
    responses.attrs["survey"] = {
        "label": profile.get("label", "Survey"),
        "group_label": profile.get("group_label", "קבוצה"),
        "split_label": profile.get("split_label", "תפקיד"),
        "sheet": profile["sheet"],
        "zero_is_missing": profile.get("zero_is_missing", False),
        "survey_id": survey_id,
    }
    catalog_records, numeric_records, open_records = [], [], []
    seen_ids = set()

    def source_values(question):
        seen = set()
        for origin in question["sources"]:
            letter = origin["column"]
            index = column_index_from_string(letter) - 1
            if index >= len(raw.columns):
                raise ValueError(f"Source column outside workbook: {letter}")
            header = raw.columns[index]
            mask = raw[header].notna()
            if "role" in origin:
                expected = responses["tenure"].astype(str).eq(origin["role"])
                if (mask & ~expected).any():
                    raise ValueError(f"Unexpected role in source column {letter}")
                mask &= expected
            for row_index in raw.index[mask]:
                if row_index in seen:
                    raise ValueError(f"Multiple answers to the same question on row {row_index + 2}")
                seen.add(row_index)
                yield row_index, letter, header, raw.at[row_index, header]

    for question in profile["questions"]:
        qid = question["question_id"]
        if qid in seen_ids:
            raise ValueError("Duplicate question ID in survey profile.")
        seen_ids.add(qid)
        first_header = raw.columns[column_index_from_string(question["sources"][0]["column"]) - 1]
        catalog_records.append({
            "question_id": qid, "domain": question["domain"],
            "domain_label": question["domain_label"], "dimension": question["dimension"],
            "label": question["label"], "full_text": first_header,
            "source_column": ", ".join(origin["column"] for origin in question["sources"]),
            "positive_direction": f"ציון גבוה משמעו הסכמה חזקה יותר עם האמירה: {first_header}",
            "audience": question.get("audience", "all"),
        })
        for index, letter, header, value in source_values(question):
            score = pd.to_numeric(value, errors="coerce")
            if pd.isna(score):
                raise ValueError(f"Non-numeric score at {letter}{index + 2}")
            if score == 0 and profile.get("zero_is_missing", False):
                continue
            if not 1 <= score <= 10 or score != int(score):
                raise ValueError(f"Expected an integer score from 1 to 10 at {letter}{index + 2}")
            respondent = responses.loc[index]
            numeric_records.append({
                "response_id": int(respondent["response_id"]), "source_excel_row": index + 2,
                "team": str(respondent["team"]), "tenure": str(respondent["tenure"]),
                "question_id": qid, "question_label": question["label"],
                "domain": question["domain"], "dimension": question["dimension"],
                "source_column": letter, "source_sheet": profile["sheet"],
                "source_question_text": header, "score": float(score),
            })
    for question in profile.get("open_questions", []):
        for index, letter, header, value in source_values(question):
            respondent = responses.loc[index]
            text = str(value).strip()
            open_records.append({
                "answer_id": f"r{int(respondent['response_id']):03d}_{question['question_id']}",
                "response_id": int(respondent["response_id"]), "source_excel_row": index + 2,
                "team": str(respondent["team"]), "tenure": str(respondent["tenure"]),
                "source_question_id": question["question_id"], "source_question_label": header,
                "source_column": letter, "source_sheet": profile["sheet"],
                "domain": question["domain"], "raw_text": text,
                "informative": is_informative(text), "survey_id": survey_id,
            })
    catalog = pd.DataFrame(catalog_records)
    numeric = pd.DataFrame(numeric_records, columns=[
        "response_id", "source_excel_row", "team", "tenure", "question_id", "question_label",
        "domain", "dimension", "source_column", "source_sheet", "source_question_text", "score",
    ])
    open_answers = pd.DataFrame(open_records, columns=[
        "answer_id", "response_id", "source_excel_row", "team", "tenure", "source_question_id",
        "source_question_label", "source_column", "source_sheet", "domain", "raw_text", "informative", "survey_id",
    ])
    return responses, catalog, numeric, open_answers
