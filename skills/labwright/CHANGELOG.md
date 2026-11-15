# Changelog: labwright

- C-20261115-2 · 0.2.0 · First public release: held VRAM on idle hosts is reported, pick adds --vram notes when a job will not fit, README with banner, SECURITY.md, version in the marketplace and evergreen.json. because: the owner ruled labwright public with a private sidecar.
- C-20261115-1 · 0.1.0 · First version: lw.py (hosts, status, where, pick, place, doctor), registry format, idle rules, placement, probes, unit and leak tests. because: one read-only view of the user's model servers replaces host facts copied into several skills.
- C-20261115-3 · unreleased · SKILL.md: shared-server OOM goes to /free, wait or a lighter job; starting Ollama sets OLLAMA_MODELS first. because: the with-skill eval pass found never-restart-others and ollama-models-env passed only on model priors.
