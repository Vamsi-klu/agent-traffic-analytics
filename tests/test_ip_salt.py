"""The salt of the visitors' address hashes: agentcake/ip_salt.py.

    python3 -I -m unittest discover -s tests -p test_ip_salt.py -v      (from the AgentCake folder)

One salt per period of ip_salt_days, then a new one. A replaced salt must be gone from the database's files too, not
only from its settings row: until a checkpoint the old page is still in cake.db and its copies in cake.db-wal, and a
cell SQLite deletes keeps its bytes unless secure_delete is on (a privacy scan found the old salt in the file
after a replacement). The callers ask for the salt before their transaction's first write, as collect_store and log_match do.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import config, ip_salt, paths, store  # noqa: E402
from agentcake.units import MS_PER_DAY  # noqa: E402

T0 = 1794518371300


def copies_on_disk(salt):
    """How many times the salt, as the settings row writes it (hex), is in cake.db and its write-ahead log."""
    found = 0
    for path in (paths.db_file(), paths.db_file() + "-wal"):
        if os.path.exists(path):
            with open(path, "rb") as f:
                found += f.read().count(salt.hex().encode("ascii"))
    return found


class Salt(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp(prefix="agentcake-ip-salt-")
        self.addCleanup(shutil.rmtree, home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": home})
        patch.start()
        self.addCleanup(patch.stop)
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.period_ms = config.load_cfg()["ip_salt_days"] * MS_PER_DAY

    def test_one_salt_per_period_then_a_new_one(self):
        first = ip_salt.current(self.con, T0)
        self.assertEqual(ip_salt.current(self.con, T0 + self.period_ms - 1), first)
        later = ip_salt.current(self.con, T0 + self.period_ms)
        self.assertNotEqual(later, first)
        self.assertEqual(ip_salt.current(self.con, T0 + self.period_ms + 1), later)

    def test_a_small_step_back_keeps_the_salt(self):
        """The callers take their time before they wait for store.LOCK, so a time taken first can reach the lock
        after a later one that started the salt (two first uploads 6 ms apart did): that is no clock set back."""
        first = ip_salt.current(self.con, T0)
        self.assertEqual(ip_salt.current(self.con, T0 - 6), first)
        self.assertEqual(ip_salt.current(self.con, T0 - ip_salt.BACKWARD_TOLERANCE_MS), first)

    def test_a_clock_set_back_beyond_the_tolerance_starts_a_new_salt(self):
        first = ip_salt.current(self.con, T0)
        self.assertNotEqual(ip_salt.current(self.con, T0 - ip_salt.BACKWARD_TOLERANCE_MS - 1), first)

    def test_a_replaced_salt_is_gone_from_the_database_file_and_its_log(self):
        old = ip_salt.current(self.con, T0)
        self.con.commit()
        self.assertGreater(copies_on_disk(old), 0)  # the search finds a salt that is there
        new = ip_salt.current(self.con, T0 + self.period_ms)
        self.con.commit()
        self.assertGreater(copies_on_disk(new), 0)
        self.assertEqual(copies_on_disk(old), 0)

    def test_a_replaced_salt_is_gone_also_after_the_file_held_it(self):
        old = ip_salt.current(self.con, T0)
        self.con.commit()
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # the old salt now in cake.db itself, as after a restart
        ip_salt.current(self.con, T0 + self.period_ms)
        self.con.commit()
        self.assertEqual(copies_on_disk(old), 0)

    def test_the_callers_transaction_goes_on_after_a_replacement(self):
        ip_salt.current(self.con, T0)
        self.con.commit()
        salt = ip_salt.current(self.con, T0 + self.period_ms)
        self.con.execute("INSERT INTO requests(session_id, recv_ms, seq, facts) VALUES('s1', ?, 0, '{}')", (T0,))
        self.con.rollback()  # the caller's own work is still its to keep or drop
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)
        self.assertEqual(ip_salt.current(self.con, T0 + self.period_ms), salt, "the new salt was kept")

    def test_the_callers_connection_keeps_its_secure_delete_setting(self):
        before = self.con.execute("PRAGMA secure_delete").fetchone()[0]
        ip_salt.current(self.con, T0)
        ip_salt.current(self.con, T0 + self.period_ms)
        self.assertEqual(self.con.execute("PRAGMA secure_delete").fetchone()[0], before)


if __name__ == "__main__":
    unittest.main()
