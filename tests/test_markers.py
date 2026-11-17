"""Agent products' marks on the page and when each was there (threshold A5): agentcake/detect/markers.py.

    python3 -I -m unittest discover -s tests -p test_markers.py -v      (from the AgentCake folder)

The mark table (agentcake/data/agent_markers.json) is checked when it is loaded; cake.js gets its page part; a page
view's `marker` records become spans (when each mark was there), and a span reads as a reason's words. cake.js's
records go through collect into the database and come back to env_signals as spans; a page view whose watch did not
run reads as unknown. The browser half (cake.js noting the marks in Chromium) is tests/browser/test_markers.py.
"""
import copy
import http.client
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import collect, config, evidence, store, visit_batches  # noqa: E402
from agentcake.detect import env_signals, markers  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from tools import build_js  # noqa: E402

TABLE = markers.load_table()
WORKING, COMET, WAITING = "claude-chrome.working", "comet.overlay", "claude-chrome.waiting"
START_MS = 1794518371000.0  # when the visit began (epoch ms)
KEY = "ck_markers_test"


def raw_table():
    with open(markers.TABLE_FILE, encoding="utf-8") as f:
        return json.load(f)


def watch(t, **fields):
    return {"t": t, "ty": "markers", "why": "start", "list": TABLE.version, "every_ms": TABLE.page["every_ms"],
            **fields}


def mark(t, marker, on):
    return {"t": t, "ty": "marker", "m": marker, "on": on}


def at(seconds):
    return START_MS + seconds * 1000


class Table(unittest.TestCase):
    def test_a_marks_reason_says_when_the_mark_was_shown_not_that_the_agent_was_active(self):
        """The session page's summary says when the agent was active from its actions (api.en.json summary.acted);
        a mark's reason gives the mark's own time, which runs on after the last action, so it never says it in the
        summary's words: one page would give two times for the same words."""
        with open(os.path.join(HERE, "agentcake", "data", "api.en.json"), encoding="utf-8") as f:
            acted = json.load(f)["summary"]["acted"]
        summary_words = acted.split("{who}", 1)[1].split("{start}", 1)[0]  # " was active from "
        span = TABLE.spans["closed"].format(**{"from": "0:28", "to": "1:19"})
        for marker, meta in raw_table()["markers"].items():
            with self.subTest(marker):
                self.assertNotIn(summary_words, " " + meta["text"].format(span=span))

    def test_the_shipped_table_loads(self):
        self.assertEqual(set(TABLE.markers), {m["id"] for m in TABLE.page["markers"]} | set(TABLE.recorder.values()))
        self.assertIn(WORKING, TABLE.markers)

    def test_cake_js_gets_the_page_part(self):
        self.assertEqual(build_js.script_settings(build_js.load_config())["markers"], raw_table()["page"])

    def broken(self, change):
        data = raw_table()
        change(data)
        with self.assertRaises(markers.MarkersError):
            markers.parse_table(data)

    def test_a_mark_without_its_description_is_refused(self):
        self.broken(lambda data: data["markers"].pop(COMET))

    def test_a_mark_listed_twice_is_refused(self):
        self.broken(lambda data: data["page"]["markers"].append(copy.deepcopy(data["page"]["markers"][0])))

    def test_a_mark_with_both_spots_and_a_selector_is_refused(self):
        self.broken(lambda data: data["page"]["markers"][0].update(selector="#x"))

    def test_a_spot_needs_one_edge(self):
        self.broken(lambda data: data["page"]["markers"][0]["spots"][0].update(bottom=1))

    def test_an_unknown_grade_kind_or_source_is_refused(self):
        self.broken(lambda data: data["markers"][WORKING].update(grade="rumour"))
        self.broken(lambda data: data["markers"][WORKING].update(kind="sometimes"))
        self.broken(lambda data: data["markers"][WORKING].update(sources=["a blog"]))

    def test_a_text_without_its_span_is_refused(self):
        self.broken(lambda data: data["markers"][WAITING].update(text="Claude in Chrome was waiting"))

    def test_a_turn_kinds_mark_with_a_time_is_refused(self):
        self.broken(lambda data: data["markers"][WORKING].update(text="Claude in Chrome was active {span}"))

    def test_a_selector_reading_an_attribute_the_watch_does_not_follow_is_refused(self):
        # cake.js matches selectors again only on changes of page.attributes: an attribute missing there would be missed
        def change(data):
            comet = next(m for m in data["page"]["markers"] if m["id"] == COMET)
            comet["selector"] = "[data-new-agent]"
        self.broken(change)


class Words(unittest.TestCase):
    def test_the_words_of_a_mark_call_a_visitor_human_or_agent_only(self):
        # as tests/test_verdict_text.py checks reasons.json: a mark's text becomes a reason's
        forbidden = re.compile(r"\b(?:person|people|visitors?)\b|\busers?\b(?!-agent)", re.IGNORECASE)
        for text in [meta["text"] for meta in TABLE.markers.values()] + list(TABLE.spans.values()):
            with self.subTest(text=text):
                self.assertIsNone(forbidden.search(text))


class PageMarks(unittest.TestCase):
    def test_a_page_view_without_the_watch_is_not_known(self):
        self.assertIsNone(markers.page_marks([{"t": at(0), "ty": "page", "n": 1}, mark(at(1), WORKING, 1)]))

    def test_a_watched_page_view_without_marks_has_no_spans(self):
        self.assertEqual(markers.page_marks([watch(at(1))], until=at(9)),
                         {"list": TABLE.version, "from": at(1), "until": at(9), "hidden": [], "spans": []})

    def test_marks_shown_and_gone_become_spans_in_order(self):
        records = [mark(at(76), WORKING, 0), watch(at(1)), mark(at(42), WORKING, 1), mark(at(90), COMET, 1),
                   mark(at(95), COMET, 0)]
        spans = markers.page_marks(records)["spans"]
        self.assertEqual(spans, [
            {"marker": WORKING, "product": "claude-chrome", "kind": "indicator", "from": at(42), "to": at(76)},
            {"marker": COMET, "product": "comet", "kind": "indicator", "from": at(90), "to": at(95)}])

    def test_a_mark_still_there_at_the_end_has_no_end(self):
        spans = markers.page_marks([watch(at(1)), mark(at(42), WORKING, 1)])["spans"]
        self.assertEqual([(span["from"], span["to"]) for span in spans], [(at(42), None)])

    def test_a_repeated_state_changes_nothing(self):
        records = [watch(at(1)), mark(at(5), WORKING, 0), mark(at(10), WORKING, 1), mark(at(10), WORKING, 1),
                   mark(at(20), WORKING, 0), mark(at(21), WORKING, 0)]
        spans = markers.page_marks(records)["spans"]
        self.assertEqual([(span["from"], span["to"]) for span in spans], [(at(10), at(20))])

    def test_the_times_the_page_was_hidden_are_kept(self):
        raw = [{"t": at(10), "ty": "visibility", "vs": 0}, {"t": at(20), "ty": "visibility", "vs": 1},
               {"t": at(30), "ty": "visibility", "vs": 0}, {"t": at(31), "ty": "click"}]
        marks = markers.page_marks([watch(at(1))], raw=raw, until=at(40))
        self.assertEqual(marks["hidden"], [[at(10), at(20)], [at(30), at(40)]])

    def test_a_mark_the_table_does_not_list_is_kept_without_a_product(self):
        spans = markers.page_marks([watch(at(1)), mark(at(2), "new-agent.badge", 1)])["spans"]
        self.assertEqual(spans, [{"marker": "new-agent.badge", "product": None, "kind": None, "from": at(2),
                                  "to": None}])


def overlay(t, on):
    return {"t": t, "ty": "overlay", "on": on, "vs": 1}


class Recorder(unittest.TestCase):
    """The recorder's raw.js checks Claude in Chrome's indicator itself (`overlay` items): read as its own mark."""

    def test_its_overlay_items_are_the_recorders_mark(self):
        items = [{"t": at(0), "ty": "geo"}, overlay(at(5), 1), overlay(at(9), 0), {"t": at(12), "ty": "click"}]
        marks = markers.recorder_marks(items)
        self.assertEqual((marks["list"], marks["from"], marks["until"]), ("recorder", at(0), at(12)))
        self.assertEqual([(s["marker"], s["kind"], s["from"], s["to"]) for s in marks["spans"]],
                         [("claude-chrome.recorder", "indicator", at(5), at(9))])

    def test_a_page_without_overlay_items_is_not_known(self):
        self.assertIsNone(markers.recorder_marks([{"t": at(0), "ty": "click"}]))


def page(spans, until=None, hidden=()):
    return {"markers": {"list": TABLE.version, "from": at(0), "until": until, "hidden": [list(h) for h in hidden],
                        "spans": spans}}


def span(marker, start, end):
    meta = TABLE.markers.get(marker, {})
    return {"marker": marker, "product": meta.get("product"), "kind": meta.get("kind"), "from": start, "to": end}


class TurnSpans(unittest.TestCase):
    def test_only_the_kinds_that_bound_the_agents_turn(self):
        spans = [span(WORKING, at(1), at(2)), span("claude-chrome.waiting", at(3), at(4)),
                 span("claude-chrome.bottom", at(3), at(4)), span("claude-chrome.styles", at(1), None)]
        signals = {"pages": [page(spans, until=at(9))]}
        self.assertEqual([(s["marker"], s["from"], s["to"]) for s in markers.turn_spans(signals)],
                         [(WORKING, at(1), at(2))])

    def test_a_span_still_open_at_the_end_closes_with_its_page_view(self):
        signals = {"pages": [page([span(WORKING, at(5), None)], until=at(8)), page([span(COMET, at(9), at(10))])]}
        self.assertEqual([(s["from"], s["to"]) for s in markers.turn_spans(signals)],
                         [(at(5), at(8)), (at(9), at(10))])

    def test_the_times_the_page_was_hidden_are_cut_out(self):
        hidden = [(at(3), at(5)), (at(8), None)]
        signals = {"pages": [page([span(WORKING, at(0), at(10))], until=at(20), hidden=hidden)]}
        self.assertEqual([(s["from"], s["to"]) for s in markers.turn_spans(signals)], [(at(0), at(3)), (at(5), at(8))])

    def test_pages_not_watched_give_none(self):
        self.assertEqual(markers.turn_spans({"pages": [{"path": "/"}, page([])]}), [])

    def test_a_span_says_whether_its_mark_went_off_while_the_page_view_went_on(self):
        hidden = [(at(3), at(5))]
        signals = {"pages": [page([span(WORKING, at(0), at(10)), span(WORKING, at(12), None)], until=at(20),
                                  hidden=hidden)]}
        self.assertEqual([(s["from"], s["to"], s["went_off"]) for s in markers.turn_spans(signals)],
                         [(at(0), at(3), False), (at(5), at(10), True), (at(12), at(20), False)])

    def test_a_mark_that_went_off_while_the_page_was_hidden_did_not_go_off_in_sight(self):
        signals = {"pages": [page([span(WORKING, at(0), at(10))], until=at(20), hidden=[(at(8), None)])]}
        self.assertEqual([(s["to"], s["went_off"]) for s in markers.turn_spans(signals)], [(at(8), False)])


class Describe(unittest.TestCase):
    def test_a_span_reads_with_times_from_the_visits_start(self):
        span = {"marker": WAITING, "from": at(42), "to": at(75)}
        self.assertEqual(markers.describe(span, START_MS),
                         "Claude in Chrome was waiting for human input from 0:42 to 1:15")
        self.assertEqual(markers.words(WAITING, 42000, 75000, "detail"),
                         "Claude in Chrome's waiting indicator appears on the screen from 0:42 to 1:15.")

    def test_a_span_without_an_end_says_from_when(self):
        span = {"marker": WAITING, "from": at(42.9), "to": None}
        self.assertEqual(markers.describe(span, START_MS), "Claude in Chrome was waiting for human input from 0:42 onward")

    def test_a_turn_kinds_mark_is_named_without_its_times(self):
        """The reason names the indicator and gives no time: the summary says when the agent was active."""
        self.assertEqual(markers.words(WORKING, 42000, 75000), "Claude in Chrome's working indicator")
        self.assertEqual(markers.words(WORKING, 42000, None, "detail"),
                         "Claude in Chrome shows its “working” indicator on the screen while it works.")

    def test_the_clock_writes_a_moment_as_the_player_does(self):
        """m:ss under an hour and h:mm:ss past it, whole seconds rounded down (web/src/lib/format.ts clock)."""
        self.assertEqual(markers.clock(47_927), "0:47")
        self.assertEqual(markers.clock(96_400), "1:36")
        self.assertEqual(markers.clock(3723 * 1000), "1:02:03")
        self.assertEqual(markers.clock(-5), "0:00")


def batch(seq, x, pv="pv-1"):
    return {"v": 1, "k": KEY, "s": "5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5", "pv": pv, "seq": seq, "t": at(seq),
            "u": "https://shop.example.com/demo", "why": "timer", "ua": "Mozilla/5.0", "wd": False, "e": [], "r": [],
            "x": x}


class Signals(unittest.TestCase):
    def test_env_signals_gives_each_page_views_spans(self):
        visit = [batch(0, [{"t": at(0), "ty": "page", "n": 1}, watch(at(1))]),
                 batch(1, [mark(at(42), WORKING, 1), mark(at(75), WORKING, 0)]),
                 batch(0, [{"t": at(80), "ty": "page", "n": 2}], pv="pv-2")]
        first, second = env_signals.from_cake(visit)["pages"]
        self.assertEqual(first["markers"]["spans"][0]["from"], at(42))
        self.assertNotIn("markers", second, "no watch on that page view: not known")

    def test_the_labs_recordings_have_no_marks(self):
        payload = {"kind": "load", "page": "/", "snap": {"env": {}}}
        self.assertNotIn("markers", env_signals.from_lab([payload])["pages"][0])

    def test_the_recorders_check_of_the_indicator_is_read_from_its_raw_items(self):
        items = [{"t": at(0), "ty": "geo"}, overlay(at(5), 1), overlay(at(9), 0)]
        payloads = [{"kind": "meta", "page": "/demo", "items": []}, {"kind": "raw", "page": "/demo", "items": items}]
        page_signals = env_signals.from_lab(payloads)["pages"][0]
        self.assertEqual(page_signals["markers"]["spans"][0]["marker"], "claude-chrome.recorder")

    def test_cake_js_page_views_close_their_marks_with_their_last_record(self):
        visit = [batch(0, [watch(at(1)), mark(at(42), WORKING, 1)]),
                 dict(batch(1, [{"t": at(60), "ty": "leave", "why": "pagehide"}]),
                      r=[{"t": at(50), "ty": "visibility", "vs": 0, "hf": 0}])]
        marks = env_signals.from_cake(visit)["pages"][0]["markers"]
        self.assertEqual((marks["until"], marks["hidden"]), (at(60), [[at(50), at(60)]]))
        self.assertEqual([(s["from"], s["to"]) for s in markers.turn_spans(env_signals.from_cake(visit))],
                         [(at(42), at(50))])


class ThroughCollect(unittest.TestCase):
    """What collect keeps of the records comes back to env_signals as the same spans."""

    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, sent):
        body = json.dumps(sent, separators=(",", ":"), ensure_ascii=False).encode()
        answer = collect.from_local(Request("/collect", {}, http.client.HTTPMessage(), body))
        self.assertEqual(answer.status, 204, answer.body)

    def test_the_marks_come_back_from_the_database(self):
        visit = [batch(0, [{"t": at(0), "ty": "page", "n": 1}, watch(at(1))]),
                 batch(1, [mark(at(42), WORKING, 1), mark(at(75), WORKING, 0), mark(at(80), COMET, 1)]),
                 batch(2, [{"t": at(90), "ty": "markers", "why": "exit", "looks": 356, "ms": 12.5,
                            "longest_ms": 0.4}])]
        for sent in visit:
            self.post(sent)
        stored = visit_batches.batches(self.con, visit[0]["s"])
        self.assertEqual(env_signals.from_cake(stored)["pages"][0]["markers"],
                         env_signals.from_cake(visit)["pages"][0]["markers"])
        spans = env_signals.from_cake(stored)["pages"][0]["markers"]["spans"]
        self.assertEqual([(s["marker"], s["from"], s["to"]) for s in spans],
                         [(WORKING, at(42), at(75)), (COMET, at(80), None)])
        built, _, _ = evidence.session_evidence(self.con, visit[0]["s"])
        self.assertEqual([(s["marker"], s["from"], s["to"]) for s in built["marks"]],
                         [(WORKING, at(42), at(75)), (COMET, at(80), at(90))])  # Comet's: closed at the last record
        self.assertIn("env.product.claude-chrome-indicator", [hit.rule for hit in built["env"].hits])


if __name__ == "__main__":
    unittest.main()
