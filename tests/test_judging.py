"""Judging wired to collect, the maintenance round and the pages (agentcake.judging).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

On injected clocks: the first batch is judged, a batch
inside judge_interval_ms waits, opening the session judges it at once, a quiet session gets its final verdict from the
maintenance round, new data after that opens it again; the dashboard catches up on stale sessions. A Bot known by name
and a session with too few actions never reach the behaviour model; a verdict keeps the version of the judge that made
it, and a session an older judge judged (cake 0.3.4's among them) is judged anew when it is opened and by the round,
latest first, after the quiet ones and within its limit, unless its replay was freed (a phone an older judge left on
limited evidence becomes a Human that way, or says which check its records failed); a judgement that fails is rolled
back and collect still answers 204; and
none of it opens a socket.
"""
import ast, gzip, http.client, json, os, shutil, socket, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import synthetic_sessions  # noqa: E402  (made up by rule: no recording)
from verdict_cases import CHROME_LINUX, IPHONE  # noqa: E402
from test_collect_replay import GZIP_FROM  # noqa: E402
from agentcake import collect, config, judging, store  # noqa: E402
from agentcake.detect import model, verdict  # noqa: E402
from agentcake.responses import Request  # noqa: E402

KEY = "ck_judging_test"
SID = "6c1f7d3e1e9b5b72c8e5d1c2f3e4b5a6"
PV = "d3b9e1f2a3b4c5d6e7f8091a2b3c4d5e"
T0 = 1_794_500_000_000
S = 1000
CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
UPTIMEROBOT = "Mozilla/5.0+(compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)"


def refuse(*args, **kwargs):
    raise AssertionError("judging tried to use the network")


def visit_batch(seq, at_ms, raw, ua=CHROME, sid=SID):
    """A version 1 batch of one page view: the page record, then the raw input records given."""
    page = [{"t": at_ms, "ty": "page", "n": 1, "nav": "navigate", "prerendering": False, "vis": "visible"}] if seq == 0 else []
    return {"v": 1, "k": KEY, "s": sid, "pv": PV, "seq": seq, "t": at_ms, "u": "https://shop.example/demo",
            "why": "timer", "ua": ua, "wd": False, "e": [], "r": raw, "x": page}


def clicks(n, start_ms):
    """n clicks a second apart, each after a short pointer path, as raw records."""
    out = []
    for i in range(n):
        t = start_ms + i * S
        out += [{"t": t - 300 + k * 50, "ty": "mousemove", "cx": 100 + 7 * k, "cy": 200 + 3 * k, "tr": 1}
                for k in range(5)]
        out.append({"t": t, "ty": "click", "cx": 135, "cy": 215, "tr": 1})
    return out


class JudgingCase(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, body, at_ms, header_pairs=None):
        """Upload a batch at at_ms; without header_pairs, with the headers a browser sends (its User-Agent and
        Accept-Language: none at all is chrome-headless-shell's mark, env.auto.collect-no-accept-language)."""
        if header_pairs is None:
            header_pairs = [("User-Agent", body.get("ua") or CHROME), ("Accept-Language", "en-US,en")]
        headers = http.client.HTTPMessage()
        for name, value in header_pairs:
            if name.lower() != "content-length":
                headers[name] = value
        raw = json.dumps(body, separators=(",", ":")).encode()
        raw = gzip.compress(raw) if len(raw) >= GZIP_FROM else raw
        with mock.patch.object(collect, "clock_ms", return_value=at_ms):
            answer = collect.from_local(Request("/collect", {}, headers, raw))
        self.assertEqual(answer.status, 204, answer.body)

    def row(self, *columns, sid=SID):
        return self.con.execute(f"SELECT {', '.join(columns)} FROM sessions WHERE id=?", (sid,)).fetchone()


class WhenItIsJudged(JudgingCase):
    def test_new_data_waits_for_the_interval_opening_catches_up_quiet_finalises_new_data_reopens(self):
        quiet_ms = config.load_cfg()["judge_quiet_s"] * S
        self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        self.assertEqual(self.row("judged_ms"), (T0,))
        self.post(visit_batch(1, T0 + 5 * S, clicks(4, T0 + 5 * S)), T0 + 5 * S)  # inside judge_interval_ms
        self.assertEqual(self.row("judged_ms", "end_ms"), (T0, T0 + 5 * S))
        self.assertTrue(judging.on_open(SID, T0 + 6 * S))
        self.assertEqual(self.row("judged_ms"), (T0 + 6 * S,))
        self.assertFalse(judging.on_open(SID, T0 + 7 * S), "nothing new: not judged again")
        self.assertEqual(judging.tick(T0 + 5 * S + quiet_ms - 1), 0)
        self.assertEqual(judging.tick(T0 + 5 * S + quiet_ms), 1)
        judged, end = self.row("judged_ms", "end_ms")
        self.assertGreaterEqual(judged - end, quiet_ms, "final: judged a quiet period after the newest data")
        self.assertEqual(judging.tick(T0 + 5 * S + 2 * quiet_ms), 0, "a final verdict is not judged again")
        later = T0 + 300 * S
        self.post(visit_batch(2, later, clicks(3, later)), later)
        judged, end = self.row("judged_ms", "end_ms")
        self.assertEqual((judged, end), (later, later), "new data opened it again and it was judged")

    def test_log_lines_judge_their_sessions_at_once_also_a_final_verdict_and_inside_the_interval(self):
        quiet_ms = config.load_cfg()["judge_quiet_s"] * S
        self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        final = T0 + quiet_ms
        self.assertEqual(judging.tick(final), 1)
        self.assertEqual(judging.on_log_lines([SID, "f" * 32], final + S), 1, "an unknown session is skipped")
        self.assertEqual(judging.on_log_lines([SID], final + 2 * S), 1, "inside judge_interval_ms all the same")
        self.assertEqual(self.row("judged_ms", "end_ms"), (final + 2 * S, T0), "a log line moves no end_ms")

    def test_the_dashboard_judges_the_stale_sessions_first(self):
        for n, sid in enumerate(("a" * 32, "b" * 32)):
            self.post(visit_batch(0, T0 + n, clicks(3, T0), sid=sid), T0 + n)
            self.post(visit_batch(1, T0 + n + 2 * S, clicks(3, T0 + 2 * S), sid=sid), T0 + n + 2 * S)
        stale = self.con.execute("SELECT COUNT(*) FROM sessions WHERE judged_ms < end_ms").fetchone()[0]
        self.assertEqual((stale, judging.catch_up(now_ms=T0 + 9 * S)), (2, 2))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessions WHERE judged_ms < end_ms").fetchone()[0], 0)

    def test_nothing_opens_a_socket(self):
        with mock.patch.object(socket, "socket", refuse), mock.patch.object(socket, "create_connection", refuse), \
                mock.patch.object(socket, "getaddrinfo", refuse):
            self.post(visit_batch(0, T0, clicks(5, T0)), T0)
            self.post(visit_batch(1, T0 + 2 * S, clicks(5, T0 + 2 * S)), T0 + 2 * S)
            judging.on_open(SID, T0 + 3 * S)
            judging.tick(T0 + 3 * S + config.load_cfg()["judge_quiet_s"] * S)
        self.assertIsNotNone(self.row("verdict_class")[0])


class Counting:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.judge(*args, **kwargs)

    judge = staticmethod(model.judge_session)


class TheModelIsSpared(JudgingCase):
    def judged_calls(self, body):
        counting = Counting()
        with mock.patch.object(model, "judge_session", counting):
            self.post(body, T0)
        return counting.calls, self.row("verdict_class", sid=body["s"])[0]

    def test_a_listed_bot_and_too_few_actions_never_reach_the_model(self):
        self.assertEqual(self.judged_calls(visit_batch(0, T0, clicks(6, T0), ua=UPTIMEROBOT, sid="c" * 32)),
                         (0, "bot"))
        self.assertEqual(self.judged_calls(visit_batch(0, T0, clicks(1, T0), sid="d" * 32)), (0, "too_little_data"))
        enough = visit_batch(0, T0, synthetic_sessions.agent_raw(T0), sid="e" * 32)
        self.assertEqual(self.judged_calls(enough)[0], 1)


class ProductAttribution(JudgingCase):
    def test_one_action_grok_bot_upload_agrees_across_the_name_and_environment_layers(self):
        ua = CHROME_LINUX + " GrokAgent/1.0"
        body = visit_batch(0, T0, clicks(1, T0), ua=ua)
        body["x"].append({"t": T0 + 5, "ty": "botscent", "why": "start", "type": "agent", "agent": "grok-bot",
                          "reasons": ["grok.cloud-computer.environment"], "ver": "1.2.0"})
        self.post(body, T0)

        verdict_class, name, detail, reasons = self.row("verdict_class", "agent_name", "verdict_detail", "reasons")
        self.assertEqual((verdict_class, name), ("agent", "grok-bot"))
        detail = json.loads(detail)
        self.assertEqual((detail["display_name"], detail["operator"], detail["name_method"], detail["name_certainty"]),
                         ("Grok Bot", "Anysphere", "product-rule", "likely"))
        candidates = set(self.con.execute("SELECT name, method FROM labels WHERE session_id=?", (SID,)))
        self.assertEqual(candidates, {("grok-bot", "ua"), ("grok-bot", "product-rule")})
        ids = {reason["id"] for reason in json.loads(reasons)}
        self.assertTrue({"behavior.too-little-data", "env.product.grok-bot"}.issubset(ids))
        self.assertFalse({"name.disagree", "name.outranked"} & ids)


class OldSessions(JudgingCase):
    def add_old(self, sid, end_ms):
        """A session cake 0.3.4's judge decided: its columns, no verdict_class."""
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms, ua, verdict, human_pct, agent_pct, unsure_pct, "
                         "group_id, source, judged_ms) VALUES(?,?,?,?, 'human', 100, 0, 0, 'H1/L?', 'x', ?)",
                         (sid, end_ms - 60 * S, end_ms, CHROME, end_ms))
        self.con.commit()

    def test_judged_anew_when_opened_and_by_the_round(self):
        self.add_old("f" * 32, T0)
        self.add_old("e" * 32, T0 + S)
        later = T0 + 10 * config.load_cfg()["judge_quiet_s"] * S
        self.assertTrue(judging.on_open("e" * 32, later))
        self.assertEqual(judging.tick(later), 1, "the round: the other one")
        for sid in ("e" * 32, "f" * 32):
            self.assertEqual(self.row("verdict_class", "model_version", sid=sid),
                             ("too_little_data", judging.model_version()))


class ModelVersion(JudgingCase):
    """A verdict keeps the version of the judge that made it; after an upgrade an older judge's verdicts are made
    anew (so that the sessions already kept get the new rules and percents too)."""

    def setUp(self):
        super().setUp()
        self.quiet_ms = config.load_cfg()["judge_quiet_s"] * S

    def judged_by_an_older_judge(self, *sids):
        self.con.execute(f"UPDATE sessions SET model_version='older' WHERE id IN ({', '.join('?' * len(sids))})", sids)
        self.con.commit()

    def this_judges(self):
        return {sid: version == judging.model_version()
                for sid, version in self.con.execute("SELECT id, model_version FROM sessions")}

    def test_the_version_is_a_fingerprint_of_the_judges_code_and_data_files(self):
        files = judging.model_files(os.path.dirname(judging.__file__))
        for name in ("judging.py", "evidence.py", "detect/model.py", "detect/verdict.py", "detect/confidence.py",
                     "data/behavior_model.json", "data/calibration.json", "data/verdict.json", "data/lists/names.json"):
            self.assertIn(name, files)
        self.assertEqual([name for name in files if "__pycache__" in name or name.endswith(".pyc")], [])
        root = tempfile.mkdtemp(prefix="cake-judge-")
        self.addCleanup(shutil.rmtree, root)

        def write(name, text):
            os.makedirs(os.path.dirname(os.path.join(root, name)), exist_ok=True)
            with open(os.path.join(root, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        write("judging.py", "judge"), write("detect/model.py", "rules"), write("data/behavior_model.json", "{}")
        first = judging.fingerprint(root)
        write("detect/__pycache__/model.cpython-314.pyc", "cache"), write("data/.DS_Store", "finder")
        self.assertEqual(judging.fingerprint(root), first, "a cache and a hidden file are not the judge")
        write("data/behavior_model.json", '{"min_agent_actions": 3}')
        self.assertNotEqual(judging.fingerprint(root), first, "a data file changed")

    def test_a_verdict_keeps_the_version_of_the_judge_that_made_it(self):
        self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        self.assertEqual(self.row("model_version"), (judging.model_version(),))

    def test_the_round_judges_an_older_judges_sessions_anew_latest_first_after_the_quiet_ones_within_its_limit(self):
        a, b, c, d = "a" * 32, "b" * 32, "c" * 32, "d" * 32
        for n, sid in enumerate((a, b, c)):
            self.post(visit_batch(0, T0 + n * S, clicks(4, T0 + n * S), sid=sid), T0 + n * S)
        final = T0 + 2 * S + self.quiet_ms
        self.assertEqual(judging.tick(final), 3)
        self.judged_by_an_older_judge(a, b, c)
        self.post(visit_batch(0, final + S, clicks(4, final + S), sid=d), final + S)
        self.assertEqual(judging.tick(final + S + self.quiet_ms, limit=2), 2, "d's final verdict, then c")
        self.assertEqual(self.this_judges(), {a: False, b: False, c: True, d: True})
        self.assertEqual(judging.tick(final + 2 * S + self.quiet_ms, limit=2), 2)
        self.assertEqual(judging.tick(final + 3 * S + self.quiet_ms, limit=2), 0, "every verdict is this judge's")
        self.assertEqual(set(self.this_judges().values()), {True})

    def test_opening_judges_anew_a_session_an_older_judge_judged(self):
        self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        self.assertEqual(judging.tick(T0 + self.quiet_ms), 1)
        self.judged_by_an_older_judge(SID)
        self.assertTrue(judging.on_open(SID, T0 + self.quiet_ms + S))
        self.assertEqual(self.row("model_version"), (judging.model_version(),))
        self.assertFalse(judging.on_open(SID, T0 + self.quiet_ms + 2 * S), "this judge's, nothing new: not again")

    def test_a_real_phone_an_older_judge_left_on_limited_evidence_is_made_a_human_when_opened_and_by_the_round(self):
        """After an upgrade: the verdicts already kept get the rule for a real phone or tablet too."""
        iphone = {"userAgent": IPHONE, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5,
                  "uaData": None, "screen": {"w": 390, "h": 844}, "dpr": 3}
        opened, by_the_round = "a" * 32, "b" * 32
        for n, sid in enumerate((opened, by_the_round)):
            body = visit_batch(0, T0 + n * S, clicks(4, T0 + n * S), ua=IPHONE, sid=sid)
            body["x"].append({"t": T0 + n * S + 5, "ty": "env", "env": iphone})
            self.post(body, T0 + n * S)
        final = T0 + S + self.quiet_ms
        self.assertEqual(judging.tick(final), 2)
        self.con.execute("UPDATE sessions SET model_version='older', verdict_class='too_little_data', verdict='unsure'")
        self.con.commit()
        self.assertTrue(judging.on_open(opened, final + S))
        self.assertEqual(judging.tick(final + 2 * S), 1)
        for sid in (opened, by_the_round):
            self.assertEqual(self.row("verdict_class", "verdict", "model_version", sid=sid),
                             ("human", "human", judging.model_version()))

    def test_a_phone_an_older_judge_kept_on_limited_evidence_gets_the_checks_it_failed_when_judged_anew(self):
        """After an upgrade: a phone whose record has no screen says so, when opened and by the round alike."""
        phone = {"userAgent": IPHONE, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5, "uaData": None}
        opened, by_the_round = "a" * 32, "b" * 32
        for n, sid in enumerate((opened, by_the_round)):
            body = visit_batch(0, T0 + n * S, clicks(4, T0 + n * S), ua=IPHONE, sid=sid)
            body["x"].append({"t": T0 + n * S + 5, "ty": "env", "env": phone})
            self.post(body, T0 + n * S)
        final = T0 + S + self.quiet_ms
        self.assertEqual(judging.tick(final), 2)
        for sid in (opened, by_the_round):
            kept = [r for r in json.loads(self.row("reasons", sid=sid)[0]) if not r["id"].startswith("behavior.touch-")]
            self.con.execute("UPDATE sessions SET model_version='older', reasons=? WHERE id=?", (json.dumps(kept), sid))
        self.con.commit()
        self.assertTrue(judging.on_open(opened, final + S))
        self.assertEqual(judging.tick(final + 2 * S), 1)
        for sid in (opened, by_the_round):
            self.assertIn("behavior.touch-no-screen", [r["id"] for r in json.loads(self.row("reasons", sid=sid)[0])])
            self.assertEqual(self.row("verdict_class", "model_version", sid=sid),
                             ("too_little_data", judging.model_version()))

    def test_a_freed_replays_verdict_stands_neither_the_round_nor_opening_judges_it(self):
        self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        self.assertEqual(judging.tick(T0 + self.quiet_ms), 1)
        kept = self.row("verdict_class", "reasons", "segs")
        self.judged_by_an_older_judge(SID)
        self.con.execute("UPDATE sessions SET replay_freed_ms=?", (T0 + self.quiet_ms,))
        self.con.commit()
        self.assertEqual(judging.tick(T0 + self.quiet_ms + S), 0)
        self.assertFalse(judging.on_open(SID, T0 + self.quiet_ms + 2 * S))
        self.assertEqual(self.row("verdict_class", "reasons", "segs", "model_version"), (*kept, "older"))


# The modules the judge's code imports that read what it judges, keep what it decided or word it, and decide no
# verdict: a change to one is no new judge. Every other module it imports is part of the fingerprint.
JUDGE_SUPPORT = {
    "activity": "the first and last recorded action a session's length is made of, written beside the verdict",
    "addresses": "an address read without failing; the path it gives goes into the signals unchanged",
    "config": "the owner's settings: changing one makes no new judge",
    "datafiles": "the loader of the data files, which the fingerprint holds themselves (data/)",
    "downloads": "the lists' downloads for `agentcake lists update` (detect/lists_build.py); judging downloads nothing",
    "geoip": "address_check.current() only, the dashboard's and doctor's warning; judging calls check()",
    "paths": "where the package and its data folder are",
    "session_replay": "the session's stored rrweb events, read",
    "store": "the database's tables, which the verdict is written into",
    "storage_config": "the clock",
    "streams": "the session's stored raw events, read",
    "units": "units of time and of percent",
    "visit_batches": "the session's stored uploads and collect requests, read",
    "visit_verdict": "the verdict of the visit the session is a tab of, merged after the session's own is written",
    "wording": "the product's name in the reasons' words",
}


def imported_modules(root, names):
    """The agentcake modules the given files of the package import, as dotted names under agentcake."""
    found = set()
    for name in names:
        with open(os.path.join(root, name), encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "agentcake":
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("agentcake."):
                found.add(node.module.removeprefix("agentcake."))
            elif isinstance(node, ast.Import):
                found.update(alias.name.removeprefix("agentcake.") for alias in node.names
                             if alias.name.startswith("agentcake."))
    return found


class TheJudgesCode(unittest.TestCase):
    """What the judge's code imports from the package is part of its fingerprint, or only supports it (JUDGE_SUPPORT):
    a module that comes to decide verdicts, as web_device.py did through detect/touch_device.py, is not left out."""

    def test_every_module_the_judges_code_imports_is_fingerprinted_or_only_supports_it(self):
        root = os.path.dirname(judging.__file__)
        files = judging.model_files(root)
        imported = imported_modules(root, [name for name in files if name.endswith(".py")])

        def file_of(module):
            path = module.replace(".", "/")
            return f"{path}/__init__.py" if os.path.isdir(os.path.join(root, path)) else f"{path}.py"
        left_out = sorted(module for module in imported if file_of(module) not in files and module not in JUDGE_SUPPORT)
        self.assertEqual(left_out, [], "a module the judge imports is neither fingerprinted nor only a support")
        self.assertEqual(sorted(set(JUDGE_SUPPORT) - imported), [], "JUDGE_SUPPORT names a module the judge no longer "
                         "imports")
        self.assertEqual(sorted(module for module in JUDGE_SUPPORT if file_of(module) in files), [],
                         "a fingerprinted module is no support")


class Failures(JudgingCase):
    def test_a_judgement_that_fails_is_rolled_back_and_collect_still_answers(self):
        def broken(*args, **kwargs):
            raise RuntimeError("a bug in a layer")
        with mock.patch.object(verdict, "judge", broken), mock.patch("traceback.print_exc") as logged:
            self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        self.assertTrue(logged.called)
        self.assertEqual(self.row("verdict_class", "judged_ms"), (None, 0))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM segments").fetchone()[0], 0)
        self.post(visit_batch(1, T0 + 20 * S, clicks(4, T0 + 20 * S)), T0 + 20 * S)
        self.assertIsNotNone(self.row("verdict_class")[0], "tried again with the next data")


if __name__ == "__main__":
    unittest.main()
