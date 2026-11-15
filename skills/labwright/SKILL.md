---
name: labwright
description: "The user's local AI servers (ComfyUI, Ollama) as one read-only pool: which machine is up, idle or busy, where a model lives, which host takes a job or which to queue behind, which drive can take a download above the free-space floor, registry drift. lw.py status, where, pick, place, doctor. Use on 'which of my machines', 'is the GPU free', 'which server is idle', 'where is model X', 'where can this download go', 'are my AI servers up', 'check the pool'. Not for workflows (comfyui-gen), text offload (local-delegate), killing processes or waits (quirkwright), or music (musicwright)."
---

# Labwright

The pool of the user's own model servers, read live. Host facts live in the registry, never in this file.

## Step 0

1. Read `evergreen.json` (freshness, see Maintenance).
2. Registry: `$LABWRIGHT_HOME/hosts.json` (format: [registry](references/registry.md); start from `hosts.example.json`). Read `LEARNINGS-private.md` there too if it exists: owner rules about hosts and models. Nothing from that folder goes into this repository.

`LW` below means `python "<this folder>/scripts/lw.py"` (Python 3.10+, stdlib).

## Use

- Before quoting a host, a model list or a GPU as free: `LW status` (idle, busy or down, with the reason). The registry is a dated snapshot; the probe is the truth.
- Where is a model: `LW where <name>`.
- Which host for a job: `LW pick --role image|video|music|llm|train [--model M] [--vram GB] [--batch]`. `run` names the idle host (every idle host for `--batch`: split the work across them); `queue` names the busy host to queue behind and wait on ([idle rules](references/idle.md)); `none` means nothing capable is up: say so, never swap in another source silently.
- Before a model download: `LW place --size GB` ([placement](references/placement.md)); then check the model's licence and gating.
- New machine, hardware change or odd results: `LW doctor`; record a hardware change in the registry and the shared environment file.

lw.py only reads. Running, waiting on, stopping or restarting anything is the caller's job; another session's server is never stopped or restarted ([probes](references/probes.md)). Out of memory on a shared server: unload (ComfyUI `POST /free`), wait or lighten the job. Starting a stopped Ollama: set `OLLAMA_MODELS` to the registry's store first, or its models vanish.

Neighbours: comfyui-gen runs image and video jobs; local-delegate offloads text to Ollama; quirkwright has real pids and wait loops (`qw.py wait`); musicwright and voicewright own their models.

## Maintenance

Evergreen unit: follows the Evergreen Protocol in the installed evergreen plugin; see [MAINTENANCE.md](MAINTENANCE.md). Files: [RESEARCH.md](RESEARCH.md), [CHANGELOG.md](CHANGELOG.md), [LEARNINGS.md](LEARNINGS.md), [TESTS.md](TESTS.md), `evals/evals.json`, `evergreen.json`, `harvest.json` (source lessons the cases cite).
