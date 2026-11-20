# Log: labwright

- 2026-11-15 · Built 0.1.0 (step E): lw.py, references, evergreen files, unit tests (fake ComfyUI and Ollama on an ephemeral 127.0.0.1 port), read-only source test, leak test reading terms from LABWRIGHT_HOME. First real status and doctor run recorded in the sidecar.
- 2026-11-15 · 0.2.0 released public from a fresh one-commit repo (the first private history held a real GPU name in a test); prove pass: skill and bare both 12/12, decoys 4/4, worth leans TRIM until action cases exist.
- 2026-11-18 · 0.3.0 (harvest ct10): guarded free in lw_free.py, global --json, runs_file VRAM in pick, snapshot check in doctor, GPU temp and power. Found: on Windows (WDDM) nvidia-smi --query-compute-apps lists every desktop app with [N/A] memory, so free ignores [N/A] non-python processes. 37 tests pass with LABWRIGHT_HOME set. Private registry gained comfyui_dir for pc.
- 2026-11-20: 0.3.1 rented-GPU overflow line (r/aivideomaking harvest).
