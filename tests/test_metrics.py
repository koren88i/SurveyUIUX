from pathlib import Path

import pandas as pd
import pytest

from survey_loader import load_model
from metrics import (
    compute_matrix,
    drilldown,
    result_direction,
    score_distribution_counts,
    score_distribution_label,
    sort_matrix_rows,
    team_question_distribution,
)
from evidence import classify_relation, load_evidence, relation_counts

ROOT = Path(__file__).resolve().parents[1]
EXCEL = ROOT / "data" / "survey.xlsx"


def private_file(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"Private survey fixture is not committed: {path.name}")
    return path


def model():
    return load_model(private_file(EXCEL))


def first_valid_cell(matrix: pd.DataFrame) -> tuple[str, str]:
    stacked = matrix.stack(dropna=True)
    if stacked.empty:
        pytest.skip("No visible matrix cells in private fixture")
    return str(stacked.index[0][0]), str(stacked.index[0][1])


def test_loader_private_fixture_smoke():
    responses, catalog, numeric, open_answers = model()
    assert not responses.empty
    assert not catalog.empty
    assert numeric["question_id"].nunique() == len(catalog)
    assert {"response_id", "team", "tenure"}.issubset(responses.columns)
    assert {"answer_id", "raw_text", "informative"}.issubset(open_answers.columns)


def test_matrix_and_drilldown_private_fixture_smoke():
    _, catalog, numeric, _ = model()
    matrix, _ = compute_matrix(numeric, catalog, "team", "delta", min_group_size=5)
    group, qid = first_valid_cell(matrix)
    detail = drilldown(numeric, qid, "team", group)
    assert detail["stats"]["n"] > 0
    assert detail["stats"]["mean"] is not None
    assert len(detail["rows"]) == detail["stats"]["n"]


def test_privacy_masks_when_threshold_exceeds_group_sizes():
    _, catalog, numeric, _ = model()
    matrix, _ = compute_matrix(numeric, catalog, "team", "mean", min_group_size=10_000)
    assert matrix.isna().all().all()


def test_relation_is_deterministic():
    assert result_direction(-0.8) == "negative"
    assert classify_relation("negative", "negative") == "תומכת"
    assert classify_relation("positive", "negative") == "סותרת/מסייגת"


def test_evidence_private_fixture_smoke():
    _, catalog, numeric, _ = model()
    evidence = load_evidence(private_file(ROOT / "data" / "evidence_links.jsonl"))
    if evidence.empty:
        pytest.skip("Private evidence fixture is empty")
    matrix, _ = compute_matrix(numeric, catalog, "team", "delta", min_group_size=5)
    group, qid = first_valid_cell(matrix)
    detail = drilldown(numeric, qid, "team", group)
    counts = relation_counts(evidence, qid, detail["response_ids"], result_direction(detail["stats"]["delta"]))
    assert set(counts) == {"support", "contradict", "matched"}


def test_batch_payload_shape_private_fixture():
    import json

    path = private_file(ROOT / "data" / "batch_requests.jsonl")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    assert all(line["url"] == "/v1/chat/completions" for line in lines)
    assert all(line["body"]["response_format"]["type"] == "json_schema" for line in lines)


def test_batch_parser_with_synthetic_response(tmp_path):
    import json
    from semantic_batch import parse

    manifest_path = private_file(ROOT / "data" / "open_answer_manifest.csv")
    manifest = pd.read_csv(manifest_path, encoding="utf-8-sig")
    row = manifest.iloc[0]
    _, catalog, _, _ = model()
    qid = catalog[catalog["domain"] == row["domain"]]["question_id"].iloc[0]
    output = {
        "custom_id": row["answer_id"],
        "response": {
            "body": {
                "choices": [{
                    "message": {"content": json.dumps({
                        "segments": [{
                            "segment_text": "synthetic parser check",
                            "matches": [{
                                "question_id": qid,
                                "relevance": "related",
                                "direction": "neutral",
                                "evidence_span": "synthetic parser check",
                                "explanation": "parser check",
                                "confidence": "low",
                            }],
                        }]
                    })}
                }]
            }
        },
    }
    batch_output = tmp_path / "batch.jsonl"
    batch_output.write_text(json.dumps(output) + "\n", encoding="utf-8")
    evidence_out = tmp_path / "evidence.jsonl"
    parse(batch_output, manifest_path, private_file(EXCEL), evidence_out, "test-run")
    records = [json.loads(x) for x in evidence_out.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["run_id"] == "test-run"


def test_relation_counts_count_atomic_statements():
    evidence = pd.DataFrame([
        {"segment_id": "s1", "question_id": "q1", "response_id": 1, "direction": "negative"},
        {"segment_id": "s2", "question_id": "q1", "response_id": 1, "direction": "positive"},
        {"segment_id": "s2", "question_id": "q1", "response_id": 1, "direction": "positive"},
    ])
    counts = relation_counts(evidence, "q1", {1}, "negative")
    assert counts == {"support": 1, "contradict": 1, "matched": 2}
    neutral = relation_counts(evidence, "q1", {1}, "neutral")
    assert neutral["support"] is None
    assert neutral["contradict"] is None


def test_extract_selected_cell_from_streamlit_shapes():
    from ui_helpers import extract_selected_cell

    x_ids = ["q1", "q2"]
    x_labels = ["Question 1", "Question 2"]
    y_labels = ["Team A", "Team B"]

    dict_event = {"selection": {"points": [{"x": "Question 2", "y": "Team A"}]}}
    assert extract_selected_cell(dict_event, x_ids=x_ids, x_labels=x_labels, y_labels=y_labels) == ("Team A", "q2")

    custom_event = {"selection": {"points": [{"customdata": [5, 8.0, 7.0, 1.0, True, "q1", "Team B"]}]}}
    assert extract_selected_cell(custom_event, x_ids=x_ids, x_labels=x_labels, y_labels=y_labels) == ("Team B", "q1")


def test_team_question_distribution_private_fixture_smoke():
    responses, catalog, numeric, _ = model()
    qid = catalog["question_id"].iloc[0]
    distribution = team_question_distribution(numeric, qid, min_group_size=1)
    assert len(distribution) == responses["team"].nunique()
    assert distribution["display_allowed"].any()


def test_sort_matrix_rows_keeps_masked_values_at_bottom():
    import numpy as np

    matrix = pd.DataFrame(
        {"q1": [2.0, np.nan, 8.0, 5.0], "q2": [1.0, 4.0, 3.0, np.nan]},
        index=["A", "Masked", "C", "B"],
    )

    descending = sort_matrix_rows(matrix, "q1", descending=True)
    assert descending.index.tolist() == ["C", "B", "A", "Masked"]

    ascending = sort_matrix_rows(matrix, "q1", descending=False)
    assert ascending.index.tolist() == ["A", "B", "C", "Masked"]


def test_score_distribution_helpers():
    counts = score_distribution_counts([1, 1, 4, 10, 10, 10])
    assert counts[1] == 2
    assert counts[2] == 0
    assert counts[10] == 3
    assert score_distribution_label([1, 1, 4, 10, 10, 10]) == "1: 2, 4: 1, 10: 3"