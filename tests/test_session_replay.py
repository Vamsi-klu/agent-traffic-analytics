"""A session's rrweb replay for cake 0.3.4's judge and replay page: agentcake/session_replay.py.

    python3 -I -m unittest discover -s tests -p test_session_replay.py -v      (from the Agent Cake folder)

Since 0.4.0 collect keeps rrweb events in chunks; a cake 0.3.4 database still has replay rows, which `agentcake
migrate` copies into chunks and keeps. Every event is read once, in time order: chunks only, rows only, rows and
their copies, and a visit that went on across the upgrade (rows, then newer chunks).
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import session_replay, store, streams  # noqa: E402

BASE = 1794517500000


def event(ts, n):
    return json.dumps({"type": 3, "data": {"source": 1, "n": n}, "timestamp": ts})


class Replay(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.rows = [(BASE + (i // 2) * 100, event(BASE + (i // 2) * 100, i)) for i in range(10)]  # pairs share a ms

    def add_rows(self, rows, sid="s1"):
        self.con.executemany("INSERT INTO events VALUES(?,?,?)", [(sid, ts, body) for ts, body in rows])

    def add_chunks(self, items, sid="s1", seal=False):
        streams.append(self.con, sid, "rrweb", items, BASE)
        if seal:
            streams.seal(self.con, BASE, force=True, session_id=sid)
        self.con.commit()

    def texts(self, sid="s1"):
        return list(session_replay.rrweb_texts(self.con, sid))

    def test_chunks_only(self):
        items = [(BASE + i, event(BASE + i, i), "pv1") for i in range(5)]
        self.add_chunks(items)
        self.assertEqual(self.texts(), [text for _, text, _ in items])

    def test_0_3_4_rows_only_in_the_order_they_were_written(self):
        self.add_rows(self.rows)
        self.add_rows([(BASE, '{"kind": "pageview", "url": "/"}')])  # a small event, not replay
        self.assertEqual(self.texts(), [body for _, body in self.rows])

    def test_rows_and_their_copies_are_read_once(self):
        self.add_rows(self.rows)
        self.add_chunks(self.rows, seal=True)  # what migrate does
        self.assertEqual(self.texts(), [body for _, body in self.rows])

    def test_a_visit_that_went_on_after_the_upgrade(self):
        self.add_rows(self.rows)
        newer = [(BASE + 5000 + i, event(BASE + 5000 + i, 100 + i), "pv9") for i in range(3)]
        self.add_chunks(newer)
        want = [body for _, body in self.rows] + [text for _, text, _ in newer]
        self.assertEqual(self.texts(), want, "before migrate: rows, then the newer chunks")
        self.add_chunks(session_replay.missing_rows(self.con, "s1"), seal=True)
        self.assertEqual(self.texts(), want, "after migrate copied the rows: still once each")

    def test_missing_rows_counts_identical_rows_one_by_one(self):
        twice = [(BASE, event(BASE, 0)), (BASE, event(BASE, 0)), (BASE + 1, event(BASE + 1, 1))]
        self.add_rows(twice)
        self.assertEqual(session_replay.missing_rows(self.con, "s1"), twice)
        self.add_chunks(twice[:1])
        self.assertEqual(session_replay.missing_rows(self.con, "s1"), twice[1:])

    def test_other_sessions_rows_are_not_read(self):
        self.add_rows(self.rows, sid="other")
        self.assertEqual(self.texts(), [])


if __name__ == "__main__":
    unittest.main()
