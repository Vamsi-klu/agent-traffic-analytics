"""tools/release.py and tools/releasing/build.py (plan step S6.4): the command refuses a folder that is not empty and
a tag that is not v<version> before building anything, and says which tools differ from release.json "toolchain".

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The whole build (npm ci, the web build, esbuild) is run by hand and in .github/workflows/release.yml; its output is
kept as the S6.4 evidence.
"""
import os
import subprocess
import sys
import unittest

from release_trees import ROOT, scratch, settings, write

from tools.releasing import build

RELEASE = os.path.join(ROOT, "tools", "release.py")


def release(*args):
    return subprocess.run([sys.executable, "-I", RELEASE, *args], capture_output=True, text=True, cwd=ROOT)


class Refusals(unittest.TestCase):
    def test_a_folder_that_is_not_empty_is_refused_and_left_alone(self):
        out = scratch(self)
        write(out, "older.whl", "an older release\n")
        done = release("build", "--out", out)
        self.assertEqual(done.returncode, 1)
        self.assertIn("is not empty", done.stderr)
        self.assertEqual(os.listdir(out), ["older.whl"])

    def test_a_tag_that_is_not_v_version_is_refused(self):
        out = os.path.join(scratch(self), "dist")
        done = release("build", "--out", out, "--tag", "v0.0.0-not-this")
        self.assertEqual(done.returncode, 1)
        self.assertIn("does not match the version", done.stderr)
        self.assertFalse(os.path.exists(out))


class Toolchain(unittest.TestCase):
    def test_a_tool_other_than_the_toolchains_is_pointed_out(self):
        changed = dict(settings(), toolchain={"python": "0.0.1", "node": build.node_version()})
        used, notes = build.toolchain_notes(changed, "0.0.0")
        self.assertEqual(used["esbuild"], "0.0.0")
        self.assertIn("zlib", used)
        self.assertEqual(len(notes), 1)
        self.assertIn("python", notes[0])


if __name__ == "__main__":
    unittest.main()
