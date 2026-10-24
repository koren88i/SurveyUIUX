import json
from io import BytesIO

import pandas as pd
import pytest

import survey_loader
from scripts.check_public_release import check_snapshot, check_text, noreply


def test_public_scan_rejects_contact_secret_and_personal_path():
    secret = ("sk-" + "x" * 30).encode()
    contact = ("owner" + "@" + "personal.invalid").encode()
    personal_path = ("C:" + "/Users/" + "Example/file").encode()
    assert check_text("example.txt", secret)
    assert check_text("example.txt", contact)
    assert check_text("example.txt", personal_path)
    assert not check_text("example.txt", b"hello@example.com")


def test_identity_requires_noreply_for_both_commit_roles():
    assert noreply("123+example@users.noreply.github.com")
    assert noreply("noreply@github.com")
    assert not noreply("owner@example.com")
    assert not noreply("example@users.noreply.github.com" + ".attacker.invalid")


def test_allowlist_cannot_override_private_artifact_rules():
    files = {".public-files": b".public-files\ndata/responses.xlsx\n", "data/responses.xlsx": b"private"}
    assert any("private artifact" in error for error in check_snapshot(files))


def test_unreviewed_file_is_blocked():
    assert any("allowlist" in error for error in check_snapshot({"unreviewed.csv": b"data"}))


def raw_workbook(columns):
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        pd.DataFrame(columns).to_excel(writer, sheet_name=survey_loader.RAW_SHEET, index=False)
    return stream.getvalue()


def test_local_column_alias_preserves_legacy_workbook(tmp_path, monkeypatch):
    config = tmp_path / "columns.json"
    config.write_text(json.dumps({"manager_keep": "Example legacy keep column"}), encoding="utf-8")
    monkeypatch.setattr(survey_loader, "COLUMN_MAP_PATH", config)
    frame = survey_loader.load_responses(raw_workbook({
        "צוות": ["Team Example"], "זמן בצוות": ["0-6 months"],
        "Example legacy keep column": ["Synthetic example answer"],
    }))
    answers = survey_loader.build_open_answers(frame)
    assert answers.loc[answers.source_question_id == "manager_keep", "raw_text"].iloc[0] == "Synthetic example answer"


def test_local_alias_rejects_ambiguous_columns(tmp_path, monkeypatch):
    config = tmp_path / "columns.json"
    config.write_text(json.dumps({"manager_keep": "Example legacy keep column"}), encoding="utf-8")
    monkeypatch.setattr(survey_loader, "COLUMN_MAP_PATH", config)
    with pytest.raises(ValueError, match="Ambiguous"):
        survey_loader.load_responses(raw_workbook({
            "Example legacy keep column": ["One example"],
            survey_loader.OPEN_QUESTION_META["manager_keep"]["column"]: ["Another example"],
        }))
