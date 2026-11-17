"""GET /api/health and /healthz (agentcake/api/health.py).

    python3 -I -m unittest discover -s tests -p test_api_health.py -v      (from the AgentCake folder)

/api/health answers the contract (cake 0.3.4's fields, and the disk 0.4.0 added); real_sessions leaves out self-checks
and uploads from another site. /healthz is the load balancer's: "ok".
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from agentcake import __version__, config, paths, routes, store  # noqa: E402
from agentcake.responses import Request  # noqa: E402

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

    def test_the_public_health_check_says_ok(self):
        view = routes.resolve(routes.PUBLIC, "GET", "/healthz")
        self.assertEqual(view(Request("/healthz", {}, {})).body, "ok")


if __name__ == "__main__":
    unittest.main()
