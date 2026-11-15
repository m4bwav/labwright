# Research: labwright

## Current understanding (2026-11-15)

- ComfyUI exposes `/system_stats`, `/queue`, `/models` and `/models/<folder>` as GET endpoints; `/system_stats` does not report disk.
- Ollama exposes `/api/tags` (installed) and `/api/ps` (loaded) as GET endpoints.
- `nvidia-smi --query-gpu` and `--query-compute-apps` give load and processes on the local host only; on Windows the process list includes desktop graphics apps.
- In-path balancers (Olla, LiteLLM, ComfyUI-Distributed) route requests; labwright only reads and advises, and could point at them later.

## Open questions

- Remote GPU load for hosts without a local probe (Apple silicon, other Linux boxes).
- A disk figure for hosts whose HTTP APIs report none.

## Search plan

- subject: ComfyUI server routes changelog; Ollama API docs changes.
- tooling: `path:SKILL.md comfyui ollama status` on GitHub; MCP registry search "gpu pool".
- practice: how people share one GPU between ComfyUI and Ollama.
- testing: fake-server unit tests for HTTP probes.

## Log

- R-20261115-1 · subject · ComfyUI and Ollama read endpoints confirmed against live servers on the first run · magnitude 0
