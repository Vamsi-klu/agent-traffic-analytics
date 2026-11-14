"""tools/releasing/bundled_lists.py (plan step S6.4, D23): a commit whose lists were built more than max_age_days
before it is refused, counting from the commit's day (not today); `refresh` runs the refresh scripts in the repository.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import calendar
import contextlib
import io
import subprocess
import sys
import unittest

from release_trees import make_tree, settings, write

from tools.releasing import bundled_lists
from tools.releasing.settings import ReleaseError

BUILT = "2026-11-01"
DAY_SECONDS = 24 * 60 * 60


def day(text):
    """The POSIX time of a day at 12:00 UTC."""
    year, month, number = (int(part) for part in text.split("-"))
    return calendar.timegm((year, month, number, 12, 0, 0))


class Fresh(unittest.TestCase):
    def setUp(self):
        self.tree = make_tree(self, {settings()["lists"]["names_file"]: f'{{"built": "{BUILT}"}}\n'})
        self.limit = settings()["lists"]["max_age_days"]

    def test_lists_built_within_the_limit_pass_and_say_their_age(self):
        self.assertEqual(bundled_lists.check_fresh(self.tree, settings(), day(BUILT)), 0)
        self.assertEqual(bundled_lists.check_fresh(self.tree, settings(), day(BUILT) + self.limit * DAY_SECONDS), self.limit)

    def test_older_lists_are_refused_with_what_to_do(self):
        with self.assertRaisesRegex(ReleaseError, "release.py refresh"):
            bundled_lists.check_fresh(self.tree, settings(), day(BUILT) + (self.limit + 1) * DAY_SECONDS)

    def test_lists_without_a_build_date_are_refused(self):
        write(self.tree, settings()["lists"]["names_file"], "{}\n")
        with self.assertRaises(ReleaseError):
            bundled_lists.check_fresh(self.tree, settings(), day(BUILT))


class Refresh(unittest.TestCase):
    def test_each_script_runs_isolated_in_the_repository(self):
        calls = []

        def run(command, **options):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with contextlib.redirect_stdout(io.StringIO()):
            bundled_lists.refresh("/made/up/repository", settings(), run=run)
        scripts = settings()["lists"]["refresh"]
        self.assertEqual([c[0][:2] for c in calls[:len(scripts)]], [[sys.executable, "-I"]] * len(scripts))
        self.assertEqual([c[0][2] for c in calls[:len(scripts)]], [f"/made/up/repository/{s}" for s in scripts])
        self.assertTrue(all(c[1]["cwd"] == "/made/up/repository" for c in calls[:len(scripts)]))

    def test_a_failing_script_stops_the_refresh(self):
        def run(command, **options):
            return subprocess.CompletedProcess(command, 1)

        with self.assertRaises(ReleaseError), contextlib.redirect_stdout(io.StringIO()):
            bundled_lists.refresh("/made/up/repository", settings(), run=run)


if __name__ == "__main__":
    unittest.main()
