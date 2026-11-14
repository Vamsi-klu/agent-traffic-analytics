"""POST /edge: agentcake/edge_api.py, the resource `logs import` sends a web server's log records to.

    python3 -I -m unittest discover -s tests -p test_edge_api.py -v      (from the Agent Cake folder)

Only a web server holding the server half's secret (srv_secret) may send records: each request carries the HMAC of
its time and body (the signature itself: test_edge_signature.py). Without it, with another secret, with a time outside the page tokens' window, with a body changed
after signing, or when this Agent Cake has no secret at all, the answer is 403 and nothing is read. A signed request
with an envelope that cannot be read is 400; a good one is matched and answered with its counts. Both listeners
answer /edge, the public one below path_prefix, the way SERVER.md says.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from http.client import HTTPMessage
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config, edge_api, evidence, judging, log_report, logs, store  # noqa: E402
from agentcake.edge_secret import create_secret, srv_secret  # noqa: E402
from agentcake.edge_signature import HEADER, sign  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from agentcake.units import MS_PER_S  # noqa: E402
from cake_server import CakeServer, http, run_cli  # noqa: E402
from log_samples import SITE_HOST, USER_AGENTS  # noqa: E402
from test_log_match import PageView, Visitor, upload_once  # noqa: E402

NOW = 1794500000000


def envelope(records=(), run="edgetest", format_name="nginx-agentcake"):
    return json.dumps({"v": logs.ENVELOPE_VERSION, "run": run, "format": format_name,
                       "fields": {"missing": [], "empty": []}, "records": list(records)}).encode()


def record(t_ms=NOW, ip="192.0.2.44"):
    return {"t": t_ms, "ip": ip, "m": "GET", "u": "/", "s": 200, "h": "shop.example", "sc": "https",
            "hd": {"user-agent": "Mozilla/5.0"}}


def headers_of(pairs):
    message = HTTPMessage()
    for name, value in pairs.items():
        message[name] = value
    return message


class View(unittest.TestCase):
    """The view on a Request, in a scratch CAKE_HOME."""

    def setUp(self):
        home = tempfile.mkdtemp(prefix="agentcake-edge-view-")
        self.addCleanup(shutil.rmtree, home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": home})
        patch.start()
        self.addCleanup(patch.stop)

    def post(self, body, header=None):
        pairs = {HEADER: header} if header is not None else {}
        return edge_api.receive(Request(edge_api.ROUTE, {}, headers_of(pairs), body))

    def test_without_a_secret_here_every_request_is_403(self):
        self.assertEqual(self.post(envelope(), sign(b"x" * 48, envelope(), int(time.time() * MS_PER_S)))
                         .status, 403)

    def test_without_the_signature_or_with_another_secret_it_is_403(self):
        create_secret()
        body = envelope([record()])
        self.assertEqual(self.post(body).status, 403)
        self.assertEqual(self.post(body, sign(b"x" * 48, body, int(time.time() * MS_PER_S))).status, 403)

    def test_a_signed_request_whose_body_is_no_envelope_is_400(self):
        create_secret()
        for body in (b"not json", b"[]", json.dumps({"v": 99, "records": []}).encode(),
                     json.dumps({"v": logs.ENVELOPE_VERSION, "records": "x"}).encode(),
                     envelope([record()] * (edge_api.MAX_RECORDS + 1))):
            answer = self.post(body, sign(srv_secret(), body, int(time.time() * MS_PER_S)))
            self.assertEqual(answer.status, 400, body[:60])

    def test_a_signed_envelope_is_matched_counted_and_reported(self):
        create_secret()
        body = envelope([record(int(time.time() * MS_PER_S))])
        answer = self.post(body, sign(srv_secret(), body, int(time.time() * MS_PER_S)))
        self.assertEqual(answer.status, 200)
        self.assertEqual(json.loads(answer.body)["unmatched"], 1)
        con = store.db()
        self.addCleanup(con.close)
        self.assertEqual(log_report.last(con)["format"], "nginx-agentcake")


class LogLinesAreJudged(unittest.TestCase):
    """The sessions a request's log lines were kept for are judged as soon as it is answered: a log line moves no
    session's end_ms, so neither a later upload, a maintenance round nor an opened page would come back for it."""

    SESSION = "edgevisit"

    def setUp(self):
        home = tempfile.mkdtemp(prefix="agentcake-edge-judging-")
        self.addCleanup(shutil.rmtree, home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": home})
        patch.start()
        self.addCleanup(patch.stop)
        create_secret()
        c, now = config.load_cfg(), int(time.time() * MS_PER_S)
        self.person = Visitor("198.51.100.77", USER_AGENTS[0], "en-US")
        opened = now - 10 * c["judge_quiet_s"] * MS_PER_S
        self.views = [PageView(self.SESSION, f"{self.SESSION}p{k}", path, at, [at + 900])  # first upload 0.9 s later
                      for k, (path, at) in enumerate((("/", opened), ("/cart", opened + 20_000)))]
        con = store.db()
        try:
            for view in self.views:
                upload_once(con, view, 0, view.uploads[0], self.person, c)
            self.final_ms = now - 2 * c["judge_quiet_s"] * MS_PER_S  # its verdict is final before the log comes
            judging.rejudge(con, self.SESSION, self.final_ms, c)
            con.commit()
        finally:
            con.close()

    def post_lines(self, *lines):
        body = envelope([{"t": t_ms, "ip": ip, "m": "GET", "u": path, "s": 200, "h": SITE_HOST, "sc": "https",
                          "hd": {"user-agent": self.person.ua}} for t_ms, ip, path in lines])
        header = sign(srv_secret(), body, int(time.time() * MS_PER_S))
        return json.loads(edge_api.receive(Request(edge_api.ROUTE, {}, headers_of({HEADER: header}), body)).body)

    def judged_log_lines(self):
        """Patches the judging's evidence to note how many log lines of the session each judgement saw."""
        seen, session_evidence = [], evidence.session_evidence

        def noting(con, session_id, *args):
            seen.append(con.execute("SELECT COUNT(*) FROM requests WHERE session_id=? AND seq IS NULL",
                                    (session_id,)).fetchone()[0])
            return session_evidence(con, session_id, *args)
        patch = mock.patch.object(evidence, "session_evidence", noting)
        patch.start()
        self.addCleanup(patch.stop)
        return seen

    def test_lines_of_one_session_in_two_requests_a_moment_apart_are_both_judged(self):
        seen = self.judged_log_lines()
        for view in self.views:  # well inside judge_interval_ms of each other
            self.assertEqual(self.post_lines((view.opened_ms, self.person.ip, view.path))["matched"], 1)
        self.assertEqual(seen, [1, 2])
        con = store.db()
        self.addCleanup(con.close)
        self.assertGreater(con.execute("SELECT judged_ms FROM sessions WHERE id=?", (self.SESSION,)).fetchone()[0],
                           self.final_ms)

    def test_lines_that_match_no_visit_judge_nothing(self):
        seen = self.judged_log_lines()
        view = self.views[0]
        self.assertEqual(self.post_lines((view.opened_ms, "192.0.2.200", view.path))["matched"], 0)
        self.assertEqual(seen, [])


class BothListeners(unittest.TestCase):
    """A real `agentcake serve`: /edge answers on 127.0.0.1 and below path_prefix on the public listener."""

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=True)
        run_cli(cls.server.env, "secret", "init")
        with open(os.path.join(cls.server.home, "srv_secret"), "rb") as f:
            cls.secret = f.read().strip()

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def post(self, base, body, secret):
        headers = {"Content-Type": "application/json"}
        if secret:
            headers[HEADER] = sign(secret, body, int(time.time() * MS_PER_S))
        return http(base + edge_api.ROUTE, body, headers, "POST")

    def test_unsigned_is_403_and_signed_is_200_on_both_listeners(self):
        body = envelope([record(int(time.time() * MS_PER_S))])
        for base in (self.server.local, self.server.public):
            self.assertEqual(self.post(base, body, None)[0], 403, base)
            self.assertEqual(self.post(base, body, b"y" * 48)[0], 403, base)
            status, _, answer = self.post(base, body, self.secret)
            self.assertEqual(status, 200, base)
            self.assertEqual(json.loads(answer)["records"], 1)

    def test_the_address_sent_is_not_in_the_servers_files(self):
        address = "198.51.100.231"
        body = envelope([record(int(time.time() * MS_PER_S), ip=address)])
        self.assertEqual(self.post(self.server.public, body, self.secret)[0], 200)
        for folder, _, files in os.walk(self.server.home):
            for name in files:
                with open(os.path.join(folder, name), "rb") as f:
                    self.assertNotIn(address, f.read().decode("latin-1"), name)


if __name__ == "__main__":
    unittest.main()
