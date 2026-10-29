from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import subprocess
import sys

import pandas as pd

from survey_loader import load_model, workbook_fingerprint

PROMPT_VERSION = "question-evidence-v1"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

SYSTEM_PROMPT = """אתה מנתח תשובות פתוחות בעברית מתוך שאלון ארגוני.
המטרה היא לחבר כל אמירה אטומית רק לשאלות המספריות שהיא מספקת עליהן ראיה סמנטית אמיתית.

כללים מחייבים:
1. פצל את התשובה לאמירות אטומיות כאשר היא כוללת כמה רעיונות.
2. לכל אמירה בחר אפס, אחת או מספר שאלות רלוונטיות מתוך הקטלוג שסופק.
3. direction מתייחס לכיוון של השאלה המספרית: positive = האמירה מעידה על רמה גבוהה; negative = מעידה על חסר/צורך בשיפור; mixed = מכילה שני הכיוונים; neutral = מידע ללא הערכה.
4. אל תנסה להסביר ציון מספרי — אינך מקבל ציונים. נתח את המלל בלבד.
5. direct רק כאשר האמירה עוסקת ממש בנושא השאלה. related כאשר היא מספקת הקשר קרוב אך לא ישיר.
6. evidence_span חייב להיות ציטוט קצר ומדויק מתוך התשובה המקורית.
7. אל תמציא התאמות. אם אין ראיה, החזר segments ריקים או matches ריקים.
8. explanation יהיה קצר, עובדתי, וללא טענה לסיבתיות.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "segment_text": {"type": "string"},
                    "matches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "question_id": {"type": "string"},
                                "relevance": {"type": "string", "enum": ["direct", "related"]},
                                "direction": {"type": "string", "enum": ["positive", "negative", "mixed", "neutral"]},
                                "evidence_span": {"type": "string"},
                                "explanation": {"type": "string"},
                                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            },
                            "required": ["question_id", "relevance", "direction", "evidence_span", "explanation", "confidence"],
                        },
                    },
                },
                "required": ["segment_text", "matches"],
            },
        }
    },
    "required": ["segments"],
}


def build_user_prompt(answer: dict, questions: list[dict]) -> str:
    catalog = [
        {
            "question_id": q["question_id"],
            "label": q["label"],
            "dimension": q["dimension"],
            "question": q["full_text"],
            "positive_direction": q["positive_direction"],
        }
        for q in questions
    ]
    payload = {
        "source_question": answer["source_question_label"],
        "answer": answer["raw_text"],
        "question_catalog": catalog,
    }
    return json.dumps(payload, ensure_ascii=False)


def prepare(excel: Path, requests_path: Path, manifest_path: Path, model: str, source_question_ids: list[str] | None = None) -> None:
    _, catalog, _, open_answers = load_model(excel)
    informative = open_answers[open_answers["informative"]].copy()
    if source_question_ids:
        unknown = set(source_question_ids) - set(open_answers["source_question_id"])
        if unknown:
            raise ValueError(f"Unknown open-question IDs: {sorted(unknown)}")
        informative = informative[informative["source_question_id"].isin(source_question_ids)]
    requests = []
    manifest_records = []
    for answer in informative.to_dict("records"):
        candidates = catalog[catalog["domain"] == answer["domain"]]
        if "audience" in candidates.columns:
            candidates = candidates[candidates["audience"].isin(["all", answer["tenure"]])]
        domain_questions = candidates.to_dict("records")
        custom_id = answer["answer_id"]
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(answer, domain_questions)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "survey_evidence",
                    "strict": True,
                    "schema": SCHEMA,
                },
            },
        }
        requests.append({"custom_id": custom_id, "method": "POST", "url": "/v1/chat/completions", "body": body})
        manifest_records.append(answer)

    requests_path.parent.mkdir(parents=True, exist_ok=True)
    with requests_path.open("w", encoding="utf-8") as handle:
        for request in requests:
            handle.write(json.dumps(request, ensure_ascii=False) + "\n")
    pd.DataFrame(manifest_records).to_csv(manifest_path, index=False, encoding="utf-8-sig")
    print(f"Prepared {len(requests)} requests: {requests_path}")


def submit(requests_path: Path) -> None:
    from openai import OpenAI
    client = OpenAI()
    with requests_path.open("rb") as handle:
        uploaded = client.files.create(file=handle, purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": "Survey evidence classification", "prompt_version": PROMPT_VERSION},
    )
    print(json.dumps({"batch_id": batch.id, "input_file_id": uploaded.id, "status": batch.status}, ensure_ascii=False))


def status(batch_id: str) -> None:
    from openai import OpenAI
    batch = OpenAI().batches.retrieve(batch_id)
    print(batch.model_dump_json(indent=2))


def download(batch_id: str, output_path: Path) -> None:
    from openai import OpenAI
    client = OpenAI()
    batch = client.batches.retrieve(batch_id)
    if not batch.output_file_id:
        raise RuntimeError(f"Batch has no output file yet. Status: {batch.status}")
    content = client.files.content(batch.output_file_id)
    output_path.write_bytes(content.read())
    print(output_path)


def _extract_content(line: dict) -> str:
    response = line.get("response") or {}
    body = response.get("body") or {}
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("Missing choices in batch output")
    return choices[0]["message"]["content"]


def _extract_model(line: dict) -> str | None:
    response = line.get("response") or {}
    body = response.get("body") or {}
    model = body.get("model")
    return str(model) if model else None


def _write_json_atomic(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_jsonl_atomic(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _rebuild_demo() -> Path:
    script = Path(__file__).with_name("build_demo.py")
    if not script.exists():
        raise FileNotFoundError(f"Demo builder not found: {script}")
    subprocess.run([sys.executable, str(script)], cwd=script.parent, check=True)
    return script.parent / "static" / "demo.html"


def parse(
    batch_output: Path,
    manifest_path: Path,
    catalog_source: Path,
    evidence_path: Path,
    run_id: str | None,
    status_path: Path | None = None,
    batch_id: str | None = None,
    model: str | None = None,
    rebuild_demo: bool = False,
) -> None:
    responses, catalog, _, _ = load_model(catalog_source)
    allowed_by_domain = {
        domain: set(group["question_id"])
        for domain, group in catalog.groupby("domain")
    }
    manifest_frame = pd.read_csv(manifest_path, encoding="utf-8-sig")
    if responses.attrs.get("survey") and (
        "survey_id" not in manifest_frame or not manifest_frame["survey_id"].eq(workbook_fingerprint(catalog_source)).all()
    ):
        raise ValueError("Batch manifest does not match the current workbook.")
    manifest = manifest_frame.set_index("answer_id")
    manifest_count = int(len(manifest_frame))
    run_id = run_id or datetime.now(timezone.utc).strftime("batch-%Y%m%dT%H%M%SZ")
    status_path = status_path or evidence_path.with_name("evidence_status.json")

    records: list[dict] = []
    errors: list[dict] = []
    output_answer_ids: set[str] = set()
    classified_answer_ids: set[str] = set()
    answers_with_evidence: set[str] = set()
    detected_models: set[str] = set()

    with batch_output.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                line = json.loads(raw_line)
            except Exception as exc:
                errors.append({"line": line_number, "custom_id": None, "error": f"invalid_json:{exc}"})
                continue

            custom_id = line.get("custom_id")
            if custom_id:
                output_answer_ids.add(str(custom_id))
            if custom_id not in manifest.index:
                errors.append({"line": line_number, "custom_id": custom_id, "error": "missing_manifest"})
                continue

            response_model = _extract_model(line)
            if response_model:
                detected_models.add(response_model)

            meta = manifest.loc[custom_id].to_dict()
            try:
                payload = json.loads(_extract_content(line))
            except Exception as exc:
                errors.append({"line": line_number, "custom_id": custom_id, "error": str(exc)})
                continue

            classified_answer_ids.add(str(custom_id))
            segment_counter = 0
            for segment in payload.get("segments", []):
                segment_counter += 1
                for match_index, match in enumerate(segment.get("matches", []), 1):
                    question_id = match.get("question_id")
                    if question_id not in allowed_by_domain.get(meta["domain"], set()):
                        errors.append({
                            "line": line_number,
                            "custom_id": custom_id,
                            "error": f"question_not_allowed:{question_id}",
                        })
                        continue
                    if "audience" in catalog.columns:
                        audience = catalog.set_index("question_id").at[question_id, "audience"]
                        if audience not in {"all", meta["tenure"]}:
                            errors.append({"line": line_number, "custom_id": custom_id, "error": "question_audience_mismatch"})
                            continue
                    answers_with_evidence.add(str(custom_id))
                    records.append({
                        "segment_id": f"{custom_id}_s{segment_counter:02d}_m{match_index:02d}",
                        "answer_id": custom_id,
                        "response_id": int(meta["response_id"]),
                        "team": meta["team"],
                        "tenure": meta["tenure"],
                        "source_question_id": meta["source_question_id"],
                        "source_question_label": meta["source_question_label"],
                        "raw_text": meta["raw_text"],
                        "segment_text": segment.get("segment_text", ""),
                        "question_id": question_id,
                        "relevance": match.get("relevance"),
                        "direction": match.get("direction"),
                        "evidence_span": match.get("evidence_span"),
                        "explanation": match.get("explanation"),
                        "confidence": match.get("confidence"),
                        "coding_source": "llm_batch",
                        "model": response_model or model or DEFAULT_MODEL,
                        "prompt_version": PROMPT_VERSION,
                        "run_id": run_id,
                        "survey_id": meta.get("survey_id"),
                    })

    _write_jsonl_atomic(evidence_path, records)
    error_path = evidence_path.with_suffix(".errors.json")
    _write_json_atomic(error_path, errors)

    classified_answers = len(classified_answer_ids)
    error_count = len(errors)
    coverage = classified_answers / manifest_count if manifest_count else 0.0
    complete = classified_answers == manifest_count and error_count == 0
    effective_models = sorted(detected_models) or [model or DEFAULT_MODEL]
    status_value = "llm_batch_complete" if complete else "llm_batch_partial"
    if complete:
        message = (
            f"OpenAI Batch הושלם: נותחו {classified_answers} מתוך {manifest_count} "
            f"תשובות תוכן ונוצרו {len(records)} קישורי evidence."
        )
    else:
        message = (
            f"OpenAI Batch נטען חלקית: נותחו {classified_answers} מתוך {manifest_count} "
            f"תשובות תוכן, נוצרו {len(records)} קישורי evidence ונרשמו {error_count} שגיאות."
        )

    status_payload = {
        "status": status_value,
        "message": message,
        "classified_answers": classified_answers,
        "answers_with_evidence": len(answers_with_evidence),
        "answers_without_evidence": classified_answers - len(answers_with_evidence),
        "evidence_links": len(records),
        "informative_answers_in_manifest": manifest_count,
        "batch_output_answers": len(output_answer_ids),
        "coverage_pct": round(coverage * 100, 2),
        "errors": error_count,
        "openai_batch_executed": True,
        "coding_source": "llm_batch",
        "models": effective_models,
        "prompt_version": PROMPT_VERSION,
        "run_id": run_id,
        "batch_id": batch_id,
        "parsed_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_output_file": str(batch_output),
        "manifest_file": str(manifest_path),
        "evidence_file": str(evidence_path),
        "error_file": str(error_path),
    }
    _write_json_atomic(status_path, status_payload)

    demo_path = None
    if rebuild_demo:
        demo_path = _rebuild_demo()

    print(json.dumps({
        "evidence_links": len(records),
        "classified_answers": classified_answers,
        "manifest_answers": manifest_count,
        "coverage_pct": status_payload["coverage_pct"],
        "errors": error_count,
        "output": str(evidence_path),
        "status": str(status_path),
        "demo": str(demo_path) if demo_path else None,
    }, ensure_ascii=False))

def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic evidence batch pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--excel", type=Path, required=True)
    p.add_argument("--requests", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--source-question", action="append", help="Optional open-question ID to include; repeat for multiple questions")

    p = sub.add_parser("submit")
    p.add_argument("--requests", type=Path, required=True)

    p = sub.add_parser("status")
    p.add_argument("--batch-id", required=True)

    p = sub.add_parser("download")
    p.add_argument("--batch-id", required=True)
    p.add_argument("--output", type=Path, required=True)

    p = sub.add_parser("parse")
    p.add_argument("--batch-output", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--excel", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--run-id")
    p.add_argument("--status-file", type=Path, help="Defaults to evidence_status.json next to --evidence")
    p.add_argument("--batch-id", help="Optional batch ID stored in evidence_status.json")
    p.add_argument("--model", help="Fallback model name when the batch output does not include it")
    p.add_argument("--rebuild-demo", action="store_true", help="Rebuild static/demo.html after parsing")

    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.excel, args.requests, args.manifest, args.model, args.source_question)
    elif args.command == "submit":
        submit(args.requests)
    elif args.command == "status":
        status(args.batch_id)
    elif args.command == "download":
        download(args.batch_id, args.output)
    elif args.command == "parse":
        parse(
            args.batch_output,
            args.manifest,
            args.excel,
            args.evidence,
            args.run_id,
            status_path=args.status_file,
            batch_id=args.batch_id,
            model=args.model,
            rebuild_demo=args.rebuild_demo,
        )


if __name__ == "__main__":
    main()
