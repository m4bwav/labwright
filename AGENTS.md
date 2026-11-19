# AGENTS.md: labwright

Claude Code plugin (one skill): the user's local AI servers (ComfyUI, Ollama) as one read-only pool.

- Layout: `.claude-plugin/plugin.json`; `skills/labwright/` (SKILL.md, references/, scripts/lw.py, hosts.example.json, evals/, evergreen files); `tests/`.
- Before committing: `python -m unittest discover -s tests` with `LABWRIGHT_HOME` pointing at the private sidecar so the leak test runs (it skips when unset).
- lw.py stays read-only: HTTP GET and local read commands only. `tests/test_lw.py` fails on write verbs or process control in its source. The single guarded write (`free`: Ollama unload, ComfyUI /free) lives in `scripts/lw_free.py`, acts only with `--apply` and refuses unless its guards pass; never add process control.
- Never put real hosts, addresses, ports, paths or names in a tracked file, ai-docs/ included. The real registry (`hosts.json`) and owner notes live in `LABWRIGHT_HOME`.
- Python edits keep LF line endings; write Python with backslashes via a file tool, not a Bash heredoc.
- State and handoff: [ai-docs/HANDOFF.md](ai-docs/HANDOFF.md), log [ai-docs/log.md](ai-docs/log.md), index [ai-docs/INDEX.md](ai-docs/INDEX.md).
