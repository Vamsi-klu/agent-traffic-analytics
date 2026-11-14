"""tools/releasing/commands.py: a build command is shown without this computer's paths, and a missing
program or a failing command stops the release with what is needed.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import contextlib
import io
import os
import sys
import unittest

from release_trees import scratch

from tools.releasing import commands
from tools.releasing.settings import ReleaseError


class Commands(unittest.TestCase):
    def test_the_log_shows_the_program_by_name_and_paths_inside_the_tree_relative(self):
        tree = scratch(self)
        command = [sys.executable, "-I", os.path.join(tree, "agentcake", "build_js.py"), "--check"]
        self.assertEqual(commands.shown(command, tree),
                         f"{os.path.basename(sys.executable)} -I agentcake/build_js.py --check")

    def test_a_missing_program_says_node_and_npm_are_needed(self):
        tree = scratch(self)
        with self.assertRaisesRegex(ReleaseError, "Node.js and npm"), contextlib.redirect_stdout(io.StringIO()):
            commands.run(["no-such-program-for-the-release-test"], tree, tree)

    def test_a_failing_command_stops_the_release(self):
        tree = scratch(self)
        with self.assertRaisesRegex(ReleaseError, "exit 3"), contextlib.redirect_stdout(io.StringIO()):
            commands.run([sys.executable, "-c", "raise SystemExit(3)"], tree, tree)

    def test_output_returns_what_the_command_wrote(self):
        self.assertEqual(commands.output([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
                                         "cake", scratch(self)), "CAKE\n")


if __name__ == "__main__":
    unittest.main()
