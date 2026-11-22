# Learnings: labwright

Lessons that shaped [SKILL.md](SKILL.md) and lw.py. Seeded 2026-11-15 from a harvest of one owner's agent memory, environment profile and neighbouring skills' LEARNINGS files (52 lessons; only the general ones are here, the owner-specific ones live in the private sidecar). Harvest numbers in brackets. Entry shape: `L-NNN code-name · date · source · lesson · fix`.

- L-001 `split-batch-idle-hosts` · 2026-11-15 · image-generation skill learnings [2] · Queueing a batch behind a busy host while another sits idle wastes hours. · `pick --batch` names every idle host; one runner per host on disjoint items.
- L-002 `any-host-order-and-say-down` · 2026-11-15 · image-generation skill [5, 6] · When the needed host is down, a silent fallback to another source or a smaller model gives the wrong result. · `pick` returns `none` with the reason; say so.
- L-003 `record-hardware-changes` · 2026-11-15 · environment profile, music skill learnings [10] · A GPU swap sat unrecorded for months while skills reasoned about the old card. · `doctor` flags registry drift; update the registry and the shared environment file.
- L-004 `probe-before-model-list` · 2026-11-15 · text-offload skill learnings [12, 15] · Served model lists drift (auto-updates, other sessions' pulls). · `status` and `where` probe live; the registry is a dated snapshot.
- L-005 `licence-and-gating-first` · 2026-11-15 · image-generation skill learnings [16] · Gated or restrictively licensed weights waste a download. · Check licence and gating before `place`.
- L-006 `disk-floor` · 2026-11-15 · agent memory [20] · A download is fine without asking while the drive keeps the floor after it. · `place --size`, floor from the registry.
- L-007 `models-env-before-serve` · 2026-11-15 · text-offload skill learnings [23] · Starting `ollama serve` without OLLAMA_MODELS hides existing models. · Record the store path in the registry; set the variable before serving.
- L-008 `queue-behind-busy` · 2026-11-15 · agent memory [28, 30] · A busy shared server is not a stop point; waiting on one pid misses other sessions' jobs. · `pick` returns `queue`; wait until the queue and GPU are idle, with a deadline.
- L-009 `empty-queue-not-free-gpu` · 2026-11-15 · image-generation skill learnings [29, 35] · Training and scripts hold the GPU outside the queue; a loaded Ollama model takes VRAM from renders. · Busy also on GPU load and loaded Ollama models.
- L-010 `idle-definition` · 2026-11-15 · idle-watcher docs [31] · Down is never idle; read idle twice before an unattended start. · references/idle.md.
- L-011 `wait-needs-fail-and-deadline` · 2026-11-15 · agent memory [36, 37] · Success-only waits hang and leave the GPU idle. · quirkwright `qw.py wait`.
- L-012 `kaggle-cloud-lane` · 2026-11-21 · comfyui-gen kaggle_video.py · Kaggle's free T4 (~30 GPU h/week) is a remote video lane outside the pool: `pick` cannot see it and it never holds local models. · When both PC video hosts are busy and the job is a draft, offer comfyui-gen `kaggle_video.py`; quota is per week, so say how much a batch will use.
- L-012 `never-restart-shared` · 2026-11-15 · several skills [41, 45, 50] · Restarting or killing by image name ended other sessions' servers. · lw.py has no write or process control (tested); the agent stops only what it started, by pid.
- L-013 `127-not-localhost` · 2026-11-15 · environment profile [44] · localhost can cost seconds per call on IPv6-first hosts. · Registry URLs use 127.0.0.1.
- L-014 `vram-held-is-not-load` · 2026-11-15 · first real run · An idle ComfyUI holds most of the card's memory in cached weights at 0% load, and on Windows nvidia-smi lists desktop apps as processes. · Busy is decided by load, queue and loaded models, not memory held or process count.
- L-015 `up-is-not-ready` · 2026-11-21 · Nygard, Release It! ch. 13, ch. 5 "Handshaking" · A port that answers is not a host ready for work: one being drained or with a long queue makes callers discover overload by timing out. · `ready` only when idle and not draining; `idle.max_pending` makes `pick` shed instead of queue.

Not taken (owned by neighbours): HF download habits [24], Manager installs [25], empty extra_model_paths crash [27], VRAM unload [33], Ollama cold-load 500 [34], watchdogs [38], start-command fixes [40-43], msys pids and reboot checks [46, 47].
