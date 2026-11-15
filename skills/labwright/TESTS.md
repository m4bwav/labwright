# Tests: labwright

Cases in `evals/evals.json` (12 behaviour cases, 4 decoys). Script tests: `python -m unittest discover -s tests` from the repo root (lw.py, read-only source check, leak test). A case passes on evidence outside the transcript.

Entry shape: `### T-YYYYMMDD-n · date · harness · env · passed/total`. Newest first.

## Runs

### T-20261115-2 · 2026-11-15 · python unittest · repo · 25/25 (leak test with the private term list)

### T-20261115-1 · 2026-11-15 · claude-code, one agent per case · baseline (no skill) · 12/12
- Every behaviour rule passed bare (memory index present, so not a clean bare run). SKILL.md prose stays thin; the value is lw.py and the registry.
- Skill-on runs and the decoys are still owed.
