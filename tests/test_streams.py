"""A session's recorded streams: agentcake/streams.py.

    python3 -I -m unittest discover -s tests -p test_streams.py -v      (from the cake folder)

Batches of events go in as cake.js sends them (every 2-10 s, several streams); they come out again in time order,
byte for byte, whether still in an open 10-second window or already sealed into a compressed chunk file; a session's
replay can be dropped while its session, server-half and segment rows stay.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import replay_chunks, store, streams  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402

BASE = 1794517500000  # 2026-11-12 21:05:00 UTC, a multiple of the 10 s chunk length
SECOND = 1000


def fresh_db():
    os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
    return store.db()


def rr(ts, i):
    """An rrweb-like event as JSON text (Python's default separators, like 0.3.4's collect wrote them)."""
    return json.dumps({"type": 3, "data": {"source": 1, "positions": [{"x": i, "y": i, "id": 4, "timeOffset": 0}]},
                       "timestamp": ts})


def raw(ts, i):
    return json.dumps({"t": ts + 0.25, "ty": "pointermove", "x": i, "y": 2 * i, "tr": 1}, separators=(",", ":"))


def batch(start_s, end_s, make=rr, step_ms=250):
    return [(BASE + ms, make(BASE + ms, ms)) for ms in range(start_s * SECOND, end_s * SECOND, step_ms)]


class AppendAndRead(unittest.TestCase):
    def setUp(self):
        self.con = fresh_db()
        self.addCleanup(self.con.close)

    def put(self, items, stream="rrweb", sid="s1", now=None):
        streams.append(self.con, sid, stream, items, now or BASE + 60 * SECOND)
        self.con.commit()

    def texts(self, sid="s1", **kw):
        return [t for _, _, t in streams.read_events(self.con, sid, **kw)]

    def test_events_come_back_in_order_byte_for_byte_before_and_after_sealing(self):
        sent = []
        for a in range(0, 35, 5):  # seven batches of 5 s, like cake.js sends them
            items = batch(a, a + 5)
            sent += items
            self.put(items)
        self.assertEqual(self.texts(), [t for _, t in sent], "readable while windows are still open")
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        self.con.commit()
        self.assertEqual(self.texts(), [t for _, t in sent], "and after they are sealed into chunks")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM open_chunks").fetchone()[0], 0)
        rows = self.con.execute("SELECT t_start, t_end, n_events, codec, level FROM chunks ORDER BY t_start").fetchall()
        self.assertEqual(len(rows), 4, "35 s of events in 10-second chunks")
        for (t0, t1, n, codec, level), k in zip(rows, range(len(rows))):
            self.assertGreaterEqual(t0, BASE + k * SETTINGS["chunk_ms"])
            self.assertLess(t1, BASE + (k + 1) * SETTINGS["chunk_ms"])
            self.assertEqual(level, SETTINGS["levels"][codec]["live"])

    def test_a_window_is_sealed_once_later_events_arrive(self):
        self.put(batch(0, 10))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], 0)
        lag_s = (SETTINGS["chunk_ms"] + SETTINGS["seal_lag_ms"]) // SECOND
        self.put(batch(lag_s, lag_s + 1))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], 1)

    def test_quiet_windows_are_sealed_and_recent_ones_wait(self):
        self.put(batch(0, 3), sid="quiet", now=BASE)
        self.put(batch(0, 3), sid="busy", now=BASE + SETTINGS["seal_idle_ms"])
        streams.seal(self.con, BASE + SETTINGS["seal_idle_ms"])
        self.assertEqual([r[0] for r in self.con.execute("SELECT DISTINCT session_id FROM chunks")], ["quiet"])
        self.assertEqual([r[0] for r in self.con.execute("SELECT session_id FROM open_chunks")], ["busy"])

    def test_late_and_shuffled_events_still_come_back_in_time_order(self):
        early, late = batch(0, 20), batch(20, 40)
        self.put(late)
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        self.put(list(reversed(early)))
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        self.assertEqual(self.texts(), [t for _, t in early + late])

    def test_a_window_still_open_reads_in_time_order_too(self):
        """cake.js's raw records of one batch are not always in time order (a focus event's time can be earlier
        than the pointerup sent before it): an open window reads oldest first, as the sealed chunk will."""
        items = [(BASE + 300, raw(BASE + 300, 1)), (BASE + 100, raw(BASE + 100, 2)), (BASE + 300, raw(BASE + 300, 3)),
                 (BASE + 200, raw(BASE + 200, 4))]
        want = [items[1][1], items[3][1], items[0][1], items[2][1]]  # by time; equal times in the order they came
        self.put(items, "raw")
        self.assertEqual(self.texts(streams=["raw"]), want, "open")
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        self.assertEqual(self.texts(streams=["raw"]), want, "sealed")

    def test_equal_times_keep_the_order_they_arrived_in(self):
        same = [(BASE, json.dumps({"n": i})) for i in range(50)]
        self.put(same[:25])
        self.put(same[25:])
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        self.assertEqual(self.texts(), [t for _, t in same])

    def test_streams_are_merged_by_time_or_read_alone(self):
        a, b = batch(0, 30, rr, 700), batch(0, 30, raw, 300)
        self.put(a, "rrweb")
        self.put(b, "raw")
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        got = list(streams.read_events(self.con, "s1", ["rrweb", "raw"]))
        self.assertEqual([ts for ts, _, _ in got], sorted(ts for ts, _ in a + b))
        self.assertEqual(sorted(t for _, _, t in got), sorted(t for _, t in a + b))
        self.assertEqual(self.texts(streams=["raw"]), [t for _, t in b])
        self.assertEqual({s for _, s, _ in got}, {"rrweb", "raw"})

    def test_a_time_range_reads_only_that_range(self):
        items = batch(0, 40)
        self.put(items)
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        lo, hi = BASE + 12 * SECOND, BASE + 27 * SECOND
        self.assertEqual(self.texts(t_from=lo, t_to=hi), [t for ts, t in items if lo <= ts <= hi])

    def test_reading_is_streamed_one_chunk_at_a_time(self):
        self.put(batch(0, 60))
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        real = replay_chunks.read_chunk
        with mock.patch.object(replay_chunks, "read_chunk", side_effect=real) as spy:
            events = streams.read_events(self.con, "s1")
            next(events)
            self.assertEqual(spy.call_count, 1, "the first event needs only the first chunk")
            list(events)
            self.assertEqual(spy.call_count, 6)

    def test_each_event_keeps_its_page_view_open_sealed_and_counted(self):
        """Two tabs of one visit (cake.js page views) interleave in time; each event comes back with its own page
        view, and an event appended without one (0.3.4's rows, a 0.3.4 batch) comes back with None."""
        tabs = [(ts, text, "pvA" if n % 3 else "pvB") for n, (ts, text) in enumerate(batch(0, 25))]
        self.put(tabs[:40])
        self.put(tabs[40:])
        self.put([(BASE + 26 * SECOND, rr(BASE + 26 * SECOND, 0))])
        want = [(ts, "rrweb", text, page) for ts, text, page in tabs] + \
               [(BASE + 26 * SECOND, "rrweb", rr(BASE + 26 * SECOND, 0), None)]
        self.assertEqual(list(streams.read_events(self.con, "s1", with_page=True)), want, "open windows")
        self.assertEqual(streams.event_count(self.con, "s1", "rrweb"), len(want))
        streams.seal(self.con, BASE + 120 * SECOND, force=True)
        self.con.commit()
        self.assertEqual(list(streams.read_events(self.con, "s1", with_page=True)), want, "sealed chunks")
        self.assertEqual(self.texts(), [text for _, _, text, _ in want], "without with_page: (ts, stream, text)")
        self.assertEqual([page for *_, page in streams.stored_lines(self.con, "s1", "rrweb", with_page=True)],
                         [page for *_, page in want])
        self.assertEqual(streams.event_count(self.con, "s1", "rrweb"), len(want), "sealed and open alike")
        self.assertEqual(streams.event_count(self.con, "s1", "raw"), 0)

    def test_dict_events_are_stored_as_compact_json(self):
        self.put([(BASE, {"type": 4, "data": {"href": "https://example.com/é"}})])
        self.assertEqual(self.texts(), ['{"type":4,"data":{"href":"https://example.com/é"}}'])

    def test_unknown_streams_and_multi_line_text_are_refused(self):
        with self.assertRaises(ValueError):
            streams.append(self.con, "s1", "keys", [(BASE, "{}")], BASE)
        with self.assertRaises(ValueError):
            streams.append(self.con, "s1", "rrweb", [(BASE, '{"a":\n1}')], BASE)

    def test_the_chunk_length_comes_from_the_settings(self):
        half = dict(SETTINGS, chunk_ms=SETTINGS["chunk_ms"] // 2)
        streams.append(self.con, "s1", "rrweb", batch(0, 40), BASE, cfg=half)
        streams.seal(self.con, BASE + 120 * SECOND, force=True, cfg=half)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], 8)


class DropReplay(unittest.TestCase):
    """The disk rules' interface: a replay removed to free space; what the session was judged by and from stays."""

    def test_the_replay_goes_and_the_session_raw_input_server_half_and_segments_stay(self):
        con = fresh_db()
        self.addCleanup(con.close)
        con.execute("INSERT INTO sessions(id, start_ms, end_ms, verdict) VALUES('s1', ?, ?, 'human')", (BASE, BASE))
        con.execute("INSERT INTO srv(id, session_id, recv_ms, page_ms, path, body, net_match) VALUES('tok-1', 's1', ?, ?, '/', '{}', 1)", (BASE, BASE))
        con.execute("INSERT INTO segments(session_id, t_start, t_end, actor) VALUES('s1', ?, ?, 'human')", (BASE, BASE))
        con.execute("INSERT INTO events VALUES('s1', ?, ?)", (BASE, rr(BASE, 0)))  # a 0.3.4 replay row
        con.execute("INSERT INTO events VALUES('s1', ?, ?)", (BASE, '{"kind": "pageview", "url": "/"}'))
        streams.append(con, "s1", "rrweb", batch(0, 25), BASE)
        streams.seal(con, BASE + 120 * SECOND, force=True)
        streams.append(con, "s1", "raw", batch(30, 32, raw), BASE)  # still open
        streams.append(con, "s2", "rrweb", batch(0, 5), BASE)
        con.commit()
        stored = streams.replay_bytes(con, "s1")
        self.assertGreater(stored, 0)
        self.assertEqual(streams.drop_replay(con, "s1"), stored + len(rr(BASE, 0)))
        con.commit()
        self.assertEqual(list(streams.read_events(con, "s1", ["rrweb"])), [])
        self.assertEqual([t for _, _, t in streams.read_events(con, "s1")], [t for _, t in batch(30, 32, raw)],
                         "the raw input stays: verdicts are made from it")
        for table in ("sessions WHERE id='s1'", "srv WHERE session_id='s1'", "segments WHERE session_id='s1'",
                      "events WHERE session_id='s1'"):  # the small pageview event stays, the replay row went
            self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1, table)
        self.assertEqual(len(list(streams.read_events(con, "s2"))), len(batch(0, 5)), "other sessions untouched")
        raw_bytes = streams.replay_bytes(con, "s1", SETTINGS["streams"])
        self.assertEqual(streams.drop_replay(con, "s1", SETTINGS["streams"]), raw_bytes, "named streams go too")
        self.assertEqual(list(streams.read_events(con, "s1")), [])


if __name__ == "__main__":
    unittest.main()
