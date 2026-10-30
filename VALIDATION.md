# Validation Status

## Automated Checks

Run:

```bash
pytest -q
```

The test suite covers:

- private fixture loading when local private data is present;
- matrix and drilldown smoke behavior without committing private expectations;
- privacy masking at high minimum-respondent thresholds;
- deterministic support/contradiction relation logic;
- batch request shape and parser behavior when local batch fixtures are present;
- Streamlit/Plotly selected-cell parsing helpers;
- public synthetic demo payload generation and leak validation;
- profile-backed branched forms, shared-question pairing and physical source lineage;
- exclusion of not-relevant zeros from means, response counts, percentages, and privacy thresholds;
- matching profiles for uploaded workbook bytes, rejecting changed headers and unexpected branch data;
- audience-specific batch question catalogs and workbook fingerprint tagging;
- rejection of mismatched evidence and manifests before replacing prior output;
- explicit open-question request scopes;
- exported HTML role filtering, source-answer role separation, and physical cell lineage using a Node runtime with an in-memory DOM test double.
- always-enabled HTML group selection and peer-name masking across matrix labels, comparison/details, tooltips, source text, selector options, and exclusion chips; scores, internal selection keys, and manual row order are preserved.

Latest local verification on 2026-10-30: **32 tests passed**. Two existing pandas `stack` deprecation warnings remain in private-fixture smoke tests. The JavaScript runtime check requires Node and skips when Node is unavailable. Private-fixture checks can also skip when their local inputs are absent.

Streamlit's test harness was also exercised against local original and profile-backed workbooks, including grouping modes, role filters, empty selections, and switching sources. Full browser visual inspection was unavailable in this session; runtime and HTTP checks do not replace visual QA.

Private survey counts, team names, source rows, batch IDs, and evidence totals are intentionally not documented in tracked files.

## Public Demo Validation

`build_public_demo.py` generates `static/public_demo.html` from synthetic data only:

- 5 fake teams;
- 50 fake respondents;
- generated numeric scores;
- synthetic open-text evidence;
- fake `DEMO-*` source rows.

The public demo must not include real respondent data, internal team names, or generated private evidence artifacts.
