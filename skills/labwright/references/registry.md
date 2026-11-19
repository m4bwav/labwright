# Registry format

`$LABWRIGHT_HOME/hosts.json` (or `lw.py --hosts FILE`). Example: [hosts.example.json](../hosts.example.json).

Top level: `floor_gb` (free space a download must leave, default 100), `idle.gpu_busy_pct` (GPU load at or above which a host is busy, default 15), `runs_file` (optional JSON lines `{model, peak_vram_gb}`, e.g. comfyui-gen's `score_data/runs.jsonl`: `pick --model` without `--vram` uses the highest matching peak), `hosts` (list).

Per host:
- `name`, `os`, `local` (true when this machine can read its GPU and disks directly).
- `gpu` `{name, vram_gb}` for a discrete card, or `unified_gb` for shared memory. `doctor` compares `gpu.name` and `vram_gb` with what ComfyUI and `nvidia-smi` report.
- `ram_gb`, `speed` (relative; `pick` tries faster hosts first).
- `roles`: any of image, video, music, llm, train.
- `services`: `{type: comfyui|ollama|http, url}`; `http` takes an optional `health` path.
- `stores`: `{path, kind}`; remote stores may carry `free_gb` and `free_checked` (a dated figure, used when the disk cannot be read).
- `comfyui_dir` (local hosts): ComfyUI root; `doctor` warns when its newest ComfyUI-Manager snapshot is older than the newest `custom_nodes` folder.
- `free.allow_processes`: extra GPU process names `free` may ignore.
- `notes`: free text for owners, install rules and quirks.

A hardware change goes into the registry the day it happens; skills that reason about an old card waste runs.
