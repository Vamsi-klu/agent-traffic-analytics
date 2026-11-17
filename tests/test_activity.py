"""agentcake/activity.py: when a session's recorded actions began and ended.

    python3 -I -m unittest discover -s tests -p test_activity.py -v      (from the AgentCake folder)

A session's length runs from its first to its last recorded action: a page opened, or the visitor's pointer, keys,
wheel or touch. Focus, visibility, window geometry, elements added to the page and the page leaving are not actions,
so a tab left open after the last action adds nothing. A cake 0.3.x recording (rrweb only) gives its page metas and
interactions. judging.py keeps the span with each verdict.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import activity, config, judging, store, streams  # noqa: E402

T0 = 1_794_520_000_000
HOUR = 3_600_000


def raw(t, ty, **fields):
    return {"t": t, "ty": ty, **fields}


class Span(unittest.TestCase):
    def test_from_the_first_page_to_the_last_input(self):
        records = [raw(T0 + 400, "pointermove", cx=1, cy=1), raw(T0 + 900, "click"), raw(T0 + 5_250.6, "keydown")]
        self.assertEqual(activity.span(records, None, [T0]), (T0, T0 + 5_251))

    def test_a_tab_left_open_after_the_last_action_adds_nothing(self):
        records = [raw(T0 + 900, "click"), raw(T0 + HOUR, "visibility", vs=0), raw(T0 + HOUR, "winblur"),
                   raw(T0 + HOUR + 5, "geo", g=[1]), raw(T0 + HOUR + 9, "dom_add", tag="DIV")]
        self.assertEqual(activity.span(records, None, [T0]), (T0, T0 + 900))

    def test_a_later_page_opened_without_input_still_counts(self):
        self.assertEqual(activity.span([raw(T0 + 900, "click")], None, [T0, T0 + 7_000]), (T0, T0 + 7_000))

    def test_a_cake_03_recording_gives_its_page_metas_and_interactions(self):
        rrweb = [{"type": 4, "timestamp": T0, "data": {"href": "http://127.0.0.1:7878/demo"}},
                 {"type": 2, "timestamp": T0 + 10, "data": {}},
                 {"type": 3, "timestamp": T0 + 2_000, "data": {"source": 2, "type": 2, "id": 7, "x": 5, "y": 5}},
                 {"type": 3, "timestamp": T0 + 9_000, "data": {"source": 0, "adds": [], "removes": []}}]
        self.assertEqual(activity.span([], rrweb, []), (T0, T0 + 2_000), "a page mutation is not an action")

    def test_nothing_recorded_is_no_span(self):
        self.assertEqual(activity.span([], None, []), (None, None))


class KeptWithTheVerdict(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_activity", disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def test_page_starts_are_the_page_records_of_the_signals_stream(self):
        streams.append(self.con, "s1", "env", [(T0, json.dumps({"t": T0, "ty": "page", "n": 1})),
                                               (T0 + 5, json.dumps({"t": T0 + 5, "ty": "env", "env": {}})),
                                               (T0 + 8_000, json.dumps({"t": T0 + 8_000.4, "ty": "page", "n": 2})),
                                               (T0 + 9_000, json.dumps({"t": T0 + 9_000, "ty": "leave"}))], T0)
        self.assertEqual(activity.page_starts(self.con, "s1"), [T0, T0 + 8_000])

    def test_judging_writes_the_first_and_last_action_into_the_session(self):
        self.con.execute("INSERT INTO sessions(id, start_ms, end_ms) VALUES('s1', ?, ?)", (T0, T0 + HOUR))
        streams.append(self.con, "s1", "env", [(T0, json.dumps({"t": T0, "ty": "page", "n": 1}))], T0)
        streams.append(self.con, "s1", "raw", [(T0 + 900, json.dumps(raw(T0 + 900, "click"))),
                                               (T0 + HOUR, json.dumps(raw(T0 + HOUR, "winblur")))], T0)
        judging.rejudge(self.con, "s1", T0 + HOUR)
        self.assertEqual(self.con.execute("SELECT first_action_ms, last_action_ms FROM sessions WHERE id='s1'")
                         .fetchone(), (T0, T0 + 900))


if __name__ == "__main__":
    unittest.main()
