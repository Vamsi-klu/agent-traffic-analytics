"""agentcake/api/visits.py: which sessions the pages show, and each one as the lists show it.

    python3 -I -m unittest discover -s tests -p test_api_visits.py -v      (from the AgentCake folder)

Sessions are written into a scratch database the way judging.py and collect leave them. Self-checks, other sites'
uploads and prefetches never count. The session categories (the verdict with an Agent session's split, and the agent's name
with how sure it is) come from the four layers' verdict, or from cake 0.3.4's columns for a session judged before 0.4.0;
the kind of agent stays inside the verdict. The share adds up to 100 and
counts the actions its page lists (Every action, by who took them), 0 everywhere without one. A row's length is its recording's, the player's: from its first
recorded event to its last action, replay event or segment, whichever is later (the dashboard's average length is another
measure); a Human + agent row's segments count from the same start. Its pages are the pages its
page lists: each page view and each new address within one. Paging is stable while sessions arrive.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import config, streams  # noqa: E402
from agentcake.api import visits  # noqa: E402

T0 = 1_794_500_000_000
NOW = T0 + 3_600_000
MACHINE = None  # the times in words follow this computer's timezone (periods.py)
DETAIL = {"display_name": None, "category": None, "operator": None}


class Visits(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_visits", disk_min_free_mb=0)
        self.con = visits.connect()
        self.addCleanup(self.con.close)

    def put(self, sid, start=T0, **columns):
        row = {"id": sid, "start_ms": start, "end_ms": start + 1000, "origin": "site", "is_test": 0, **columns}
        if isinstance(row.get("verdict_detail"), dict):
            row["verdict_detail"] = json.dumps(dict(DETAIL, **row["verdict_detail"]))
        if isinstance(row.get("layers"), dict):
            row["layers"] = json.dumps(row["layers"])
        self.con.execute(f"INSERT INTO sessions({', '.join(row)}) VALUES({', '.join('?' * len(row))})",
                         tuple(row.values()))

    def runs(self, sid, *runs):
        self.con.executemany("INSERT INTO segments(session_id, t_start, t_end, actor, n_actions) VALUES(?,?,?,?,?)",
                             [(sid, *run) for run in runs])

    def listed(self, scope=None):
        rows, _ = visits.page(self.con, scope or visits.Scope(), 50, NOW, MACHINE)
        return {row["id"]: row for row in rows}


class WhichCount(Visits):
    def test_self_checks_other_sites_and_prefetches_are_left_out(self):
        self.put("visit", verdict_class="human")
        self.put("selfcheck", verdict_class="human", is_test=1)
        self.put("copy", verdict_class="human", origin="other")
        self.put("prefetch", verdict_class="excluded")
        self.assertEqual(list(self.listed()), ["visit"])
        self.assertEqual(visits.counts(self.con, visits.Scope())["all"], 1)

    def test_a_demo_shop_session_is_listed_and_marked_as_the_demo_shops(self):
        self.put("visit", verdict_class="human")
        self.put("demo", verdict_class="human", origin="demo")  # an earlier AgentCake's demo shop recorded it
        rows = self.listed()
        self.assertEqual(set(rows), {"visit", "demo"})
        self.assertIs(rows["demo"]["demo_shop"], True)
        self.assertNotIn("demo_shop", rows["visit"])

    def test_the_website_scope_leaves_out_the_demo_shops_sessions(self):
        self.put("visit", verdict_class="human")
        self.put("old-row", verdict_class="agent", agent_row="ai", origin=None)  # before origin had a default
        self.put("demo", verdict_class="human", origin="demo")
        self.assertEqual(visits.total(self.con, visits.Scope()), 3)
        self.assertEqual(visits.total(self.con, visits.Scope().from_site()), 2)


class Verdicts(Visits):
    def test_three_verdicts_mixed_is_an_agent_session_and_what_cake_cant_tell_is_human_on_thin_evidence(self):
        for cls in ("human", "agent", "mixed", "bot", "not_sure", "too_little_data"):
            self.put(cls, verdict_class=cls, agent_row="ai" if cls in ("agent", "mixed") else None)
        self.assertEqual({sid: (row["verdict"], row["agent_turns"], row["evidence"]) for sid, row in self.listed().items()},
                         {"human": ("human", None, None), "agent": ("agent", "agent_only", None),
                          "mixed": ("agent", "human_agent", None), "bot": ("bot", None, None),
                          "not_sure": ("human", None, "thin"), "too_little_data": ("human", None, "thin")})

    def test_a_session_judged_by_cake_034_keeps_its_verdict(self):
        self.put("old-agent", verdict="agent", webdriver=1)
        self.put("old-unsure", verdict="unsure")
        self.put("not-judged-yet")
        rows = self.listed()
        self.assertEqual({sid: (row["verdict"], row["evidence"], row["agent_turns"]) for sid, row in rows.items()},
                         {"old-agent": ("agent", None, "agent_only"), "old-unsure": ("human", "thin", None),
                          "not-judged-yet": ("human", "thin", None)})
        self.assertTrue(all("agent_kind" not in row for row in rows.values()), "the kind stays inside the verdict")

    def test_the_agent_is_its_name_and_how_sure_it_is_else_none_whatever_its_category(self):
        self.put("verified", verdict_class="agent", agent_row="ai",
                 verdict_detail={"display_name": "ChatGPT agent", "name_certainty": "certain"})
        self.put("declared", verdict_class="mixed", agent_row="ai",
                 verdict_detail={"display_name": "Claude in Chrome", "name_certainty": "likely"})
        self.put("network", verdict_class="agent", agent_row="ai",
                 verdict_detail={"category": "infrastructure", "operator": "OpenAI"})
        self.put("tool", verdict_class="agent", agent_row="automated",
                 verdict_detail={"display_name": "Playwright", "name_certainty": "likely"})
        self.put("unnamed", verdict_class="agent", agent_row="automated", verdict_detail={"category": "automated"})
        self.put("bot", verdict_class="bot", verdict_detail={"display_name": "Googlebot", "name_certainty": "likely"})
        self.put("human", verdict_class="human", verdict_detail={})
        rows = self.listed()
        self.assertEqual({sid: (row["agent"], row["certainty"]) for sid, row in rows.items()},
                         {"verified": ("ChatGPT agent", "verified"), "declared": ("Claude in Chrome", "likely"),
                          "network": (None, None), "tool": ("Playwright", "likely"), "unnamed": (None, None),
                          "bot": ("Googlebot", "likely"), "human": (None, None)})

    def test_counts_split_agent_sessions_by_turns(self):
        self.put("a1", verdict_class="agent", agent_row="ai")
        self.put("a2", verdict_class="agent", agent_row="automated")
        self.put("m1", verdict_class="mixed", agent_row="ai")
        self.put("h1", verdict_class="human")
        self.put("b1", verdict_class="bot")
        self.put("u1", verdict_class="too_little_data")
        self.assertEqual(visits.counts(self.con, visits.Scope()),
                         {"all": 6, "human": 2, "agent": 3, "bot": 1, "agent_only": 2, "human_agent": 1, "thin": 1})

    def test_the_thin_evidence_filter_keeps_the_human_sessions_cake_could_not_tell(self):
        self.put("h1", verdict_class="human")
        self.put("u1", verdict_class="too_little_data")
        self.put("u2", verdict_class="not_sure")
        scope = visits.Scope().group("human").group("thin")
        self.assertEqual((sorted(self.listed(scope)), visits.total(self.con, scope)), (["u1", "u2"], 2))

    def test_the_split_and_the_agent_filters_combine(self):
        self.put("a1", verdict_class="agent", agent_row="ai", verdict_detail={"display_name": "Comet"})
        self.put("m1", verdict_class="mixed", agent_row="ai", verdict_detail={"display_name": "Comet"})
        self.put("m2", verdict_class="mixed", agent_row="ai", verdict_detail={"display_name": "Claude in Chrome"})
        scope = visits.Scope().group("human_agent").agent("Comet")
        self.assertEqual((list(self.listed(scope)), visits.total(self.con, scope)), (["m1"], 1))


class Shares(Visits):
    def test_the_share_counts_the_actions_its_page_lists_and_adds_up_to_100(self):
        self.put("thirds", verdict_class="mixed", agent_row="ai", human_pct=10, agent_pct=80, unsure_pct=10)
        self.runs("thirds", (T0, T0 + 2_000, "human", 9), (T0 + 3_000, T0 + 5_000, "agent", 9),
                  (T0 + 6_000, T0 + 8_000, "unsure", 9))
        streams.append(self.con, "thirds", "raw", [(t, {"t": t, "ty": "click"}) for t in (T0 + 1_000, T0 + 4_000,
                                                                                            T0 + 7_000)], NOW)
        self.assertEqual(self.listed()["thirds"]["share"], {"human": 34, "agent": 33, "unsure": 33})

    def test_a_session_without_actions_has_no_share(self):
        self.put("little", verdict_class="too_little_data", human_pct=0, agent_pct=0, unsure_pct=100)
        self.assertEqual(self.listed()["little"]["share"], {"human": 0, "agent": 0, "unsure": 0})

    def test_no_share_when_the_behaviour_model_did_not_run(self):
        self.put("bot", verdict_class="bot", human_pct=0, agent_pct=0, unsure_pct=100)
        self.put("silent", verdict_class="human", layers={"behavior": {"state": "off", "why": "no_events"}},
                 unsure_pct=100)
        rows = self.listed()
        for sid in ("bot", "silent"):
            self.assertEqual(rows[sid]["share"], {"human": 0, "agent": 0, "unsure": 0}, sid)


class Lengths(Visits):
    def test_from_the_first_recorded_event_to_the_last_action(self):
        self.put("kept", verdict_class="human", first_action_ms=T0 + 500, last_action_ms=T0 + 96_900)
        streams.append(self.con, "kept", "raw", [(T0 + 100, {"t": T0 + 100, "ty": "click"})], NOW)
        self.assertEqual(self.listed()["kept"]["duration_ms"], 96_800)
        self.assertEqual(visits.recording(self.con, "kept"), (T0 + 100, 96_800))

    def test_a_replay_event_after_the_last_action_counts_as_the_player_shows_it(self):
        self.put("idle", verdict_class="human", first_action_ms=T0 + 500, last_action_ms=T0 + 20_000)
        streams.append(self.con, "idle", "rrweb", [(T0 + 100, {"type": 4, "timestamp": T0 + 100}),
                                                   (T0 + 45_100, {"type": 3, "timestamp": T0 + 45_100})], NOW)
        self.assertEqual(self.listed()["idle"]["duration_ms"], 45_000)

    def test_judged_before_the_span_was_kept_to_the_last_replay_event(self):
        self.put("older", verdict_class="human")
        streams.append(self.con, "older", "rrweb", [(T0 + 100, {"type": 4, "timestamp": T0 + 100}),
                                                    (T0 + 9_100, {"type": 3, "timestamp": T0 + 9_100})], NOW)
        self.assertEqual(self.listed()["older"]["duration_ms"], 9_000)

    def test_a_mixed_rows_segments_count_from_the_recordings_start_and_stay_inside_its_length(self):
        self.put("mixed", verdict_class="mixed", agent_row="ai", first_action_ms=T0, last_action_ms=T0 + 60_000)
        self.runs("mixed", (T0 - 500, T0 + 20_000, "human", 5), (T0 + 21_000, T0 + 65_000, "agent", 9))
        row = self.listed()["mixed"]
        self.assertEqual(row["segments"], [{"who": "human", "start_ms": 0, "end_ms": 20_000},
                                           {"who": "agent", "start_ms": 21_000, "end_ms": 65_000}])
        self.assertEqual(row["duration_ms"], 65_000)

    def test_a_row_with_runs_carries_its_segments_and_one_without_none(self):
        self.put("agent", verdict_class="agent", agent_row="ai")
        self.runs("agent", (T0, T0 + 10, "agent", 3))
        self.put("quiet", verdict_class="human")
        rows = self.listed()
        self.assertEqual(rows["agent"]["segments"], [{"who": "agent", "start_ms": 0, "end_ms": 10}])
        self.assertNotIn("segments", rows["quiet"])


class PagesAndOrder(Visits):
    def test_pages_are_the_pages_its_page_lists_and_a_034_visit_is_one(self):
        self.put("three-pages", verdict_class="human")
        for pv, seq, url in (("pv1", 0, "https://shop.example/"), ("pv1", 1, "https://shop.example/"),
                             ("pv1", 2, "https://shop.example/?q=shirt"), ("pv2", 0, "https://shop.example/cart")):
            self.con.execute("INSERT INTO batches(session_id, pv, seq, recv_ms, t, url, n_rrweb, n_raw, n_env) "
                             "VALUES('three-pages', ?, ?, ?, ?, ?, 0, 0, 0)", (pv, seq, T0, T0 + seq, url))
        self.put("old", verdict="human")
        rows = self.listed()
        self.assertEqual((rows["three-pages"]["pages"], rows["old"]["pages"]), (3, 1))

    def test_newest_first_and_the_next_page_starts_after_the_last_row(self):
        for n in range(5):
            self.put(f"s{n}", start=T0 + n * 1000, verdict_class="human")
        self.put("tie", start=T0 + 3000, verdict_class="human")
        first, keys = visits.page(self.con, visits.Scope(), 3, NOW, MACHINE)
        self.assertEqual([row["id"] for row in first], ["s4", "tie", "s3"])
        self.put("newer", start=T0 + 9000, verdict_class="human")  # arrives between the two pages
        second, _ = visits.page(self.con, visits.Scope().before(keys[-1]), 3, NOW, MACHINE)
        self.assertEqual([row["id"] for row in second], ["s2", "s1", "s0"])


class WholePercents(unittest.TestCase):
    def test_largest_remainders_and_nothing(self):
        self.assertEqual(visits.whole_percents([1, 1, 1]), [34, 33, 33])
        self.assertEqual(visits.whole_percents([2, 1, 0]), [67, 33, 0])
        self.assertEqual(visits.whole_percents([0, 0, 0]), [0, 0, 0])

    def test_a_page_is_its_path_and_query(self):
        self.assertEqual(visits.page_path("http://127.0.0.1:7878/demo/product?id=classic-tee#reviews"),
                         "/demo/product?id=classic-tee")
        self.assertEqual(visits.page_path("https://shop.example"), "/")


if __name__ == "__main__":
    unittest.main()
