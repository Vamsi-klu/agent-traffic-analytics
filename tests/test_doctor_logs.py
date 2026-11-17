"""`agentcake doctor`, the line about the web server's log import: agentcake/doctor_logs.py.

    python3 -I -m unittest discover -s tests -p test_doctor_logs.py -v      (from the AgentCake folder)

No line before the first import. Then one line on the last import (log_report.py's report in cake.db): PASS when the
log has every recommended header; WARN naming each header the log format lacks or leaves empty on every page request,
and where the recommended format is; FAIL when no line could match because the uploads carry no visitor's address
(trust_lb). doctor() prints it with its other lines, and only the FAIL fails doctor.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import doctor_lines, doctor_logs, log_report, store, wording  # noqa: E402
from cake_server import free_port  # noqa: E402
from test_doctor_machine import run_doctor  # noqa: E402

NOW = 1794500000000
COUNTS = {"records": 10, "matched": 8, "duplicates": 0, "unmatched": 2, "bad": 0, "views_without_address": 0}
COMBINED_LACKS = ["host", "accept-language", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "sec-fetch-user",
                  "sec-ch-ua", "signature-agent", "signature-input", "signature"]


class LogsLine(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-doctor-logs-")
        self.addCleanup(shutil.rmtree, self.home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        patch.start()
        self.addCleanup(patch.stop)

    def imported(self, format_name="nginx-agentcake", missing=(), empty=(), **counts):
        con = store.db()
        try:
            log_report.update(con, {"run": "run1", "format": format_name,
                                    "fields": {"missing": list(missing), "empty": list(empty)}},
                              dict(COUNTS, **counts), NOW)
            con.commit()
        finally:
            con.close()

    def test_no_line_before_the_first_import(self):
        self.assertEqual(doctor_logs.logs_checks(), [])
        store.db().close()
        self.assertEqual(doctor_logs.logs_checks(), [])

    def test_a_log_with_every_recommended_header_passes(self):
        self.imported()
        [(name, verdict, info)] = doctor_logs.logs_checks()
        self.assertEqual((name, verdict), (wording.text("doctor_logs"), True))
        self.assertIn("nginx-agentcake", info)
        self.assertIn("2026-11-12", info)

    def test_each_header_the_format_lacks_or_leaves_empty_is_named_in_a_warning(self):
        self.imported("combined", missing=COMBINED_LACKS[:-1], empty=["accept-language"])
        [(_, verdict, info)] = doctor_logs.logs_checks()
        self.assertEqual(verdict, doctor_lines.WARN)
        for field in COMBINED_LACKS:
            self.assertIn(field, info)
        self.assertIn("logs formats", info)

    def test_uploads_without_an_address_fail_and_say_why(self):
        self.imported(matched=0, unmatched=10, views_without_address=4)
        [(_, verdict, info)] = doctor_logs.logs_checks()
        self.assertIs(verdict, False)
        self.assertIn("trust_lb", info)

    def test_doctor_prints_the_line_with_its_other_checks(self):
        self.imported("combined", missing=COMBINED_LACKS)
        lines, _ = run_doctor()
        line = next(line for line in lines if f"] {wording.text('doctor_logs')}: " in line)
        self.assertTrue(line.startswith(f"[{wording.text('doctor_warn')}]"), line)
        self.assertIn("sec-fetch-site", line)


if __name__ == "__main__":
    unittest.main()
