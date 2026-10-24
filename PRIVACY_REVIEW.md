# Publication privacy review

Reviewed on 2026-10-24 for the public source release.

## Included in the release

- Application source, documentation, tests, and fictional CSV examples.
- A public HTML demo containing a fixed fictional question catalog, five fictional teams, 50 generated respondents, generated scores, and invented comments.
- Generic application branding and a generic local workbook path, `data/survey.xlsx`.
- README screenshots rendered exclusively from the synthetic public demo, including overview, scores, evidence, and source lineage. No private app session or survey export was used for the images.

The shipped demo payload was compared with the deterministic synthetic generator. A test also builds the same demo in a directory containing only the UI template, without access to private survey files.

## Kept local

Real workbooks, survey answers, evidence links, batch inputs/outputs, and the private HTML export are excluded from the release. Ignore rules also block workbook, JSONL, database, and private-key files outside the data directory. Ignore rules do not protect files already tracked or files deliberately force-added.

The reviewed public files had no exact matches for local team names of at least three characters, open answers of at least 30 characters, or private question wording of at least 30 characters. Pattern checks found no recognizable API tokens, private keys, email addresses, or personal Windows paths in those files. These checks supplement source review; they are not a guarantee against every possible identifying detail or secret format.

Publication checks cover the committed file inventory, recognizable secrets and personal paths, synthetic demo payload, and Git author and committer emails. Automated checks reduce accidental disclosures but cannot erase previously downloaded copies or guarantee removal of old commit objects cached by the hosting service.

## Runtime boundaries

The local app and private HTML exporter expose raw responses and source-row lineage to their viewer. Minimum-group display thresholds do not anonymize the embedded data in an HTML export. Only the synthetic demo is suitable for public sharing.

The optional batch submission sends open-answer text and question metadata to an external API. This review did not submit survey data or anonymize the private source files.

Validation includes synthetic artifact checks, column-mapping compatibility, and publication guard checks. Only aggregate outcomes are recorded here.
