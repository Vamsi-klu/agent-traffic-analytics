"""GET /api/web's visitors once a site calls window.cake.identify() (agentcake/api/web.py): PostHog's person.

    python3 -I -m unittest discover -s tests -p test_api_web_identify.py -v

A session counts as the identify hash it carried, else as the hash its visitor id was first sent with in any session
(before the range too: PostHog merges an anonymous distinct id into the person of its first $identify, its earlier
events included), else as its visitor id. So one visitor who signed in on two browsers counts once, their sessions
before signing in included; two who signed in one after the other on one browser, with window.cake.reset() between
(a new visitor id), count twice; a sign-in over another one without reset() keeps the browser's earlier sessions with
the first. Every count of visitors does so: the cards (all and by verdict, which may add up to more than all), the
Trends chart, Top agents, the Path table and the Sources, Devices and Geography tables. Without identify() each
visitor id counts once (test_api_web.py, unchanged).
"""
import hashlib
import json
import unittest
from unittest import mock

import visit_rows
from api_client import Client
from web_uploads import KEY, MINUTE_MS, T0, WebCase, upload
from agentcake.api import periods

BROWSERS = ["1" * 32, "2" * 32, "3" * 32]  # visitor ids: one per browser (or per reset)
DAY_MS = 24 * 60 * MINUTE_MS


def person(user_id):
    """The identify hash cake.js sends for the site's own id (static/src/identify.js)."""
    return hashlib.sha256(f"{KEY}:{user_id}".encode()).hexdigest()


class IdentifiedVisitors(WebCase):
    tabs = iter(())

    def setUp(self):
        super().setUp()
        self.tabs = (f"{n:032x}" for n in range(1, 100))

    def visit(self, verdict, browser, signed_in=None, agent=None, ago_ms=0):
        """One session of a browser (a visitor id), signed in as signed_in (a hash) or not, ago_ms before now."""
        tab = next(self.tabs)
        # each a session of its own: its own browser session (one browser's sessions at one time would join)
        self.post(dict(upload(0, T0, tab=tab, pv=tab, visitor=browser, person=signed_in, page={"rd": "www.google.com"},
                              url="https://shop.example.com/"), bs=tab))
        self.con.execute("UPDATE sessions SET verdict_class=?, judged_ms=end_ms + 1, start_ms=start_ms - ? WHERE id=?",
                         (verdict, ago_ms, tab))
        if agent:
            self.con.execute("UPDATE sessions SET verdict_detail=? WHERE id=?",
                             (json.dumps({"display_name": agent}), tab))
        visit_rows.refreshed(self.con)
        return tab

    def get(self, range_key=None):
        now = self.one("SELECT MAX(start_ms) FROM sessions")[0] + MINUTE_MS
        with mock.patch.object(periods, "now_ms", return_value=now):
            answer = Client().get("/api/web", **({"range": range_key} if range_key else {}))
        self.assertEqual(answer.status, 200)
        return answer.body

    def test_one_visitor_signed_in_on_two_browsers_counts_once(self):
        self.visit("human", BROWSERS[0], person("user-1"))
        self.visit("human", BROWSERS[1], person("user-1"))
        self.assertEqual(self.get()["visitors"], {"all": 1, "agent": 0, "human": 1, "bot": 0, "without": 0})

    def test_a_browsers_sessions_before_signing_in_count_as_the_visitor_it_signed_in_as(self):
        self.visit("human", BROWSERS[0])
        self.visit("human", BROWSERS[0], person("user-1"))
        self.visit("human", BROWSERS[1])
        self.visit("human", BROWSERS[1], person("user-1"))
        self.assertEqual(self.get()["visitors"]["all"], 1)

    def test_two_visitors_on_one_browser_with_reset_between_count_twice(self):
        self.visit("human", BROWSERS[0])
        self.visit("human", BROWSERS[0], person("user-a"))
        self.visit("human", BROWSERS[1])  # reset(): a new visitor id, not signed in yet
        self.visit("human", BROWSERS[1], person("user-b"))
        self.assertEqual(self.get()["visitors"]["all"], 2)

    def test_a_sign_in_over_another_without_reset_keeps_the_earlier_sessions_with_the_first(self):
        self.visit("human", BROWSERS[0])
        self.visit("human", BROWSERS[0], person("user-a"))
        self.visit("agent", BROWSERS[0], person("user-b"))
        visitors = self.get()["visitors"]
        self.assertEqual((visitors["all"], visitors["human"], visitors["agent"]), (2, 1, 1),
                         "the anonymous session is user-a's, as the first sign-in's")

    def test_a_sign_in_before_the_range_still_counts(self):
        self.visit("human", BROWSERS[0], person("user-1"), ago_ms=3 * DAY_MS)
        self.visit("human", BROWSERS[0])
        self.visit("human", BROWSERS[1], person("user-1"))
        visitors = self.get("24h")["visitors"]
        self.assertEqual((visitors["all"], visitors["human"]), (1, 1))

    def test_kinds_count_the_same_visitor_and_may_add_up_to_more_than_all(self):
        self.visit("human", BROWSERS[0], person("user-1"))
        self.visit("agent", BROWSERS[1], person("user-1"), agent="Comet")
        self.visit("bot", BROWSERS[2])
        self.assertEqual(self.get()["visitors"], {"all": 2, "agent": 1, "human": 1, "bot": 1, "without": 0})

    def test_every_count_of_visitors_counts_the_signed_in_visitor_once(self):
        for verdict in ("human", "agent"):
            self.visit(verdict, BROWSERS[0], person("user-1"), agent="Comet")
            self.visit(verdict, BROWSERS[1], person("user-1"), agent="Comet")
        body = self.get("7d")
        today = body["trends"]["points"][-1]
        self.assertEqual((today["human"]["visitors"], today["agent"]["visitors"]), (1, 1))
        self.assertEqual([(agent["name"], agent["sessions"], agent["visitors"]) for agent in body["agents"]],
                         [("Comet", 2, 1)])
        self.assertEqual([(row["visitors"], row["agent_visitors"], row["human_visitors"]) for row in body["paths"]],
                         [(1, 1, 1)])
        for table, dimensions in body["tables"].items():
            for dimension in dimensions:
                for row in dimension["rows"]:
                    self.assertEqual((row["visitors"], row["agent_visitors"], row["human_visitors"]), (1, 1, 1),
                                     f"{table} by {dimension['dimension']}: {row['key']}")

    def test_a_hash_and_a_visitor_id_are_never_counted_as_the_same_visitor(self):
        self.visit("human", BROWSERS[0], person("user-1"))
        self.visit("human", person("user-1")[:32])  # a visitor id that happens to read like the hash's start
        self.assertEqual(self.get()["visitors"]["all"], 2)


if __name__ == "__main__":
    unittest.main()
