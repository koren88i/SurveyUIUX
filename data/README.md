# Local private data

This directory is intentionally ignored by Git except for this note and `.gitkeep`.

Place the private survey workbook and generated batch/evidence artifacts here when working locally. Do not commit real respondent data, generated evidence JSONL, batch request/output files, or private static exports.

Expected private filenames used by the app/scripts:

- `survey.xlsx`
- `batch_requests.jsonl`
- `batch_output.jsonl`
- `open_answer_manifest.csv`
- `evidence_links.jsonl`
- `evidence_status.json`

See `samples/` for fake CSV examples that document the expected shape.

For an active private survey, consult the local `SESSION_HANDOFF.md` in this directory. It records the current workbook version, matching profile, per-workbook evidence paths, presentation HTML path, and restart command. This handoff is ignored by Git. A stable HTML filename can contain results from a newer workbook; it is not necessarily named after its current input. The localhost HTML server serves the selected output file directly, and that file can also be opened in a browser without the server.
