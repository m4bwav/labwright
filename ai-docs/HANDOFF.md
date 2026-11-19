# Handoff: labwright

State (2026-11-18): 0.3.0 released (harvest ct10: guarded `free`, global --json, runs_file VRAM, snapshot check, GPU temp/power). 37 tests pass with LABWRIGHT_HOME set (the leak test skips without it, so always set it). The only write is lw_free.py; lw.py stays read-only.

Next:
1. Wiki: waits on the owner saving a first page; pages then come from wikiwright.
2. Add action cases a bare model cannot pass (pick --vram while a host holds memory, place on a junctioned model store) to turn the worth verdict from UNPROVEN into a measured one.
3. comfyui-gen does not yet write score_data/runs.jsonl ({model, peak_vram_gb}); once it does, set runs_file in the private registry.
4. Later: let the idle watcher and the text-offload skill read the registry.
