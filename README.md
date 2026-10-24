# Survey Question Lineage App

A local survey explorer for tracing a question-level result back to the responses that produced it. The Streamlit interface is in Hebrew. It shows numeric scores, source Excel rows and columns, and, when available, related statements extracted from open-text answers.

## See the interface

These screenshots show the [static public demo](static/public_demo.html). The controls are in Hebrew, with fictional English questions and comments. **All teams, respondents, scores, and comments shown here are synthetic.**

### 1. Compare teams at a glance

Choose a metric from the dropdown, then compare teams in the heatmap. Hover over a column heading to read the full question. The annotated image shows both interaction states together; the heatmap displays each team's difference from the overall average across six example questions.

![Annotated survey overview with the metric dropdown expanded and a pointer on the Manager context heading revealing the full question](docs/images/overview.png)

### 2. Open a result and inspect the scores

Select a cell to see the group's average, response count, comparison with other teams, and raw score distribution. The demo also lets you exclude a respondent temporarily to explore how the result changes.

![Question drill-down showing summary metrics, team comparison bars, a score histogram, and fictional respondent rows](docs/images/score-drilldown.png)

### 3. Read the comments linked to a result

The evidence tabs show statements classified as supporting or qualifying the numeric result. Each card includes the statement, explanation, and respondent context, with an expandable source answer.

![Supporting evidence tab with synthetic statements linked to the selected question](docs/images/linked-evidence.png)

### 4. Trace a result to its source

The Lineage tab lists the source column and response rows, together with the group mean, overall mean, and calculated difference. The demo uses fictional `DEMO-*` source rows.

![Lineage tab showing a source column, fictional Excel row references, and the calculation behind the selected result](docs/images/source-lineage.png)

## What you can explore

- Compare questions across the whole survey, teams, tenure groups, or a team split by tenure.
- Switch between mean score, difference from the overall mean, share of scores 8–10 or 1–5, standard deviation, and response count.
- Select a heatmap cell to inspect its raw score distribution, team comparison, source Excel lineage, and related evidence.
- Filter by survey domain and set a minimum respondent count for each group. Groups below the threshold are hidden.
- View positive and negative open-text statements linked to a question. Their support or contradiction of the numeric result is determined after classification.

## Quick start

Requires Python 3.10 or newer. From the project directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On macOS or Linux, activate with `source .venv/bin/activate` instead. `run_app.bat` and `run_app.sh` also create the environment, install dependencies, and start the app.

The app needs a survey workbook. Upload an `.xlsx` file in the sidebar, or put it at `data/survey.xlsx` for local use. If no workbook is available, the app displays an upload prompt.

The workbook must contain these sheets:

| Sheet | Required content |
| --- | --- |
| `נתונים גולמיים` | One row per respondent; `צוות` and `זמן בצוות` columns; numeric question columns whose headers match the full question text in the mapping; optional supported open-answer columns. |
| `מיפוי וחישובים` | A question table with `תחום`, `ממד`, `תווית קצרה`, `נוסח מלא`, and `עמודת מקור`. The loader finds the header row automatically. |

The fake CSVs in [`samples/`](samples/README.md) illustrate the expected data shape. They are examples only; the app loads Excel workbooks, not CSV files.

## Demos

Open [`static/public_demo.html`](static/public_demo.html) directly in a browser to try the interactive explorer with synthetic teams, respondents, scores, and comments. Regenerate it with:

```bash
python build_public_demo.py
```

For a private, self-contained HTML export of a local workbook, run `python build_demo.py`. This writes `static/demo.html`. Treat that output as private survey data; it is ignored by Git.

## Optional open-text evidence

Numeric analysis works without evidence files. To show classified open-text statements alongside scores, upload a matching evidence JSONL file in the sidebar or generate `data/evidence_links.jsonl` with the batch pipeline below. If you upload a different workbook without matching evidence, the app shows numeric lineage only.

The pipeline sends informative open answers and the question catalog to the OpenAI Batch API. It asks the model to split answers into individual statements, match them to questions, and label their direction. **Survey scores are not included in those model requests.** Review your organization's data handling requirements before submitting real responses to the API.

After setting `OPENAI_API_KEY`, run these commands from the project directory (replace `BATCH_ID` with the returned ID):

```bash
python semantic_batch.py prepare --excel data/survey.xlsx --requests data/batch_requests.jsonl --manifest data/open_answer_manifest.csv
python semantic_batch.py submit --requests data/batch_requests.jsonl
python semantic_batch.py status --batch-id BATCH_ID
python semantic_batch.py download --batch-id BATCH_ID --output data/batch_output.jsonl
python semantic_batch.py parse --batch-output data/batch_output.jsonl --manifest data/open_answer_manifest.csv --excel data/survey.xlsx --evidence data/evidence_links.jsonl --status-file data/evidence_status.json --batch-id BATCH_ID
```

Add `--rebuild-demo` to `parse` to update the private static HTML export after parsing. Batch preparation and parsing can be run locally; submission, status, and download require API access.

## Privacy and project layout

Real workbooks, batch artifacts, evidence files, and `static/demo.html` belong on the local machine and are excluded by [`.gitignore`](.gitignore). The tracked public demo uses generated data. Keep any exported HTML containing real survey data private.

The generic local workbook filename is `data/survey.xlsx`. The public demo uses fictional questions as well as fictional responses; it never loads the local workbook. See [the publication privacy review](PRIVACY_REVIEW.md) for scope and limitations.

For different open-question headers, an optional local `data/open_question_columns.json` can map the keys `manager_keep`, `manager_change`, `team_jump`, and `team_keep` to your workbook's column names. This file is excluded from publication.

Before publishing, run `python scripts/check_public_release.py --staged`. The check scans the exact staged files against the public-file allowlist, rejects common secrets and personal metadata, and verifies that the embedded demo data matches the synthetic generator. Enable local commit and push checks with `git config core.hooksPath .githooks` and configure your GitHub noreply email with `git config user.email YOUR_GITHUB_NOREPLY_ADDRESS`. The push hook permits only `main` and checks every commit it would publish. GitHub also runs the check on pushes and pull requests; CI detects a leak after a push and cannot prevent its initial publication. Add a required status check in your repository rules if you want GitHub to enforce a passing check before merging. Hooks can be bypassed and do not replace review.

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit interface and drill-down. |
| `survey_loader.py` | Excel parsing and normalized response records. |
| `metrics.py` | Matrix metrics, grouping, and score distributions. |
| `semantic_batch.py`, `evidence.py` | Evidence generation, loading, and joining to responses. |
| `build_demo.py`, `build_public_demo.py` | Private and synthetic static HTML builders. |

See [architecture](ARCHITECTURE.md) for the data flow and [validation](VALIDATION.md) for test coverage. Run the tests with `python -m pytest -q`.
