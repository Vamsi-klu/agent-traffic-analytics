"""One session's evidence read from the database (agentcake.evidence).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Uploads go through collect, then evidence.session_evidence() reads them back: pages in the signals' order with the
Sec-Purpose of their server half and whether they were prerendered and shown; the server half read as the page
request for the environment rules; on server mode's public listener the network facts of the address, the earlier
visits from the same network and mode "server"; the Web Bot Auth result collect kept with a request and the page
request's Signature-Agent; a phone or tablet, and whether its records fit a real one; records without a time left
out; a cake 0.3.4 visit's User-Agent and
server half. The addresses are the first of a published range (as a load balancer would give them).
"""
import http.client, json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import geo_fixtures  # noqa: E402
from verdict_cases import IPHONE, first_address  # noqa: E402
from agentcake import collect, config, edge_secret, edge_token, evidence, geoip, store, streams  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.responses import Request  # noqa: E402

KEY = "ck_evidence_test"
SID, OTHER = "7d2e8f4a2fac6c83d9f6e2d3a4b5c6d7", "8e3f9a5b3abd7d94eaa7f3e4b5c6d7e8"
PV1, PV2 = "a1" * 16, "b2" * 16
T0 = 1_794_500_000_000
S = 1000
CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
LB = load("data/lb_headers.json")["headers"]


def page_batch(pv, n, at_ms, sid=SID, prerendering=False, shown=True, env=None, token=None, **fields):
    """A page view's first batch: its page record, an environment record, raw input visible or not."""
    signals = [{"t": at_ms, "ty": "page", "n": n, "nav": "navigate", "prerendering": prerendering,
                "vis": "visible" if shown else "hidden"},
               {"t": at_ms + 5, "ty": "env", "env": env or {"userAgent": CHROME, "platform": "MacIntel",
                                                              "anyPointer": ["fine"], "maxTouchPoints": 0}}]
    raw = [{"t": at_ms + 10 * k, "ty": "mousemove", "cx": k, "cy": k, "tr": 1, "vs": 1 if shown else 0}
           for k in range(3)]
    body = {"v": 1, "k": KEY, "s": sid, "pv": pv, "seq": 0, "t": at_ms, "u": "https://shop.example/demo",
            "why": "start", "ua": CHROME, "wd": False, "e": [], "r": raw, "x": signals, **fields}
    if token:
        body["st"] = token
    return body


class EvidenceCase(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, body, at_ms, public=False, **headers):
        message = http.client.HTTPMessage()
        for name, value in {"User-Agent": CHROME, "Accept-Language": "en-US", **headers}.items():
            message[name] = value
        with mock.patch.object(collect, "clock_ms", return_value=at_ms):
            answer = (collect.from_public if public else collect.from_local)(
                Request("/collect", {}, message, json.dumps(body).encode()))
        self.assertEqual(answer.status, 204, answer.body)

    def token(self, at_ms, **payload):
        if not edge_secret.srv_secret():
            edge_secret.create_secret()
        return edge_token.sign_payload(edge_secret.srv_secret(), {"v": 1, "id": f"tok-{at_ms}", "t": at_ms,
                                                                  "p": "/demo", **payload})

    def evidence(self, sid=SID):
        return evidence.session_evidence(self.con, sid, now_s=T0 / S)


class Pages(EvidenceCase):
    def test_pages_in_page_order_with_their_server_half_and_prerendering(self):
        self.post(page_batch(PV2, 2, T0 + 9 * S, prerendering=True, shown=False), T0 + 9 * S)
        self.post(page_batch(PV1, 1, T0, token=self.token(T0, sp="prefetch")), T0)
        case, raw, rrweb = self.evidence()
        self.assertEqual(case["pages"], [{"t": T0, "sp": "prefetch", "prerendered": False, "shown": True},
                                         {"t": T0 + 9 * S, "sp": None, "prerendered": True, "shown": False}])
        self.assertEqual((len(raw), rrweb), (6, None))
        self.assertEqual(case["mode"], "local")

    def test_a_page_view_that_reused_a_token_has_no_server_half_of_its_own(self):
        token = self.token(T0, sp="prefetch")
        self.post(page_batch(PV1, 1, T0, token=token), T0)
        self.post(page_batch(PV2, 2, T0 + 9 * S, token=token), T0 + 9 * S)  # a stored copy of the page: same token
        case, _, _ = self.evidence()
        self.assertEqual([page["sp"] for page in case["pages"]], ["prefetch", None])

    def test_the_server_half_is_read_as_the_page_request(self):
        landing = self.token(T0, sf={"s": "cross-site", "m": "navigate", "d": "document", "u": None})
        self.post(page_batch(PV1, 1, T0, token=landing), T0)
        case, _, _ = self.evidence()
        hits = {hit.rule: hit.half for hit in case["env"].hits}
        self.assertEqual(hits.get("env.ext.cross-site-landing"), "server")

    def test_records_without_a_time_are_left_out(self):
        self.post(page_batch(PV1, 1, T0), T0)
        streams.append(self.con, SID, "raw", [(T0 + 50, {"ty": "click", "cx": 1, "cy": 1})], T0 + 50)
        self.con.commit()
        _, raw, _ = self.evidence()
        self.assertEqual(len(raw), 3)

    def test_a_phone_or_tablet(self):
        phone = {"userAgent": CHROME, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5,
                 "uaData": {"mobile": True}}
        self.post(page_batch(PV1, 1, T0, env=phone), T0)
        self.post(page_batch(PV2, 1, T0, sid=OTHER), T0)
        self.assertEqual((self.evidence()[0]["touch"], self.evidence(OTHER)[0]["touch"]), (True, False))

    def test_a_phone_whose_environment_record_fits_a_real_one(self):
        """touch_fits: touch points and a screen of the size its User-Agent's device has (touch_device.fits); a
        record without its screen, and a computer's, do not fit."""
        iphone = {"userAgent": IPHONE, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5,
                  "uaData": None, "screen": {"w": 390, "h": 844}, "dpr": 3}
        no_screen = {key: value for key, value in iphone.items() if key != "screen"}
        third = "9f4a0b6c4bce8ea5fbb8a4f5c6d7e8f9"
        self.post(page_batch(PV1, 1, T0, env=iphone), T0)
        self.post(page_batch(PV2, 1, T0, sid=OTHER, env=no_screen), T0)
        self.post(page_batch("c3" * 16, 1, T0, sid=third), T0)
        found = [self.evidence(sid)[0] for sid in (SID, OTHER, third)]
        self.assertEqual([(case["touch"], case["touch_fits"]) for case in found],
                         [(True, True), (True, False), (False, False)])

    def test_a_phone_whose_environment_record_does_not_fit_names_the_check_it_failed(self):
        """touch_failed: touch_device.failed_checks() of the pages, each check with its facts, none for a record that
        fits. A computer's record fails the first check, that its browser says it is a phone or tablet (the verdict
        reads the checks only where the browser said so)."""
        iphone = {"userAgent": IPHONE, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5,
                  "uaData": None, "screen": {"w": 390, "h": 844}, "dpr": 3}
        bare = {key: value for key, value in iphone.items() if key not in ("screen", "maxTouchPoints")}
        third = "9f4a0b6c4bce8ea5fbb8a4f5c6d7e8f9"
        self.post(page_batch(PV1, 1, T0, env=iphone), T0)
        self.post(page_batch(PV2, 1, T0, sid=OTHER, env=dict(bare, maxTouchPoints=0)), T0)
        self.post(page_batch("c3" * 16, 1, T0, sid=third), T0)
        found = [self.evidence(sid)[0] for sid in (SID, OTHER, third)]
        self.assertEqual([(case["touch"], case["touch_failed"]) for case in found],
                         [(True, []), (True, [{"check": "no-touch-points", "points": 0}, {"check": "no-screen"}]),
                          (False, [{"check": "not-claimed"}])])

    def test_a_viewport_that_got_shorter_is_a_hint_on_a_computer_and_not_on_a_phone(self):
        """A phone browser's address bar hides and shows as the page scrolls: there the change says nothing."""
        def shrinking(width, height, outer):
            return [{"t": T0 + 20 + 30 * k, "ty": "geo", "why": "resize",
                     "g": [width, height - 56 * k, width, outer, 0, 0, 1, width, outer]} for k in range(2)]
        iphone = {"userAgent": IPHONE, "platform": "iPhone", "anyPointer": ["coarse"], "maxTouchPoints": 5,
                  "uaData": None, "screen": {"w": 390, "h": 844}, "dpr": 3}
        self.post(page_batch(PV1, 1, T0, env=iphone, r=shrinking(390, 714, 844)), T0)
        self.post(page_batch(PV2, 1, T0, sid=OTHER, r=shrinking(1512, 862, 949)), T0)
        held = [[hit.rule for hit in self.evidence(sid)[0]["env"].hits if hit.rule == "env.ext.viewport-shrink"]
                for sid in (SID, OTHER)]
        self.assertEqual(held, [[], ["env.ext.viewport-shrink"]])


DOM_WATCH_RULE = "env.auto.main-world-eval-stack"
PPTR_LOOKUP = {"fn": "querySelector", "arg": "#buy", "t": T0 + 40, "pptr": True, "utilityScript": False,
               "puppeteerEval": False, "stack": "at pptr:evaluate;file:///script.js:3:9"}


def watched_page_view(hook_dom, lookups):
    """One page view: its first batch, whose page record says how the site owner had set hook_dom, and its exit
    batch, whose globals record carries what the DOM-lookup watch saw (hookHits: only lookups with an automation
    frame on the call stack, so a human's page sends none)."""
    first = page_batch(PV1, 1, T0)
    first["x"][0]["hook_dom"] = hook_dom
    seen = {"t": T0 + 50, "ty": "globals", "globalsAtEnd": {}, "hookHits": lookups,
            "lookups": {"total": 4, "checked": 4}}
    return first, dict(first, seq=1, t=T0 + 50, why="pagehide", r=[], x=[seen])


class DomWatch(EvidenceCase):
    """The page script's hook_dom setting turns on the environment rule that reads its DOM-lookup watch."""

    def post_page_view(self, hook_dom, lookups):
        for batch in watched_page_view(hook_dom, lookups):
            self.post(batch, batch["t"])

    def test_the_rule_holds_on_a_visit_recorded_with_hook_dom_on(self):
        self.post_page_view(True, [PPTR_LOOKUP])
        hit = next((hit for hit in self.evidence()[0]["env"].hits if hit.rule == DOM_WATCH_RULE), None)
        self.assertIsNotNone(hit)
        self.assertEqual((hit.strength, hit.pages), ("hard", (0,)))

    def test_the_rule_stays_off_on_a_visit_recorded_with_hook_dom_off(self):
        self.post_page_view(False, [PPTR_LOOKUP])
        env = self.evidence()[0]["env"]
        self.assertNotIn(DOM_WATCH_RULE, [hit.rule for hit in env.hits])
        self.assertIn(DOM_WATCH_RULE, env.off)

    def test_the_setting_a_visit_was_recorded_with_counts_not_the_current_one(self):
        self.post_page_view(True, [PPTR_LOOKUP])
        config.save_user(hook_dom=False)  # turned off after the visit: what it recorded still counts
        self.assertIn(DOM_WATCH_RULE, [hit.rule for hit in self.evidence()[0]["env"].hits])
        config.save_user(hook_dom=True)  # turned on after a visit recorded without it
        earlier = page_batch(PV2, 1, T0, sid=OTHER)
        earlier["x"][0]["hook_dom"] = False
        self.post(earlier, T0)
        self.assertIn(DOM_WATCH_RULE, self.evidence(OTHER)[0]["env"].off)

    def test_a_human_page_with_the_watch_on_is_checked_and_does_not_match(self):
        self.post_page_view(True, [])
        env = self.evidence()[0]["env"]
        self.assertNotIn(DOM_WATCH_RULE, [hit.rule for hit in env.hits] + list(env.unknown) + list(env.off))


class ServerMode(EvidenceCase):
    def setUp(self):
        super().setUp()
        config.save_user(site_key=KEY, disk_min_free_mb=0, public_listen="127.0.0.1:9", trust_lb=True)

    def test_network_facts_mode_and_earlier_visits_from_the_same_network(self):
        address = first_address("openai-chatgpt-user")
        self.post(page_batch(PV1, 1, T0, sid=OTHER), T0, public=True, **{LB["ip"]: address})
        self.post(page_batch(PV2, 1, T0 + 600 * S), T0 + 600 * S, public=True, **{LB["ip"]: address})
        case, _, _ = self.evidence()
        self.assertEqual(case["mode"], "server")
        self.assertEqual((case["network"]["range_id"], case["network"]["range_kind"]), ("openai-chatgpt-user", "agent"))
        self.assertEqual(case["visits"], [T0])
        self.assertNotIn(address, repr(case))  # the address itself is never kept, only what it says

    def test_an_address_the_check_finds_to_be_a_cdns_is_not_used(self):
        """The front door gave Cloudflare's address for every visitor (an orange-cloud DNS record). Once enough
        of the latest sessions came from it, a session is judged as if it had no address."""
        cdn, enough = first_address("cloudflare"), load("data/verdict.json")["address_check"]["sessions"]
        geo_fixtures.install(geoip.user_folder(), geo_fixtures.single(cdn, "US"))  # its country comes from the city database
        sessions = [f"{n:032x}" for n in range(enough)]
        for n, sid in enumerate(sessions):
            self.post(page_batch(PV1, 1, T0 + n * S, sid=sid), T0 + n * S, public=True, **{LB["ip"]: cdn})
        last, _, _ = self.evidence(sessions[-1])
        self.assertEqual(last["address_check"], {"sessions": enough, "cdn": enough, "misconfigured": True})
        self.assertEqual((last["network"], last["visits"], last["weak"]["address_sessions"], last["weak"]["country"]),
                         (None, [], None, None))
        self.assertNotIn("env.cloud.datacenter-ip", [hit.rule for hit in last["env"].hits])
        first, _, _ = self.evidence(sessions[0])
        self.assertEqual(first["address_check"], {"sessions": 1, "cdn": 1, "misconfigured": False}, "too few yet")
        self.assertEqual((first["network"]["cdn"], first["weak"]["country"]), ("Cloudflare", "US"))
        self.assertIn("env.cloud.datacenter-ip", [hit.rule for hit in first["env"].hits])

    def test_the_header_order_is_not_read_on_a_server(self):
        """Every upload to a server passed a front door, which sent the headers in its own order, also one
        AgentCake takes no address from (trust_lb off: nginx or CloudFront in front)."""
        config.save_user(trust_lb=False)
        self.post(page_batch(PV1, 1, T0), T0, public=True)
        self.assertEqual(self.evidence()[0]["weak"]["header_orders"], [])
        config.save_user(public_listen="")  # local mode: the uploads reached this computer straight from the browser
        self.post(page_batch(PV2, 1, T0 + S, sid=OTHER), T0 + S)
        self.assertEqual(self.evidence(OTHER)[0]["weak"]["header_orders"], [["user-agent", "accept-language"]])

    def test_both_halves_of_web_bot_auth(self):
        claim = '"https://chatgpt.com"'
        token = self.token(T0, sg={"a": claim, "s": False, "i": False})
        self.post(page_batch(PV1, 1, T0, token=token), T0, public=True, **{"Signature-Agent": claim})
        signatures = self.evidence()[0]["signatures"]
        self.assertEqual((signatures["collector"].outcome, signatures["collector"].code,
                          signatures["collector"].claimed), ("declared", "claim-only", "chatgpt.com"))
        self.assertEqual((signatures["server"].outcome, signatures["server"].claimed), ("declared", "chatgpt.com"))


class OldVisits(EvidenceCase):
    def test_a_cake_034_visit_brings_its_user_agent_and_its_server_half(self):
        token = self.token(T0, sg={"a": '"https://chatgpt.com"', "s": False, "i": False})
        old = {"k": KEY, "s": SID, "u": "https://shop.example/", "ua": "Mozilla/5.0 Manus-User/1.0", "wd": False,
               "e": [{"type": 3, "timestamp": T0 + 5, "data": {"source": 2, "type": 2, "x": 1, "y": 1}}], "st": token}
        self.post(old, T0)
        case, raw, rrweb = self.evidence()
        self.assertIn("Mozilla/5.0 Manus-User/1.0", case["user_agents"]["page"])
        self.assertEqual(case["signatures"]["server"].claimed, "chatgpt.com")
        self.assertEqual((raw, len(rrweb)), ([], 1))


if __name__ == "__main__":
    unittest.main()
