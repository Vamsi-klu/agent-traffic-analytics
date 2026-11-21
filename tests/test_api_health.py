"""GET /api/health and /healthz (agentcake/api/health.py).

    python3 -I -m unittest discover -s tests -p test_api_health.py -v      (from the AgentCake folder)

/api/health answers the contract (cake 0.3.4's fields, and the disk 0.4.0 added); real_sessions leaves out self-checks
and uploads from another site. /healthz is the load balancer's: "ok".
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from agentcake import __version__, config, paths, routes, store, updates  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.detect import lists_build  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from agentcake.storage_config import now_ms  # noqa: E402

T0 = 1_794_500_000_000


class Health(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_health", disk_min_free_mb=0)

    def test_it_answers_the_contract_with_0_3_4s_fields(self):
        body = Client().get("/api/health").body
        self.assertEqual(contract_problems(body, "health"), [])
        self.assertEqual((body["version"], body["home"], body["site_key"]), (__version__, paths.home(), "ck_health"))

    def test_real_sessions_leave_out_self_checks_and_other_sites(self):
        con = store.db()
        rows = [("site", "site", 0), ("demo", "demo", 0), ("check", "site", 1), ("copy", "other", 0)]  # demo: before 0.4.0
        con.executemany("INSERT INTO sessions(id, start_ms, end_ms, origin, is_test) VALUES(?, ?, ?, ?, ?)",
                        [(sid, T0, T0, origin, test) for sid, origin, test in rows])
        con.commit()
        con.close()
        body = Client().get("/api/health").body
        self.assertEqual((body["sessions"], body["real_sessions"], body["selfcheck_visits"]), (4, 2, 1))
        self.assertNotIn("demo_sessions", body, "no demo shop")

    def test_the_address_check_says_whether_the_address_read_is_a_cdns(self):
        """What doctor reads: the latest sessions with a visitor's address, how many of them came from a
        CDN's published ranges, and whether that makes the address the front door's own."""
        self.assertEqual(Client().get("/api/health").body["address_check"],
                         {"sessions": 0, "cdn": 0, "misconfigured": False}, "this computer reads no address")
        config.save_user(public_listen="127.0.0.1:9", trust_lb=True)
        enough, now = load("data/verdict.json")["address_check"]["sessions"], now_ms()
        con = store.db()
        for n in range(enough):
            con.execute("INSERT INTO sessions(id, start_ms, end_ms) VALUES(?, ?, ?)", (f"s{n}", now - n, now - n))
            con.execute("INSERT INTO requests(session_id, recv_ms, facts) VALUES(?, ?, ?)",
                        (f"s{n}", now - n, json.dumps({"headers": [], "range_id": None, "ip_class": "cdn"})))
        con.commit()
        con.close()
        body = Client().get("/api/health").body
        self.assertEqual(body["address_check"], {"sessions": enough, "cdn": enough, "misconfigured": True})
        self.assertEqual(contract_problems(body, "health"), [])

    def test_it_says_whether_updates_run_monthly_and_how_the_last_one_went(self):
        self.assertEqual(Client().get("/api/health").body["updates"],
                         {"auto": True, "last": None, "failures": 0, "failing": False})

        def unreachable(url, accept=None):
            raise lists_build.BuildError(f"{url}: unreachable")

        config.save_user(lists_auto_update=False)
        updates.run(updates.MANUAL, parts=[updates.LISTS], fetchers={updates.LISTS: unreachable})
        body = Client().get("/api/health").body
        self.assertEqual(contract_problems(body, "health"), [])
        found = body["updates"]
        self.assertEqual((found["auto"], found["failures"], found["last"]["how"], found["last"]["ok"]),
                         (False, 1, updates.MANUAL, False))
        self.assertEqual(found["last"]["parts"], {updates.LISTS: updates.FAILED})
        self.assertIn("unreachable", found["last"]["error"])

    def test_the_public_health_check_says_ok(self):
        view = routes.resolve(routes.PUBLIC, "GET", "/healthz")
        self.assertEqual(view(Request("/healthz", {}, {})).body, "ok")


if __name__ == "__main__":
    unittest.main()
