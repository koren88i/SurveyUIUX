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


@pytest.fixture
def branched_workbook(tmp_path):
    """Fictional form with different source columns for two audiences."""
    import json
    from survey_loader import header_fingerprint

    raw = pd.DataFrame({
        "Group": ["A", "A", "A", "A"], "Role": ["member", "member", "member", "lead"],
        "Shared member": [0, 8, 4, None], "Shared lead": [None, None, None, 10],
        "Leadership": [None, None, None, 0],
        "Member comment": ["Fictional comment", "-", "-", None],
        "Lead comment": [None, None, None, "Another fictional comment"],
    })
    path = tmp_path / "fictional.xlsx"
    raw.to_excel(path, sheet_name="Form", index=False)
    profile = {
        "sheet": "Form", "header_fingerprint": header_fingerprint(raw.columns),
        "group_column": "Group", "split_column": "Role", "group_label": "Group", "split_label": "Role",
        "zero_is_missing": True,
        "questions": [
            {"question_id": "shared", "domain": "manager", "domain_label": "Example", "dimension": "Shared", "label": "Shared", "audience": "all", "sources": [{"column": "C", "role": "member"}, {"column": "D", "role": "lead"}]},
            {"question_id": "leader", "domain": "manager", "domain_label": "Example", "dimension": "Leader", "label": "Leader", "audience": "lead", "sources": [{"column": "E", "role": "lead"}]},
        ],
        "open_questions": [{"question_id": "comment", "domain": "manager", "sources": [{"column": "F", "role": "member"}, {"column": "G", "role": "lead"}]}],
    }
    path.with_suffix(".profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return path, profile


def test_profile_excludes_non_relevant_from_all_metrics_and_retains_lineage(branched_workbook):
    path, _ = branched_workbook
    responses, catalog, numeric, answers = load_model(path)
    assert len(responses) == 4
    assert numeric["score"].tolist() == [8, 4, 10]
    assert not numeric.duplicated(["response_id", "question_id"]).any()
    matrix, stats = compute_matrix(numeric, catalog, "general", "mean", min_group_size=1)
    assert matrix.iloc[0, 0] == pytest.approx(22 / 3)
    assert stats.iloc[0]["n"] == 3
    assert stats.iloc[0]["high"] == pytest.approx(2 / 3)
    assert stats.iloc[0]["low"] == pytest.approx(1 / 3)
    masked, _ = compute_matrix(numeric, catalog, "general", "mean", min_group_size=4)
    assert masked.isna().all().all()
    detail = drilldown(numeric, "shared", "general", "all")
    source_rows = detail["rows"].sort_values("response_id")
    assert source_rows["source_column"].tolist() == ["C", "C", "D"]
    assert source_rows["source_excel_row"].tolist() == [3, 4, 5]
    assert detail["rows"]["source_sheet"].eq("Form").all()
    assert answers["answer_id"].nunique() == 4
    assert answers["source_column"].tolist() == ["F", "F", "F", "G"]
    assert len(set(answers["survey_id"])) == 1
    assert responses.attrs["survey"]["split_label"] == "Role"


def test_profile_zero_only_selection_is_empty(branched_workbook):
    path, _ = branched_workbook
    _, catalog, numeric, _ = load_model(path)
    matrix, _ = compute_matrix(numeric[numeric["question_id"].eq("leader")], catalog, "general", "mean")
    assert matrix.empty


def test_profile_detects_uploaded_bytes(branched_workbook, monkeypatch):
    import survey_loader
    path, _ = branched_workbook
    monkeypatch.setattr(survey_loader, "COLUMN_MAP_PATH", path.parent / "open_question_columns.json")
    _, catalog, numeric, _ = load_model(path.read_bytes())
    assert len(catalog) == 2
    assert len(numeric) == 3


def test_profile_rejects_changed_headers(branched_workbook):
    path, _ = branched_workbook
    raw = pd.read_excel(path).rename(columns={"Shared member": "Changed wording"})
    raw.to_excel(path, sheet_name="Form", index=False)
    with pytest.raises(ValueError, match="headers"):
        load_model(path)


def test_profile_rejects_unexpected_branch_or_invalid_score(branched_workbook):
    from survey_loader import load_profile_model
    path, profile = branched_workbook
    raw = pd.read_excel(path)
    raw.loc[0, "Shared lead"] = 9
    raw.to_excel(path, sheet_name="Form", index=False)
    with pytest.raises(ValueError, match="Unexpected role"):
        load_profile_model(path, profile)
    raw.loc[0, "Shared lead"] = None
    raw.loc[0, "Shared member"] = 11
    raw.to_excel(path, sheet_name="Form", index=False)
    with pytest.raises(ValueError, match="integer score"):
        load_profile_model(path, profile)


def test_profile_batch_respects_audience_and_tags_workbook(branched_workbook, tmp_path):
    import json
    from semantic_batch import prepare
    from survey_loader import workbook_fingerprint

    path, _ = branched_workbook
    requests = tmp_path / "requests.jsonl"
    manifest = tmp_path / "manifest.csv"
    prepare(path, requests, manifest, "fictional-model")
    lines = [json.loads(line) for line in requests.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    member = json.loads(lines[0]["body"]["messages"][1]["content"])
    lead = json.loads(lines[1]["body"]["messages"][1]["content"])
    assert [q["question_id"] for q in member["question_catalog"]] == ["shared"]
    assert [q["question_id"] for q in lead["question_catalog"]] == ["shared", "leader"]
    assert "score" not in member
    assert pd.read_csv(manifest)["survey_id"].eq(workbook_fingerprint(path)).all()


def test_evidence_rejects_missing_or_mixed_workbook_fingerprints():
    from evidence import matches_survey
    assert matches_survey(pd.DataFrame(), "current")
    assert matches_survey(pd.DataFrame({"survey_id": ["current", "current"]}), "current")
    assert not matches_survey(pd.DataFrame({"survey_id": ["current", "old"]}), "current")
    assert not matches_survey(pd.DataFrame({"segment_id": ["old"]}), "current")


def test_profile_parser_checks_workbook_before_writing(branched_workbook, tmp_path):
    from semantic_batch import parse
    path, _ = branched_workbook
    manifest = tmp_path / "manifest.csv"
    pd.DataFrame([{"answer_id": "a1", "survey_id": "different"}]).to_csv(manifest, index=False)
    output = tmp_path / "evidence.jsonl"
    output.write_text("existing evidence", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        parse(tmp_path / "batch.jsonl", manifest, path, output, "test")
    assert output.read_text(encoding="utf-8") == "existing evidence"


def test_profile_html_export_and_role_filter_runtime(branched_workbook, tmp_path):
    """Exercise the exported JavaScript with a small in-memory DOM test double."""
    import json
    import shutil
    import subprocess
    from build_demo import build_private_demo

    path, _ = branched_workbook
    output = build_private_demo(path, tmp_path / "survey.html")
    html = output.read_text(encoding="utf-8")
    payload = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert payload["survey"]["zero_is_missing"]
    assert len(payload["numeric"]) == 3
    assert payload["evidence"] == []
    assert len(payload["open_answers"]) == 4
    assert payload["status"]["status"] == "not_classified"
    assert "data-tab=\"lineage\"" in html
    if not shutil.which("node"):
        pytest.skip("Node is required for the exported JavaScript runtime check")
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[1],'utf8');
const nodes=new Map();
function node(id){
 if(!nodes.has(id))nodes.set(id,{value:'',options:[],innerHTML:'',textContent:'',hidden:true,
 previousElementSibling:{textContent:''},dataset:{},classList:{add(){},remove(){}},
 add(option){this.options.push(option);if(this.options.length===1)this.value=option.value},
 replaceChildren(...options){this.options=options;this.value=options[0]?.value||''},
 addEventListener(){},scrollIntoView(){}});
 return nodes.get(id);
}
for(const [id,value] of Object.entries({view:'general',metric:'mean',domain:'all',minN:'1'}))node(id).value=value;
const document={getElementById:node,querySelectorAll:()=>[],querySelector(selector){
 if(selector==='.cell')return null;
 return node(selector);
}};
const context=vm.createContext({document,Option:function(text,value){this.textContent=text;this.value=value},console,Set,Map});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
vm.runInContext(`
 document.getElementById('role').value='member'; render();
 if(visibleQuestions().length!==1)throw Error('Leader questions visible for members');
 if(activeNumeric().length!==2||branchMean('shared')!==6)throw Error('Wrong member scores');
 showDetail('all','shared',{scroll:false});
 if(!document.getElementById('detail').innerHTML.includes('C3, C4'))throw Error('Wrong member lineage');
 if(document.getElementById('detail').innerHTML.includes('Another fictional comment'))throw Error('Leader comment leaked into member selection');
 document.getElementById('role').value='lead';render();
 if(visibleQuestions().length!==2)throw Error('Missing leader questions');
 if(activeNumeric().length!==1||branchMean('shared')!==10)throw Error('Wrong leader scores');
 showDetail('all','shared',{scroll:false});
 if(!document.getElementById('detail').innerHTML.includes('D5'))throw Error('Wrong leader lineage');
 if(!document.getElementById('detail').innerHTML.includes('Another fictional comment'))throw Error('Leader source comment missing');
 document.getElementById('role').value='member';document.getElementById('audience').value='lead';render();
 if(visibleQuestions().length!==0)throw Error('Invalid role/question intersection');
 if(!document.getElementById('detail').innerHTML.includes('class="empty"'))throw Error('Stale details');
 `,context);
console.log('HTML runtime role filters and lineage passed');
'''
    result = subprocess.run(["node", "-e", script, str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_batch_open_question_scope_is_explicit(branched_workbook, tmp_path):
    from semantic_batch import prepare
    path, _ = branched_workbook
    requests = tmp_path / "scoped.jsonl"
    manifest = tmp_path / "scoped.csv"
    prepare(path, requests, manifest, "fictional-model", ["comment"])
    assert pd.read_csv(manifest)["source_question_id"].eq("comment").all()
    original = requests.read_bytes()
    with pytest.raises(ValueError, match="Unknown open-question IDs"):
        prepare(path, requests, manifest, "fictional-model", ["unknown"])
    assert requests.read_bytes() == original
