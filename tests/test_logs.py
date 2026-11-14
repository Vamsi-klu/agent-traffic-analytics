"""`agentcake logs import` and `agentcake logs formats` (S4.4): agentcake/logs.py against a real `agentcake serve`.

    python3 -I -m unittest discover -s tests -p test_logs.py -v      (from the Agent Cake folder)

The server runs in server mode with trust_lb, the test plays the load balancer and the visitors' browsers: a few
visits upload through the public listener, and the web server's log holds their page requests among other lines and
other visitors. `logs import` reads the log where it is (it is never copied), sends the page requests to /edge signed
with the secret of its CAKE_HOME, and prints counts. Afterwards no file of CAKE_HOME and no output line holds any
address of the log. A missing file, a log of no known format, a cake that does not answer or holds another secret are
errors that say so; --since leaves older lines out; a log without the recommended headers is told which it lacks,
and so is doctor.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import netfacts, wording  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.units import MS_PER_S  # noqa: E402
from cake_server import SITE_KEY, CakeServer, free_port, http, run_cli  # noqa: E402
from log_samples import LINE_WRITERS, SITE_HOST, USER_AGENTS, Truth  # noqa: E402

LB = netfacts.lb_headers()
VISITORS = (("192.0.2.61", USER_AGENTS[0]), ("198.51.100.62", USER_AGENTS[2]), ("203.0.113.63", USER_AGENTS[4]))
STRANGERS = (("192.0.2.71", USER_AGENTS[1]), ("203.0.113.72", USER_AGENTS[5]))
PAGE_TO_UPLOAD_MS = 1500


def now_ms():
    return int(time.time() * MS_PER_S)


def page(t_ms, ip, ua, path="/", status=200):
    headers = {"user-agent": ua, "accept-language": "en-US,en;q=0.9", "sec-fetch-site": "none",
               "sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-user": "?1"}
    return Truth(t_ms, ip, "GET", path, "HTTP/2.0", status, SITE_HOST, "https", headers)


def visit(server, number, ip, ua):
    """One visitor's first upload through the public listener, as its browser and the load balancer send it; the
    page request that opened the page reached the web server a moment before."""
    opened = now_ms() - PAGE_TO_UPLOAD_MS
    body = json.dumps({"v": 1, "k": SITE_KEY, "s": f"logvisit{number}", "pv": f"pv{number}", "seq": 0, "t": now_ms(),
                       "u": f"https://{SITE_HOST}/", "ua": ua, "r": []}).encode()
    headers = {"Content-Type": "text/plain", "User-Agent": ua, LB["ip"]: ip, LB["region"]: "", LB["ja4"]: "",
               LB["proto"]: "HTTP/2"}
    status = http(server.public + "/collect", body, headers, "POST")[0]
    if status != 204:
        raise AssertionError(f"the visit was not accepted: {status}")
    return opened


def write_log(folder, name, truths, writer="nginx-agentcake"):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as f:
        for truth in sorted(truths, key=lambda t: t.t_ms):
            f.write(LINE_WRITERS[writer](truth) + "\n")
    return path


class ImportCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=True)
        cls.logs_dir = tempfile.mkdtemp(prefix="agentcake-logs-")  # the web server's, outside CAKE_HOME
        truths = []
        for number, (ip, ua) in enumerate(VISITORS):
            opened = visit(cls.server, number, ip, ua)
            truths += [page(opened, ip, ua), page(opened + 90, ip, ua, "/static/app.css")]
        for ip, ua in STRANGERS:
            truths.append(page(now_ms() - PAGE_TO_UPLOAD_MS, ip, ua))
        truths.append(page(now_ms() - 3 * 3600 * MS_PER_S, *STRANGERS[0], "/yesterday"))
        cls.addresses = {truth.ip for truth in truths}
        cls.log = write_log(cls.logs_dir, "agentcake.log", truths)
        cls.done = run_cli(cls.server.env, "logs", "import", cls.log)

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()
        shutil.rmtree(cls.logs_dir, ignore_errors=True)

    def log_rows(self):
        con = self.server.database()
        try:
            rows = con.execute("SELECT session_id, facts FROM requests WHERE seq IS NULL").fetchall()
        finally:
            con.close()
        return [(sid, json.loads(facts)) for sid, facts in rows if json.loads(facts).get("source") == "log"]

    def test_the_page_requests_of_the_visits_are_matched_and_stored(self):
        self.assertEqual(self.done.returncode, 0, self.done.stdout + self.done.stderr)
        self.assertEqual(sorted(sid for sid, _ in self.log_rows()), [f"logvisit{n}" for n in range(len(VISITORS))])

    def test_the_counts_are_printed(self):
        lines, sent = len(VISITORS) * 2 + len(STRANGERS) + 1, len(VISITORS) + len(STRANGERS) + 1
        self.assertIn(f"{lines} lines", self.done.stdout)
        self.assertIn(f"{sent} page requests sent", self.done.stdout)
        self.assertIn(f"{len(VISITORS)} matched a visit", self.done.stdout)
        self.assertIn(f"{len(STRANGERS) + 1} matched no visit and were dropped", self.done.stdout)

    def test_no_address_of_the_log_is_in_cake_home_or_the_output(self):
        output = self.done.stdout + self.done.stderr
        for folder, _, files in os.walk(self.server.home):
            for name in files:
                with open(os.path.join(folder, name), "rb") as f:
                    text = f.read().decode("latin-1")
                for address in self.addresses:
                    self.assertNotIn(address, text, name)
        for address in self.addresses:
            self.assertNotIn(address, output)

    def test_the_log_file_is_read_where_it_is_and_never_copied(self):
        with open(self.log, "rb") as f:
            first_line = f.readline().strip()
        for folder, _, files in os.walk(self.server.home):
            for name in files:
                with open(os.path.join(folder, name), "rb") as f:
                    self.assertNotIn(first_line, f.read(), name)

    def test_importing_again_finds_every_line_imported_already(self):
        again = run_cli(self.server.env, "logs", "import", self.log)
        self.assertIn(f"{len(VISITORS)} were already imported", again.stdout)
        self.assertEqual(len(self.log_rows()), len(VISITORS))

    def test_since_leaves_older_lines_out(self):
        done = run_cli(self.server.env, "logs", "import", self.log, "--since", "1h")
        self.assertIn("1 older than --since", done.stdout)

    def test_to_sends_to_another_cake_with_the_same_secret_and_fails_with_another(self):
        home = tempfile.mkdtemp(prefix="agentcake-logs-web-server-")
        self.addCleanup(shutil.rmtree, home, True)
        env = dict(self.server.env, CAKE_HOME=home)
        done = run_cli(env, "logs", "import", self.log, "--to", self.server.public)
        self.assertEqual(done.returncode, 1)
        self.assertIn("srv_secret", done.stdout + done.stderr)
        with open(os.path.join(home, "srv_secret"), "w") as f:
            f.write("w" * 64)
        done = run_cli(env, "logs", "import", self.log, "--to", self.server.public)
        self.assertEqual(done.returncode, 1)
        self.assertIn("403", done.stdout + done.stderr)
        shutil.copy(os.path.join(self.server.home, "srv_secret"), os.path.join(home, "srv_secret"))
        done = run_cli(env, "logs", "import", self.log, "--to", self.server.public)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("already imported", done.stdout)


class Errors(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-logs-errors-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = dict(os.environ, CAKE_HOME=self.home, CAKE_PORT=str(free_port()))  # nothing listens there

    def test_usage(self):
        for words in (["logs"], ["logs", "import"], ["logs", "import", "x.log", "--since", "soon"],
                      ["logs", "import", "x.log", "--format", "nope"]):
            self.assertEqual(run_cli(self.env, *words).returncode, 2, words)

    def test_a_missing_file_is_an_error(self):
        done = run_cli(self.env, "logs", "import", os.path.join(self.home, "missing.log"))
        self.assertEqual(done.returncode, 1)
        self.assertIn("missing.log", done.stdout + done.stderr)

    def test_a_log_of_no_known_format_is_an_error(self):
        path = os.path.join(self.home, "odd.log")
        with open(path, "w") as f:
            f.write("this is not an access log\n")
        done = run_cli(self.env, "logs", "import", path)
        self.assertEqual(done.returncode, 1)
        self.assertIn("--nginx-format", done.stdout + done.stderr)

    def test_nothing_answering_is_an_error_that_says_so(self):
        path = write_log(self.home, "a.log", [page(now_ms(), *VISITORS[0])])
        done = run_cli(self.env, "logs", "import", path)
        self.assertEqual(done.returncode, 1)
        self.assertIn("nothing answers", done.stdout + done.stderr)

    def test_formats_prints_the_recommended_config(self):
        done = run_cli(self.env, "logs", "formats")
        self.assertEqual(done.returncode, 0)
        for spec in load("data/logs.json")["formats"].values():
            for line in spec.get("config", ()):
                self.assertIn(line.strip(), done.stdout)


class MissingHeaders(unittest.TestCase):
    """A combined log has none of the recommended headers: the import says which, and so does doctor's check."""

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=True)
        cls.folder = tempfile.mkdtemp(prefix="agentcake-logs-combined-")
        path = write_log(cls.folder, "access.log", [page(now_ms(), *VISITORS[0])], writer="nginx-combined")
        cls.done = run_cli(cls.server.env, "logs", "import", path)

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_the_import_names_what_the_format_lacks(self):
        self.assertEqual(self.done.returncode, 0, self.done.stdout + self.done.stderr)
        for field in ("host", "accept-language", "sec-fetch-site", "signature"):
            self.assertIn(field, self.done.stdout)

    def test_the_server_keeps_it_for_doctor(self):
        con = sqlite3.connect(os.path.join(self.server.home, "cake.db"))
        self.addCleanup(con.close)
        report = json.loads(con.execute("SELECT value FROM settings WHERE key='log_import'").fetchone()[0])
        self.assertEqual(report["format"], "combined")
        self.assertIn("sec-fetch-dest", report["missing"])

    def test_doctor_names_them_in_a_warning(self):
        doctor = run_cli(self.server.env, "doctor").stdout
        line = next(line for line in doctor.splitlines() if f"] {wording.text('doctor_logs')}: " in line)
        self.assertTrue(line.startswith(f"[{wording.text('doctor_warn')}] "), line)
        self.assertIn("combined", line)
        for field in ("host", "sec-fetch-site", "signature"):
            self.assertIn(field, line)


if __name__ == "__main__":
    unittest.main()
