"""Tests for the 0.3.0 additions: --json envelope, GPU temperature and power,
measured VRAM from a runs file, the snapshot check and the guarded free."""
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from test_lw import Base, dead_url, lw  # noqa: F401  (Base starts the fake servers)

import lw_free  # noqa: E402  (on sys.path through test_lw)


def gpu(util=0, procs=()):
    return {"name": "RTX 4080", "vram_gb": 16.0, "used_gb": 1.0, "util_pct": util,
            "processes": [{"pid": str(i), "name": n, "mem_mb": "[N/A]" if n.startswith("app") else "900"} for i, n in enumerate(procs)]}


class TestEnvelope(Base):
    def run_cli(self, args):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "hosts.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.reg([self.host("x", url=dead_url())]), f)
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                code = lw.main(["--hosts", p, "--json"] + args)
        return code, json.loads(buf.getvalue())

    def test_ok_envelope_exit_zero(self):
        code, out = self.run_cli(["pick", "--role", "image"])
        self.assertEqual(code, 0)
        self.assertEqual(set(out), {"ok", "data", "error"})
        self.assertTrue(out["ok"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["data"]["action"], "none")

    def test_error_envelope_exit_one(self):
        code, out = self.run_cli(["free", "--host", "nobody"])
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertIn("no host named", out["error"])
        self.assertIsNone(out["data"])


class TestGpuParse(unittest.TestCase):
    def test_temperature_and_power(self):
        g = lw.parse_gpu("RTX 4080, 16376, 1200, 3, 41, 18.52\n", "")
        self.assertEqual((g["temp_c"], g["power_w"]), (41.0, 18.52))

    def test_na_fields_skipped(self):
        g = lw.parse_gpu("RTX 4080, 16376, 1200, 3, [N/A], [N/A]\n", "")
        self.assertNotIn("power_w", g)
        self.assertEqual(g["util_pct"], 3.0)


class TestMeasuredVram(Base):
    def test_runs_file_sets_vram(self):
        self.srv.comfy("a", models={"checkpoints": ["bigvid.safetensors"]})
        self.srv.comfy("b", models={"checkpoints": ["bigvid.safetensors"]})
        with tempfile.TemporaryDirectory() as d:
            runs = os.path.join(d, "runs.jsonl")
            with open(runs, "w", encoding="utf-8") as f:
                f.write(json.dumps({"model": "bigvid", "peak_vram_gb": 14.2}) + "\nnot json\n")
                f.write(json.dumps({"model": "bigvid", "peak_vram_gb": 11}) + "\n")
            reg = self.reg([self.host("small", "a", vram=8), self.host("big", "b", vram=16)])
            reg["runs_file"] = runs
            out = lw.pick(reg, "image", model="bigvid")
        self.assertEqual(out["hosts"], ["big"])
        self.assertIn("14.2", out["vram_source"])

    def test_missing_runs_file_is_ignored(self):
        self.assertIsNone(lw.measured_vram({"runs_file": "/no/such/file"}, "x"))


class TestSnapshot(unittest.TestCase):
    def make(self, d, snap_age, node_age):
        os.makedirs(os.path.join(d, "custom_nodes", "pack"))
        snaps = os.path.join(d, "user", "__manager", "snapshots")
        os.makedirs(snaps)
        s = os.path.join(snaps, "s_snapshot.json")
        open(s, "w").close()
        now = time.time()
        os.utime(s, (now - snap_age, now - snap_age))
        n = os.path.join(d, "custom_nodes", "pack")
        os.utime(n, (now - node_age, now - node_age))
        return {"name": "pc", "local": True, "comfyui_dir": d}

    def test_stale_snapshot_warns(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("older than custom_nodes/pack", lw.snapshot_note(self.make(d, 1000, 10)))

    def test_fresh_snapshot_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(lw.snapshot_note(self.make(d, 10, 1000)))


class TestFree(Base):
    def setUp(self):
        super().setUp()
        self.posts = []
        p = mock.patch.object(lw_free, "post_json", side_effect=lambda u, b, timeout=10: self.posts.append((u, b)))
        p.start()
        self.addCleanup(p.stop)

    def local(self, **kw):
        h = self.host("pc", "a", ollama=True)
        h["local"] = True
        return self.reg([h])

    def test_frees_when_idle_and_only_ours(self):
        self.srv.comfy("a")
        self.srv.ollama("ao", tags=["m"], loaded=["m"])
        with mock.patch.object(lw, "local_gpu", return_value=gpu(2, ["python.exe", "ollama.exe", "app-explorer.exe"])):
            dry = lw_free.free(self.local(), "pc")
            self.assertTrue(dry["ok"])
            self.assertEqual(self.posts, [])
            res = lw_free.free(self.local(), "pc", apply=True)
        self.assertTrue(res["applied"])
        self.assertEqual(self.posts[0][1], {"model": "m", "keep_alive": 0})
        self.assertTrue(self.posts[1][0].endswith("/free"))

    def test_refuses_busy_queue_or_foreign_process(self):
        self.srv.comfy("a", running=1)
        self.srv.ollama("ao", tags=["m"], loaded=["m"])
        with mock.patch.object(lw, "local_gpu", return_value=gpu(2, ["python.exe", "python.exe"])):
            res = lw_free.free(self.local(), "pc", apply=True)
        self.assertFalse(res["ok"])
        self.assertIn("queue has 1 running", res["why"])
        self.assertIn("not ComfyUI or Ollama", res["why"])
        self.assertEqual(self.posts, [])

    def test_refuses_remote_host(self):
        self.srv.comfy("a")
        reg = self.reg([self.host("mac", "a")])
        res = lw_free.free(reg, "mac", apply=True)
        self.assertIn("not local", res["why"])
        self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
