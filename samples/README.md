# Public sample input

These CSVs are fake and safe to commit. They document the shape expected by the private Excel workbook.

The production loader currently expects an Excel workbook, not these CSVs directly. The workbook contains:

- a raw responses sheet with respondent metadata, numeric score columns, and open-text columns;
- a question mapping sheet that maps each numeric question to its domain, dimension, short label, full text, and source column.

`sample_responses.csv` shows fake respondent rows. `sample_question_mapping.csv` shows fake question metadata.