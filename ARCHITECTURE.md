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
