"""tools/releasing/source.py (plan step S6.4): a release starts from the commit alone (no edited or untracked file),
stamped with the commit's time or SOURCE_DATE_EPOCH, and says what the working tree has that the commit has not.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Each test makes a scratch git repository with a made-up author and a fixed commit time.
"""
import os
import subprocess
import unittest

from release_trees import scratch, write

from tools.releasing import source
from tools.releasing.settings import ReleaseError

COMMIT_TIME = 1794528000  # 2026-11-12 00:00:00 UTC, a made-up commit time
MADE_UP_PERSON = {"GIT_AUTHOR_NAME": "Release Test", "GIT_AUTHOR_EMAIL": "release-test@example.com",
                  "GIT_COMMITTER_NAME": "Release Test", "GIT_COMMITTER_EMAIL": "release-test@example.com"}


def git(repository, *args):
    env = dict(os.environ, **MADE_UP_PERSON, GIT_AUTHOR_DATE=f"@{COMMIT_TIME} +0000",
               GIT_COMMITTER_DATE=f"@{COMMIT_TIME} +0000", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", repository, *args], check=True, capture_output=True, env=env)


class Commit(unittest.TestCase):
    def setUp(self):
        self.repo = scratch(self, "agentcake-release-repo-")
        git(self.repo, "init", "-q")
        write(self.repo, "tracked.txt", "committed\n")
        write(self.repo, "bin/run", "#!/bin/sh\n")
        os.chmod(os.path.join(self.repo, "bin", "run"), 0o755)  # protocol: rwxr-xr-x
        git(self.repo, "add", "tracked.txt", "bin/run")
        git(self.repo, "commit", "-q", "-m", "first")

    def test_the_commit_time_is_the_commits(self):
        self.assertEqual(source.commit_time(self.repo, source.head(self.repo), environ={}), COMMIT_TIME)

    def test_source_date_epoch_wins(self):
        self.assertEqual(source.commit_time(self.repo, "HEAD", environ={"SOURCE_DATE_EPOCH": "1700000000"}),
                         1700000000)

    def test_a_source_date_epoch_that_is_not_a_number_stops_the_release(self):
        with self.assertRaises(ReleaseError):
            source.commit_time(self.repo, "HEAD", environ={"SOURCE_DATE_EPOCH": "yesterday"})

    def test_the_export_has_only_what_is_committed(self):
        write(self.repo, "tracked.txt", "edited, not committed\n")
        write(self.repo, "untracked.txt", "never added\n")
        out = os.path.join(scratch(self), "tree")
        source.export(self.repo, source.head(self.repo), out)
        self.assertEqual(sorted(os.listdir(out)), ["bin", "tracked.txt"])
        with open(os.path.join(out, "tracked.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "committed\n")
        self.assertTrue(os.access(os.path.join(out, "bin", "run"), os.X_OK))

    def test_uncommitted_lists_edited_tracked_files_only(self):
        self.assertEqual(source.uncommitted(self.repo), [])
        write(self.repo, "tracked.txt", "edited\n")
        write(self.repo, "untracked.txt", "never added\n")
        self.assertEqual(source.uncommitted(self.repo), ["tracked.txt"])

    def test_a_folder_that_is_not_a_repository_stops_the_release(self):
        with self.assertRaises(ReleaseError):
            source.head(scratch(self))


if __name__ == "__main__":
    unittest.main()
