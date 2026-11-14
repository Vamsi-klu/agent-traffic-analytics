"""The server half's shared secret, $CAKE_HOME/srv_secret: agentcake/edge_secret.py (from cake 0.3.3;
these tests moved here with it from test_demo_token.py).

    python3 -I -m unittest discover -s tests -p test_edge_secret.py -v      (from the Agent Cake folder)

srv_secret() reads it and takes no secret shorter than secret_min_chars; create_secret() makes one readable by its
owner only and never writes over a file that is there; ensure_secret() makes one on first use, once, whichever of many
threads or another process comes first. Every test runs in a scratch CAKE_HOME.
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import edge_secret, paths  # noqa: E402
from agentcake.datafiles import sizes  # noqa: E402

OWNER_ONLY = 0o600
THREADS_AT_ONCE = 12


class Secret(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-secret-")
        self.addCleanup(shutil.rmtree, self.home, True)
        environment = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        environment.start()
        self.addCleanup(environment.stop)

    def write(self, text):
        with open(paths.secret_file(), "w", encoding="utf-8") as f:
            f.write(text)


class Reading(Secret):
    def test_no_file_no_secret(self):
        self.assertIsNone(edge_secret.srv_secret())

    def test_a_secret_shorter_than_the_minimum_is_none(self):
        shortest = sizes()["secret_min_chars"]
        self.write("s" * (shortest - 1) + "\n")
        self.assertIsNone(edge_secret.srv_secret())
        self.write("s" * shortest + "\n")
        self.assertEqual(edge_secret.srv_secret(), b"s" * shortest, "the line break is not part of it")


class Creating(Secret):
    def test_a_new_secret_is_readable_by_its_owner_only(self):
        edge_secret.create_secret()
        self.assertEqual(os.stat(paths.secret_file()).st_mode & 0o777, OWNER_ONLY)
        self.assertIsNotNone(edge_secret.srv_secret())

    def test_a_file_that_is_there_is_never_written_over(self):
        self.write("k" * sizes()["secret_min_chars"])
        with self.assertRaises(FileExistsError):
            edge_secret.create_secret()
        self.assertEqual(edge_secret.srv_secret(), b"k" * sizes()["secret_min_chars"])


class EnsureSecret(Secret):
    def test_makes_a_secret_when_there_is_none(self):
        secret = edge_secret.ensure_secret()
        self.assertEqual(secret, edge_secret.srv_secret())
        self.assertEqual(os.stat(os.path.join(self.home, "srv_secret")).st_mode & 0o777, OWNER_ONLY)

    def test_keeps_the_secret_there_is(self):
        edge_secret.create_secret()
        secret = edge_secret.srv_secret()
        with mock.patch.object(edge_secret, "create_secret") as create:
            self.assertEqual(edge_secret.ensure_secret(), secret)
        create.assert_not_called()

    def test_takes_the_secret_another_process_made_first(self):
        """Another process makes the file between this one's look and its own create: this one reads theirs."""
        real_create = edge_secret.create_secret

        def another_process_was_first():
            real_create()  # the other process's secret
            raise FileExistsError(os.path.join(self.home, "srv_secret"))  # what this process's own create then meets
        with mock.patch.object(edge_secret, "create_secret", side_effect=another_process_was_first) as create:
            secret = edge_secret.ensure_secret()
        self.assertEqual((create.call_count, secret), (1, edge_secret.srv_secret()))

    def test_threads_at_once_make_one_secret(self):
        start_together = threading.Barrier(THREADS_AT_ONCE)
        secrets_seen = [None] * THREADS_AT_ONCE

        def first_page(n):
            start_together.wait()
            secrets_seen[n] = edge_secret.ensure_secret()
        with mock.patch.object(edge_secret, "create_secret", wraps=edge_secret.create_secret) as create:
            threads = [threading.Thread(target=first_page, args=(n,)) for n in range(THREADS_AT_ONCE)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual((create.call_count, set(secrets_seen)), (1, {edge_secret.srv_secret()}))


if __name__ == "__main__":
    unittest.main()
