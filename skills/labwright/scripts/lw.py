#!/usr/bin/env python3
"""labwright: the user's local AI servers (ComfyUI, Ollama) as one read-only pool.

Subcommands: hosts, status, where <model>, pick --role R [--model M]
[--vram GB] [--batch], place --size GB [--role R], doctor, free --host H [--apply].
Global --json wraps any subcommand's result as {"ok", "data", "error"}; exit 0/1.

Read-only by design: HTTP GET only, plus local read commands (nvidia-smi
queries, disk usage). It never submits, cancels, unloads or downloads anything.
The one exception, `free`, lives in lw_free.py and acts only with --apply and
only when its guards pass.
A host that does not answer is reported as down, never raised as an error.

Registry: $LABWRIGHT_HOME/hosts.json, or the file given by --hosts.
Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 3.0
DEFAULT_FLOOR_GB = 100
DEFAULT_GPU_BUSY_PCT = 15
ROLES = ("image", "video", "music", "llm", "train")


# ---------------------------------------------------------------- registry

def registry_path(arg: str | None) -> str | None:
    if arg:
        return arg
    home = os.environ.get("LABWRIGHT_HOME")
    if home:
        return os.path.join(os.path.expanduser(home), "hosts.json")
    return None


def load_registry(path: str | None) -> dict:
    if not path:
        raise SystemExit("labwright: no registry. Set LABWRIGHT_HOME (holding hosts.json) or pass --hosts FILE. "
                         "Start from hosts.example.json.")
    with open(path, "r", encoding="utf-8") as f:
        reg = json.load(f)
    return reg


def validate(reg: dict) -> list[str]:
    problems = []
    hosts = reg.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        return ["registry has no hosts list"]
    names = set()
    for i, h in enumerate(hosts):
        n = h.get("name")
        if not n:
            problems.append("host %d has no name" % i)
            continue
        if n in names:
            problems.append("duplicate host name %s" % n)
        names.add(n)
        for r in h.get("roles", []):
            if r not in ROLES:
                problems.append("%s: unknown role %s" % (n, r))
        for s in h.get("services", []):
            if s.get("type") not in ("comfyui", "ollama", "http"):
                problems.append("%s: unknown service type %s" % (n, s.get("type")))
            if not str(s.get("url", "")).startswith(("http://", "https://")):
                problems.append("%s: service url must start with http:// or https://" % n)
    return problems


def floor_gb(reg: dict) -> float:
    return float(reg.get("floor_gb", DEFAULT_FLOOR_GB))


HELD_VRAM_GB = 2.0  # idle hosts holding at least this much VRAM say so


def gpu_busy_pct(reg: dict) -> float:
    return float(reg.get("idle", {}).get("gpu_busy_pct", DEFAULT_GPU_BUSY_PCT))


# ---------------------------------------------------------------- probes (read only)

def http_get_json(url: str, timeout: float = TIMEOUT):
    """GET a URL and parse JSON. Returns (data, None) or (None, reason)."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return json.loads(body.decode("utf-8") or "null"), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %d" % e.code
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        return None, "unreachable (%s)" % reason
    except ValueError:
        return None, "not JSON"


def run_read_cmd(argv: list[str], timeout: float = 5.0) -> str | None:
    """Run a local read-only query command; None if missing or failing."""
    if not shutil.which(argv[0]):
        return None
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def local_gpu() -> dict | None:
    out = run_read_cmd(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw",
                        "--format=csv,noheader,nounits"])
    return parse_gpu(out, run_read_cmd(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                                        "--format=csv,noheader,nounits"]))


def parse_gpu(out: str | None, apps: str | None) -> dict | None:
    if not out or not out.strip():
        return None
    first = out.strip().splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    try:
        gpu = {"name": parts[0], "vram_gb": round(float(parts[1]) / 1024, 1),
               "used_gb": round(float(parts[2]) / 1024, 1), "util_pct": float(parts[3])}
    except (IndexError, ValueError):
        return None
    for key, i in (("temp_c", 4), ("power_w", 5)):
        try:
            gpu[key] = float(parts[i])
        except (IndexError, ValueError):
            pass  # [N/A] on some cards
    gpu["processes"] = []
    for line in (apps or "").strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 3:
            gpu["processes"].append({"pid": p[0], "name": p[1], "mem_mb": p[2]})
    return gpu


def disk_free_gb(path: str) -> float | None:
    try:
        return round(shutil.disk_usage(path).free / 1024 ** 3, 1)
    except OSError:
        return None


def probe_service(svc: dict) -> dict:
    base = svc["url"].rstrip("/")
    out = {"type": svc["type"], "url": base, "up": False}
    if svc["type"] == "comfyui":
        stats, err = http_get_json(base + "/system_stats")
        if err:
            out["reason"] = err
            return out
        out["up"] = True
        devs = (stats or {}).get("devices") or []
        if devs:
            d = devs[0]
            out["device"] = d.get("name")
            if d.get("vram_total"):
                out["vram_gb"] = round(d["vram_total"] / 1024 ** 3, 1)
        q, err = http_get_json(base + "/queue")
        if err:
            out["queue_reason"] = err
        else:
            out["running"] = len((q or {}).get("queue_running") or [])
            out["pending"] = len((q or {}).get("queue_pending") or [])
    elif svc["type"] == "ollama":
        tags, err = http_get_json(base + "/api/tags")
        if err:
            out["reason"] = err
            return out
        out["up"] = True
        out["models"] = [m.get("name") for m in (tags or {}).get("models") or []]
        ps, err = http_get_json(base + "/api/ps")
        if not err:
            out["loaded"] = [m.get("name") for m in (ps or {}).get("models") or []]
    else:
        data, err = http_get_json(base + svc.get("health", "/"))
        out["up"] = err is None
        if err:
            out["reason"] = err
    return out


def host_status(host: dict, reg: dict) -> dict:
    """Probe one host. state is idle, busy or down, with reasons."""
    st = {"name": host["name"], "roles": host.get("roles", []), "services": [], "reasons": []}
    for svc in host.get("services", []):
        st["services"].append(probe_service(svc))
    if host.get("local"):
        gpu = local_gpu()
        if gpu:
            st["gpu"] = gpu
        st["stores"] = []
        for s in host.get("stores", []):
            st["stores"].append({"path": s["path"], "kind": s.get("kind", "models"), "free_gb": disk_free_gb(s["path"])})
    up = [s for s in st["services"] if s["up"]]
    if st["services"] and not up:
        st["state"] = "down"
        st["reasons"].append("no service answered")
        return st
    for s in st["services"]:
        if not s["up"]:
            st["reasons"].append("%s down: %s" % (s["type"], s.get("reason")))
    busy = []
    for s in up:
        if s.get("running") or s.get("pending"):
            busy.append("%s queue %d running, %d pending" % (s["type"], s.get("running", 0), s.get("pending", 0)))
        if s.get("loaded"):
            busy.append("ollama has loaded: %s" % ", ".join(s["loaded"]))
    gpu = st.get("gpu")
    if gpu and gpu["util_pct"] >= gpu_busy_pct(reg):
        busy.append("GPU load %d%% (work outside the queue counts)" % gpu["util_pct"])
    if busy:
        st["state"] = "busy"
        st["reasons"] = busy + st["reasons"]
    else:
        st["state"] = "idle"
    if gpu and gpu.get("used_gb", 0) >= HELD_VRAM_GB:
        st["vram_free_gb"] = round(gpu["vram_gb"] - gpu["used_gb"], 1)
        st["reasons"].append("%.1f of %.1f GB VRAM held at %d%% load (cached weights or a process); a big model may not fit until it unloads"
                             % (gpu["used_gb"], gpu["vram_gb"], gpu["util_pct"]))
    return st


def pool_status(reg: dict) -> list[dict]:
    return [host_status(h, reg) for h in reg["hosts"]]


# ---------------------------------------------------------------- inventory

def comfy_models(base: str) -> dict:
    folders, err = http_get_json(base.rstrip("/") + "/models")
    if err or not isinstance(folders, list):
        return {}
    out = {}
    for f in folders:
        items, err = http_get_json(base.rstrip("/") + "/models/" + urllib.parse.quote(str(f)))
        if not err and isinstance(items, list):
            out[f] = items
    return out


def where(reg: dict, model: str) -> list[dict]:
    needle = model.lower()
    found = []
    for h in reg["hosts"]:
        for svc in h.get("services", []):
            base = svc["url"].rstrip("/")
            if svc["type"] == "comfyui":
                stats, err = http_get_json(base + "/system_stats")
                if err:
                    found.append({"host": h["name"], "service": "comfyui", "down": err})
                    continue
                for folder, items in comfy_models(base).items():
                    for it in items:
                        if needle in str(it).lower():
                            found.append({"host": h["name"], "service": "comfyui", "folder": folder, "file": it})
            elif svc["type"] == "ollama":
                tags, err = http_get_json(base + "/api/tags")
                if err:
                    found.append({"host": h["name"], "service": "ollama", "down": err})
                    continue
                for m in (tags or {}).get("models") or []:
                    if needle in str(m.get("name", "")).lower():
                        found.append({"host": h["name"], "service": "ollama", "tag": m.get("name")})
    return found


# ---------------------------------------------------------------- pick and place

def host_vram(h: dict) -> float:
    g = h.get("gpu") or {}
    return float(g.get("vram_gb") or h.get("unified_gb") or 0)


def measured_vram(reg: dict, model: str) -> float | None:
    """Peak VRAM (GB) measured for a model in the registry's runs_file (JSON lines with
    model and peak_vram_gb, e.g. comfyui-gen's score_data/runs.jsonl). None if absent."""
    path = reg.get("runs_file")
    if not path or not os.path.isfile(os.path.expanduser(path)):
        return None
    needle, peak = model.lower(), None
    with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if needle in str(row.get("model", "")).lower():
                    peak = max(peak or 0.0, float(row["peak_vram_gb"]))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    return peak


def pick(reg: dict, role: str, model: str | None = None, vram: float | None = None,
         batch: bool = False, statuses: list[dict] | None = None) -> dict:
    if vram is None and model:
        vram = measured_vram(reg, model)
        if vram:
            out = _pick(reg, role, model, vram, batch, statuses)
            out["vram_source"] = "measured peak %.1f GB from runs_file" % vram
            return out
    return _pick(reg, role, model, vram, batch, statuses)


def _pick(reg: dict, role: str, model: str | None, vram: float | None,
          batch: bool, statuses: list[dict] | None) -> dict:
    capable = [h for h in reg["hosts"] if role in h.get("roles", [])]
    reasons = {}
    if vram:
        keep = []
        for h in capable:
            if host_vram(h) >= vram:
                keep.append(h)
            else:
                reasons[h["name"]] = "has %.0f GB, job needs %.0f GB" % (host_vram(h), vram)
        capable = keep
    if model:
        hits = where({"hosts": capable}, model)
        have = {x["host"] for x in hits if "down" not in x}
        for h in capable:
            if h["name"] not in have:
                reasons.setdefault(h["name"], "model %s not found there (or host down)" % model)
        capable = [h for h in capable if h["name"] in have]
    if not capable:
        return {"action": "none", "hosts": [], "why": "no registered host fits role %s" % role, "excluded": reasons}
    by_name = {s["name"]: s for s in (statuses or [])}
    sts = [by_name.get(h["name"]) or host_status(h, reg) for h in capable]
    order = sorted(range(len(capable)), key=lambda i: -float(capable[i].get("speed", 1)))
    idle = [sts[i] for i in order if sts[i]["state"] == "idle"]
    busy = [sts[i] for i in order if sts[i]["state"] == "busy"]
    if idle:
        chosen = idle if batch else idle[:1]
        why = "idle" if not batch else "split the batch across every idle capable host"
        out = {"action": "run", "hosts": [s["name"] for s in chosen], "why": why, "excluded": reasons}
        notes = ["%s: idle, %s" % (s["name"], r) for s in chosen for r in s["reasons"] if "VRAM held" in r]
        if vram:
            notes += ["%s: only %.1f GB VRAM free now, job needs %.0f GB" % (s["name"], s["vram_free_gb"], vram)
                      for s in chosen if s.get("vram_free_gb", vram) < vram]
        if notes:
            out["notes"] = notes
        return out
    if busy:
        def load(s):
            return sum(x.get("running", 0) + x.get("pending", 0) for x in s["services"] if x["up"])
        best = min(busy, key=load)
        return {"action": "queue", "hosts": [best["name"]],
                "why": "every capable host is busy; queue behind it and wait, do not stop its work: "
                       + "; ".join(best["reasons"]), "excluded": reasons}
    return {"action": "none", "hosts": [], "why": "every capable host is down",
            "excluded": {s["name"]: "; ".join(s["reasons"]) for s in sts} | reasons}


def place(reg: dict, size_gb: float, role: str | None = None) -> list[dict]:
    floor = floor_gb(reg)
    rows = []
    for h in reg["hosts"]:
        if role and role not in h.get("roles", []):
            continue
        for s in h.get("stores", []):
            free = disk_free_gb(s["path"]) if h.get("local") else None
            src = "measured"
            if free is None and s.get("free_gb") is not None:
                free, src = float(s["free_gb"]), "registry %s" % s.get("free_checked", "undated")
            row = {"host": h["name"], "path": s["path"], "kind": s.get("kind", "models")}
            if free is None:
                row.update(ok=None, why="free space unknown; measure it before downloading")
            else:
                after = round(free - size_gb, 1)
                row.update(free_gb=free, after_gb=after, source=src, ok=after >= floor,
                           why="keeps %.0f GB floor" % floor if after >= floor else "would leave %.1f GB, under the %.0f GB floor" % (after, floor))
            rows.append(row)
    return rows


# ---------------------------------------------------------------- doctor

SNAPSHOT_DIRS = ("user/__manager/snapshots", "user/default/ComfyUI-Manager/snapshots")


def snapshot_note(host: dict) -> str | None:
    """Warn when the newest ComfyUI-Manager snapshot is older than the newest custom_nodes folder."""
    root = host.get("comfyui_dir")
    if not root or not host.get("local"):
        return None
    nodes = os.path.join(root, "custom_nodes")
    try:
        newest_node = max((e for e in os.scandir(nodes) if e.is_dir() and not e.name.startswith((".", "__"))),
                          key=lambda e: e.stat().st_mtime, default=None)
    except OSError:
        return None
    if newest_node is None:
        return None
    snaps = []
    for d in SNAPSHOT_DIRS:
        try:
            snaps += [e.stat().st_mtime for e in os.scandir(os.path.join(root, d)) if e.name.endswith(".json")]
        except OSError:
            pass
    if not snaps:
        return "%s: no ComfyUI-Manager snapshot; save one before the next node or ComfyUI update (comfy node save-snapshot)" % host["name"]
    if max(snaps) < newest_node.stat().st_mtime:
        return ("%s: newest snapshot is older than custom_nodes/%s; save one before the next update (comfy node save-snapshot)"
                % (host["name"], newest_node.name))
    return None


def doctor(reg: dict, statuses: list[dict]) -> list[str]:
    notes = ["registry: " + p for p in validate(reg)]
    for h in reg["hosts"]:
        n = snapshot_note(h)
        if n:
            notes.append(n)
    for h, st in zip(reg["hosts"], statuses):
        want = (h.get("gpu") or {})
        for s in st["services"]:
            if not s["up"]:
                notes.append("%s: %s at %s is down (%s)" % (h["name"], s["type"], s["url"], s.get("reason")))
            if s.get("device") and want.get("name") and want["name"].lower() not in s["device"].lower():
                notes.append("%s: registry GPU %s but ComfyUI reports %s; record the hardware change"
                             % (h["name"], want["name"], s["device"]))
        g = st.get("gpu")
        if g and want:
            if want.get("name") and want["name"].lower() not in g["name"].lower():
                notes.append("%s: registry GPU %s but nvidia-smi reports %s; record the hardware change"
                             % (h["name"], want["name"], g["name"]))
            if want.get("vram_gb") and abs(float(want["vram_gb"]) - g["vram_gb"]) > 1.5:
                notes.append("%s: registry VRAM %s GB but nvidia-smi reports %s GB" % (h["name"], want["vram_gb"], g["vram_gb"]))
        for s in st.get("stores", []):
            if s["free_gb"] is None:
                notes.append("%s: store %s not readable" % (h["name"], s["path"]))
            elif s["free_gb"] < floor_gb(reg):
                notes.append("%s: store %s has %.1f GB free, under the floor" % (h["name"], s["path"], s["free_gb"]))
    return notes


# ---------------------------------------------------------------- output

def fmt_status(st: dict) -> str:
    lines = ["%s: %s" % (st["name"], st["state"].upper())]
    for s in st["services"]:
        if s["up"]:
            extra = []
            if "running" in s:
                extra.append("queue %d/%d" % (s["running"], s["pending"]))
            if "device" in s:
                extra.append(s["device"])
            if "models" in s:
                extra.append("%d models" % len(s["models"]))
            if s.get("loaded"):
                extra.append("loaded " + ", ".join(s["loaded"]))
            lines.append("  %s up  %s" % (s["type"], "; ".join(extra)))
        else:
            lines.append("  %s DOWN  %s" % (s["type"], s.get("reason")))
    g = st.get("gpu")
    if g:
        extra = "".join([", %.0f C" % g["temp_c"] if "temp_c" in g else "", ", %.0f W" % g["power_w"] if "power_w" in g else ""])
        lines.append("  gpu %s %.0f%% load, %.1f/%.1f GB%s, %d processes" % (g["name"], g["util_pct"], g["used_gb"], g["vram_gb"], extra, len(g["processes"])))
    for s in st.get("stores", []):
        lines.append("  store %s free %s GB" % (s["path"], s["free_gb"]))
    for r in st["reasons"]:
        lines.append("  - " + r)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lw.py", description=__doc__.splitlines()[0])
    ap.add_argument("--hosts", help="registry file (default $LABWRIGHT_HOME/hosts.json)")
    ap.add_argument("--json", dest="envelope", action="store_true",
                    help='print {"ok", "data", "error"} for any subcommand; exit 0 ok, 1 not')
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hosts")
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("where")
    p.add_argument("model")
    p = sub.add_parser("pick")
    p.add_argument("--role", required=True, choices=ROLES)
    p.add_argument("--model")
    p.add_argument("--vram", type=float)
    p.add_argument("--batch", action="store_true")
    p = sub.add_parser("place")
    p.add_argument("--size", type=float, required=True)
    p.add_argument("--role", choices=ROLES)
    sub.add_parser("doctor")
    p = sub.add_parser("free", help="guarded: unload Ollama models, then ComfyUI free-memory (lw_free.py)")
    p.add_argument("--host", required=True)
    p.add_argument("--apply", action="store_true", help="act; without it only the guard verdict is printed")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        ok, data, text = run(a, load_registry(registry_path(a.hosts)))
    except (SystemExit, OSError, ValueError) as e:
        if not a.envelope:
            raise
        ok, data, text = False, None, str(e)
    if a.envelope:
        print(json.dumps({"ok": ok, "data": data if ok else None,
                          "error": None if ok else (text if isinstance(text, str)
                                                    else (data or {}).get("why", "failed") if isinstance(data, dict) else "failed"),
                          **({"detail": data} if not ok and data is not None else {})}, indent=2))
    else:
        print(text if isinstance(text, str) else json.dumps(data, indent=2))
    return 0 if ok else 1


def run(a, reg: dict):
    """Run one subcommand: (ok, data, text). text None means print data as JSON."""
    if a.cmd == "hosts":
        probs = validate(reg)
        info = {"hosts": reg["hosts"], "floor_gb": floor_gb(reg), "problems": probs}
        return not probs, info, ("registry problems: " + "; ".join(probs)) if probs and a.envelope else None
    if a.cmd == "status":
        sts = pool_status(reg)
        return True, sts, None if a.json else "\n".join(fmt_status(s) for s in sts)
    if a.cmd == "where":
        return True, where(reg, a.model), None
    if a.cmd == "pick":
        return True, pick(reg, a.role, a.model, a.vram, a.batch), None
    if a.cmd == "place":
        return True, {"size_gb": a.size, "floor_gb": floor_gb(reg), "stores": place(reg, a.size, a.role)}, None
    if a.cmd == "doctor":
        sts = pool_status(reg)
        notes = doctor(reg, sts)
        text = "\n".join(fmt_status(s) for s in sts)
        text += "\n\ndoctor: " + ("no drift found" if not notes else "%d note(s)" % len(notes))
        text += "".join("\n  - " + n for n in notes)
        return True, {"status": sts, "notes": notes}, text
    if a.cmd == "free":
        import lw_free
        res = lw_free.free(reg, a.host, a.apply)
        return res["ok"], res, None
    raise SystemExit("unknown command %s" % a.cmd)


if __name__ == "__main__":
    sys.exit(main())
