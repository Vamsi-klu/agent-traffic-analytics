"""The dashboard's date ranges on a scratch database (agentcake/api/overview.py, sessions.py and web.py, by periods.py):
which Agent sessions each range counts, which the period before it counts (agent_earlier, what the Agent block
compares with), and that the session list and the Trends chart count the cards' sessions.

    python3 -I -m unittest discover -s tests -p test_api_overview_ranges.py -v      (from the AgentCake folder)

As PostHog's do: Last 24 hours run from the start of the hour 24 hours ago, the last 7 and 30 days from midnight 7
and 30 days ago (8 and 31 days, today's included), and each is compared with its previous period, as long as the
range is to the end of the current hour or day, right before it: 25 hours, 8 days, 31 days. All time has none.
"""
import os
import time
import unittest
from unittest import mock

from api_client import Client, contract_problems
from web_uploads import MINUTE_MS, WebCase, upload
from agentcake.api import periods

HOUR_MS = 60 * MINUTE_MS
DAY_MS = 24 * HOUR_MS
NOW = 1_794_546_780_000  # 2026-11-12 21:13 in Los Angeles: the last 24 hours start at 21:00 the day before
# The Agent sessions, by how long before NOW each began; a week ago is the morning of Thursday 2026-11-05
AGENT_AGO = {"just now": 5 * MINUTE_MS, "an hour ago": HOUR_MS,
             "in the first hour, 24 hours ago": DAY_MS + 10 * MINUTE_MS,
             "before the first hour": DAY_MS + 20 * MINUTE_MS, "30 hours ago": 30 * HOUR_MS,
             "36 hours ago": 36 * HOUR_MS, "in the first of the 25 hours before": 48 * HOUR_MS + 30 * MINUTE_MS,
             "also in it": 49 * HOUR_MS, "before the 25 hours before": 49 * HOUR_MS + 30 * MINUTE_MS,
             "a week ago": 7 * DAY_MS + 12 * HOUR_MS, "8 days ago": 8 * DAY_MS, "40 days ago": 40 * DAY_MS}
HUMAN_AGO = 2 * HOUR_MS


class Ranges(WebCase):
    def setUp(self):
        super().setUp()
        zone = mock.patch.dict(os.environ, {"TZ": "America/Los_Angeles"})
        zone.start()
        self.addCleanup(zone.stop)
        self.addCleanup(time.tzset)
        time.tzset()
        tabs = (f"{n:032x}" for n in range(1, 100))
        for ago in AGENT_AGO.values():
            self.visit(next(tabs), "agent", ago)
        self.visit(next(tabs), "human", HUMAN_AGO)

    def visit(self, tab, verdict, ago):
        self.post(upload(0, NOW - ago, tab=tab, pv=tab))
        self.con.execute("UPDATE sessions SET start_ms=?, verdict_class=?, judged_ms=end_ms + 1 WHERE id=?",
                         (NOW - ago, verdict, tab))
        self.con.commit()

    def get(self, path, name, **query):
        with mock.patch.object(periods, "now_ms", return_value=NOW):
            answer = Client().get(path, **query)
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, name), [])
        return answer.body

    def agent(self, range_key):
        """(Agent sessions of the range, of the same range earlier)."""
        body = self.get("/api/overview", "overview", range=range_key)
        return body["counts"]["agent"], body["agent_earlier"]

    def test_the_last_24_hours_count_from_the_start_of_the_hour_24_hours_ago(self):
        self.assertEqual(self.agent("24h")[0], 3, "just now, an hour ago and in the first hour, 24 hours ago")

    def test_the_last_24_hours_compare_with_the_25_hours_before_their_first_hour(self):
        self.assertEqual(self.agent("24h")[1], 5, "before the first hour to the first of the 25 hours before")

    def test_days_compare_with_as_many_days_before_and_all_time_with_nothing(self):
        self.assertEqual(self.agent("7d"), (10, 1), "from Thursday a week ago; 8 days ago is the 8 days before's")
        self.assertEqual(self.agent("30d"), (11, 1), "40 days ago is the 31 days before's")
        self.assertEqual(self.agent("all"), (12, None))
        self.assertEqual(self.agent(None), (12, None))

    def test_the_session_list_and_the_trends_count_the_cards_sessions(self):
        for range_key in ("24h", "7d", "30d", "all"):
            counts = self.get("/api/overview", "overview", range=range_key)["counts"]
            listed = self.get("/api/sessions", "sessions", range=range_key)
            points = self.get("/api/web", "web", range=range_key)["trends"]["points"]
            self.assertEqual(listed["total"], counts["all"], range_key)
            for group in ("agent", "human"):
                self.assertEqual(sum(point[group]["sessions"] for point in points), counts[group], (range_key, group))

    def test_the_last_24_hours_trends_have_an_hour_for_each_hour_from_the_first(self):
        trends = self.get("/api/web", "web", range="24h")["trends"]
        self.assertEqual((trends["interval"], len(trends["points"])), ("hour", 25))
        first, current = trends["points"][0], trends["points"][-1]
        self.assertEqual((first["label"], first["agent"]["sessions"]), ("Nov 11, 21:00", 1))
        self.assertEqual((current["label"], current["agent"]["sessions"]), ("Nov 12, 21:00", 1))


if __name__ == "__main__":
    unittest.main()
