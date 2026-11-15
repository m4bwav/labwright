# Probes (all GET)

| Server | Endpoints | Used for |
|---|---|---|
| ComfyUI | `/system_stats` | up, device name, VRAM |
| ComfyUI | `/queue` | running and pending counts |
| ComfyUI | `/models`, `/models/<folder>` | inventory for `where` |
| Ollama | `/api/tags` | up, model tags |
| Ollama | `/api/ps` | loaded models |
| local | `nvidia-smi --query-gpu`, `--query-compute-apps` | load, memory, processes |
| local | disk usage | free space per store |

Timeout 3 s per request. Use 127.0.0.1 rather than localhost for local IPv4 services. Nothing here starts, stops or changes a server; a test fails if lw.py ever gains a write request or process control.
