# Architecture

## עיקרון

`תא מספרי → רשומות הציון → response_id → אמירות פתוחות → evidence_links`

## שכבות

1. **Excel loader** — קורא את `נתונים גולמיים` ואת `מיפוי וחישובים`.
2. **Numeric long model** — שורה לכל `response_id × question_id`.
3. **Metric engine** — מחשב את המטריצות בזמן אמת מהגלם.
4. **Semantic evidence pipeline** — Batch LLM ללא ציונים מספריים.
5. **Evidence join** — מחבר אמירה לציון של אותו משיב רק בתצוגה.
6. **Relation logic** — תומכת/סותרת נקבע באופן דטרמיניסטי לפי כיוון הפער.
7. **UI renderers** — `app.py` מציג את החוקר ב-Streamlit, ו-`build_demo.py` מייצר את `static/demo.html` עם הנתונים משובצים והאינטראקציות הסטטיות.

## אבטחת אמינות

- אין hard-code של ממוצעים מה-Excel המסכם.
- כל metric מחושב מחדש מהנתונים הגולמיים.
- התפלגות ציונים, סטיית תקן, hover וגרפי Drill-down מחושבים מרשומות הציון, לא מטבלת סיכום.
- לכל evidence נשמרים answer_id, response_id, ציטוט, הסבר, model, prompt_version ו-run_id.
- המודל אינו מקבל את הציון ולכן אינו מחפש הצדקה לתוצאה.
- קבוצות קטנות מסף הפרטיות מוסתרות.
- `static/demo.html` הוא תוצר בנייה: מקור האמת לתצוגה הסטטית הוא `build_demo.py`, ויש לבנות מחדש אחרי שינוי.

## Public demo architecture

`build_public_demo.py` creates a separate shareable artifact, `static/public_demo.html`, instead of anonymizing the internal `static/demo.html` in place.

The public builder:

- uses a fixed, fictional question catalog without reading the private workbook;
- generates 5 synthetic teams and fake respondent IDs;
- generates synthetic numeric scores with different team profiles so the UI has useful variance;
- generates synthetic free-text evidence comments with positive, negative, and neutral directions;
- uses fake source rows such as `DEMO-9001`;
- supports checking rendered HTML against an explicitly supplied set of forbidden names. The build does not read private files to discover names; publication checks must verify the generated artifact separately.

The public HTML is a built artifact. The source of truth is `build_public_demo.py` plus the current static UI template extracted from `build_demo.py`.

## Multiple workbook layouts

`load_model` first looks for a matching private profile. A sidecar named `<workbook-stem>.profile.json`, or a local profile with the same sheet/header fingerprint for an upload, selects the form loader. Without a matching profile, the original two-sheet loader is used. Duplicate matching profiles and changed sidecar headers are rejected.

A profile maps physical columns and respondent roles to logical questions. Corresponding branch questions share a question ID, while the numeric records retain their actual source column, row, sheet, and question wording. Role mismatches, duplicate branch answers, and invalid scores are rejected. A profile can explicitly exclude zero as not relevant; excluded values never reach the metric engine. The internal `team` and `tenure` fields remain compatible with the original engine, while survey metadata supplies the actual group and role labels.

Both renderers filter responses by role and restrict question eligibility to the selected audience. Comparison means use the active role cohort. The HTML exporter accepts explicit input/output paths and can serve a single generated artifact on localhost with `Cache-Control: no-store`.

## Source answers and classified evidence

The source-answer tab groups informative answers by logical open question and then role, using a single collapsible question heading. It selects only respondents contributing valid scores to the selected numeric cell. Source comments are not presented as evidence for that question until separately classified.

Batch preparation filters the question catalog by domain and role eligibility, and can optionally restrict the source open-question IDs. Model payloads contain the source prompt, answer text, and eligible question catalog; scores and respondent context are excluded from those payloads. The local manifest retains the respondent join and workbook fingerprint. Parsing checks that fingerprint and question eligibility; profile-backed renderers reject evidence from other workbook versions.

For profile-backed surveys, evidence/status artifacts are named per workbook. Preparing requests, submitting a batch, downloading output, parsing evidence, and rebuilding HTML are distinct operations. Local automation may chain these steps, but a submitted or processing batch must not be reported as applied evidence. The generic CLI does not automatically monitor submitted jobs.
