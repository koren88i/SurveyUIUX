# Import another survey

## Choose the workbook format

The original format has raw-response and question-mapping sheets, documented in the [README](../README.md). A form export with a different layout needs a private profile under `data/`. CSV files are examples only and cannot be loaded directly.

If question headers, routing values, and column positions stay the same, an existing profile can load new responses. Uploaded workbooks match local profiles by sheet name and the exact header fingerprint. Changed wording or structure requires a reviewed profile update. Keep separate survey artifacts instead of overwriting another survey's evidence.

## Private profile schema

This is a fictional example; replace the placeholders locally. Do not publish actual question text or respondent information.

```json
{
  "label": "Example survey",
  "sheet": "Form",
  "header_fingerprint": "SHA256_OF_ORDERED_HEADERS",
  "group_column": "Group",
  "split_column": "Role",
  "group_label": "Group",
  "split_label": "Role",
  "zero_is_missing": true,
  "questions": [
    {
      "question_id": "example_clarity",
      "label": "Clarity",
      "domain": "manager",
      "domain_label": "Leadership",
      "dimension": "Shared",
      "audience": "all",
      "sources": [
        {"column": "C", "role": "member"},
        {"column": "D", "role": "lead"}
      ]
    }
  ],
  "open_questions": [
    {
      "question_id": "example_keep",
      "domain": "manager",
      "sources": [
        {"column": "E", "role": "member"},
        {"column": "F", "role": "lead"}
      ]
    }
  ]
}
```

Save this beside `data/example.xlsx` as `data/example.profile.json`. Compute the fingerprint with `survey_loader.header_fingerprint` from the sheet's ordered pandas column names. The configured group and role columns must be present. `audience` is either `all` or an exact role value. Question IDs must be unique, stable, and specific to the questionnaire. Map branch questions together only after confirming they measure the same statement; do not assume repeated columns have the same order.

Each source column uses Excel letters and an optional exact role value. The loader rejects populated branch columns belonging to other roles and duplicate answers to one logical question. Valid scores are integers from 1 to 10. With `zero_is_missing`, zero is excluded before calculating averages, percentages, response counts, and privacy thresholds. Blank form-branch cells stay absent rather than becoming zero scores.

## Build the private explorer

```bash
python build_demo.py --excel data/example.xlsx --output data/example.html
python build_demo.py --excel data/example.xlsx --output data/example.html --serve --port 8502
```

The second command builds and serves the file on loopback. Only the selected HTML is served; source workbooks and manifests are not HTTP routes. Keep the process running to use its local URL. Rebuild after changing the workbook, profile, evidence, or template. Streamlit instead loads the selected workbook directly from the sidebar.

## Generate evidence separately

First confirm the question scope and authorization to send real open answers to the external API. Preparing requests does not send them. Set `OPENAI_API_KEY` without committing it.

```bash
python semantic_batch.py prepare --excel data/example.xlsx --requests data/example_batch_requests.jsonl --manifest data/example_open_answer_manifest.csv
python semantic_batch.py submit --requests data/example_batch_requests.jsonl
python semantic_batch.py status --batch-id BATCH_ID
python semantic_batch.py download --batch-id BATCH_ID --output data/example_batch_output.jsonl
python semantic_batch.py parse --batch-output data/example_batch_output.jsonl --manifest data/example_open_answer_manifest.csv --excel data/example.xlsx --evidence data/example_evidence_links.jsonl --status-file data/example_evidence_status.json --batch-id BATCH_ID
python build_demo.py --excel data/example.xlsx --output data/example.html
```

Optionally repeat `--source-question OPEN_QUESTION_ID` during preparation to restrict the included questions. Record the returned batch ID locally before continuing; inspect that existing job instead of resubmitting when results are delayed. The generic CLI has no background monitor. A local watcher, if separately configured, must download, parse, and rebuild without submitting another paid job.

Inspect parsed coverage and errors before reporting completion. Some classified answers can legitimately produce no question links. Source answers remain readable independently; the supporting/qualifying tabs use classified links. The workbook fingerprint in the manifest and evidence must match the current input, and role-specific questions remain restricted to the matching role.

## Keep private artifacts local

Keep profiles, original answers, manifests, requests, outputs, status files, batch receipts, private HTML, and any watcher scripts under ignored `data/`. HTML includes raw source answers and scores even when filters hide them. Use the synthetic public demo for sharing. Check the exact staged inventory and publication guards before any Git push.
