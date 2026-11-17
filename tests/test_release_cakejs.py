"""tools/releasing/cakejs.py: cake.js is minified with its runtime markers kept, so cake still fills
in an installation's values; esbuild is pinned; with the release's target it rewrites no syntax, keeps the bundled
licences and makes a script that Node parses.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The tests with the real esbuild need it installed: npm ci in tools/releasing (release.py does that when it builds).
"""
import json
import os
import subprocess
import unittest

from release_trees import ROOT, scratch, settings

from agentcake import assets  # noqa: E402  (release_trees puts the repository on sys.path)
from tools.releasing import cakejs
from tools.releasing.settings import ReleaseError

MARKER = "cake:runtime"
MARKED = f"/*{MARKER}*/{{}}/*{MARKER}*/"
SLOT = settings()["cakejs"]["runtime_slot"]
TOOLS = os.path.join(ROOT, settings()["cakejs"]["tools_folder"])
ESBUILD = os.path.join(TOOLS, settings()["cakejs"]["esbuild"])
CAKE_JS = os.path.join(ROOT, settings()["cakejs"]["file"])


def squeeze(text):
    """A stand-in minifier: runs of white space become one space."""
    return " ".join(text.split())


class Minify(unittest.TestCase):
    SOURCE = f"var RUNTIME = {MARKED}\nvar   site  =  RUNTIME.site_key\n"

    def test_the_markers_are_put_back_around_the_value(self):
        self.assertEqual(cakejs.minify(self.SOURCE, MARKER, SLOT, squeeze),
                         f"var RUNTIME = {MARKED} var site = RUNTIME.site_key")

    def test_a_script_without_exactly_one_marked_value_is_refused(self):
        for source in ("var RUNTIME = {}\n", self.SOURCE + self.SOURCE):
            with self.subTest(source=source), self.assertRaises(ReleaseError):
                cakejs.minify(source, MARKER, SLOT, squeeze)

    def test_a_script_that_already_uses_the_slot_name_is_refused(self):
        with self.assertRaises(ReleaseError):
            cakejs.minify(self.SOURCE + f"var {SLOT}\n", MARKER, SLOT, squeeze)

    def test_a_minifier_that_drops_or_copies_the_value_is_refused(self):
        for minifier in (lambda text: text.replace(SLOT, "{}"), lambda text: text + text):
            with self.subTest(minifier=minifier), self.assertRaises(ReleaseError):
                cakejs.minify(self.SOURCE, MARKER, SLOT, minifier)


class Pinned(unittest.TestCase):
    def test_package_json_pins_one_exact_version_and_the_lockfile_has_it(self):
        pinned = cakejs.pinned_esbuild(TOOLS)
        self.assertRegex(pinned, r"^\d+\.\d+\.\d+$")
        with open(os.path.join(TOOLS, "package-lock.json"), encoding="utf-8") as f:
            lock = json.load(f)
        self.assertEqual(lock["packages"]["node_modules/esbuild"]["version"], pinned)


@unittest.skipUnless(os.path.isfile(ESBUILD), "esbuild is not installed: npm ci in tools/releasing")
class RealEsbuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CAKE_JS, encoding="utf-8") as f:
            cls.source = f.read()
        command = [ESBUILD, *settings()["cakejs"]["flags"]]
        cls.result = cakejs.minify(cls.source, MARKER, SLOT, lambda text: esbuild(command, text))

    def test_the_bundled_licences_and_the_header_are_kept(self):
        for text in cakejs.licences(ROOT, settings()):
            self.assertIn(text, self.result)
        self.assertTrue(self.result.startswith("/*! AgentCake page script (cake.js)"))

    def test_cake_fills_in_the_runtime_values_as_it_serves_the_script(self):
        served = assets.with_runtime(self.result, {"site_key": "k-made-up"}, MARKER)
        self.assertIn(f'/*{MARKER}*/{{"site_key":"k-made-up"}}/*{MARKER}*/', served)

    def test_it_is_smaller(self):
        self.assertLess(len(self.result), len(self.source))

    def test_node_parses_it(self):
        path = os.path.join(scratch(self), "cake.min.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(assets.with_runtime(self.result, {"site_key": "k-made-up"}, MARKER))
        done = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_at_the_release_target_esbuild_rewrites_no_syntax(self):
        target = [flag for flag in settings()["cakejs"]["flags"] if flag.startswith("--target=")]
        self.assertEqual(esbuild([ESBUILD, *target], self.source), esbuild([ESBUILD, "--target=esnext"], self.source))


def esbuild(command, text):
    done = subprocess.run(command, input=text, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return done.stdout


if __name__ == "__main__":
    unittest.main()
