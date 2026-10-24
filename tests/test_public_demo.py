import json
from pathlib import Path

import build_public_demo

from build_public_demo import PUBLIC_TEAMS, build_public_payload, validate_public_html


def test_public_demo_payload_is_synthetic():
    payload = build_public_payload()
    teams = {row["team"] for row in payload["numeric"]}
    assert teams == set(PUBLIC_TEAMS)
    assert len(teams) == 5
    assert len({row["response_id"] for row in payload["numeric"]}) == 50
    assert all(str(row["source_excel_row"]).startswith("DEMO-") for row in payload["numeric"])
    assert payload["evidence"]
    assert any(row["direction"] == "positive" for row in payload["evidence"])
    assert any(row["direction"] == "negative" for row in payload["evidence"])
    assert payload["status"]["status"] == "public_demo_synthetic"


def test_public_demo_validator_rejects_forbidden_team_name():
    validate_public_html(json.dumps(build_public_payload()), internal_team_names={"Internal Team"})
    try:
        validate_public_html("leaked Internal Team", internal_team_names={"Internal Team"})
    except RuntimeError as exc:
        assert "Internal Team" in str(exc)
    else:
        raise AssertionError("Expected forbidden team leak to fail validation")


def test_public_demo_build_needs_only_the_ui_template(tmp_path, monkeypatch):
    """A public export must build even when no private data directory exists."""
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "build_demo.py").write_text(
        (root / "build_demo.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(build_public_demo, "ROOT", tmp_path)
    output = build_public_demo.render_public_demo(tmp_path / "public.html")
    assert "Synthetic demo: all questions" in output.read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == (root / "static" / "public_demo.html").read_text(encoding="utf-8")


def test_shipped_demo_contains_exactly_the_synthetic_payload():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "public_demo.html").read_text(encoding="utf-8")
    payload = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert payload == build_public_payload()
