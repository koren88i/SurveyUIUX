# Session handoff

Updated: 2026-10-30.

## Entry points

- [STATUS.md](STATUS.md): current capabilities and limitations.
- [README.md](README.md): launch instructions and UI walkthrough.
- [docs/SURVEY_IMPORT.md](docs/SURVEY_IMPORT.md): profile schema and evidence lifecycle.
- [ARCHITECTURE.md](ARCHITECTURE.md): data flow and role/evidence boundaries.
- [VALIDATION.md](VALIDATION.md): automated coverage and QA limitations.

## Resume work

1. Check `git status --short` and remotes before editing or publishing. This workspace and a separate publication checkout may have different remotes. Do not unarchive or repoint a remote as a routine sync step.
2. Read the ignored local `data/SESSION_HANDOFF.md` for the active survey and runtime snapshot. Confirm endpoints and files again before reporting them as current.
3. Use Streamlit for interactive source selection, or build HTML with an explicit workbook/output pair. HTML embeds its data and must be rebuilt after source, profile, evidence, or template changes.
   The HTML server serves the exact `--output` file, which also opens directly in a browser. A stable output filename can contain results from a newer input version; consult the private handoff and verify the served bytes rather than inferring the version from the HTML filename. Do not run the default original-workbook build to refresh a profile-backed survey.
   For presentations, the HTML group selector works in every view. Select the group to identify, then enable peer-name masking. Anonymous labels apply throughout the rendered view; source data remains private and unchanged.
4. Inspect existing submission receipts and watcher state before starting a batch. Do not submit again merely because the UI has not refreshed. Any new external submission needs the owner's authorization for its scope.
5. Run `python -m pytest -q` after code changes. For UI-template changes, regenerate the synthetic demo with `python build_public_demo.py` and verify the private artifact separately.
6. Stage explicit source/documentation paths, run `git diff --cached --check` and `python scripts/check_public_release.py --staged --check-identity`, then commit. Apply the same checks in the actual publication checkout before pushing.

## Remaining limitations

New questionnaire layouts require a reviewed local profile; there is no automatic mapping wizard or direct CSV loader. Generic batch submission does not start a completion watcher. `parse --rebuild-demo` still rebuilds the original default workbook; profile-backed outputs require an explicit build command. Source-answer filtering follows respondents with valid scores in the selected cell, so it is not an all-comments browser for an entire survey. Browser visual QA remains outstanding.
