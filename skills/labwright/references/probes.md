# Probes (all GET)

| Server | Endpoints | Used for |
|---|---|---|
| ComfyUI | `/system_stats` | up, device name, VRAM |
| ComfyUI | `/queue` | running and pending counts |
| ComfyUI | `/models`, `/models/<folder>` | inventory for `where` |
| Ollama | `/api/tags` | up, model tags |
| Ollama | `/api/ps` | loaded models |
| local | `nvidia-smi --query-gpu`, `--query-compute-apps` | load, memory, processes |
| local | `nvidia-smi --query-gpu` temperature.gpu, power.draw | `temp_c`, `power_w` in status (skipped when [N/A]) |
| local | disk usage | free space per store |
| local | `<comfyui_dir>/user/__manager/snapshots`, `custom_nodes` mtimes | doctor: snapshot older than the newest node pack |

## The one write: `lw.py free --host H [--apply]` (lw_free.py)

Frees VRAM before a big job: unloads loaded Ollama models (`/api/generate` with `keep_alive: 0`), then ComfyUI `POST /free` (`unload_models`, `free_memory`). Without `--apply` it only prints the guard verdict. It refuses unless the host is local, every ComfyUI queue answers and is empty, GPU load is under `idle.gpu_busy_pct`, and no other GPU process holds memory (one python = ComfyUI; Ollama; `free.allow_processes`).
Windows (WDDM) lists every desktop app in `--query-compute-apps` with memory `[N/A]`: those are ignored, but a second python with `[N/A]` refuses (it may be a trainer). Never run it against another session's job; a refusal means wait or lighten the job.

Timeout 3 s per request. Use 127.0.0.1 rather than localhost for local IPv4 services. Apart from `free`, nothing here starts, stops or changes a server; a test fails if lw.py ever gains a write request or process control (the write lives in lw_free.py).
