from __future__ import annotations

from pathlib import Path
import json
import random
import re
from typing import Any

import pandas as pd

ROOT = Path(__file__).parent
OUTPUT = ROOT / "static" / "public_demo.html"

PUBLIC_TEAMS = ["Team Alon", "Team Barak", "Team Gefen", "Team Dekel", "Team Hadas"]
TENURES = ["0-6 months", "6-18 months", "18+ months"]

SYNTHETIC_CATALOG = [
    {"question_id": "demo_manager_context", "domain": "manager", "domain_label": "Manager", "dimension": "Clarity", "label": "Manager context", "full_text": "My manager gives clear context before work starts.", "source_column": "A", "positive_direction": "Higher score means stronger agreement."},
    {"question_id": "demo_manager_priorities", "domain": "manager", "domain_label": "Manager", "dimension": "Prioritization", "label": "Clear priorities", "full_text": "Priorities are clear when several tasks compete for attention.", "source_column": "B", "positive_direction": "Higher score means stronger agreement."},
    {"question_id": "demo_team_knowledge", "domain": "team", "domain_label": "Team", "dimension": "Knowledge sharing", "label": "Knowledge sharing", "full_text": "The team shares knowledge early enough for others to use it.", "source_column": "C", "positive_direction": "Higher score means stronger agreement."},
    {"question_id": "demo_team_coordination", "domain": "team", "domain_label": "Team", "dimension": "Coordination", "label": "Coordination", "full_text": "The team coordinates work clearly across people and tasks.", "source_column": "D", "positive_direction": "Higher score means stronger agreement."},
    {"question_id": "demo_feedback_actionable", "domain": "feedback_quality", "domain_label": "Feedback", "dimension": "Actionability", "label": "Actionable feedback", "full_text": "Feedback is specific enough to act on.", "source_column": "E", "positive_direction": "Higher score means stronger agreement."},
    {"question_id": "demo_feedback_timing", "domain": "feedback_quality", "domain_label": "Feedback", "dimension": "Timing", "label": "Timely feedback", "full_text": "Feedback arrives close enough to the work to be useful.", "source_column": "F", "positive_direction": "Higher score means stronger agreement."},
]

TEAM_PROFILES = {
    "Team Alon": {"base": 8.0, "spread": 0.6},
    "Team Barak": {"base": 4.6, "spread": 0.8},
    "Team Gefen": {"base": 6.5, "spread": 0.9},
    "Team Dekel": {"base": 6.0, "spread": 1.9, "polarized": True},
    "Team Hadas": {"base": 7.1, "spread": 0.8},
}

COMMENT_BANK = {
    "manager": {
        "positive": [("The manager explains context before tasks start and keeps priorities visible.", "explains context before tasks start")],
        "negative": [("Priorities sometimes change without enough explanation for the team.", "change without enough explanation")],
        "neutral": [("Communication is steady, but clarity varies by week.", "clarity varies by week")],
    },
    "team": {
        "positive": [("The team shares decisions and helps people close gaps quickly.", "shares decisions and helps people")],
        "negative": [("Knowledge is still concentrated with a few people during busy periods.", "concentrated with a few people")],
        "neutral": [("Coordination depends on the project and current workload.", "depends on the project")],
    },
    "feedback_quality": {
        "positive": [("Feedback is specific, timely, and makes the next step clear.", "specific, timely, and makes the next step clear")],
        "negative": [("Feedback sometimes arrives too late to change the current work.", "arrives too late")],
        "neutral": [("Feedback quality is uneven across tasks.", "uneven across tasks")],
    },
    "default": {
        "positive": [("The process is clear and the team knows how to move forward.", "process is clear")],
        "negative": [("There is room to improve clarity and follow-up.", "room to improve clarity")],
        "neutral": [("The experience changes depending on workload.", "changes depending on workload")],
    },
}


def _clean_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.where(frame.notna(), None).to_dict("records")


def _synthetic_catalog_frame() -> pd.DataFrame:
    return pd.DataFrame(SYNTHETIC_CATALOG)


def _score_direction(score: int) -> str:
    if score >= 7:
        return "positive"
    if score <= 5:
        return "negative"
    return "neutral"


def _clamp_score(value: float) -> int:
    return max(1, min(10, int(round(value))))


def _synthetic_score(team: str, respondent_idx: int, question_idx: int, rng: random.Random) -> int:
    profile = TEAM_PROFILES[team]
    q_bias = ((question_idx % 5) - 2) * 0.28
    respondent_bias = ((respondent_idx % 4) - 1.5) * 0.18
    if profile.get("polarized"):
        base = 8.4 if (respondent_idx + question_idx) % 3 == 0 else 4.8
    else:
        base = float(profile["base"])
    return _clamp_score(base + q_bias + respondent_bias + rng.gauss(0, float(profile["spread"])))


def _comment(domain: str, direction: str, index: int) -> tuple[str, str]:
    bank = COMMENT_BANK.get(domain, COMMENT_BANK["default"])
    options = bank.get(direction) or COMMENT_BANK["default"][direction]
    return options[index % len(options)]


def build_public_payload() -> dict[str, Any]:
    # Public exports never accept a catalog derived from a private workbook.
    catalog = _synthetic_catalog_frame()

    rng = random.Random(42)
    catalog_records = _clean_records(catalog)
    numeric: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    response_id = 9001
    for team_idx, team in enumerate(PUBLIC_TEAMS):
        for respondent_idx in range(10):
            tenure = TENURES[(respondent_idx + team_idx) % len(TENURES)]
            source_row = f"DEMO-{response_id}"
            for question_idx, q in enumerate(catalog_records):
                score = _synthetic_score(team, respondent_idx, question_idx, rng)
                numeric.append({
                    "response_id": response_id,
                    "team": team,
                    "tenure": tenure,
                    "question_id": q["question_id"],
                    "score": score,
                    "source_excel_row": source_row,
                })

                direction = _score_direction(score)
                raw_text, span = _comment(str(q.get("domain") or "default"), direction, response_id + question_idx)
                evidence.append({
                    "segment_id": f"demo_r{response_id}_{q['question_id']}",
                    "answer_id": f"demo_answer_{response_id}_{q['question_id']}",
                    "response_id": response_id,
                    "team": team,
                    "tenure": tenure,
                    "source_question_id": f"demo_open_{q.get('domain', 'general')}",
                    "source_question_label": "Demo open question",
                    "raw_text": raw_text,
                    "segment_text": span,
                    "question_id": q["question_id"],
                    "relevance": "direct" if direction != "neutral" else "related",
                    "direction": direction,
                    "evidence_span": span,
                    "explanation": "Synthetic demo statement showing how open text can be linked to a numeric question.",
                    "confidence": "high" if direction != "neutral" else "medium",
                    "coding_source": "synthetic_public_demo",
                    "model": "synthetic",
                    "prompt_version": "public-demo-v1",
                    "run_id": "public-demo-synthetic",
                })
            response_id += 1

    status = {
        "status": "public_demo_synthetic",
        "message": "Public demo with synthetic teams, fake respondents, generated scores, and synthetic open-text evidence.",
        "coverage_pct": 100.0,
        "responses_total": len(PUBLIC_TEAMS) * 10,
        "evidence_links": len(evidence),
        "run_id": "public-demo-synthetic",
    }
    return {"catalog": catalog_records, "numeric": numeric, "evidence": evidence, "status": status}


def _extract_demo_template() -> str:
    source = (ROOT / "build_demo.py").read_text(encoding="utf-8")
    match = re.search(r"html = r'''([\s\S]*)'''\.replace\('__DATA__', json_blob\)", source)
    if not match:
        raise RuntimeError("Could not extract HTML template from build_demo.py")
    template = match.group(1)
    template = re.sub(r"teamSelect\.value='[^']*';", "teamSelect.value=teams[0]||'';", template, count=1)
    return template


def validate_public_html(html: str, internal_team_names: set[str] | None = None) -> None:
    forbidden = internal_team_names or set()
    leaked = sorted(team for team in forbidden if team and team in html)
    if leaked:
        raise RuntimeError(f"Public demo contains forbidden team names: {', '.join(leaked)}")


def render_public_demo(output: Path = OUTPUT) -> Path:
    payload = build_public_payload()
    json_blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _extract_demo_template().replace("__DATA__", json_blob)
    html = html.replace("Survey — חוקר שאלות ו-Lineage", "Public demo — Question lineage explorer")
    html = html.replace("<header>", '<header><p><strong>Synthetic demo: all questions, teams, scores, and comments are fictional.</strong></p>', 1)
    validate_public_html(html)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output


def main() -> None:
    print(render_public_demo())


if __name__ == "__main__":
    main()
