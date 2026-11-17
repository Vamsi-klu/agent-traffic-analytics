"""The report of the last log import: agentcake/log_report.py. doctor's line on it: test_doctor_logs.py.

    python3 -I -m unittest discover -s tests -p test_log_report.py -v      (from the AgentCake folder)

Each /edge request adds its counts to the report of its import run (a new run starts new counts) and keeps the
fields the run's log format lacks or leaves empty. stored_report() reads it from cake.db without writing: None
before the database or the first import.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import log_report, store  # noqa: E402

NOW = 1794500000000
COUNTS = {"records": 10, "matched": 8, "duplicates": 0, "unmatched": 2, "bad": 0, "views_without_address": 0}


def meta(run="run1", format_name="nginx-agentcake", missing=(), empty=()):
    return {"run": run, "format": format_name, "fields": {"missing": list(missing), "empty": list(empty)}}


class Report(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-log-report-")
        self.addCleanup(shutil.rmtree, self.home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        patch.start()
        self.addCleanup(patch.stop)

    def update(self, envelope, counts=COUNTS, now=NOW):
        con = store.db()
        try:
            log_report.update(con, envelope, counts, now)
            con.commit()
            return log_report.last(con)
        finally:
            con.close()

    def test_before_any_import_there_is_no_report(self):
        self.assertIsNone(log_report.stored_report())
        store.db().close()  # a database without a report
        self.assertIsNone(log_report.stored_report())

    def test_a_run_adds_up_and_a_new_run_starts_again(self):
        self.update(meta())
        report = self.update(meta(), now=NOW + 1)
        self.assertEqual((report["records"], report["matched"], report["last_ms"]), (20, 16, NOW + 1))
        report = self.update(meta(run="run2"))
        self.assertEqual(report["records"], 10)

    def test_the_stored_report_is_the_one_kept(self):
        kept = self.update(meta(format_name="combined", missing=["host"]))
        self.assertEqual(log_report.stored_report(), kept)
        self.assertEqual((kept["format"], kept["missing"], kept["empty"]), ("combined", ["host"], []))

    def test_reading_the_stored_report_does_not_write(self):
        self.update(meta())
        before = os.path.getmtime(os.path.join(self.home, "cake.db"))
        log_report.stored_report()
        self.assertEqual(os.path.getmtime(os.path.join(self.home, "cake.db")), before)


if __name__ == "__main__":
    unittest.main()
