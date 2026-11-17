"""Settings and data files: every value comes from defaults.json or data/*.json, the user's config.json
overrides a default, `config get` says where each value comes from, and bad values are refused as in 0.3.4.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

"Behaviour follows the default" is shown by changing a default in this process (mock.patch.dict on the table read
from defaults.json, or on a loaded data file) and watching the code that uses it change. Every test has its own
CAKE_HOME. Clocks are passed in or patched; nothing sleeps.
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, unittest
import urllib.error, urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import collect, config, datafiles, edge_secret, edge_token, netfacts, server, space, store, streams, wording  # noqa: E402
from agentcake.detect import lists  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from cake_server import POLL_S, free_port  # noqa: E402

AGENTCAKE = [sys.executable, "-I", os.path.join(ROOT, "agentcake", "__main__.py")]
MIB = 1024 * 1024
NOW_S = 1_800_000_000  # a fixed clock: 2027-01-15


def click(at_ms):
    return {"type": 3, "timestamp": at_ms, "data": {"source": 2, "type": 2, "x": 1, "y": 1}}


class Home(unittest.TestCase):
    """A scratch CAKE_HOME, and no $CAKE_PORT unless a test sets one."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-config-")
        self.addCleanup(shutil.rmtree, self.home, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        env.start(); self.addCleanup(env.stop)
        os.environ.pop("CAKE_PORT", None)

    def write_user(self, values):
        with open(os.path.join(self.home, "config.json"), "w") as f:
            json.dump(values, f)

    def read_user(self):
        with open(os.path.join(self.home, "config.json")) as f:
            return json.load(f)

    def post(self, body, public=False, at_s=NOW_S):
        with mock.patch.object(collect, "clock_ms", return_value=at_s * 1000):
            return collect.collect(Request("/collect", {}, http.client.HTTPMessage(), json.dumps(body).encode()), public)

    def session_row(self, sid, columns):
        con = store.db()
        try:
            return con.execute(f"SELECT {columns} FROM sessions WHERE id=?", (sid,)).fetchone()
        finally:
            con.close()


class DefaultsFile(unittest.TestCase):
    def test_every_setting_has_a_default_and_says_what_it_is_for(self):
        for key, spec in config.SCHEMA.items():
            self.assertIn("default", spec, key)
            self.assertTrue(spec.get("about"), key)

    def test_every_default_passes_its_own_check(self):
        for key, spec in config.SCHEMA.items():
            default = spec["default"]
            if default is None or "retired" in spec:  # a retired setting refuses every value (RetiredSettings)
                continue
            typed = json.dumps(default) if isinstance(default, bool) else str(default)
            value = config.coerce(key, typed)  # raises if the default breaks its own rule
            if not isinstance(default, str):  # text is tidied (site_dir becomes a full path), numbers come back as they are
                self.assertEqual(value, default, key)


class UserOverrides(Home):
    def test_user_config_overrides_the_default_and_says_so(self):
        self.write_user({"budget_mb": 2048})
        self.assertEqual(config.load_cfg()["budget_mb"], 2048)
        self.assertEqual(config.sources()["budget_mb"], "user")
        self.assertEqual(config.sources()["retention_days"], "default")

    def test_cake_port_overrides_both_and_says_so(self):
        self.write_user({"port": 9001})
        with mock.patch.dict(os.environ, {"CAKE_PORT": "9002"}):
            self.assertEqual(config.load_cfg()["port"], 9002)
            self.assertEqual(config.sources()["port"], "env")

    def test_config_json_keeps_only_what_the_user_set(self):
        config.ensure_cfg()
        self.assertEqual(set(self.read_user()), {"site_key"})
        config.save_user(budget_mb=500)
        self.assertEqual(set(self.read_user()), {"site_key", "budget_mb"})

    def test_config_get_lists_every_setting_with_its_value_and_source(self):
        self.write_user({"budget_mb": 2048})
        port = str(free_port())
        out = subprocess.run(AGENTCAKE + ["config", "get"], env=dict(os.environ, CAKE_PORT=port), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        rows = {line.split()[0]: line.split(None, 2)[1:] for line in out.stdout.splitlines()}
        self.assertEqual(set(config.DEFAULTS) - set(rows), set())
        labels = wording.raw("config_source")
        self.assertEqual(rows["budget_mb"], ["2048", labels["user"]])
        self.assertEqual(rows["port"], [port, labels["env"]])
        self.assertEqual(rows["retention_days"], ["0", labels["default"]])
        self.assertEqual(rows["site_key"][1], labels["user"])


class BadValues(Home):
    """Refused the way cake 0.3.4 refused them, and the new numbers by their min / max."""

    def test_refused(self):
        for key, value in (("retention_days", "7"), ("budget_mb", "10"), ("path_prefix", "/ca ke"),
                           ("public_listen", "anywhere"), ("site_key", "bad"), ("site_key", ""), ("port", "x"),
                           ("token_max_age_ms", "soon"), ("budget_warn_ratio", "1.5"), ("start_poll_s", "-1")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                config.coerce(key, value)

    def test_accepted_and_tidied(self):
        self.assertEqual(config.coerce("site_domain", "https://example.com/"), "example.com")
        self.assertEqual(config.coerce("path_prefix", "cake/"), "/cake")
        self.assertEqual(config.coerce("path_prefix", "/"), "")
        self.assertEqual(config.coerce("public_listen", ""), "")
        self.assertIs(config.coerce("trust_lb", "on"), True)

    def test_config_set_refuses_and_keeps_the_file(self):
        self.write_user({"retention_days": 30})
        out = subprocess.run(AGENTCAKE + ["config", "set", "retention_days", "7"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.read_user()["retention_days"], 30)


class RetiredSettings(Home):
    """mask_inputs turned input masking off in 0.3.4. Since 0.4.0 cake.js masks every input whatever is configured
    (data/privacy.json), so setting it is refused with the reason instead of being saved and ignored."""

    def test_mask_inputs_cannot_be_set(self):
        for value in ("false", "true"):
            with self.subTest(value=value), self.assertRaises(ValueError) as refused:
                config.coerce("mask_inputs", value)
            self.assertEqual(str(refused.exception), wording.raw("invalid_setting")["mask_inputs"])

    def test_config_set_mask_inputs_says_why_and_keeps_the_file(self):
        self.write_user({"budget_mb": 500})
        out = subprocess.run(AGENTCAKE + ["config", "set", "mask_inputs", "false"], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (2, wording.raw("invalid_setting")["mask_inputs"]))
        self.assertNotIn("mask_inputs", self.read_user())
        self.assertEqual(self.read_user()["budget_mb"], 500)


class DefaultsDriveBehaviour(Home):
    """Change a default here, and the code that uses it changes with it."""

    def test_port(self):
        port = free_port()
        with mock.patch.dict(config.DEFAULTS, {"port": port}):
            self.assertEqual(config.base_url(), f"http://127.0.0.1:{port}")
            local, public = server.make_listeners(config.load_cfg())
            self.addCleanup(local.server_close)
            self.assertEqual(local.server_address, ("127.0.0.1", port))
            self.assertIsNone(public)

    def test_budget(self):
        with mock.patch.dict(config.DEFAULTS, {"budget_mb": 123}):
            self.assertEqual(space.budget_bytes(config.load_cfg()), 123 * MIB)

    def test_budget_warning_share(self):
        con = store.db()
        self.addCleanup(con.close)
        self.assertFalse(space.space_status(con, config.load_cfg())["warn"])
        with mock.patch.dict(config.DEFAULTS, {"budget_warn_ratio": 0}):
            self.assertTrue(space.space_status(con, config.load_cfg())["warn"])

    def test_token_max_age(self):
        edge_secret.create_secret()
        secret, now_ms, con = edge_secret.srv_secret(), NOW_S * 1000, store.db()
        self.addCleanup(con.close)
        version = edge_token.EDGE["payload_version"]
        two_minutes_old = lambda token_id: edge_token.sign_payload(secret, {"v": version, "id": token_id, "t": now_ms - 2 * 60_000})
        self.assertEqual(edge_token.take_token(con, two_minutes_old("t1"), edge_token.Delivery("s1"), now_ms), "ok")
        with mock.patch.dict(config.DEFAULTS, {"token_max_age_ms": 60_000}):
            self.assertEqual(edge_token.take_token(con, two_minutes_old("t2"), edge_token.Delivery("s2"), now_ms), "stale")

    def test_public_judge_interval(self):
        key = config.ensure_cfg()["site_key"]
        body = lambda at_s: {"k": key, "s": "sessJ", "u": "https://example.com/", "ua": "x", "e": [click(at_s * 1000)]}
        for at_s in (NOW_S, NOW_S + 10):  # the second 10 s later: inside the default 15 s, so not judged again
            self.post(body(at_s), public=True, at_s=at_s)
        self.assertEqual(self.session_row("sessJ", "judged_ms"), (NOW_S * 1000,))
        with mock.patch.dict(config.DEFAULTS, {"public_judge_interval_ms": 5000}):
            self.post(body(NOW_S + 20), public=True, at_s=NOW_S + 20)
        self.assertEqual(self.session_row("sessJ", "judged_ms"), ((NOW_S + 20) * 1000,))

    def test_events_kept_per_post(self):
        """An upload with more records than max_events_per_post is refused and counted (0.3.4 kept its first
        ones); one within the limit is kept whole."""
        key = config.ensure_cfg()["site_key"]
        body = lambda sid, n: {"k": key, "s": sid, "u": "https://example.com/", "e": [click(NOW_S * 1000 + i) for i in range(n)]}
        with mock.patch.dict(config.DEFAULTS, {"max_events_per_post": 2, "disk_min_free_mb": 0}):  # whatever the disk
            self.assertEqual(self.post(body("sessE", 5)).status, 413)
            self.assertEqual(self.post(body("sessF", 2)).status, 204)
        con = store.db()
        self.addCleanup(con.close)
        self.assertIsNone(self.session_row("sessE", "id"))
        self.assertEqual(con.execute("SELECT posts, records FROM refusals WHERE reason='post_limit'").fetchone(), (1, 5))
        self.assertEqual(streams.event_count(con, "sessF", "rrweb"), 2)

    def test_public_body_cap(self):
        port, public_port = free_port(), free_port()
        with mock.patch.dict(config.DEFAULTS, {"port": port, "public_listen": f"127.0.0.1:{public_port}",
                                               "public_max_body_bytes": 10}):
            local, public = server.make_listeners(config.ensure_cfg())
            self.addCleanup(local.server_close)
            threading.Thread(target=public.serve_forever, kwargs={"poll_interval": POLL_S}, daemon=True).start()
            self.addCleanup(public.server_close)
            self.addCleanup(public.shutdown)
            request = urllib.request.Request(f"http://127.0.0.1:{public_port}/collect", data=b"x" * 11, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(request, timeout=5)
            refused.exception.close()
            self.assertEqual(refused.exception.code, 413)


class DataFilesDriveBehaviour(unittest.TestCase):
    """The name lists, the header names and the product name are read from data/*.json."""

    def test_user_agent_names_come_from_the_lists(self):
        # the bundled lists (data/lists/names.json) replaced 0.3.4's patterns, whose "Comet|Perplexity" called
        # PerplexityBot Comet; the kind is the list's.
        perplexitybot = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; "
                         "+https://perplexity.ai/perplexitybot)")
        found = lists.current().match_ua(perplexitybot)
        self.assertEqual((found["name"], found["kind"]), ("PerplexityBot", "search-crawler"))
        self.assertIsNone(lists.current().match_ua("Mozilla/5.0"))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "agentcake", "data", "ua_agents.json")))

    def test_lb_headers_json(self):
        headers = http.client.HTTPMessage()
        headers["X-Example-Region"] = "DE"
        with mock.patch.dict(datafiles.load("data/lb_headers.json")["headers"], {"region": "X-Example-Region"}):
            facts, _ = netfacts.net_facts(headers, {"trust_lb": True})
        self.assertEqual(facts["country"], "DE")

    def test_product_json(self):
        with mock.patch.dict(datafiles.load("data/product.json"), {"name": "Example Cake", "command": "examplecake"}):
            self.assertEqual(wording.text("not_running"), "Example Cake is not running")
            self.assertEqual(wording.text("unknown_command"), "unknown command; try: examplecake help")


if __name__ == "__main__":
    unittest.main()
