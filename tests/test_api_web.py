"""GET /api/web, the dashboard's visitors and Sources, Devices and Geography tables (agentcake/api/web.py), and the
session list's filter by one of their rows (/api/sessions?dimension=&key=).

    python3 -I -m unittest discover -s tests -p test_api_web.py -v

Visitors are the distinct visitor ids of all the range's sessions, and of its Agent, Human and Bot sessions (a visitor
with sessions of two kinds counts in both); sessions without one are counted as without, never as visitors. The
tables leave bots out (Total = Agent + Human): each row holds the sessions (Agent, Human), visitors (all, Agent, Human)
and page views of one value, most sessions first. On this computer the place dimensions
have no "not set" row (the dashboard says they come only on a server; test_api_places.py has the server's). A row's
key opens its sessions.
The Trends chart counts the Agent and the Human sessions by the hour (the last 24 hours) or by the day (7 and 30 days,
all time) they began in, as the cards count them; Top agents counts each agent's Agent sessions the same way, by its name (the
ones no name fits together), and never a bot.
"""
import json
import time
import unittest
from unittest import mock

import visit_rows
from api_client import Client, contract_problems
from web_uploads import MINUTE_MS, T0, UA_IPHONE, WebCase, upload
from agentcake.api import periods, web

TABS = [f"{n:032x}" for n in range(1, 6)]
VISITORS = ["a" * 32, "b" * 32]


class Answers(WebCase):
    def record(self, tab, verdict, visitor, page=None, ua=None, pages=1, agent=None):
        for n in range(pages):
            pv = f"{n + 1:032x}"
            body = upload(0, T0 + n * MINUTE_MS, tab=tab, pv=pv, visitor=visitor, page=page if n == 0 else {},
                          url=f"https://shop.example.com/p{n}", **({"ua": ua} if ua else {}))
            body["bs"] = tab  # a session of its own: one visitor's sessions at one time would join
            self.post(body)
        self.con.execute("UPDATE sessions SET verdict_class=?, judged_ms=end_ms + 1 WHERE id=?", (verdict, tab))
        if agent:
            self.name(tab, agent)
        visit_rows.refreshed(self.con)

    def name(self, tab, agent):
        """The name the judge gave the session's agent or bot."""
        self.con.execute("UPDATE sessions SET verdict_detail=? WHERE id=?", (json.dumps({"display_name": agent}), tab))
        visit_rows.refreshed(self.con)

    def setUp(self):
        super().setUp()
        self.record(TABS[0], "human", VISITORS[0], page={"rd": "www.google.com"}, pages=2)
        self.record(TABS[1], "human", VISITORS[0], page={"rd": "www.google.com"})
        self.record(TABS[2], "agent", VISITORS[1], page={"rd": "chatgpt.com"}, ua=UA_IPHONE)
        self.record(TABS[3], "human", None, page={})
        self.record(TABS[4], "bot", "c" * 32, page={"rd": "www.google.com"})

    def now(self):
        """A minute after the last session was received (its start_ms is the collector's clock)."""
        return self.one("SELECT MAX(start_ms) FROM sessions")[0] + MINUTE_MS

    def get(self, path="/api/web", **query):
        with mock.patch.object(periods, "now_ms", return_value=self.now()):
            answer = Client().get(path, **query)
        self.assertEqual(answer.status, 200)
        return answer.body

    def dimension(self, body, table, name):
        return next(d["rows"] for d in body["tables"][table] if d["dimension"] == name)

    def test_the_answer_matches_the_contract(self):
        self.assertEqual(contract_problems(self.get(), "web"), [])

    def test_visitors_are_distinct_ids_all_and_by_verdict(self):
        self.assertEqual(self.get()["visitors"], {"all": 3, "agent": 1, "human": 1, "bot": 1, "without": 1})

    def test_a_visitor_with_human_and_agent_sessions_counts_in_both(self):
        self.record("f" * 32, "agent", VISITORS[0], page={})
        visitors = self.get()["visitors"]
        self.assertEqual((visitors["all"], visitors["agent"], visitors["human"]), (3, 2, 1))

    def test_rows_count_sessions_visitors_and_page_views_without_bots(self):
        rows = self.dimension(self.get(), "sources", "referring_domain")
        google = next(row for row in rows if row["key"] == "www.google.com")
        self.assertEqual((google["agent"], google["human"], google["visitors"], google["agent_visitors"],
                          google["human_visitors"], google["page_views"]), (0, 2, 1, 0, 1, 3))

    def test_rows_come_most_sessions_first(self):
        rows = self.dimension(self.get(), "sources", "channel")
        self.assertEqual([row["key"] for row in rows], ["Organic Search", "AI", "Direct"])

    def test_a_table_keeps_the_top_rows_of_each_kind(self):
        with mock.patch.object(web, "settings", return_value={**web.settings(), "rows_max": 1}):
            body = self.get()
        self.assertEqual([row["key"] for row in self.dimension(body, "sources", "channel")], ["Organic Search", "AI"],
                         "the top row by all and by Human sessions, and the top one by Agent sessions")
        self.assertEqual([row["path"] for row in body["paths"]], ["/p0"], "the top path of every kind")

    def test_a_row_without_visitor_ids_has_none(self):
        direct = next(row for row in self.dimension(self.get(), "sources", "channel") if row["key"] == "Direct")
        self.assertIsNone(direct["visitors"])

    def test_devices_come_from_the_user_agent(self):
        rows = self.dimension(self.get(), "devices", "device_type")
        self.assertEqual({row["key"]: row["agent"] + row["human"] for row in rows}, {"Desktop": 3, "Mobile": 1})

    def test_on_this_computer_the_place_dimensions_have_no_rows(self):
        body = self.get()
        self.assertEqual(body["place"]["source"], "none")
        for name in ("country", "region", "city"):
            self.assertEqual(self.dimension(body, "geography", name), [])

    def test_a_region_is_named_with_its_country_and_a_cldr_id_by_its_name(self):
        from agentcake.api import web_dimensions
        self.assertEqual(web_dimensions.label("region", "US:California"), {"value": "California", "country": "US"})
        self.assertEqual(web_dimensions.label("region", "US:USCA"), {"value": "California", "country": "US"})
        self.assertEqual(web_dimensions.label("region", "JP:JP13"), {"value": "Tokyo", "country": "JP"})
        self.assertEqual(web_dimensions.label("region", "ZZ:ZZ99"), {"value": "99", "country": "ZZ"})  # unknown: its code
        self.assertEqual(web_dimensions.label("region", "DE:"), {"value": None, "country": "DE"})
        self.assertEqual(web_dimensions.label("city", "DE:"), {"value": None, "country": "DE"})

    def test_rows_split_page_views_by_agent_and_human(self):
        rows = self.dimension(self.get(), "sources", "referring_domain")
        google = next(row for row in rows if row["key"] == "www.google.com")
        self.assertEqual((google["agent_page_views"], google["human_page_views"]), (0, google["page_views"]))

    def test_a_time_zone_reads_as_its_offset_from_utc(self):
        rows = self.dimension(self.get(), "geography", "timezone")
        self.assertEqual([row["value"] for row in rows], ["UTC-08:00"])

    def test_a_language_is_its_primary_subtag(self):
        self.assertEqual([row["key"] for row in self.dimension(self.get(), "geography", "language")], ["en"])

    def test_a_rows_key_opens_its_sessions(self):
        page = self.get("/api/sessions", dimension="referring_domain", key="www.google.com")
        self.assertEqual(sorted(row["id"] for row in page["results"]), sorted([TABS[0], TABS[1], TABS[4]]))

    def test_a_dimension_without_a_key_opens_the_sessions_without_a_value(self):
        page = self.get("/api/sessions", dimension="utm_source")
        self.assertEqual(page["total"], 5)

    def test_a_session_whose_address_cannot_be_read_does_not_stop_the_dashboard(self):
        self.post(upload(0, T0, tab="e" * 32, visitor=None, url="https://["))
        self.con.execute("DELETE FROM session_web WHERE session_id=?", ("e" * 32,))  # recorded before session_web
        self.con.commit()
        for path in ("/api/web", "/api/overview"):
            self.get(path)  # 200, twice: the first request describes it, the next ones find it described
            self.get(path)

    def test_the_empty_key_of_no_referrer_opens_the_direct_sessions_not_the_ones_without_a_value(self):
        direct = next(row for row in self.dimension(self.get(), "sources", "referring_domain") if row["key"] == "")
        page = self.get("/api/sessions", dimension="referring_domain", key="")
        self.assertEqual([row["id"] for row in page["results"]], [TABS[3]])
        self.assertEqual(page["total"], direct["agent"] + direct["human"])

    def test_page_views_are_page_loads_of_every_verdict(self):
        self.assertEqual(self.get()["page_views"], {"all": 6, "agent": 1, "human": 4, "bot": 1})

    def test_active_time_is_averaged_all_and_by_verdict(self):
        active = self.get()["active_time"]
        self.assertEqual(set(active), {"all", "agent", "human", "bot"})
        self.assertEqual(active["bot"], {"active_ms": 1, "total_ms": 1})
        self.assertEqual(active["human"], {"active_ms": 20_001, "total_ms": 20_001})  # (60 001 + 1 + 1) / 3

    def test_the_path_table_counts_sessions_visitors_and_page_views_by_path(self):
        rows = {row["path"]: row for row in self.get()["paths"]}
        self.assertEqual(rows["/p0"], {"path": "/p0", "agent": 1, "human": 3, "visitors": 2, "agent_visitors": 1,
                                       "human_visitors": 1, "page_views": 4, "agent_page_views": 1,
                                       "human_page_views": 3})
        self.assertEqual((rows["/p1"]["human"], rows["/p1"]["page_views"]), (1, 1))

    def test_top_agents_count_each_agents_sessions_as_the_cards_do_and_never_a_bot(self):
        self.record("e" * 32, "agent", VISITORS[0], page={}, pages=3, agent="Comet")
        self.record("f" * 32, "mixed", VISITORS[1], page={}, agent="Comet")  # Human + agent is an Agent session too
        self.name(TABS[4], "Googlebot")
        self.assertEqual(self.get()["agents"], [
            {"name": "Comet", "sessions": 2, "visitors": 2, "page_views": 4, "active_ms": 60_001, "pages_per_session": 2},
            {"name": None, "sessions": 1, "visitors": 1, "page_views": 1, "active_ms": 1, "pages_per_session": 1}])

    def test_top_agents_name_the_agents_the_top_block_names_and_add_up_to_the_agent_cards(self):
        self.record("e" * 32, "agent", VISITORS[0], page={}, pages=3, agent="Comet")
        body, overview = self.get(), self.get("/api/overview")
        self.assertEqual([(a["name"], a["sessions"]) for a in body["agents"]],
                         [(a["name"], a["sessions"]) for a in overview["agents_seen"]], "the same order, ties too")
        self.assertEqual(sum(a["sessions"] for a in body["agents"]), overview["counts"]["agent"])
        self.assertEqual(sum(a["page_views"] for a in body["agents"]), body["page_views"]["agent"])

    def test_an_agent_whose_sessions_have_no_visitor_id_has_none(self):
        self.record("e" * 32, "agent", None, page={}, agent="Comet")
        comet = next(a for a in self.get()["agents"] if a["name"] == "Comet")
        self.assertIsNone(comet["visitors"])

    def local(self, *fields):
        return int(time.mktime(fields + (0, 0, -1)) * 1000)

    def trends(self, range_key, now, starts):
        """/api/web's trends at now, the sessions moved to start at {tab: local time fields}."""
        for tab, fields in starts.items():
            self.con.execute("UPDATE sessions SET start_ms=? WHERE id=?", (self.local(*fields), tab))
        visit_rows.refreshed(self.con)
        with mock.patch.object(periods, "now_ms", return_value=now):
            answer = Client().get("/api/web", range=range_key)
        self.assertEqual(answer.status, 200)
        return answer.body["trends"]

    def starts(self, yesterday=(2026, 11, 13, 10, 0, 0)):
        """The sessions of setUp: two Human ones of one visitor this morning and after lunch, an Agent and a Bot one
        after lunch, a Human one without a visitor id yesterday (or then)."""
        return {TABS[0]: (2026, 11, 14, 9, 10, 0), TABS[1]: (2026, 11, 14, 13, 5, 0), TABS[2]: (2026, 11, 14, 13, 20, 0),
                TABS[3]: yesterday, TABS[4]: (2026, 11, 14, 13, 30, 0)}

    def test_trends_count_the_last_24_hours_by_hour_from_the_hour_24_hours_ago(self):
        trends = self.trends("24h", self.local(2026, 11, 14, 15, 30, 0), self.starts(yesterday=(2026, 11, 13, 15, 10, 0)))
        self.assertEqual((trends["interval"], trends["every"]), ("hour", 3), "the axis names every third hour")
        self.assertEqual((trends["points"][0]["key"], trends["points"][-1]["key"]), ("2026-11-13 15", "2026-11-14 15"))
        points = {point["label"]: point for point in trends["points"]}
        self.assertEqual(list(points), [f"Nov 13, {hour:02d}:00" for hour in range(15, 24)] +
                         [f"Nov 14, {hour:02d}:00" for hour in range(16)])
        none = {"sessions": 0, "visitors": 0, "page_views": 0, "active_ms": None, "pages_per_session": None}
        self.assertEqual((points["Nov 14, 09:00"]["human"], points["Nov 14, 09:00"]["agent"]),
                         ({"sessions": 1, "visitors": 1, "page_views": 2, "active_ms": 60_001, "pages_per_session": 2},
                          none))
        self.assertEqual((points["Nov 14, 13:00"]["human"]["sessions"], points["Nov 14, 13:00"]["agent"]["sessions"]),
                         (1, 1),
                         "the Bot session isn't counted")
        self.assertEqual(points["Nov 13, 15:00"]["human"]["sessions"], 1, "the first hour is a whole one, 24h20m ago too")
        self.assertEqual(points["Nov 14, 15:00"]["human"], none)

    def test_the_last_24_hours_leave_out_what_began_before_the_hour_24_hours_ago(self):
        trends = self.trends("24h", self.local(2026, 11, 14, 15, 30, 0), self.starts(yesterday=(2026, 11, 13, 14, 59, 0)))
        self.assertEqual(sum(point["human"]["sessions"] for point in trends["points"]), 2)

    def test_trends_count_each_day_of_a_week_and_visitors_as_the_cards_do(self):
        trends = self.trends("7d", self.local(2026, 11, 14, 15, 30, 0), self.starts())
        self.assertEqual((trends["interval"], len(trends["points"]), trends["every"]), ("day", 8, 1))
        self.assertEqual(trends["points"][-1]["key"], "2026-11-14")
        yesterday, today = trends["points"][-2:]
        self.assertEqual((today["human"]["sessions"], today["human"]["visitors"], today["human"]["page_views"]), (2, 1, 3),
                         "one visitor's two sessions")
        self.assertEqual((yesterday["human"]["sessions"], yesterday["human"]["visitors"]), (1, None),
                         "sessions, but none with a visitor id")

    def test_trends_count_all_time_by_day_from_the_first_sessions_day(self):
        trends = self.trends("all", self.local(2026, 11, 14, 15, 30, 0), self.starts(yesterday=(2026, 9, 20, 10, 0, 0)))
        self.assertEqual((trends["interval"], trends["every"]), ("day", "month"), "the axis names the months")
        points = [(p["label"], p["human"]["sessions"]) for p in trends["points"]]
        self.assertEqual((len(points), points[0], points[1], points[-1]),
                         (56, ("Sep 20", 1), ("Sep 21", 0), ("Nov 14", 2)))

    def test_all_time_over_a_new_year_names_the_years(self):
        trends = self.trends("all", self.local(2026, 11, 14, 15, 30, 0), self.starts(yesterday=(2025, 10, 1, 10, 0, 0)))
        labels = [p["label"] for p in trends["points"]]
        self.assertEqual((len(labels), labels[0], labels[-1]), (410, "Oct 1, 2025", "Nov 14, 2026"))
        self.assertEqual(len(set(labels)), len(labels), "Nov 1 comes twice in 410 days, each with its year")

    def test_trends_add_up_to_the_cards(self):
        now = self.local(2026, 11, 14, 15, 30, 0)
        trends = self.trends("30d", now, self.starts())
        self.assertEqual((len(trends["points"]), trends["every"]), (31, 3), "every third day: both ends")
        with mock.patch.object(periods, "now_ms", return_value=now):
            body = Client().get("/api/web", range="30d").body
        for group in ("agent", "human"):
            self.assertEqual(sum(p[group]["page_views"] for p in trends["points"]), body["page_views"][group], group)
        self.assertEqual(sum(p["human"]["sessions"] + p["agent"]["sessions"] for p in trends["points"]), 4)

    def test_an_unknown_dimension_is_refused(self):
        with mock.patch.object(periods, "now_ms", return_value=self.now()):
            self.assertEqual(Client().get("/api/sessions", dimension="shoe_size").status, 400)


if __name__ == "__main__":
    unittest.main()
