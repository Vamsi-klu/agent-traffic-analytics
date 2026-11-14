"""Server mode end to end (0.3.3, data rules 0.3.4): 35 checks against one real `agentcake serve`.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Moved from our own research code (smoke_server_mode.py). One server
runs in a scratch CAKE_HOME on two free ports, set up through the command line the way SERVER.md says. The test plays
the load balancer (it sets the X-Cake-* headers a load balancer sets) and tartini.ai's web server (it signs
Server-Timing tokens in the c1 format of cake-server-timing.js). Checks: the public listener serves only the script,
the recorder, collect and the health check under /cake; the local page stays on 127.0.0.1; a token is accepted once,
and replayed, stale or forged tokens are refused; the visitor's address is looked up and never stored.
"""
import base64, hashlib, hmac, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import agentcake  # noqa: E402
from cake_server import POLL_S, free_port, pages_stub  # noqa: E402

AGENTCAKE = [sys.executable, "-I", os.path.join(ROOT, "agentcake", "__main__.py")]  # what bin/agentcake runs
RANGES = os.path.join(ROOT, "agentcake", "data", "lists", "ip_ranges.json")
SITE_KEY = "ck_tartini"
PREFIX = "/cake"
START_TIMEOUT_S = 10
# Everything that is not the script, the recorder, collect or the health check below the prefix: all 404 publicly.
NOT_SERVED = ("/cake/", "/cake/api/sessions", "/cake/api/settings", "/cake/api/session/x", "/cake/assets/x.js", "/cake/api/health",
              "/cake/demo", "/", "/settings", "/cake.js", "/cakex/cake.js")


def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=5) as x:
            return x.status, dict(x.headers), x.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, dict(e.headers), e.read()
    except (urllib.error.URLError, ConnectionError) as e:  # the server refused before reading the body
        return "closed", {}, str(e).encode()


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sign(secret, payload):
    """A token the way tartini.ai's cake-server-timing.js signs it: c1.<payload>.<HMAC-SHA256>."""
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"c1.{body}." + b64(hmac.new(secret, f"c1.{body}".encode(), hashlib.sha256).digest())


class ServerMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="agentcake-smoke-")
        cls.env = dict(os.environ, CAKE_HOME=cls.home, CAKE_WEB_DIR=pages_stub())
        cls.env.pop("CAKE_PORT", None)
        local, public = free_port(), free_port()
        cls.P, cls.L = f"http://127.0.0.1:{public}", f"http://127.0.0.1:{local}"
        for key, value in (("port", local), ("public_listen", f"127.0.0.1:{public}"), ("path_prefix", PREFIX),
                           ("trust_lb", "true"), ("site_key", SITE_KEY)):
            cls.cli("config", "set", key, str(value))
        cls.bad_prefix = cls.cli("config", "set", "path_prefix", "/ca ke")
        cls.cli("secret", "init")
        cls.secret_print = cls.cli("secret", "print")
        cls.secret = cls.secret_print.stdout.strip().encode()
        cls.server = subprocess.Popen(AGENTCAKE + ["serve"], env=cls.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.wait_until_public_health_answers()
        cls.send_visits()

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(5)
        cls.server.stdout.close()
        shutil.rmtree(cls.home, ignore_errors=True)

    @classmethod
    def cli(cls, *args):
        return subprocess.run(AGENTCAKE + list(args), env=cls.env, capture_output=True, text=True)

    @classmethod
    def wait_until_public_health_answers(cls):
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError("agentcake serve exited: " + cls.server.stdout.read())
            if req(cls.P + PREFIX + "/healthz")[0] == 200:
                return
            time.sleep(POLL_S)
        raise RuntimeError(f"agentcake serve did not answer within {START_TIMEOUT_S} s")

    @classmethod
    def send_visits(cls):
        """The visits, in order: a page with a valid token, the same token again from the same session and from
        another one, a stale and a forged token, a wrong site key, a body over 1 MB, a visit that says it is a test."""
        with open(RANGES, encoding="utf-8") as f:
            block = [e for e in json.load(f)["ranges"] if e["label"] == "OpenAI ChatGPT-User"][0]["v4"][0]
        cls.agent_ip = block.split("/")[0]  # inside OpenAI's PUBLISHED range, not a visitor's
        now = int(time.time() * 1000)
        day = time.strftime("%Y-%m-%d", time.gmtime(now / 1000))
        pre = ".".join(cls.agent_ip.split(".")[:3]) + ".0/24"
        cls.ik = hmac.new(cls.secret, f"ip|{day}|{pre}".encode(), hashlib.sha256).hexdigest()[:16]
        tok = sign(cls.secret, {"v": 1, "id": "tok-1", "t": now, "p": "/", "bs": {"t": "agent", "a": "chatgpt-agent", "r": ["web-bot-auth"]},
                                "bsv": "0.4.2", "sf": {"s": "none", "m": "navigate", "d": "document", "u": None}, "md": False, "al": "en-US",
                                "ch": {"ua": None, "pf": None, "mb": None}, "ua": "Mozilla/5.0", "hn": ["host", "user-agent"],
                                "sg": {"a": "\"https://chatgpt.com\"", "s": True, "i": True}, "rg": "US", "ik": cls.ik})
        lb = {"X-Cake-Client-IP": cls.agent_ip, "X-Cake-Region": "US", "X-Cake-JA4": "t13d1516h2_8daaf6152771_d8a2da3f94cd",
              "X-Cake-Proto": "HTTP/2", "Content-Type": "text/plain", "Signature-Agent": "\"https://chatgpt.com\"", "Signature": "sig1=:AAAA:"}
        ev = [{"type": 4, "timestamp": now, "data": {"href": "https://tartini.ai/"}},
              {"type": 3, "timestamp": now + 500, "data": {"source": 2, "type": 2, "id": 1, "x": 10, "y": 10}}]

        def body(sid, token, events=ev):
            return json.dumps({"k": SITE_KEY, "s": sid, "u": "https://tartini.ai/", "ua": "Mozilla/5.0", "wd": False,
                               "e": events, "st": token}).encode()

        collect = cls.P + PREFIX + "/collect"
        cls.accepted = req(collect, body("sessA", tok), lb, "POST")
        cls.dup = req(collect, body("sessA", tok, []), lb, "POST")
        cls.replayed = req(collect, body("sessB", tok, []), lb, "POST")
        cls.stale = req(collect, body("sessC", sign(cls.secret, {"v": 1, "id": "tok-old", "t": now - 16 * 60 * 1000}), []), lb, "POST")
        cls.forged = req(collect, body("sessD", sign(b"x" * 48, {"v": 1, "id": "tok-f", "t": now}), []), lb, "POST")
        cls.wrong_key = req(collect, json.dumps({"k": "ck_other", "s": "x"}).encode(), lb, "POST")
        cls.too_big = req(collect, b"x" * 1_000_001, lb, "POST")
        req(collect, json.dumps({"k": SITE_KEY, "s": "sessT", "u": "https://tartini.ai/", "ua": "x", "test": True, "e": []}).encode(), lb, "POST")

    def query(self, sql):
        con = sqlite3.connect(os.path.join(self.home, "cake.db"))
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def net_of_session_a(self):
        return json.loads(self.query("SELECT net FROM sessions WHERE id='sessA'")[0][0])

    def health(self):
        return json.loads(req(self.L + "/api/health")[2])

    # ---------------------------------------------------------------- setup through the command line
    def test_config_set_refuses_a_bad_path_prefix(self):
        self.assertEqual(self.bad_prefix.returncode, 2)

    def test_secret_init_and_print(self):
        self.assertEqual(self.secret_print.returncode, 0)
        self.assertGreaterEqual(len(self.secret), 32)
        self.assertEqual(os.stat(os.path.join(self.home, "srv_secret")).st_mode & 0o777, 0o600)

    # ---------------------------------------------------------------- what the public listener serves
    def test_public_health_check(self):
        self.assertEqual(req(self.P + "/cake/healthz")[0], 200)

    def test_public_serves_cake_js_under_the_prefix(self):
        st, _, js = req(self.P + "/cake/cake.js")
        self.assertEqual(st, 200)
        self.assertIn(b"serverTiming", js)
        self.assertRegex(js, rb"window\.cake\s*=\s*\{\s*stop\b")  # window.cake.stop(), formatted or minified

    def test_public_serves_the_recorder_under_the_prefix(self):
        self.assertEqual(req(self.P + "/cake/rrweb-record.min.js")[0], 200)

    def test_public_sends_no_cors_header(self):
        self.assertNotIn("Access-Control-Allow-Origin", req(self.P + "/cake/cake.js")[1])

    def test_local_page_stays_on_127_0_0_1(self):
        self.assertEqual(req(self.L + "/")[0], 200)

    # ---------------------------------------------------------------- tokens and collect
    def test_collect_accepts_a_signed_token(self):
        st, h, _ = self.accepted
        self.assertEqual((st, h.get("X-Cake-Token")), (204, "ok"))

    def test_same_token_again_from_the_same_session_is_dup(self):
        self.assertEqual(self.dup[1].get("X-Cake-Token"), "dup")

    def test_same_token_from_another_session_is_replay(self):
        self.assertEqual(self.replayed[1].get("X-Cake-Token"), "replay")

    def test_token_older_than_15_minutes_is_stale(self):
        self.assertEqual(self.stale[1].get("X-Cake-Token"), "stale")

    def test_token_signed_with_another_secret_is_bad(self):
        self.assertEqual(self.forged[1].get("X-Cake-Token"), "bad")

    def test_wrong_site_key_is_403(self):
        self.assertEqual(self.wrong_key[0], 403)

    def test_body_over_1_mb_is_refused_unread(self):
        self.assertIn(self.too_big[0], (413, "closed"))

    # ---------------------------------------------------------------- what was kept
    def test_the_session_page_shows_the_server_half(self):
        st, _, body = req(self.L + "/api/session/sessA")  # the page draws it from the JSON API
        self.assertEqual(st, 200)
        pages = json.loads(body)["server"]["pages"]
        self.assertEqual([(p["path"], p["signature"], p["same_network"]) for p in pages],
                         [("/", {"agent": "\"https://chatgpt.com\"", "verified": False}, True)])

    def test_published_range_found(self):
        net = self.net_of_session_a()
        self.assertEqual((net.get("range"), net.get("range_kind")), ("OpenAI ChatGPT-User", "agent"))

    def test_the_address_is_nowhere_in_the_database(self):
        dump = "\n".join(str(r) for r in self.query("SELECT * FROM sessions") + self.query("SELECT * FROM srv"))
        self.assertNotIn(self.agent_ip, dump)
        with open(os.path.join(self.home, "cake.db"), "rb") as f:
            self.assertNotIn(self.agent_ip, f.read().decode("latin-1"))

    def test_network_key_matched_same_24(self):
        self.assertEqual(self.query("SELECT net_match FROM srv WHERE id='tok-1'"), [(1,)])

    def test_ik_itself_not_stored(self):
        dump = "\n".join(str(r) for r in self.query("SELECT * FROM sessions") + self.query("SELECT * FROM srv"))
        self.assertNotIn(self.ik, dump)

    def test_judged_source_from_the_published_range(self):
        # the published agent range is the operator's infrastructure, a reason of the four layers' verdict
        cls, reasons = self.query("SELECT verdict_class, reasons FROM sessions WHERE id='sessA'")[0]
        self.assertEqual(cls, "agent")
        self.assertIn("OpenAI ChatGPT-User", reasons or "")

    def test_cake_js_request_signature_kept(self):
        self.assertEqual((self.net_of_session_a().get("sig") or {}).get("Signature-Agent"), "\"https://chatgpt.com\"")

    def test_public_visit_cannot_mark_itself_a_test(self):
        self.assertEqual(self.query("SELECT is_test FROM sessions WHERE id='sessT'"), [(0,)])

    def test_health_reports_the_version(self):
        self.assertEqual(self.health().get("version"), agentcake.__version__)

    def test_health_reports_disk_space(self):
        space = self.health().get("space")
        self.assertIsInstance(space, dict)
        self.assertGreater(space.get("budget", 0), 0)


def _not_served(path):
    def test(self):
        self.assertEqual(req(self.P + path)[0], 404)
    test.__doc__ = f"public: {path} is not served"
    return test


# one test per path, so each shows up (and fails) on its own
for _path in NOT_SERVED:
    setattr(ServerMode, "test_public_does_not_serve_" + (_path.strip("/").replace("/", "_").replace(".", "_") or "root"),
            _not_served(_path))


if __name__ == "__main__":
    unittest.main()
