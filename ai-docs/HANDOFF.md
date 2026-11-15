# Handoff: labwright

State (2026-11-15): 0.2.0 released, public, installed (labwright@mark-local). lw.py with hosts, status, where, pick, place, doctor; 26 tests pass with LABWRIGHT_HOME set (the leak test skips without it, so always set it). Idle hosts report held VRAM; pick --vram notes when a model will not fit.

Next:
1. Wiki: waits on the owner saving a first page; pages then come from wikiwright.
2. Add action cases a bare model cannot pass (pick --vram while a host holds memory, place on a junctioned model store) to turn the worth verdict from UNPROVEN into a measured one.
3. Later: let the idle watcher and the text-offload skill read the registry.
