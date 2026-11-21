"""Unit tests for lw.py. No network: a local http.server on 127.0.0.1 (ephemeral port)
plays ComfyUI and Ollama; nvidia-smi and disk reads are patched."""
import http.server
import json
import os
import re
import sys
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "labwright", "scripts", "lw.py")
sys.path.insert(0, os.path.dirname(SCRIPT))
import lw  # noqa: E402


class FakeServers:
    """Routes by path prefix: /a/... is one host's ComfyUI, /o/... its Ollama."""

    def __init__(self):
        self.routes = {}
        self.methods = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.methods.append("GET")
                body = outer.routes.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, prefix):
        return "http://127.0.0.1:%d/%s" % (self.port, prefix)

    def comfy(self, prefix, running=0, pending=0, models=None, device="cuda:0 RTX 4080"):
        self.routes["/%s/system_stats" % prefix] = {"devices": [{"name": device, "vram_total": 16 * 1024 ** 3}]}
        self.routes["/%s/queue" % prefix] = {"queue_running": [[i] for i in range(running)],
                                             "queue_pending": [[i] for i in range(pending)]}
        models = models or {}
        self.routes["/%s/models" % prefix] = list(models)
        for f, items in models.items():
            self.routes["/%s/models/%s" % (prefix, f)] = items

    def ollama(self, prefix, tags=(), loaded=()):
        self.routes["/%s/api/tags" % prefix] = {"models": [{"name": t} for t in tags]}
        self.routes["/%s/api/ps" % prefix] = {"models": [{"name": t} for t in loaded]}

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def dead_url():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d" % port


class Base(unittest.TestCase):
    def setUp(self):
        self.srv = FakeServers()
        p = mock.patch.object(lw, "local_gpu", return_value=None)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.srv.close)

    def reg(self, hosts, floor=100):
        return {"floor_gb": floor, "hosts": hosts}

    def host(self, name, prefix=None, roles=("image",), vram=16, speed=1, ollama=False, url=None):
        svcs = []
        if url:
            svcs.append({"type": "comfyui", "url": url})
        elif prefix:
            svcs.append({"type": "comfyui", "url": self.srv.url(prefix)})
            if ollama:
                svcs.append({"type": "ollama", "url": self.srv.url(prefix + "o")})
        return {"name": name, "roles": list(roles), "gpu": {"name": "RTX 4080", "vram_gb": vram},
                "speed": speed, "services": svcs}


class TestIdle(Base):
    def test_idle_when_queue_empty_and_nothing_loaded(self):
        self.srv.comfy("a")
        st = lw.host_status(self.host("a", "a"), {})
        self.assertEqual(st["state"], "idle")

    def test_busy_when_queue_has_work(self):
        self.srv.comfy("a", running=1, pending=3)
        st = lw.host_status(self.host("a", "a"), {})
        self.assertEqual(st["state"], "busy")

    def test_empty_queue_but_gpu_loaded_is_busy(self):
        self.srv.comfy("a")
        gpu = {"name": "RTX 4080", "vram_gb": 16, "used_gb": 12, "util_pct": 97, "processes": []}
        h = self.host("a", "a")
        h["local"] = True
        with mock.patch.object(lw, "local_gpu", return_value=gpu):
            st = lw.host_status(h, {})
        self.assertEqual(st["state"], "busy")
        self.assertIn("outside the queue", " ".join(st["reasons"]))

    def test_loaded_ollama_model_is_busy(self):
        self.srv.comfy("a")
        self.srv.ollama("ao", tags=["m:8b"], loaded=["m:8b"])
        st = lw.host_status(self.host("a", "a", ollama=True), {})
        self.assertEqual(st["state"], "busy")

    def test_down_host_is_down_not_error(self):
        st = lw.host_status(self.host("x", url=dead_url()), {})
        self.assertEqual(st["state"], "down")

    def test_threshold_from_registry(self):
        self.srv.comfy("a")
        gpu = {"name": "RTX 4080", "vram_gb": 16, "used_gb": 1, "util_pct": 30, "processes": []}
        h = self.host("a", "a")
        h["local"] = True
        with mock.patch.object(lw, "local_gpu", return_value=gpu):
            self.assertEqual(lw.host_status(h, {"idle": {"gpu_busy_pct": 50}})["state"], "idle")
            self.assertEqual(lw.host_status(h, {})["state"], "busy")

    def test_idle_but_vram_held_says_so(self):
        self.srv.comfy("a")
        gpu = {"name": "Example GPU 16GB", "vram_gb": 15.9, "used_gb": 11.9, "util_pct": 0, "processes": []}
        h = self.host("a", "a")
        h["local"] = True
        with mock.patch.object(lw, "local_gpu", return_value=gpu):
            st = lw.host_status(h, {})
            r = lw.pick(self.reg([h]), "image", vram=8)
        self.assertEqual(st["state"], "idle")
        self.assertEqual(st["vram_free_gb"], 4.0)
        self.assertIn("11.9 of 15.9 GB VRAM held", " ".join(st["reasons"]))
        self.assertEqual(r["action"], "run")
        self.assertTrue(any("only 4.0 GB VRAM free" in n for n in r["notes"]))


class TestPick(Base):
    def test_idle_host_chosen_fastest_first(self):
        self.srv.comfy("a")
        self.srv.comfy("b")
        reg = self.reg([self.host("slow", "a", speed=1), self.host("fast", "b", speed=3)])
        r = lw.pick(reg, "image")
        self.assertEqual((r["action"], r["hosts"]), ("run", ["fast"]))

    def test_batch_splits_across_idle_hosts(self):
        self.srv.comfy("a")
        self.srv.comfy("b")
        self.srv.comfy("c", running=1)
        reg = self.reg([self.host("a", "a"), self.host("b", "b"), self.host("c", "c")])
        r = lw.pick(reg, "image", batch=True)
        self.assertEqual(sorted(r["hosts"]), ["a", "b"])

    def test_all_busy_means_queue_not_stop(self):
        self.srv.comfy("a", running=1, pending=5)
        self.srv.comfy("b", running=1)
        reg = self.reg([self.host("a", "a"), self.host("b", "b")])
        r = lw.pick(reg, "image")
        self.assertEqual((r["action"], r["hosts"]), ("queue", ["b"]))
        self.assertIn("do not stop", r["why"])

    def test_role_and_vram_filter(self):
        self.srv.comfy("a")
        self.srv.comfy("b")
        reg = self.reg([self.host("small", "a", roles=("image", "video"), vram=8),
                        self.host("big", "b", roles=("video",), vram=24),
                        self.host("noimg", "b", roles=("llm",))])
        r = lw.pick(reg, "video", vram=16)
        self.assertEqual(r["hosts"], ["big"])
        self.assertIn("small", r["excluded"])

    def test_model_filter(self):
        self.srv.comfy("a", models={"checkpoints": ["other.safetensors"]})
        self.srv.comfy("b", models={"checkpoints": ["zimage_turbo.safetensors"]})
        reg = self.reg([self.host("a", "a", speed=9), self.host("b", "b")])
        r = lw.pick(reg, "image", model="zimage")
        self.assertEqual(r["hosts"], ["b"])

    def test_all_down(self):
        reg = self.reg([self.host("x", url=dead_url())])
        r = lw.pick(reg, "image")
        self.assertEqual(r["action"], "none")
        self.assertIn("down", r["why"])

    def test_draining_host_is_up_but_not_ready_and_skipped(self):
        self.srv.comfy("a")
        self.srv.comfy("b")
        drain = self.host("fast", "a", speed=9)
        drain["draining"] = True
        reg = self.reg([drain, self.host("slow", "b")])
        st = lw.host_status(drain, reg)
        self.assertEqual((st["state"], st["ready"]), ("draining", False))
        r = lw.pick(reg, "image")
        self.assertEqual(r["hosts"], ["slow"])
        self.assertIn("draining", r["excluded"]["fast"])
        self.assertTrue(lw.host_status(self.host("slow", "b"), reg)["ready"])

    def test_only_draining_host_means_none(self):
        self.srv.comfy("a")
        h = self.host("a", "a")
        h["draining"] = True
        r = lw.pick(self.reg([h]), "image")
        self.assertEqual(r["action"], "none")

    def test_full_queue_sheds_load_instead_of_queue(self):
        self.srv.comfy("a", running=1, pending=4)
        reg = self.reg([self.host("a", "a")])
        self.assertEqual(lw.pick(reg, "image")["action"], "queue")
        reg["idle"] = {"max_pending": 3}
        r = lw.pick(reg, "image")
        self.assertEqual(r["action"], "none")
        self.assertIn("shed", r["why"])
        reg["idle"] = {"max_pending": 10}
        self.assertEqual(lw.pick(reg, "image")["action"], "queue")

    def test_no_capable_host(self):
        r = lw.pick(self.reg([self.host("a", "a", roles=("llm",))]), "video")
        self.assertEqual(r["action"], "none")


class TestWhere(Base):
    def test_finds_across_comfy_and_ollama_and_reports_down(self):
        self.srv.comfy("a", models={"diffusion_models": ["acestep_v1.5_xl.safetensors"], "loras": []})
        self.srv.ollama("ao", tags=["qwen3:30b", "llama3:8b"])
        reg = self.reg([self.host("a", "a", ollama=True), self.host("x", url=dead_url())])
        hits = lw.where(reg, "ACESTEP")
        self.assertIn({"host": "a", "service": "comfyui", "folder": "diffusion_models",
                       "file": "acestep_v1.5_xl.safetensors"}, hits)
        self.assertTrue(any(h.get("host") == "x" and "down" in h for h in hits))
        self.assertEqual([h["tag"] for h in lw.where(reg, "qwen3") if "tag" in h], ["qwen3:30b"])

    def test_only_get_requests(self):
        self.srv.comfy("a", models={"checkpoints": ["m"]})
        lw.where(self.reg([self.host("a", "a")]), "m")
        self.assertTrue(self.srv.methods)
        self.assertEqual(set(self.srv.methods), {"GET"})


class TestPlace(unittest.TestCase):
    def reg(self, stores, local=True):
        return {"floor_gb": 100, "hosts": [{"name": "h", "local": local, "roles": ["image"], "stores": stores}]}

    def test_floor_kept_and_broken(self):
        with mock.patch.object(lw, "disk_free_gb", return_value=150.0):
            ok = lw.place(self.reg([{"path": "E:/m"}]), 40)[0]
            bad = lw.place(self.reg([{"path": "E:/m"}]), 60)[0]
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["after_gb"], 110.0)
        self.assertFalse(bad["ok"])
        self.assertIn("floor", bad["why"])

    def test_remote_uses_registry_figure_with_date(self):
        r = lw.place(self.reg([{"path": "/m", "free_gb": 450, "free_checked": "2026-01-01"}], local=False), 38)[0]
        self.assertTrue(r["ok"])
        self.assertIn("2026-01-01", r["source"])

    def test_unknown_free_space(self):
        r = lw.place(self.reg([{"path": "/m"}], local=False), 1)[0]
        self.assertIsNone(r["ok"])

    def test_role_filter(self):
        self.assertEqual(lw.place(self.reg([{"path": "/m"}]), 1, role="video"), [])


class TestDoctorAndRegistry(Base):
    def test_hardware_drift(self):
        self.srv.comfy("a", device="cuda:0 RTX 9999")
        h = self.host("a", "a")
        reg = self.reg([h])
        notes = lw.doctor(reg, lw.pool_status(reg))
        self.assertTrue(any("hardware change" in n for n in notes))

    def test_validate(self):
        bad = {"hosts": [{"name": "a", "roles": ["paint"], "services": [{"type": "comfyui", "url": "ftp://x"}]},
                         {"name": "a"}]}
        probs = lw.validate(bad)
        self.assertEqual(len(probs), 3)

    def test_schema_version(self):
        ok = {"hosts": [{"name": "a"}]}
        self.assertEqual(lw.validate(ok), [])
        self.assertEqual(lw.validate(dict(ok, schema_version=1)), [])
        self.assertIn("newer", " ".join(lw.validate(dict(ok, schema_version=2))))
        self.assertTrue(lw.validate(dict(ok, schema_version="1")))

    def test_example_registry_is_valid(self):
        path = os.path.join(ROOT, "skills", "labwright", "hosts.example.json")
        self.assertEqual(lw.validate(lw.load_registry(path)), [])

    def test_cli_status_down_host_exit_zero(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "hosts.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.reg([self.host("x", url=dead_url())]), f)
            with mock.patch("sys.stdout"):
                self.assertEqual(lw.main(["--hosts", p, "status", "--json"]), 0)


class TestReadOnlySource(unittest.TestCase):
    def test_no_write_verbs_or_process_control(self):
        with open(SCRIPT, "r", encoding="utf-8") as f:
            src = f.read()
        banned = [r"\b(POST|PUT|DELETE|PATCH)\b", r"method\s*=", r"\bdata\s*=",
                  r"taskkill", r"Stop-Process", r"\.kill\(", r"\.terminate\(", r"os\.kill",
                  r"(?i)restart", r"Start-ScheduledTask", r"/interrupt", r"/free\b",
                  r"/api/(pull|delete|generate|chat|push|create)", r"/prompt\b", r"manager/queue"]
        hits = [b for b in banned if re.search(b, src)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
