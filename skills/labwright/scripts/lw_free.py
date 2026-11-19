"""labwright free: the one guarded write, kept out of lw.py so lw.py stays read-only.

Frees GPU memory on a local host before a big job: unloads every loaded Ollama
model (keep_alive 0), then asks ComfyUI to unload models and free memory (/free).
Acts only with apply=True and only when every guard passes:
  - the host is local (its GPU processes can be read with nvidia-smi);
  - every ComfyUI queue on it answers and is empty;
  - GPU load is under the registry's busy threshold;
  - no GPU process other than Ollama and one ComfyUI python holds memory
    (override with the host's "free": {"allow_processes": [...]}).
Another session's job is never touched: any doubt refuses. Idea from Comfy-Org
comfy-mcp's VRAM handoff (idea only, no code).
"""
from __future__ import annotations

import json
import urllib.request

import lw


def post_json(url: str, body: dict, timeout: float = 10.0) -> str | None:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        return None
    except OSError as e:
        return str(getattr(e, "reason", e))


def guards(reg: dict, host: dict) -> tuple[list[str], dict]:
    """Return (refusals, facts). Empty refusals means safe to free."""
    refuse, facts = [], {"ollama_loaded": {}, "comfy": []}
    if not host.get("local"):
        refuse.append("host is not local: its GPU processes cannot be checked")
    for svc in host.get("services", []):
        st = lw.probe_service(svc)
        if svc["type"] == "comfyui":
            if not st["up"] or "running" not in st:
                refuse.append("ComfyUI at %s did not report its queue" % st["url"])
            elif st["running"] or st["pending"]:
                refuse.append("ComfyUI queue has %d running, %d pending" % (st["running"], st["pending"]))
            else:
                facts["comfy"].append(st["url"])
        elif svc["type"] == "ollama" and st["up"]:
            facts["ollama_loaded"][st["url"]] = st.get("loaded") or []
    if host.get("local"):
        gpu = lw.local_gpu()
        if not gpu:
            refuse.append("nvidia-smi gave no reading")
        else:
            if gpu["util_pct"] >= lw.gpu_busy_pct(reg):
                refuse.append("GPU load %d%%: something is running" % gpu["util_pct"])
            allow = [a.lower() for a in (host.get("free") or {}).get("allow_processes", [])]
            pythons = 0
            for p in gpu["processes"]:
                name = p["name"].lower()
                if "ollama" in name or any(a in name for a in allow):
                    continue
                try:
                    small = float(p["mem_mb"]) < 256
                except ValueError:  # Windows WDDM reports [N/A]: lists every desktop app
                    small = "python" not in name
                if small:
                    continue
                if "python" in name and pythons == 0:
                    pythons += 1  # ComfyUI itself
                    continue
                refuse.append("GPU process %s (pid %s) is not ComfyUI or Ollama" % (p["name"], p["pid"]))
    if not facts["comfy"] and not any(facts["ollama_loaded"].values()):
        refuse.append("nothing to free: no ComfyUI and no loaded Ollama model")
    return refuse, facts


def free(reg: dict, name: str, apply: bool = False) -> dict:
    host = next((h for h in reg["hosts"] if h.get("name") == name), None)
    if host is None:
        return {"ok": False, "why": "no host named %s" % name}
    refuse, facts = guards(reg, host)
    if refuse:
        return {"ok": False, "applied": False, "why": "; ".join(refuse), "facts": facts}
    if not apply:
        return {"ok": True, "applied": False, "why": "guards pass; rerun with --apply to free", "facts": facts}
    done, errors = [], []
    for url, models in facts["ollama_loaded"].items():
        for m in models:
            err = post_json(url + "/api/generate", {"model": m, "keep_alive": 0})
            (errors if err else done).append("ollama unload %s%s" % (m, ": " + err if err else ""))
    for url in facts["comfy"]:
        err = post_json(url + "/free", {"unload_models": True, "free_memory": True})
        (errors if err else done).append("comfyui /free %s%s" % (url, ": " + err if err else ""))
    return {"ok": not errors, "applied": True, "done": done, "errors": errors,
            "why": "; ".join(errors) if errors else "freed", "facts": facts}
