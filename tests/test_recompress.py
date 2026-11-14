"""Night work on replay chunks (S2.2): agentcake/recompress.py.

    python3 -I -m unittest discover -s tests -p test_recompress.py -v      (from the cake folder)

A session whose chunks are older than recompress_after_days becomes one chunk per stream at the archive level and
reads back exactly as before; younger and still-open sessions are left alone; reclaim() deletes files nothing points
into, moves the live chunks out of mostly-dead files, and drops stylesheets no chunk uses.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import codecs, recompress, replay_chunks, store, streams  # noqa: E402
from agentcake.storage_config import SETTINGS, ms_from_days  # noqa: E402

BASE = 1794517500000  # 2026-11-12 21:05 UTC
DAY = ms_from_days(1)
OLD = BASE - 15 * DAY
CSS = ".hero{background:linear-gradient(#fff,#eee)}" * 40


def fresh_db():
    os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
    return store.db()


def snapshot(ts, n):
    node = {"type": 0, "childNodes": [{"type": 2, "tagName": "style", "attributes": {"_cssText": CSS},
                                       "childNodes": []}, {"type": 3, "textContent": f"page {n}", "id": 3}]}
    return json.dumps({"type": 2, "data": {"node": node}, "timestamp": ts})


def record(con, sid, at, seconds=60):
    """A visit of `seconds` recorded at `at`: a snapshot every 20 s, mouse moves, raw input; sealed at the end."""
    rr = [(at + ms, snapshot(at + ms, ms) if ms % 20_000 == 0 else json.dumps(
        {"type": 3, "data": {"source": 1, "positions": [{"x": ms % 977, "y": ms % 613}]}, "timestamp": at + ms}))
        for ms in range(0, seconds * 1000, 100)]
    raw = [(at + ms, {"t": at + ms + 0.5, "ty": "mousemove", "x": ms % 977, "y": ms % 613, "tr": True})
           for ms in range(0, seconds * 1000, 50)]
    streams.append(con, sid, "rrweb", rr, at)
    streams.append(con, sid, "raw", raw, at)
    streams.seal(con, at + seconds * 1000, force=True)
    con.commit()


def everything(con, sid):
    return list(streams.read_events(con, sid))


class Recompress(unittest.TestCase):
    def setUp(self):
        self.con = fresh_db()
        self.addCleanup(self.con.close)

    def test_old_sessions_become_one_archive_chunk_per_stream_and_read_the_same(self):
        record(self.con, "old", OLD)
        record(self.con, "young", BASE - DAY)
        before = {sid: everything(self.con, sid) for sid in ("old", "young")}
        young_chunks = self.con.execute("SELECT id FROM chunks WHERE session_id='young' ORDER BY id").fetchall()
        old_bytes = streams.replay_bytes(self.con, "old")
        self.assertEqual(recompress.run(BASE), 1)
        rows = self.con.execute("SELECT stream, level, archived, n_events FROM chunks WHERE session_id='old' ORDER BY stream").fetchall()
        codec = codecs.writer_codec()
        archive = SETTINGS["levels"][codec]["archive"]
        self.assertEqual(rows, [("raw", archive, 1, 1200), ("rrweb", archive, 1, 600)])
        self.assertLess(streams.replay_bytes(self.con, "old"), old_bytes)
        self.assertEqual(self.con.execute("SELECT id FROM chunks WHERE session_id='young' ORDER BY id").fetchall(), young_chunks)
        for sid, events in before.items():
            self.assertEqual(everything(self.con, sid), events, sid)
        self.assertEqual(recompress.run(BASE), 0, "nothing left to do")

    def test_page_views_survive_the_archive(self):
        events = [(OLD + ms, json.dumps({"type": 3, "timestamp": OLD + ms}), f"pv{ms // 20_000}")
                  for ms in range(0, 60_000, 500)]
        streams.append(self.con, "old", "rrweb", events, OLD)
        streams.seal(self.con, OLD + 60_000, force=True)
        self.con.commit()
        self.assertEqual(recompress.run(BASE), 1)
        self.assertEqual(list(streams.read_events(self.con, "old", with_page=True)),
                         [(ts, "rrweb", text, page) for ts, text, page in events])

    def test_a_session_still_being_recorded_waits(self):
        record(self.con, "old", OLD)
        streams.append(self.con, "old", "raw", [(BASE, {"t": BASE, "ty": "click"})], BASE)
        self.con.commit()
        self.assertEqual(recompress.run(BASE), 0)

    def test_without_zstd_the_archive_is_zlib_at_its_archive_level(self):
        with mock.patch.object(codecs, "ZSTD", None):
            record(self.con, "old", OLD)
            before = everything(self.con, "old")
            recompress.run(BASE)
            levels = {r for r in self.con.execute("SELECT codec, level FROM chunks WHERE session_id='old'")}
            self.assertEqual(levels, {("zlib", SETTINGS["levels"]["zlib"]["archive"])})
            self.assertEqual(everything(self.con, "old"), before)


class Reclaim(unittest.TestCase):
    def setUp(self):
        self.con = fresh_db()
        self.addCleanup(self.con.close)
        self.root = replay_chunks.replay_dir()

    def files(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.root) for d, _, fs in os.walk(self.root) for f in fs)

    def test_files_left_dead_by_recompression_are_deleted(self):
        record(self.con, "old", OLD)
        old_file = replay_chunks.file_for(OLD)
        recompress.run(BASE)
        result = recompress.reclaim(self.con, BASE)
        self.assertEqual(result["deleted"], 1)
        self.assertNotIn(old_file, self.files())
        self.assertEqual(self.files(), [replay_chunks.file_for(BASE)])
        self.assertEqual(len(everything(self.con, "old")), 1800)

    def test_a_mostly_dead_file_is_rewritten_with_only_its_live_chunks(self):
        record(self.con, "keep", OLD, seconds=20)
        record(self.con, "drop", OLD, seconds=120)
        keep = everything(self.con, "keep")
        size = os.path.getsize(os.path.join(self.root, replay_chunks.file_for(OLD)))
        streams.drop_replay(self.con, "drop", SETTINGS["streams"])  # every stream of it: most of the file is dead
        self.con.commit()
        result = recompress.reclaim(self.con, BASE)
        self.assertEqual(result["compacted"], 1)
        self.assertEqual(self.files(), [replay_chunks.file_for(BASE)])
        self.assertLess(os.path.getsize(os.path.join(self.root, replay_chunks.file_for(BASE))), size / 2)
        self.assertEqual(everything(self.con, "keep"), keep)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM styles").fetchone()[0], 1, "keep still uses it")
        streams.drop_replay(self.con, "keep")
        self.con.commit()
        recompress.reclaim(self.con, BASE)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM styles").fetchone()[0], 0)

    def test_the_file_of_the_current_hour_is_left_for_later(self):
        record(self.con, "now", BASE)
        streams.drop_replay(self.con, "now", SETTINGS["streams"])  # every stream of it: the whole file is dead
        self.con.commit()
        self.assertEqual(recompress.reclaim(self.con, BASE)["deleted"], 0)
        self.assertEqual(recompress.reclaim(self.con, BASE + DAY)["deleted"], 1)

    def test_uncommitted_drops_are_refused(self):
        record(self.con, "a", OLD)
        streams.drop_replay(self.con, "a")
        with self.assertRaises(RuntimeError):
            recompress.reclaim(self.con, BASE)


if __name__ == "__main__":
    unittest.main()
