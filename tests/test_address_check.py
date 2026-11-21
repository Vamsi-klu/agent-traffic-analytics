"""The safety net under the verification layer (agentcake.address_check).

    python3 -I -m unittest discover -s tests -p test_address_check.py -v      (from the repository root)

When most of the latest sessions with a visitor's address came from a CDN's published ranges, the address AgentCake
reads is the front door's own (Cloudflare's orange cloud in front of the subdomain route, a CDN in front of a
same-site path). The check counts the latest sessions (verdict.json "address_check": how many, the CDN share, the
window) before a given time: too few say nothing, relay addresses (iCloud Private Relay) are visitors, self-checks
and other sites do not count, and a fix shows within a few sessions while a session recorded before it is judged the
same as when it was recorded. Sessions are written straight into the requests table here, in netfacts.request_facts'
shape; the platform simulation posts its visits through collect.
"""
import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import address_check, config, store  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.units import MS_PER_S  # noqa: E402

RULE = load("data/verdict.json")["address_check"]
T0 = 1_794_500_000_000
GAP_MS = 60 * MS_PER_S  # one session a minute


class AddressCheckCase(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_address_check", public_listen="127.0.0.1:9", trust_lb=True)
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.made = 0

    def sessions(self, n, ip_class, is_test=0, origin="site", address=True):
        """n sessions one minute apart, each with two upload requests whose address is in a network of ip_class
        (None: in no published network); address False: uploads without an address. Returns the last one's time."""
        for _ in range(n):
            self.made += 1
            sid, at = f"s{self.made:04d}", T0 + self.made * GAP_MS
            facts = {"headers": [], "names": [], "origin": origin}
            if address:
                facts.update(range=None, range_id=None, range_kind=None, ip_class=ip_class)
            self.con.execute("INSERT INTO sessions(id, start_ms, end_ms, is_test, origin) VALUES(?,?,?,?,?)",
                             (sid, at - MS_PER_S, at, is_test, origin))
            self.con.executemany("INSERT INTO requests(session_id, recv_ms, seq, facts) VALUES(?,?,?,?)",
                                 [(sid, at - MS_PER_S, 0, json.dumps(facts)), (sid, at, 1, json.dumps(facts))])
        self.con.commit()
        return T0 + self.made * GAP_MS

    def check(self, at_ms):
        return address_check.check(self.con, at_ms)


class Counting(AddressCheckCase):
    def test_too_few_sessions_with_an_address_say_nothing(self):
        at = self.sessions(RULE["sessions"] - 1, "cdn")
        self.assertEqual(self.check(at), {"sessions": RULE["sessions"] - 1, "cdn": RULE["sessions"] - 1,
                                          "misconfigured": False})

    def test_most_of_the_latest_sessions_from_a_cdn_mean_the_address_is_the_front_doors(self):
        at = self.sessions(RULE["sessions"], "cdn")
        self.assertEqual(self.check(at), {"sessions": RULE["sessions"], "cdn": RULE["sessions"], "misconfigured": True})

    def test_the_share_decides(self):
        cdn = round(RULE["sessions"] * RULE["cdn_share"])
        self.sessions(cdn, "cdn")
        at = self.sessions(RULE["sessions"] - cdn, None)
        self.assertTrue(self.check(at)["misconfigured"], "exactly the share")
        at = self.sessions(1, "cloud")  # the newest pushes the oldest CDN session out of the latest ones
        self.assertEqual(self.check(at), {"sessions": RULE["sessions"], "cdn": cdn - 1, "misconfigured": False})

    def test_relay_addresses_are_visitors(self):
        """iCloud Private Relay's egress sits in CDN ranges but is classed relay: those are people."""
        at = self.sessions(RULE["sessions"], "relay")
        self.assertFalse(self.check(at)["misconfigured"])

    def test_sessions_without_an_address_self_checks_and_other_sites_do_not_count(self):
        self.sessions(RULE["sessions"], "cdn", is_test=1)
        self.sessions(RULE["sessions"], "cdn", origin="other")
        at = self.sessions(RULE["sessions"], None, address=False)
        self.assertEqual(self.check(at), {"sessions": 0, "cdn": 0, "misconfigured": False})


class Time(AddressCheckCase):
    def test_only_sessions_within_the_window_before_the_time_count(self):
        last_cdn = self.sessions(RULE["sessions"], "cdn")
        self.assertFalse(self.check(last_cdn + RULE["window_s"] * MS_PER_S + GAP_MS)["misconfigured"], "too long ago")
        before = self.check(T0)
        self.assertEqual(before["sessions"], 0, "nothing before the first session")

    def test_a_fix_shows_within_a_few_sessions_and_earlier_sessions_keep_their_answer(self):
        broken = self.sessions(2 * RULE["sessions"], "cdn")
        allowed = round(RULE["sessions"] * (1 - RULE["cdn_share"]))  # correct sessions the share leaves room for
        fixed = self.sessions(allowed + 1, None)
        self.assertFalse(self.check(fixed)["misconfigured"])
        self.assertTrue(self.check(broken)["misconfigured"], "a session recorded before the fix, judged again later")


class Current(AddressCheckCase):
    def test_now_on_a_server_that_reads_addresses(self):
        self.sessions(RULE["sessions"], "cdn")
        self.assertTrue(address_check.current(self.con, now_ms=T0 + (self.made + 1) * GAP_MS)["misconfigured"])

    def test_nothing_to_check_without_an_address_source(self):
        self.sessions(RULE["sessions"], "cdn")
        now = T0 + (self.made + 1) * GAP_MS
        for settings in ({"trust_lb": False}, {"public_listen": ""}):
            with self.subTest(settings):
                config.save_user(**settings)
                self.assertEqual(address_check.current(self.con, now_ms=now),
                                 {"sessions": 0, "cdn": 0, "misconfigured": False})
                config.save_user(public_listen="127.0.0.1:9", trust_lb=True)


if __name__ == "__main__":
    unittest.main()
