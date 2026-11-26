"""Sessions of more than one tab in the API: /api/sessions, /api/session/<id> and its replay, /api/overview
and /api/web.

    python3 -I -m unittest discover -s tests -p test_api_tabs.py -v      (from the AgentCake folder)

Tab sessions are recorded through collect as cake.js sends them, joined into one session as the collector joins them
(visit_rows.joined) and given the verdicts a judge leaves (judging is held still: these tests read how the API puts a
session's tabs together, not how a tab is judged). A session is one row of the list however many tabs it has, its
length from its first tab's first event to the latest end of any, its pages all its tabs', a line per tab; a session of
one tab has none of the tab fields. Its page has each tab with its own verdict, reasons, track and replay, the tab to
follow at each moment, the tab its verdict rests on, and pages and actions marked with their tab; a tab's own address
opens its session with that tab named; a tab's replay is read by ?tab= on the session's clock. The dashboard counts the
session once, all its page views, and its active time as the union of the time its tabs were shown. A tab session the
upgrade has not placed in a visit yet is a session of its own everywhere, so nothing leaves the pages meanwhile.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visit_rows  # noqa: E402
from api_client import Client, contract_problems  # noqa: E402
from test_judging import CHROME, KEY, S, JudgingCase  # noqa: E402
from agentcake import judging  # noqa: E402
from agentcake.api import answers  # noqa: E402

T0 = 1_794_500_000_000
FIRST, SECOND, THIRD = "a" * 32, "b" * 32, "c" * 32  # three tab sessions' ids, as cake.js makes them
VISIT = "f" * 32  # the session they make: its browser session id
SHOP = "https://shop.example"
CLAUDE = {"display_name": "Claude in Chrome", "name_certainty": "likely"}
CODEX = {"display_name": "Codex in-app browser", "name_certainty": "likely"}


def page_record(t, path="/"):
    return {"t": t, "ty": "page", "n": 1, "nav": "navigate", "prerendering": False, "vis": "visible", "p": path}


def click(t):
    return {"t": t, "ty": "click", "cx": 135, "cy": 215, "tr": 1}


def shown(t, visible):
    return {"t": t, "ty": "visibility", "vs": 1 if visible else 0, "hf": 1 if visible else 0}


def replay_events(t, path="/"):
    """A page's first two rrweb events: its address and its whole page."""
    return [{"type": 4, "timestamp": t, "data": {"href": SHOP + path, "width": 1280, "height": 720}},
            {"type": 2, "timestamp": t, "data": {"node": {"type": 0, "childNodes": [], "id": 1},
                                                   "initialOffset": {"top": 0, "left": 0}}}]


class TabsCase(JudgingCase):
    def setUp(self):
        super().setUp()
        for name in ("catch_up", "on_open"):  # the verdicts below stay as written
            patcher = mock.patch.object(judging, name, return_value=0)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tab(self, sid, start, path="/", raw=(), seq=0):
        """One tab session's batch: its page opened at start, its raw input, its page's first replay events."""
        self.post({"v": 1, "k": KEY, "s": sid, "pv": sid[:16] + "0" * 16, "seq": seq, "t": start, "u": SHOP + path,
                   "why": "timer", "ua": CHROME, "wd": False, "e": replay_events(start, path) if seq == 0 else [],
                   "r": list(raw), "x": [page_record(start, path)] if seq == 0 else []}, start)

    def judged(self, sid, verdict_class, detail=None, runs=()):
        """The verdict a judge left for a tab session, and the runs of its timeline."""
        self.con.execute("UPDATE sessions SET verdict_class=?, verdict_detail=?, judged_ms=end_ms WHERE id=?",
                         (verdict_class, json.dumps(detail) if detail else None, sid))
        self.con.executemany("INSERT INTO segments(session_id, t_start, t_end, actor, n_actions) VALUES(?,?,?,?,1)",
                             [(sid, *run) for run in runs])
        self.con.commit()

    def two_tabs(self):
        """A human on the landing page clicks a link that opens the shop in a second tab, shown from 5 s, used until
        65 s; the first tab stays in front until 30 s (a second window), then is hidden."""
        self.tab(FIRST, T0, "/", [click(T0 + 1 * S), click(T0 + 4 * S), shown(T0 + 30 * S, False)])
        self.tab(SECOND, T0 + 5 * S, "/shop", [click(T0 + 10 * S), click(T0 + 65 * S)])
        self.judged(FIRST, "human", runs=[(T0, T0 + 4 * S, "human")])
        self.judged(SECOND, "human", runs=[(T0 + 5 * S, T0 + 65 * S, "human")])
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])

    def get(self, path, schema, **query):
        answer = Client().get(path, **query)
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, schema), [], path)
        return answer.body


class TheList(TabsCase):
    def test_two_tabs_are_one_row_with_a_line_per_tab_and_every_tabs_pages(self):
        self.two_tabs()
        listed = self.get("/api/sessions", "sessions")
        self.assertEqual((listed["total"], listed["counts"]["all"]), (1, 1))
        row = listed["results"][0]
        self.assertEqual((row["id"], row["verdict"], row["pages"]), (VISIT, "human", 2))
        self.assertEqual(row["duration_ms"], 65 * S, "from the first tab's first event to the second tab's last")
        # a tab ends with its last action: the first tab's page being hidden at 30 s is no action
        self.assertEqual([(tab["start_ms"], tab["end_ms"]) for tab in row["tabs"]], [(0, 4 * S), (5 * S, 65 * S)])
        self.assertEqual(row["tabs"][1]["segments"], [{"who": "human", "start_ms": 5 * S, "end_ms": 65 * S}])
        self.assertNotIn("segments", row)

    def test_a_session_of_one_tab_has_none_of_the_tab_fields(self):
        self.tab(FIRST, T0, "/", [click(T0 + S)])
        self.judged(FIRST, "human", runs=[(T0, T0 + S, "human")])
        visit_rows.alone(self.con)
        row = self.get("/api/sessions", "sessions")["results"][0]
        self.assertEqual(row["id"], FIRST)
        self.assertEqual(row["segments"], [{"who": "human", "start_ms": 0, "end_ms": S}])
        for key in ("tabs", "agents"):
            self.assertNotIn(key, row)

    def test_a_tab_that_went_on_after_a_pause_is_still_one_line(self):
        self.tab(FIRST, T0, "/", [click(T0 + S)])
        self.tab(SECOND, T0 + 2 * S, "/shop", [click(T0 + 3 * S)])
        self.tab(THIRD, T0 + 40 * S, "/cart", [click(T0 + 41 * S)])
        for sid in (FIRST, SECOND, THIRD):
            self.judged(sid, "human")
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2"), (THIRD, "w1")])
        row = self.get("/api/sessions", "sessions")["results"][0]
        self.assertEqual([(tab["start_ms"], tab["end_ms"]) for tab in row["tabs"]], [(0, 41 * S), (2 * S, 3 * S)])
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual([(tab["id"], tab["tab"]) for tab in detail["tabs"]], [(FIRST, 1), (SECOND, 2), (THIRD, 1)])

    def test_a_human_tab_and_an_agent_tab_make_a_human_and_agent_session_named_by_the_agent(self):
        self.two_tabs()
        self.judged(SECOND, "agent", CLAUDE)
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        listed = self.get("/api/sessions", "sessions")
        row = listed["results"][0]
        self.assertEqual((row["verdict"], row["agent_turns"], row["agent"], row["certainty"]),
                         ("agent", "human_agent", "Claude in Chrome", "likely"))
        self.assertEqual(listed["agent_names"], ["Claude in Chrome"])
        self.assertEqual(self.get("/api/sessions", "sessions", agent="Claude in Chrome")["total"], 1)

    def test_two_agents_in_two_tabs_are_both_named_and_each_counts_the_session(self):
        self.two_tabs()
        self.judged(FIRST, "agent", {"display_name": None, "category": "automated"})
        self.judged(SECOND, "agent", CLAUDE)
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        row = self.get("/api/sessions", "sessions")["results"][0]
        self.assertEqual(row["agents"], [{"name": "Claude in Chrome", "certainty": "likely"},
                                         {"name": None, "certainty": None}])
        self.assertEqual(row["agent"], "Claude in Chrome", "a named agent first")
        seen = self.get("/api/overview", "overview")["agents_seen"]
        self.assertEqual(sorted(seen, key=lambda agent: agent["name"] or ""),
                         [{"name": None, "sessions": 1}, {"name": "Claude in Chrome", "sessions": 1}])


class ThePage(TabsCase):
    def test_each_tab_with_its_own_verdict_track_and_replay_and_the_tab_to_follow_at_each_moment(self):
        self.two_tabs()
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual([tab["id"] for tab in detail["tabs"]], [FIRST, SECOND])
        self.assertEqual([(tab["start_ms"], tab["end_ms"]) for tab in detail["tabs"]], [(0, 4 * S), (5 * S, 65 * S)])
        self.assertEqual(detail["timeline"]["duration_ms"], 65 * S)
        follow = detail["follow"]
        self.assertEqual((follow[0]["start_ms"], follow[-1]["end_ms"]), (0, 65 * S))
        for before, after in zip(follow, follow[1:]):
            self.assertEqual(before["end_ms"], after["start_ms"])

        def at(ms):
            return next(stretch["tab"] for stretch in follow if stretch["start_ms"] <= ms < stretch["end_ms"])
        self.assertEqual([at(S), at(5 * S), at(10 * S), at(64 * S)], [FIRST, SECOND, SECOND, SECOND])
        self.assertEqual(detail["tabs"][1]["replay"]["chunks"][0]["start_ms"], 5 * S, "on the session's clock")

    def test_pages_and_actions_name_their_tab_in_time_order(self):
        self.two_tabs()
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual([(page["path"], page["tab"], page["at_ms"]) for page in detail["pages"]],
                         [("/", 1, 0), ("/shop", 2, 5 * S)])
        self.assertEqual(detail["pages"][0]["duration_ms"], 4 * S, "until its own tab's end, not another tab's page")
        self.assertEqual(detail["session"]["pages"], 2)
        self.assertEqual([(action["tab"], action["at_ms"]) for action in detail["actions"]],
                         sorted([(1, 0), (1, S), (1, 4 * S), (2, 5 * S), (2, 10 * S), (2, 65 * S)],
                                key=lambda pair: pair[1]))

    def test_the_verdict_rests_on_the_agent_tab_and_the_hand_off_between_tabs_is_marked(self):
        self.two_tabs()
        self.con.execute("DELETE FROM segments WHERE session_id=?", (SECOND,))
        self.judged(SECOND, "agent", CLAUDE, runs=[(T0 + 5 * S, T0 + 65 * S, "agent")])
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual(detail["verdict_tab"], SECOND)
        self.assertEqual(detail["title"], "A human, then Claude in Chrome")
        self.assertEqual(detail["layers"], detail["tabs"][1]["layers"])
        self.assertEqual(detail["tabs"][1]["handoffs"], [{"at_ms": 5 * S, "to": "agent"}])
        self.assertEqual(detail["timeline"]["handoffs"], [{"at_ms": 5 * S, "to": "agent"}])
        self.assertEqual((detail["tabs"][0]["verdict"], detail["tabs"][1]["verdict"]), ("human", "agent"))

    def test_the_verdict_of_a_human_session_rests_on_a_tab_with_enough_evidence_never_a_thin_one(self):
        """A tab with too few actions counts for nothing beside one that has enough (the session is a plain Human), so
        the page's summary, percent and reasons are never the thin tab's, however sure that tab's percent."""
        self.two_tabs()
        self.judged(FIRST, "human", {"percent": 70})
        self.judged(SECOND, "too_little_data", {"percent": 80})
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual((detail["session"]["verdict"], detail["session"]["evidence"]), ("human", None))
        self.assertEqual((detail["verdict_tab"], detail["percent"]), (FIRST, 70))

    def test_a_script_bot_tab_takes_no_part_in_the_title_or_the_hand_offs_of_an_agent_session(self):
        """A Script bot decides a session only when every tab is one: beside an agent's tab it is neither told as an
        agent acting nor marked where the actor changes."""
        self.two_tabs()
        self.con.execute("DELETE FROM segments")
        self.judged(FIRST, "agent", CLAUDE, runs=[(T0, T0 + 4 * S, "agent")])
        self.judged(SECOND, "bot", {"display_name": "HeadlessChrome", "category": "automated-browser"},
                    runs=[(T0 + 5 * S, T0 + 65 * S, "agent")])
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual((detail["session"]["verdict"], detail["title"]), ("agent", "Claude in Chrome"))
        self.assertEqual(detail["timeline"]["handoffs"], [])

    def test_an_agent_that_acted_in_no_tab_is_named_beside_the_human_as_in_a_session_of_one_tab(self):
        # the second tab's agent left runs but no action: no tab has an agent's action
        self.tab(FIRST, T0, "/", [click(T0 + S), click(T0 + 4 * S)])
        self.tab(SECOND, T0 + 5 * S, "/shop")
        self.judged(FIRST, "human", runs=[(T0, T0 + 4 * S, "human")])
        self.judged(SECOND, "agent", CLAUDE, runs=[(T0 + 5 * S, T0 + 9 * S, "agent")])
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual(detail["session"]["agent_turns"], "human_agent")
        self.assertEqual(detail["title"], answers.words()["title"]["with_agent"].format(agent="Claude in Chrome"))

    def test_within_a_tab_the_title_tells_the_turns_its_judge_handed_over_as_one_tab_does(self):
        """A tab's run its judge marked no hand-off to (the agent only moved the pointer) is not a turn of its own, in a
        session of one tab or of several: the title tells what the timeline marks."""
        self.two_tabs()
        self.con.execute("DELETE FROM segments WHERE session_id=?", (SECOND,))
        runs = [(T0 + 5 * S, T0 + 20 * S, "human"), (T0 + 20 * S, T0 + 30 * S, "agent"),
                (T0 + 30 * S, T0 + 40 * S, "human"), (T0 + 40 * S, T0 + 60 * S, "agent")]
        self.judged(SECOND, "mixed", dict(CLAUDE, handoffs=[{"t": T0 + 40 * S, "to": "agent"}]), runs=runs)
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        detail = self.get(f"/api/session/{VISIT}", "session")
        self.assertEqual(detail["tabs"][1]["handoffs"], [{"at_ms": 40 * S, "to": "agent"}])
        self.assertEqual(detail["title"], "A human, then Claude in Chrome")

    def two_agents(self, first_detail, second_detail, human_first=False):
        """Two tabs, a different agent acting in each, one turn each (and a human before the first agent)."""
        before = [click(T0 + S)] if human_first else []
        self.tab(FIRST, T0, "/", before + [click(T0 + 6 * S), click(T0 + 9 * S)])
        self.tab(SECOND, T0 + 20 * S, "/shop", [click(T0 + 22 * S), click(T0 + 29 * S)])
        first_runs = ([(T0, T0 + 4 * S, "human")] if human_first else []) + [(T0 + 5 * S, T0 + 10 * S, "agent")]
        self.judged(FIRST, "mixed" if human_first else "agent", first_detail, runs=first_runs)
        self.judged(SECOND, "agent", second_detail, runs=[(T0 + 20 * S, T0 + 30 * S, "agent")])
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        return self.get(f"/api/session/{VISIT}", "session")["title"]

    def test_two_agents_in_two_tabs_are_each_told_by_their_own_name(self):
        self.assertEqual(self.two_agents(CLAUDE, CODEX), "Claude in Chrome, then Codex in-app browser")

    def test_a_human_then_two_agents_in_two_tabs_are_each_told_by_their_own_name(self):
        self.assertEqual(self.two_agents(CLAUDE, CODEX, human_first=True),
                         "A human, then Claude in Chrome, then Codex in-app browser")

    def test_an_agent_without_a_name_is_an_unnamed_agent_never_the_other_agents_name(self):
        self.assertEqual(self.two_agents(CLAUDE, {"display_name": None, "category": "automated"}),
                         "Claude in Chrome, then an unnamed agent")

    def test_an_address_of_one_of_its_tabs_opens_the_session_with_that_tab_named(self):
        self.two_tabs()
        detail = self.get(f"/api/session/{SECOND}", "session")
        self.assertEqual((detail["session"]["id"], detail["named_tab"]), (VISIT, SECOND))
        self.assertNotIn("named_tab", self.get(f"/api/session/{VISIT}", "session"))

    def test_a_session_of_one_tab_has_no_tabs_on_its_page(self):
        self.tab(FIRST, T0, "/", [click(T0 + S)])
        self.judged(FIRST, "human")
        visit_rows.alone(self.con)
        detail = self.get(f"/api/session/{FIRST}", "session")
        for key in ("tabs", "follow", "verdict_tab", "named_tab"):
            self.assertNotIn(key, detail)
        self.assertNotIn("tab", detail["pages"][0])

    def test_an_unknown_address_is_404(self):
        self.two_tabs()
        self.assertEqual(Client().get("/api/session/nothing-here").status, 404)


class Replay(TabsCase):
    def chunk(self, address, **query):
        return Client().get(f"/api/session/{address}/replay", chunk="0", **query)

    def test_a_tabs_replay_is_read_by_its_id_on_the_sessions_clock(self):
        self.two_tabs()
        answer = self.chunk(VISIT, tab=SECOND)
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "replay"), [])
        self.assertEqual(answer.body["start_ms"], 5 * S)
        self.assertEqual({event["data"].get("href") for event in answer.body["events"]} - {None}, {SHOP + "/shop"})

    def test_without_a_tab_the_first_tab_or_the_one_the_address_named(self):
        self.two_tabs()
        self.assertEqual(self.chunk(VISIT).body["start_ms"], 0)
        self.assertEqual(self.chunk(SECOND).body["start_ms"], 5 * S)

    def test_the_address_of_a_tab_session_that_does_not_count_reads_the_sessions_replay(self):
        """A prefetch the browser never showed is in the session and counts for nothing: its address opens the session,
        and the replay it then asks for, without ?tab=, is the session's (it answered 404 before)."""
        self.tab(FIRST, T0, "/", [click(T0 + 1 * S), click(T0 + 4 * S)])
        self.tab(SECOND, T0 + 5 * S, "/next")
        self.judged(FIRST, "human", runs=[(T0, T0 + 4 * S, "human")])
        self.judged(SECOND, "excluded")
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        answer = self.chunk(SECOND)
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual({event["data"].get("href") for event in answer.body["events"]} - {None}, {SHOP + "/"})

    def test_a_tab_of_another_session_is_no_part_of_this_replay(self):
        self.two_tabs()
        self.assertEqual(self.chunk(VISIT, tab="z" * 32).status, 404)


class TheDashboard(TabsCase):
    def test_a_session_of_two_tabs_counts_once_with_all_its_page_views(self):
        self.two_tabs()
        overview = self.get("/api/overview", "overview")
        self.assertEqual((overview["counts"]["all"], overview["page_views"]["all"]), (1, 2))
        self.assertEqual(overview["pages_per_session"]["all"], 2.0)
        web = self.get("/api/web", "web")
        self.assertEqual(web["page_views"]["all"], 2)
        self.assertEqual(sum(point["human"]["sessions"] for point in web["trends"]["points"]), 1)

    def test_active_time_is_the_union_of_the_time_its_tabs_were_shown(self):
        self.two_tabs()
        time = self.get("/api/web", "web")["active_time"]["all"]
        # the first tab was shown from 0 to 30 s, the second from 5 to 65 s: 65 s together, not 30 + 60
        self.assertEqual(time, {"active_ms": 65 * S, "total_ms": 65 * S})

    def test_tabs_never_open_at_once_add_up_their_active_time(self):
        self.tab(FIRST, T0, "/", [click(T0 + 10 * S)])
        self.tab(SECOND, T0 + 20 * S, "/shop", [click(T0 + 50 * S)])
        for sid in (FIRST, SECOND):
            self.judged(sid, "human")
        visit_rows.joined(self.con, VISIT, [(FIRST, "w1"), (SECOND, "w2")])
        self.assertEqual(self.get("/api/web", "web")["active_time"]["all"], {"active_ms": 40 * S, "total_ms": 50 * S})



class NotPlacedYet(TabsCase):
    """A database an older AgentCake made is placed in visits in the background (visit_upgrade.py)."""

    def setUp(self):
        super().setUp()
        self.two_tabs()
        self.tab(THIRD, T0 + 90 * S, "/old", [click(T0 + 91 * S)])
        self.judged(THIRD, "agent", CLAUDE)
        self.con.execute("DELETE FROM visits WHERE id IN (SELECT visit_id FROM session_web WHERE session_id=?)", (THIRD,))
        self.con.execute("UPDATE session_web SET visit_id=NULL WHERE session_id=?", (THIRD,))
        self.con.commit()

    def test_a_tab_session_in_no_visit_yet_is_listed_and_counted_as_a_session_of_its_own(self):
        listed = self.get("/api/sessions", "sessions")
        self.assertEqual([(row["id"], row["verdict"]) for row in listed["results"]], [(THIRD, "agent"), (VISIT, "human")])
        self.assertEqual((listed["counts"]["all"], listed["counts"]["agent"]), (2, 1))
        self.assertEqual(self.get("/api/sessions", "sessions", agent="Claude in Chrome")["total"], 1)
        self.assertNotIn("tabs", listed["results"][0])

    def test_its_page_and_its_replay_open_as_they_did(self):
        detail = self.get(f"/api/session/{THIRD}", "session")
        self.assertEqual((detail["session"]["id"], detail["session"]["agent"]), (THIRD, "Claude in Chrome"))
        self.assertNotIn("tabs", detail)
        self.assertEqual(Client().get(f"/api/session/{THIRD}/replay", chunk="0").status, 200)

    def test_the_dashboard_counts_it(self):
        overview = self.get("/api/overview", "overview")
        self.assertEqual((overview["counts"]["all"], overview["page_views"]["all"]), (2, 3))
        self.assertEqual(overview["agents_seen"], [{"name": "Claude in Chrome", "sessions": 1}])

if __name__ == "__main__":
    unittest.main()
