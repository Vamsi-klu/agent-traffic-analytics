"""One session's evidence read from the database (agentcake.evidence, plan step S3.4 wiring).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Uploads go through collect, then evidence.session_evidence() reads them back: pages in the signals' order with the
Sec-Purpose of their server half and whether they were prerendered and shown; the server half read as the page
request for the environment rules; on server mode's public listener the network facts of the address, the earlier
visits from the same network and mode "server"; the Web Bot Auth result collect kept with a request and the page
request's Signature-Agent; a phone or tablet; records without a time left out; a cake 0.3.4 visit's User-Agent and
server half. The addresses are the first of a published range (as a load balancer would give them).
"""
import http.client, json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import first_address  # noqa: E402
from agentcake import collect, config, edge_secret, edge_token, evidence, store, streams  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.responses import Request  # noqa: E402

KEY = "ck_evidence_test"
SID, OTHER = "7d2e8f4a2fac6c83d9f6e2d3a4b5c6d7", "8e3f9a5b3abd7d94eaa7f3e4b5c6d7e8"
PV1, PV2 = "a1" * 16, "b2" * 16
T0 = 1_794_500_000_000
S = 1000
CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
LB = load("data/lb_headers.json")["headers"]


class FixedTime:
    def __init__(self, ms):
        self.ms = ms

    def time(self):
        return self.ms / S


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
        with mock.patch.object(collect, "time", FixedTime(at_ms)):
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
