"""Fails if a private term appears in a public file.

Terms come from <LABWRIGHT_HOME>/leak-terms.txt (one per line, # comments). When
LABWRIGHT_HOME is unset or has no terms file the test is skipped with a notice.
A term matches case-sensitively and not inside a longer word (so a name term does
not hit an ordinary word that starts with it). Every tracked file is checked,
ai-docs/ included.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW_FILES = {"tests/test_leak.py"}


def load_terms():
    home = os.environ.get("LABWRIGHT_HOME")
    if not home:
        return None
    p = os.path.join(os.path.expanduser(home), "leak-terms.txt")
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def public_files():
    try:
        r = subprocess.run(["git", "-C", ROOT, "ls-files", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, text=True, check=True)
        files = r.stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        files = []
        for d, _, fs in os.walk(ROOT):
            for f in fs:
                files.append(os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/"))
    return [f for f in files if not f.startswith(".git/") and f not in ALLOW_FILES
            and "__pycache__/" not in f and not f.endswith(".pyc")]


def pattern(term):
    left = r"(?<![A-Za-z0-9])" if term[0].isalnum() else ""
    right = r"(?![A-Za-z0-9])" if term[-1].isalnum() else ""
    return re.compile(left + re.escape(term) + right)


class LeakTest(unittest.TestCase):
    def test_no_private_terms(self):
        terms = load_terms()
        if terms is None:
            self.skipTest("LABWRIGHT_HOME/leak-terms.txt not found: leak test skipped")
        pats = [(t, pattern(t)) for t in terms]
        hits = []
        for rel in public_files():
            hits += ["%s (file name): %s" % (rel, t) for t, p in pats if p.search(rel)]
            try:
                with open(os.path.join(ROOT, rel), "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            hits += ["%s: %s" % (rel, t) for t, p in pats if p.search(text)]
        self.assertEqual(hits, [], "private terms in public files")


if __name__ == "__main__":
    unittest.main()
