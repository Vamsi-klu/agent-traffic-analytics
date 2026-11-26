"""Weak signals (agentcake.detect.weak): each only adds a reason and never changes a verdict.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Each signal holds on its pattern and stays quiet on an ordinary session: time zone or languages against the
address's country, many sessions from one address, a header order the claimed browser does not use (cake.js's real
uploads from Chrome pass, curl's order does not), a screen that changes, a window that jumps, a script's or an
AI's rhythm. On the verdict's 16 control sessions (and the lab's 26), the verdict is the same with
and without every weak signal; only reasons are added. tools/build_timezones.py reads the tz database's zone.tab.
"""
import copy, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_timezones  # noqa: E402
import verdict_cases as cases  # noqa: E402
from agentcake.detect import verdict, weak  # noqa: E402

CHROME = cases.CHROME_MAC
QUIET = {"country": "US", "timezones": ["America/New_York"], "languages": ["en-US", "en"], "user_agents": [CHROME],
         "header_orders": [["host", "connection", "content-length", "sec-ch-ua-platform", "user-agent"]],
         "color_depths": [24], "screens": ["1512x982"], "window_jump": 3, "address_sessions": 2,
         "steps": {"n": 12, "still": 0.2}}
LOUD = {"country": "DE", "timezones": ["America/New_York"], "languages": ["en-US", "fr-FR"], "user_agents": [CHROME],
        "header_orders": [["host", "user-agent", "accept", "connection"]], "color_depths": [24, 30],
        "screens": ["1512x982", "1280x720"], "window_jump": 1100, "address_sessions": 50,
        "steps": {"n": 12, "still": 0.65}}
WEAK_IDS = {"weak.timezone-country", "weak.language-country", "weak.same-address", "weak.header-order",
            "weak.display-change", "weak.window-jump", "weak.rhythm-pauses"}
SAME = ("class", "row", "name", "verification", "confidence", "category", "segments", "shares", "handoffs", "layers")


def ids(found):
    return {r["id"] for r in weak.reasons(found)}


class EachSignal(unittest.TestCase):
    def test_an_ordinary_session_has_no_weak_signal(self):
        self.assertEqual(ids(QUIET), set())

    def test_every_pattern_gives_its_reason(self):
        self.assertEqual(ids(LOUD), WEAK_IDS)

    def test_one_at_a_time(self):
        alone = {"timezones": ["Asia/Tokyo"], "languages": ["fr-FR", "de-DE"], "header_orders": LOUD["header_orders"],
                 "color_depths": [24, 30], "screens": ["1512x982", "1280x720"], "window_jump": 1100,
                 "address_sessions": 50, "steps": LOUD["steps"]}
        for key, value in alone.items():
            with self.subTest(key):
                self.assertEqual(len(ids(dict(QUIET, **{key: value}))), 1, key)

    def test_an_ai_that_looks_before_it_acts(self):
        found = dict(QUIET, steps={"n": 20, "still": 0.65})
        self.assertEqual(ids(found), {"weak.rhythm-pauses"})

    def test_steps_right_after_each_other_are_no_reason(self):
        """Humans step without a pause as often as agents do: no "like a script" reason."""
        step_ms = 100  # every click a tenth of a second after the previous one
        clicks = [{"t": step_ms * (i + 1), "ty": "click", "tr": 1, "cx": 10, "cy": 10} for i in range(12)]
        found = weak.facts({"pages": []}, [], clicks)
        self.assertEqual(ids(dict(QUIET, steps=found["steps"])), set())

    def test_a_geometry_record_whose_size_or_place_is_not_numbers_is_left_out(self):
        """The server keeps what a browser uploaded: only cake.js's records, with numbers, measure the window."""
        def geo(t, *g):
            return {"t": t, "ty": "geo", "g": list(g)}
        good = [geo(0, 1200, 700, 1200, 787, 40, 60), geo(500, 1200, 700, 1200, 787, 540, 60)]
        broken = [geo(250, 1200, 700, 1200, 787, None, "60"), geo(300, 1200, 700, 1200, 787, True, 60)]
        self.assertEqual(weak.facts({"pages": []}, [], good)["window_jump"], 500)
        self.assertEqual(weak.facts({"pages": []}, [], good[:1] + broken + good[1:])["window_jump"], 500)

    def test_nothing_recorded_or_too_few_steps_says_nothing(self):
        self.assertEqual(weak.reasons(None), [])
        self.assertEqual(ids(dict(QUIET, steps={"n": 2, "still": 1.0})), set())
        self.assertEqual(ids(dict(QUIET, country=None, timezones=["Asia/Tokyo"], languages=["ja-JP"])), set())

    def test_header_order_is_read_only_in_local_mode(self):
        """On a server every upload passes a front door (a CDN, a load balancer, a reverse proxy) that sends the
        header names in its own order, with or without trust_lb: the order says nothing about the browser there."""
        curl_order = [["Host", "shop.example"], ["User-Agent", CHROME], ["Accept", "*/*"]]
        requests = [{"headers": curl_order, "names": [name.lower() for name, _ in curl_order]}]
        local = weak.facts({"pages": []}, requests, [])
        self.assertIn("weak.header-order", ids(dict(QUIET, header_orders=local["header_orders"])))
        server = weak.facts({"pages": []}, requests, [], local=False)
        self.assertEqual(server["header_orders"], [])
        self.assertEqual(server["user_agents"], [CHROME])  # the other facts are read as before

    def test_a_browser_that_does_not_claim_chrome_is_not_held_to_its_order(self):
        firefox = "Mozilla/5.0 (Macintosh; Intel Mac OS X 15.5; rv:146.0) Gecko/20100101 Firefox/146.0"
        self.assertEqual(ids(dict(QUIET, user_agents=[firefox], header_orders=LOUD["header_orders"])), set())


class VerdictsUnchanged(unittest.TestCase):
    """The same verdict with and without every weak signal, only more reasons."""

    def assert_only_reasons_added(self, case, label):
        plain = verdict.decide(dict(case, weak=None))
        loud = verdict.decide(dict(case, weak=copy.deepcopy(LOUD)))
        self.assertEqual({k: loud[k] for k in SAME}, {k: plain[k] for k in SAME}, label)
        added = [r["id"] for r in loud["reasons"] if r not in plain["reasons"]]
        self.assertEqual(set(added), WEAK_IDS, label)
        self.assertTrue(all(r["layer"] == "weak" for r in loud["reasons"] if r["id"] in WEAK_IDS))

    def test_the_sixteen_controls(self):
        for name, _, make, _ in cases.CONTROLS:
            with self.subTest(name):
                self.assert_only_reasons_added(make(), name)


class TimeZones(unittest.TestCase):
    def test_the_builder_reads_zone_tab(self):
        with tempfile.NamedTemporaryFile("w", suffix=".tab", delete=False) as f:
            f.write("# comment\nDE\t+5230+01322\tEurope/Berlin\nCH\t+4723+00832\tEurope/Zurich\n"
                    "LI\t+4709+00931\tEurope/Zurich\tLiechtenstein, here as a shared zone\n")
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(build_timezones.read_zone_tab(f.name),
                         {"Europe/Berlin": ["DE"], "Europe/Zurich": ["CH", "LI"]})

    def test_the_bundled_table_knows_common_zones(self):
        from agentcake.datafiles import load
        zones = load("data/timezones.json")["zones"]
        self.assertEqual((zones["Europe/Berlin"], zones["America/New_York"]), (["DE"], ["US"]))


if __name__ == "__main__":
    unittest.main()
