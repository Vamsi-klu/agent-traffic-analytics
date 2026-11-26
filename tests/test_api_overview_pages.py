"""agentcake/api/overview.py's numbers about pages, on a scratch database: page views and pages per session.

    python3 -I -m unittest discover -s tests -p test_api_overview_pages.py -v      (from the AgentCake folder)

A page view is what PostHog counts as one: each page load and each new path a single-page app shows (a new query string
alone is none), in sessions of every kind; these sessions were recorded without the page script's path records, so they
are counted from their batches' paths (web_time.py). Pages per session divides page views by sessions, of all sessions
and of each verdict's, none for a group without sessions (the dashboard's Paths are /api/web's, test_api_web.py). A
test of the private suite checks the whole answer on the fixed library.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visit_rows  # noqa: E402
from agentcake import config  # noqa: E402
from agentcake.api import overview, visits  # noqa: E402

T0 = 1_794_500_000_000
SHOP = "https://shop.example"


class SessionsByPage(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_overview", disk_min_free_mb=0)
        self.con = visits.connect()
        self.addCleanup(self.con.close)

    def visit(self, sid, verdict_class, *views):
        """A session of one tab and its page views, each (page view, path) as cake.js's batches carry them."""
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms, origin, is_test, verdict_class) "
                         "VALUES(?, ?, ?, 'site', 0, ?)", (sid, T0, T0 + 1000, verdict_class))
        for seq, (pv, path) in enumerate(views):
            self.con.execute("INSERT INTO batches(session_id, pv, seq, recv_ms, t, url, n_rrweb, n_raw, n_env) "
                             "VALUES(?, ?, ?, ?, ?, ?, 0, 0, 0)", (sid, pv, seq, T0, T0 + seq, SHOP + path))
        visit_rows.alone(self.con)

    def views(self):
        return overview.page_views(self.con, visits.Scope())

    def paths(self):
        return sorted(self.con.execute("SELECT session_id, path, views FROM web_paths").fetchall())

    def test_a_page_view_is_every_time_a_page_opened_in_sessions_of_every_kind(self):
        self.visit("agent", "agent", ("pv1", "/"), ("pv2", "/"), ("pv3", "/cart"))
        self.visit("app", "human", ("pv1", "/"), ("pv1", "/"), ("pv1", "/account"))  # the app's new address
        self.visit("bot", "bot", ("pv1", "/"))
        self.assertEqual(self.views(), {"all": 6, "human": 2, "agent": 3, "bot": 1})
        self.assertEqual(self.paths(), [("agent", "/", 2), ("agent", "/cart", 1), ("app", "/", 1), ("app", "/account", 1),
                                        ("bot", "/", 1)])

    def test_page_views_count_every_view_and_split_by_the_sessions_verdict(self):
        self.visit("agent", "agent", ("pv1", "/"), ("pv2", "/"), ("pv3", "/cart"))
        self.visit("mixed", "mixed", ("pv1", "/"))  # Human + agent: an Agent session
        self.visit("human", "not_sure", ("pv1", "/"), ("pv1", "/account"))  # thin evidence: a Human session
        self.visit("bot", "bot", ("pv1", "/"))
        self.assertEqual(self.views(), {"all": 7, "human": 2, "agent": 4, "bot": 1})

    def test_pages_per_session_divides_human_and_agent_page_views_by_their_sessions(self):
        self.visit("agent", "agent", ("pv1", "/"), ("pv2", "/"), ("pv3", "/cart"))
        self.visit("mixed", "mixed", ("pv1", "/"))  # Human + agent: an Agent session
        self.visit("human1", "human", ("pv1", "/"))
        self.visit("human2", "not_sure", ("pv1", "/"), ("pv2", "/cart"))  # thin evidence: a Human session
        self.visit("bot", "bot", ("pv1", "/"), ("pv2", "/a"), ("pv3", "/b"))
        counts = visits.counts(self.con, visits.Scope())
        self.assertEqual(overview.pages_per_session(self.views(), counts), {"all": 2.0, "human": 1.5, "agent": 2.0, "bot": 3.0})

    def test_pages_per_session_is_none_for_a_verdict_without_sessions(self):
        self.visit("human", "human", ("pv1", "/"))
        counts = visits.counts(self.con, visits.Scope())
        self.assertEqual(overview.pages_per_session(self.views(), counts), {"all": 1.0, "human": 1.0, "agent": None, "bot": None})


if __name__ == "__main__":
    unittest.main()
