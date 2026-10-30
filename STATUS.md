# Current status

Updated: 2026-10-30.

- Both the original two-sheet workbook and locally configured form workbooks use the same numeric/evidence pipeline. Direct CSV import and an in-app profile editor are not implemented.
- Profiles support role routing, shared and role-specific questions, physical source-cell lineage, and explicitly excluded not-relevant zeros.
- Streamlit supports local workbook selection. The private HTML exporter accepts explicit workbook/output paths and provides a single-artifact localhost server.
- The HTML URL and the explicit output file contain the same artifact, which also opens directly in a browser. Presentation filenames can stay stable across input revisions; the private handoff identifies the active source version.
- Both views expose source answers grouped under one heading per question, with role labels and response counts. Classified evidence remains separate from source answers.
- HTML presentation controls keep the group selector enabled in every view and can mask all other group names while retaining the selected name and unchanged scores/order. This masks the display, not the embedded export data.
- Batch preparation supports explicit open-question scopes and audience-eligible catalogs. Workbook fingerprints prevent evidence from being joined across versions. Submission and application are separate operations.
- Latest verification: 32 tests passed; known pandas deprecation warnings remain. Browser visual verification was unavailable. See [validation](VALIDATION.md).
- Public outputs remain synthetic. All real survey artifacts, local profiles, and local completion automation stay ignored under `data/`.

Use [the handoff](SESSION_HANDOFF.md) for continuation and [the import guide](docs/SURVEY_IMPORT.md) for another survey. Private runtime paths and outcomes belong in the local `data/SESSION_HANDOFF.md`, not this document.
