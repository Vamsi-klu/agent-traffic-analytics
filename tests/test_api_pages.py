"""The pages of a session in GET /api/session/<id> (agentcake/api/pages.py): in the order they opened, the first
the entry page and the last the exit page, each with when it opened, how long the visit stayed, its actions and who
took them.

    python3 -I -m unittest discover -s tests -p test_api_pages.py -v      (from the AgentCake folder)

Sessions are written into a scratch CAKE_HOME the way collect and judging.py leave them: cake.js's page records in the
signals stream, its raw input, a batch row per upload with the page's address then (batches.url), the verdict's
segments. A page view is a page; a single-page app's new address is a new page from the first batch that carries it;
a session with nothing to go by has one page, its own address. A page lasts until the next one opens, the last one
until the session's end. Who acted on a page is named as the session categories name it: a human, an agent
only, both (human_agent), unknown; a page without actions takes who acted when it opened. A cake 0.3.x recording's pages are its rrweb
Meta events. The counts hold every action, not only the ones "All actions" lists. The fixed test library's recorded
sessions answer the contract with pages that add up.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from agentcake import config, judging, store, streams  # noqa: E402
from agentcake.api import actions, answers  # noqa: E402

T0 = 1_794_600_000_000
SITE = "https://shop.example"
OPEN = "Open "


def page(path, at_ms, duration_ms, n_actions, who):
    return {"path": path, "at_ms": at_ms, "duration_ms": duration_ms, "actions": n_actions, "who": who}


class Recorded(unittest.TestCase):
    """Sessions written into a scratch CAKE_HOME and asked for through the local listener's view."""

    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_pages", disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.client = Client()

    def record(self, sid, verdict_class, views=(), inputs=(), runs=(), last_ms=None, url=None):
        """views: (pv, page record time or None, [(batch time, address)]); inputs: (time, raw type, pv);
        runs: (start, end, actor). The session's last action is last_ms (default: its last input)."""
        times = [t for _, start, batches in views for t in [start] + [b for b, _ in batches] if t is not None]
        last = last_ms if last_ms is not None else max([t for t, _, _ in inputs] + times + [T0])
        for pv, start, batches in views:
            if start is not None:
                streams.append(self.con, sid, "env", [(start, {"t": start, "ty": "page", "n": 1}, pv)], last)
            for seq, (t, address) in enumerate(batches):
                self.con.execute("INSERT INTO batches(session_id, pv, seq, recv_ms, t, url, why, n_rrweb, n_raw, n_env) "
                                 "VALUES(?, ?, ?, ?, ?, ?, 'timer', 0, 0, 0)", (sid, pv, seq, t, t, SITE + address))
        if inputs:
            streams.append(self.con, sid, "raw", [(t, {"t": t, "ty": ty, "s": "#target"}, pv) for t, ty, pv in inputs],
                           last)
        self.con.executemany("INSERT INTO segments(session_id, t_start, t_end, actor) VALUES(?, ?, ?, ?)",
                             [(sid, *run) for run in runs])
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms, url, origin, is_test, verdict_class, judged_ms, "
                         "first_action_ms, last_action_ms, model_version) VALUES(?, ?, ?, ?, 'site', 0, ?, ?, ?, ?, ?)",
                         (sid, T0, last, url and SITE + url, verdict_class, last, T0, last, judging.model_version()))
        self.con.commit()

    def detail(self, sid):
        answer = self.client.get(f"/api/session/{sid}")
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "session"), [])
        return answer.body

    def pages(self, sid):
        return self.detail(sid)["pages"]


class PageViews(Recorded):
    def test_each_page_view_is_a_page_in_the_order_it_opened(self):
        self.record("shop", "human",
                    views=[("pv1", T0, [(T0 + 300, "/")]), ("pv2", T0 + 6_000, [(T0 + 6_300, "/item?id=7")]),
                           ("pv3", T0 + 15_000, [(T0 + 15_300, "/cart")])],
                    inputs=[(T0 + 1_000, "click", "pv1"), (T0 + 4_000, "click", "pv1"), (T0 + 9_000, "input", "pv2"),
                            (T0 + 17_000, "click", "pv3"), (T0 + 20_000, "wheel", "pv3")],
                    runs=[(T0, T0 + 20_000, "human")])
        pages = self.pages("shop")
        self.assertEqual(pages, [page("/", 0, 6_000, 2, "human"), page("/item?id=7", 6_000, 9_000, 1, "human"),
                                 page("/cart", 15_000, 5_000, 2, "human")])
        self.assertEqual((pages[0]["path"], pages[-1]["path"]), ("/", "/cart"), "entry page, exit page")

    def test_one_page_lasts_the_whole_session(self):
        self.record("one", "human", views=[("pv1", T0, [(T0 + 500, "/landing?ref=mail")])],
                    inputs=[(T0 + 2_000, "click", "pv1"), (T0 + 5_000, "click", "pv1"), (T0 + 8_000, "click", "pv1")])
        self.assertEqual(self.pages("one"), [page("/landing?ref=mail", 0, 8_000, 3, "human")])

    def test_a_visit_with_nothing_to_go_by_is_one_page_its_own_address(self):
        self.record("old", "human", last_ms=T0 + 4_000, url="/hello?ref=mail")
        self.assertEqual(self.pages("old"), [page("/hello?ref=mail", 0, 4_000, 0, None)])

    def test_a_page_view_whose_record_never_came_starts_at_its_first_action(self):
        self.record("lab", "agent", views=[("pv1", None, [(T0 + 3_000, "/form")]), ("pv2", None, [(T0 + 9_000, "/done")])],
                    inputs=[(T0 + 1_000, "click", "pv1"), (T0 + 2_500, "click", "pv1"), (T0 + 7_000, "click", "pv2")],
                    last_ms=T0 + 9_000)
        self.assertEqual(self.pages("lab"), [page("/form", 0, 6_000, 2, "agent"), page("/done", 6_000, 2_000, 1, "agent")])


class SinglePageApp(Recorded):
    def test_a_new_address_is_a_new_page_from_the_first_batch_that_carries_it(self):
        self.record("spa", "human",
                    views=[("pv1", T0, [(T0 + 2_000, "/app"), (T0 + 4_000, "/app"), (T0 + 6_000, "/app/cart"),
                                        (T0 + 8_000, "/app/cart"), (T0 + 10_000, "/app?tab=2")])],
                    inputs=[(T0 + 1_000, "click", "pv1"), (T0 + 5_000, "click", "pv1"), (T0 + 7_000, "click", "pv1"),
                            (T0 + 9_000, "click", "pv1"), (T0 + 11_000, "click", "pv1")],
                    last_ms=T0 + 12_000)
        body = self.detail("spa")
        self.assertEqual(body["pages"], [page("/app", 0, 6_000, 2, "human"), page("/app/cart", 6_000, 4_000, 2, "human"),
                                         page("/app?tab=2", 10_000, 2_000, 1, "human")])
        listed = {action["at_ms"]: action for action in body["actions"]}
        self.assertEqual(listed[0]["what"], OPEN + "/app")
        self.assertEqual([listed[ms]["page"] for ms in (5_000, 7_000, 11_000)], ["/app", "/app/cart", "/app?tab=2"],
                         "every action names the page it was taken on")


class WhoActed(Recorded):
    def test_a_page_without_actions_names_nobody(self):
        self.record("browsing", "agent", views=[("pv1", T0, [(T0 + 200, "/search")]),
                                                ("pv2", T0 + 3_000, [(T0 + 3_200, "/item")])],
                    inputs=[(T0 + 4_000, "click", "pv2"), (T0 + 5_000, "click", "pv2")])
        self.assertEqual(self.pages("browsing"), [page("/search", 0, 3_000, 0, None),
                                                  page("/item", 3_000, 2_000, 2, "agent")])

    def test_a_human_agent_sessions_pages_say_who_acted_on_each(self):
        self.record("turns", "mixed",
                    views=[("pv1", T0, [(T0 + 100, "/a")]), ("pv2", T0 + 8_000, [(T0 + 8_100, "/b")]),
                           ("pv3", T0 + 16_000, [(T0 + 16_100, "/c")]), ("pv4", T0 + 26_000, [(T0 + 26_100, "/d")])],
                    inputs=[(T0 + 2_000, "click", "pv1"), (T0 + 5_000, "click", "pv1"), (T0 + 9_000, "click", "pv2"),
                            (T0 + 12_000, "click", "pv2"), (T0 + 14_000, "click", "pv2"), (T0 + 17_000, "click", "pv3"),
                            (T0 + 20_000, "click", "pv3"), (T0 + 27_000, "click", "pv4")],
                    runs=[(T0, T0 + 9_500, "human"), (T0 + 11_000, T0 + 21_000, "agent")])
        self.assertEqual(self.pages("turns"), [page("/a", 0, 8_000, 2, "human"), page("/b", 8_000, 8_000, 3, "human_agent"),
                                               page("/c", 16_000, 10_000, 2, "agent"),
                                               page("/d", 26_000, 1_000, 1, "unknown")])


class Recordings(Recorded):
    def test_a_cake_03_recordings_pages_are_its_meta_events(self):
        rrweb = [{"type": 4, "timestamp": T0, "data": {"href": SITE + "/demo"}},
                 {"type": 3, "timestamp": T0 + 2_000, "data": {"source": 2, "type": 2, "id": 7, "x": 5, "y": 5}},
                 {"type": 4, "timestamp": T0 + 5_000, "data": {"href": SITE + "/demo/cart"}},
                 {"type": 3, "timestamp": T0 + 7_000, "data": {"source": 2, "type": 2, "id": 9, "x": 5, "y": 5}}]
        streams.append(self.con, "old-replay", "rrweb", [(event["timestamp"], event) for event in rrweb], T0 + 7_000)
        self.record("old-replay", "human", last_ms=T0 + 7_000)
        self.assertEqual(self.pages("old-replay"), [page("/demo", 0, 5_000, 1, "human"),
                                                    page("/demo/cart", 5_000, 2_000, 1, "human")])

    def test_the_counts_hold_every_action_not_only_the_ones_listed(self):
        self.record("long", "human", views=[("pv1", T0, [(T0 + 100, "/")])],
                    inputs=[(T0 + 2_000 * n, "click", "pv1") for n in range(1, 6)])
        few = dict(answers.numbers(), max_actions=2)
        with mock.patch.object(actions, "numbers", lambda: few):
            body = self.detail("long")
        self.assertEqual(len(body["actions"]), 2)
        self.assertEqual(body["pages"][0]["actions"], 5)


if __name__ == "__main__":
    unittest.main()
