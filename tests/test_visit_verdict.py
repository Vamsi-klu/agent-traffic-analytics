"""A visit's verdict, merged from the verdicts of its tab sessions: agentcake/visit_verdict.py.

    python3 -I -m unittest discover -s tests -p test_visit_verdict.py -v

Each tab session is judged on its own; a visit (the tabs of one browser, a session as the dashboard counts it) is
Agent once a tab has an agent, Human + agent when a human tab with enough evidence or a Human + agent tab is in it too,
Human when its tabs are human (a tab on thin evidence counts for nothing next to one with enough), Human on thin
evidence when every tab is, and Script bot only when every tab is one. A prefetch, a self-check and an upload from
another site count for nothing. The class is the one a tab session holds, so a visit of one tab reads exactly as that
tab did; the order of the tabs does not matter. Judging a tab merges its visit again.

A tab in Muse's own cloud browser with only human-looking actions is judged Agent (its runs the agent's), so tabs of
it are an Agent visit; beside a tab with a human's own evidence the visit is Human + agent, and its page marks the
hand-off from one tab to the other (api/session_tabs.py), which it could not while that tab's runs read human.
"""
import itertools
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_api_tabs as two_tabs  # noqa: E402  (a session of two tabs, its verdicts as a judge left them)
import visit_rows  # noqa: E402
from test_judging import KEY, SID, T0, S, JudgingCase, clicks, visit_batch  # noqa: E402
from verdict_cases import CHROME_LINUX, HUMAN_RUN, behavior, evidence, hit, run  # noqa: E402
from agentcake import config, judging, store, visit_verdict  # noqa: E402
from agentcake.api import visits  # noqa: E402
from agentcake.detect import verdict  # noqa: E402
from agentcake.visit_verdict import merge, tab_class  # noqa: E402

HUMAN, AGENT, MIXED, BOT = "human", "agent", "mixed", "bot"
NOT_SURE, TOO_LITTLE, UNSURE, EXCLUDED, NEVER = "not_sure", "too_little_data", "unsure", "excluded", None
EVERY_CLASS = (HUMAN, AGENT, MIXED, BOT, NOT_SURE, TOO_LITTLE, UNSURE, EXCLUDED, NEVER)
OLD_VERDICTS = ("human", "agent", "unsure")  # what cake 0.3.4's verdict column holds
VISIT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def read(verdict_class, old_verdict=None):
    """How the pages read a class: the verdict, an Agent's split, thin evidence (api/visits.py)."""
    return (visits.verdict_of(verdict_class, old_verdict), visits.turns_of(verdict_class, old_verdict),
            visits.evidence_of(verdict_class, old_verdict))


def muse_tab(human_run=HUMAN_RUN):
    """A tab session in Muse's own cloud browser with only human-looking actions, judged (verdict.py)."""
    return verdict.decide(evidence(uas=CHROME_LINUX, platform="Linux x86_64", hits=[hit("env.product.muse")],
                                   behavior_result=behavior("human", human_run)))


class Merge(unittest.TestCase):
    def test_a_visit_of_one_tab_reads_as_that_tab(self):
        for cls in EVERY_CLASS:
            self.assertEqual(merge([cls]), cls)
            self.assertEqual(read(merge([cls])), read(cls), cls)
        for old in OLD_VERDICTS:
            self.assertEqual(read(merge([tab_class(None, old)])), read(None, old), old)

    def test_human_tabs_are_human(self):
        self.assertEqual(merge([HUMAN, HUMAN]), HUMAN)

    def test_a_tab_on_thin_evidence_counts_for_nothing_next_to_a_human_one(self):
        self.assertEqual(merge([TOO_LITTLE, HUMAN, NOT_SURE, NEVER, UNSURE]), HUMAN)

    def test_tabs_all_on_thin_evidence_are_human_on_thin_evidence(self):
        self.assertEqual(merge([TOO_LITTLE, TOO_LITTLE]), TOO_LITTLE)
        self.assertEqual(merge([TOO_LITTLE, NOT_SURE]), NOT_SURE, "classes that differ: not sure")
        self.assertEqual(read(merge([TOO_LITTLE, NEVER])), ("human", None, "thin"))

    def test_tabs_never_judged_are_a_visit_never_judged(self):
        self.assertIsNone(merge([NEVER, NEVER]))

    def test_an_agent_tab_makes_the_visit_agent(self):
        self.assertEqual(merge([AGENT, AGENT]), AGENT)
        self.assertEqual(read(merge([AGENT, AGENT])), ("agent", "agent_only", None))

    def test_human_tabs_on_thin_evidence_leave_an_agent_visit_agent_only(self):
        self.assertEqual(merge([TOO_LITTLE, AGENT, NOT_SURE, NEVER]), AGENT)

    def test_a_human_tab_with_enough_evidence_and_an_agent_tab_are_human_plus_agent(self):
        self.assertEqual(merge([HUMAN, AGENT]), MIXED)
        self.assertEqual(read(merge([HUMAN, AGENT])), ("agent", "human_agent", None))

    def test_a_tab_where_a_human_and_an_agent_took_turns_makes_the_visit_human_plus_agent(self):
        self.assertEqual(merge([AGENT, MIXED, TOO_LITTLE]), MIXED)

    def test_script_bot_tabs_decide_only_when_every_tab_is_one(self):
        self.assertEqual(merge([BOT, BOT]), BOT)
        self.assertEqual(merge([BOT, HUMAN]), HUMAN)
        self.assertEqual(merge([BOT, AGENT]), AGENT)
        self.assertEqual(merge([BOT, TOO_LITTLE]), TOO_LITTLE)
        self.assertIsNone(merge([BOT, NEVER]), "a tab not judged yet reads as Human on thin evidence")

    def test_a_prefetch_counts_for_nothing_and_a_visit_of_nothing_else_is_no_session(self):
        self.assertEqual(merge([EXCLUDED, HUMAN]), HUMAN)
        self.assertEqual(merge([EXCLUDED, EXCLUDED]), EXCLUDED)
        self.assertEqual(merge([]), EXCLUDED)
        self.assertIsNone(visits.verdict_of(merge([]), None), "the pages list no such visit")

    def test_cake_0_3_4_verdicts_merge_as_the_classes_they_read_as(self):
        self.assertEqual(merge([tab_class(None, "agent"), tab_class(None, "human")]), MIXED)
        self.assertEqual(merge([tab_class(None, "unsure"), tab_class(None, "unsure")]), UNSURE)
        self.assertEqual(tab_class(HUMAN, "agent"), HUMAN, "a class of its own comes first")
        self.assertIsNone(tab_class(None, None))

    def test_the_order_of_the_tabs_does_not_matter(self):
        tabs = (TOO_LITTLE, AGENT, BOT, EXCLUDED, NOT_SURE)
        self.assertEqual({merge(order) for order in itertools.permutations(tabs)}, {AGENT})
        tabs = (TOO_LITTLE, NOT_SURE, BOT, NEVER)
        self.assertEqual({merge(order) for order in itertools.permutations(tabs)}, {NOT_SURE})


class CloudBrowserTabs(unittest.TestCase):
    def test_tabs_of_muse_with_human_looking_actions_only_are_an_agent_visit(self):
        muse = muse_tab()["class"]
        self.assertEqual(muse, AGENT, "each tab on its own")
        self.assertEqual((merge([muse, muse]), merge([muse, NOT_SURE])), (AGENT, AGENT))
        self.assertEqual(read(merge([muse, muse])), ("agent", "agent_only", None))

    def test_a_muse_tab_beside_a_human_tab_is_human_plus_agent(self):
        self.assertEqual(merge([muse_tab()["class"], HUMAN]), MIXED)


class CloudBrowserTabOnThePage(two_tabs.TabsCase):
    def test_the_hand_off_from_a_human_tab_to_a_muse_tab_is_marked_between_them(self):
        self.two_tabs()  # a human's tab, then a second tab from 5 s to 65 s
        tab = muse_tab(run("human", 5, 65, 15, 0.08))
        self.con.execute("DELETE FROM segments WHERE session_id=?", (two_tabs.SECOND,))
        self.judged(two_tabs.SECOND, tab["class"], {key: tab[key] for key in judging.DETAIL},
                    runs=[(segment["start"], segment["end"], segment["who"]) for segment in tab["segments"]])
        visit_rows.joined(self.con, two_tabs.VISIT, [(two_tabs.FIRST, "w1"), (two_tabs.SECOND, "w2")])
        detail = self.get(f"/api/session/{two_tabs.VISIT}", "session")
        self.assertEqual((detail["session"]["verdict"], detail["session"]["agent_turns"]), ("agent", "human_agent"))
        self.assertEqual(detail["timeline"]["handoffs"], [{"at_ms": 5 * S, "to": "agent"}])
        self.assertEqual(detail["title"], "A human, then Muse")


class Remerge(unittest.TestCase):
    """remerge() reads the tabs of a visit from the database: the ones that count, and writes the class."""

    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-visit-verdict-test-")
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.con.execute("INSERT INTO visits(id, joined_by, created_ms) VALUES(?,?,?)", (VISIT, "collector", T0))
        self.tabs = 0

    def tab(self, verdict_class, old_verdict=None, is_test=0, origin="site"):
        self.tabs += 1
        session_id = f"{self.tabs:032x}"
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms, verdict_class, verdict, is_test, origin) "
                         "VALUES(?,?,?,?,?,?,?)", (session_id, T0, T0, verdict_class, old_verdict, is_test, origin))
        self.con.execute("INSERT INTO session_web(session_id, tab_id, visit_id) VALUES(?,?,?)",
                         (session_id, session_id, VISIT))
        return session_id

    def written(self):
        return self.con.execute("SELECT verdict_class FROM visits WHERE id=?", (VISIT,)).fetchone()[0]

    def test_the_merged_class_is_written(self):
        self.tab(HUMAN)
        self.tab(AGENT)
        self.assertEqual(visit_verdict.remerge(self.con, VISIT), MIXED)
        self.assertEqual(self.written(), MIXED)

    def test_a_cake_0_3_4_verdict_is_read_where_a_tab_has_no_class(self):
        self.tab(None, "agent")
        self.assertEqual(visit_verdict.remerge(self.con, VISIT), AGENT)

    def test_a_self_check_and_an_upload_from_another_site_count_for_nothing(self):
        self.tab(HUMAN, is_test=1)
        self.tab(HUMAN, origin="other")
        self.tab(AGENT)
        self.assertEqual(visit_verdict.remerge(self.con, VISIT), AGENT)

    def test_a_visit_of_self_checks_only_is_no_session(self):
        self.tab(HUMAN, is_test=1)
        self.assertEqual(visit_verdict.remerge(self.con, VISIT), EXCLUDED)

    def test_a_tab_in_no_visit_changes_no_visit(self):
        session_id = self.tab(AGENT)
        self.con.execute("UPDATE session_web SET visit_id=NULL WHERE session_id=?", (session_id,))
        visit_verdict.remerge_tab(self.con, session_id)
        self.assertIsNone(self.written())


class JudgingATabMergesItsVisit(JudgingCase):
    def test_a_tabs_new_verdict_is_merged_into_its_visit(self):
        config.save_user(site_key=KEY, disk_min_free_mb=0, judge_interval_ms=0)
        self.post(visit_batch(0, T0, clicks(4, T0)), T0)
        self.con.execute("INSERT OR IGNORE INTO visits(id, joined_by, created_ms) VALUES(?,?,?)",
                         (VISIT, "collector", T0))
        self.con.execute("UPDATE session_web SET visit_id=? WHERE session_id=?", (VISIT, SID))
        self.con.commit()
        judging.rejudge(self.con, SID, T0)
        tab = self.con.execute("SELECT verdict_class FROM sessions WHERE id=?", (SID,)).fetchone()[0]
        self.assertIsNotNone(tab)
        self.assertEqual(self.con.execute("SELECT verdict_class FROM visits WHERE id=?", (VISIT,)).fetchone()[0], tab)


if __name__ == "__main__":
    unittest.main()
