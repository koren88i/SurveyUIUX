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
- public synthetic demo payload generation and leak validation.

Private survey counts, team names, source rows, batch IDs, and evidence totals are intentionally not documented in tracked files.

## Public Demo Validation

`build_public_demo.py` generates `static/public_demo.html` from synthetic data only:

- 5 fake teams;
- 50 fake respondents;
- generated numeric scores;
- synthetic open-text evidence;
- fake `DEMO-*` source rows.

The public demo must not include real respondent data, internal team names, or generated private evidence artifacts.