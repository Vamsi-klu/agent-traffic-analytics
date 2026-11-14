"""Agent Cake's disk rules on the chunk storage (S2.5): cake 0.3.4's eight space tests, rewritten for replays kept as
chunks without loosening any of their assertions, and the rules S2.5 adds.

    python3 -I -m unittest discover -s tests -p test_space.py -v      (from the Agent Cake folder)

Each test runs in its own CAKE_HOME. Sessions of every kind are mixed together, each with a replay (the rrweb stream)
plus raw input and environment signals, sealed into chunk files, and the budget is made tiny, so cake is "full"; then:
only the oldest human-only sessions lose their replay, down to 90% of the budget; their raw input, environment
signals, verdicts, shares, timelines and server-half rows stay, and no session an agent took part in loses anything.
With auto_free off a full cake still records the visit and its verdict but stores no new replay events. Nothing is
deleted by age by default; a chosen retention deletes whole old sessions, chunks included. With less free disk than
disk_min_free_mb new replays stop and nothing is freed (the disk is a stand-in for shutil.disk_usage: nothing is
filled). Dropped chunks give their file bytes back at the next maintenance round.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config, recompress, replay_chunks, space, streams  # noqa: E402  (needs the path above)
from api_client import Client  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402
from space_sessions import (DAY, MB, RAW_EVENTS, ROOMY, add_mix, add_session, chunk_file_bytes,  # noqa: E402
                            disk_with, fresh_cake, recorded, replay)

HUMANS = ["human1", "human2", "human3", "human4"]  # the human-only sessions, oldest first
KEPT = ("agent1", "agent2", "mixed1", "mixed2", "unsure1", "named1", "humanLive")
SERVER_POLL_S = 0.01  # how often a test server's loop checks for shutdown(); each tearDown waited out the default 0.5 s
# The storage settings with the night recompression at the live level: for a test of what recompression does to the
# rows, not of how small zstd-19 makes them (tests/test_recompress.py checks that); level 19 takes seconds here.
LIVE_LEVEL_ARCHIVES = dict(SETTINGS, levels={codec: dict(levels, archive=levels["live"])
                                             for codec, levels in SETTINGS["levels"].items()})


class Space(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The sessions are recorded once, in a CAKE_HOME of their own, and every test works on a copy of it: sealing
        # eleven sessions into chunk files is most of what a test's setup costs.
        cls.cake, cls.recorded_home = fresh_cake()
        cls.addClassCleanup(shutil.rmtree, cls.recorded_home, True)
        cls.now = int(time.time() * 1000)
        con = cls.cake.db()
        add_mix(cls.cake, con, cls.now)  # space_sessions.MIX: every kind of session, oldest first
        con.commit()
        con.close()  # the last connection: its write-ahead log goes into cake.db, so the folder copies whole

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        shutil.copytree(self.recorded_home, self.home, dirs_exist_ok=True)
        os.environ["CAKE_HOME"] = self.home
        self.con = self.cake.db()
        self.addCleanup(self.con.close)
        self.used = self.cake.used_bytes(self.con)

    def events(self, sid):
        return replay(self.con, sid)

    def tiny(self, **kv):
        return dict(self.cake.load_cfg(), budget_mb=0.0001, **kv)  # impossible to reach

    def test_defaults_keep_everything(self):
        c = self.cake.load_cfg()
        self.assertEqual(c["retention_days"], 0)
        self.assertTrue(c["auto_free"])
        self.assertEqual(c["budget_mb"], 10240)
        self.assertEqual(c["disk_min_free_mb"], 10240, "K2: below 10 GB of free disk the oldest replays make room")
        everything = {sid: recorded(self.con, sid) for (sid,) in self.con.execute("SELECT id FROM sessions").fetchall()}
        self.cake.prune(self.con, c["retention_days"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 11, "nothing deleted by age by default")
        self.cake.prune(self.con, 30)  # an explicit 30 days still works
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 11, "all are under 30 days old")
        self.assertEqual({sid: recorded(self.con, sid) for sid in everything}, everything, "and every recorded event stays")

    def test_full_frees_only_oldest_person_only_replays(self):
        # a budget cake is over: about 60% of what it holds now, so freeing has to remove some but not all
        c = dict(self.cake.load_cfg(), budget_mb=self.used * 0.6 / MB)
        before = {sid: recorded(self.con, sid) for sid in KEPT}
        verdicts = dict(self.con.execute("SELECT id, verdict || '/' || agent_pct || '/' || segs FROM sessions"))
        freed = self.cake.free_space(self.con, c, self.now)
        self.con.commit()
        self.assertGreater(freed, 0)
        # oldest human-only first: human1 goes before human2, human2 before human3...
        gone = [s for s in HUMANS if self.events(s) == 0]
        self.assertEqual(gone, HUMANS[:len(gone)], "oldest first")
        self.assertTrue(gone)
        for sid, events in before.items():  # every stream, event for event
            self.assertEqual(recorded(self.con, sid), events, f"{sid}: never removed automatically")
        # verdicts, shares, timelines and server half all stay
        self.assertEqual(dict(self.con.execute("SELECT id, verdict || '/' || agent_pct || '/' || segs FROM sessions")), verdicts)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 11)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM srv WHERE session_id='human1'").fetchone()[0], 1)
        for sid in gone:
            self.assertIsNotNone(self.con.execute("SELECT replay_freed_ms FROM sessions WHERE id=?", (sid,)).fetchone()[0])
        # a later judgement does not overwrite the verdict of a removed replay with an empty one
        self.cake.rejudge(self.con, "human1", self.now)
        self.assertEqual(self.con.execute("SELECT verdict, segs FROM sessions WHERE id='human1'").fetchone()[0], "human")
        self.assertNotEqual(self.con.execute("SELECT segs FROM sessions WHERE id='human1'").fetchone()[0], "[]")

    def test_when_nothing_person_only_is_left_agent_sessions_still_stay(self):
        self.cake.free_space(self.con, self.tiny(), self.now)
        for sid in HUMANS:
            self.assertEqual(self.events(sid), 0)
        for sid in KEPT:
            self.assertEqual(self.events(sid), 60, sid)

    def test_status_and_meter(self):
        c = dict(self.cake.load_cfg(), budget_mb=self.used / 0.85 / MB)
        st = self.cake.space_status(self.con, c, self.now)
        self.assertTrue(st["warn"])
        self.assertFalse(st["full"])
        self.assertIsNotNone(st["days_left"])
        # the settings page draws the meter from /api/settings (S5.1): past the warning share, with days until full
        self.con.commit()
        for budget_mb, warns in ((c["budget_mb"], True), (self.used * 10 / MB, False)):
            config.save_user(budget_mb=budget_mb)
            storage = Client().get("/api/settings").body["storage"]
            self.assertEqual(storage["used_bytes"] >= storage["warn_at_pct"] / 100 * budget_mb * MB, warns)
            self.assertIsNotNone(storage["days_left"])

    def test_freeing_stops_at_the_target_share_of_the_budget(self):
        # full, and removing the two oldest human-only replays is just enough to get under 90% of the budget
        first, second = (streams.replay_bytes(self.con, sid) for sid in HUMANS[:2])
        c = dict(self.cake.load_cfg(), budget_mb=(self.used - first - second / 2) / 0.9 / MB)
        self.assertGreaterEqual(self.used, space.budget_bytes(c), "the budget is full")
        self.assertTrue(space.room_for_replay(self.con, c, self.now, usage=ROOMY))
        self.assertEqual([self.events(s) for s in HUMANS], [0, 0, 60, 60], "no more than needed")
        self.assertLessEqual(self.cake.used_bytes(self.con), c["auto_free_target_ratio"] * space.budget_bytes(c))

    def test_a_freed_session_keeps_its_raw_input_and_environment_signals(self):
        kept = {sid: recorded(self.con, sid, ["raw", "env"]) for sid in HUMANS}
        self.cake.free_space(self.con, self.tiny(), self.now)
        for sid in HUMANS:
            self.assertEqual(self.events(sid), 0)
            self.assertEqual(recorded(self.con, sid, ["raw", "env"]), kept[sid], f"{sid}: verdicts are made from these")

    def test_a_session_with_an_agent_stretch_or_an_agent_name_is_never_freed(self):
        # human-only by 0.3.4's columns, but the newer tables say an agent was there
        self.con.execute("INSERT INTO segments(session_id, t_start, t_end, actor) VALUES('human1', 1, 2, 'agent')")
        self.con.execute("INSERT INTO labels(session_id, name, layer) VALUES('human2', 'Operator', 'names')")
        self.con.execute("INSERT INTO segments(session_id, t_start, t_end, actor) VALUES('human3', 1, 2, 'unsure')")
        self.cake.free_space(self.con, self.tiny(), self.now)
        self.assertEqual([self.events(s) for s in HUMANS], [60, 60, 0, 0])

    def test_a_human_only_session_without_a_replay_is_not_marked_freed(self):
        add_session(self.cake, self.con, "noreplay", verdict="human", agent_pct=0, group="H1/L?", end_ms=self.now - 20 * DAY, n_events=0)
        self.cake.free_space(self.con, self.tiny(), self.now)
        self.assertIsNone(self.con.execute("SELECT replay_freed_ms FROM sessions WHERE id='noreplay'").fetchone()[0])
        self.assertEqual(len(recorded(self.con, "noreplay")), RAW_EVENTS + 1, "its raw input and signals stay")

    def test_used_counts_the_database_and_the_live_chunks(self):
        pragma = lambda name: self.con.execute(f"PRAGMA {name}").fetchone()[0]  # noqa: E731
        chunks = lambda: self.con.execute("SELECT SUM(byte_length) FROM chunks").fetchone()[0]  # noqa: E731
        total = lambda: self.con.execute("SELECT value FROM totals WHERE name='chunk_bytes'").fetchone()[0]  # noqa: E731
        db = (pragma("page_count") - pragma("freelist_count")) * pragma("page_size")
        self.assertEqual(self.used, db + chunks())
        # SQLite keeps the total, whoever writes the chunks: dropping, the night recompression, reclaim moving them
        streams.drop_replay(self.con, "human1")
        self.con.commit()
        self.assertEqual(recompress.run(self.now + 30 * DAY, LIVE_LEVEL_ARCHIVES), 11)
        recompress.reclaim(self.con, self.now + 30 * DAY)
        self.assertEqual(total(), chunks())
        # a database whose chunks are older than the total (set up by an older cake: another user_version) starts
        # from their sum
        for name in ("TABLE totals", "TRIGGER chunks_bytes_add", "TRIGGER chunks_bytes_drop", "TRIGGER chunks_bytes_resize"):
            self.con.execute(f"DROP {name}")
        self.con.execute("PRAGMA user_version = 0")
        add_session(self.cake, self.con, "late", verdict="agent", agent_pct=100, group="L?/V?", end_ms=self.now)
        self.con.commit()
        self.con = self.cake.db()
        self.addCleanup(self.con.close)
        self.assertEqual(total(), chunks())

    def test_the_files_give_back_the_bytes_of_freed_replays(self):
        on_disk, dropped = chunk_file_bytes(), sum(streams.replay_bytes(self.con, sid) for sid in HUMANS)
        raw = {sid: recorded(self.con, sid, ["raw", "env"]) for sid in HUMANS}
        self.cake.free_space(self.con, self.tiny(), self.now)
        self.con.commit()
        self.assertEqual(chunk_file_bytes(), on_disk, "dropping deletes rows; the files change at the next round")
        self.assertIsNotNone(space.reclaim_if_due(self.con, self.now))
        self.assertEqual(chunk_file_bytes(), on_disk - dropped)
        self.assertIsNone(space.reclaim_if_due(self.con, self.now), "once, until something is dropped again")
        self.assertEqual({sid: recorded(self.con, sid, ["raw", "env"]) for sid in HUMANS}, raw, "moved, not lost")

    def test_a_chosen_retention_deletes_whole_old_sessions_with_their_chunks(self):
        # an agent session too: a retention is the user's own choice, unlike freeing space
        old = self.now - 40 * DAY
        add_session(self.cake, self.con, "old", verdict="agent", agent_pct=100, group="L?/V?", end_ms=old, srv=True)
        self.con.execute("INSERT INTO events VALUES('old', ?, '{\"kind\": \"pageview\"}')", (old,))
        self.con.execute("INSERT INTO segments(session_id, t_start, t_end, actor) VALUES('old', 1, 2, 'agent')")
        self.con.execute("INSERT INTO labels(session_id, name, layer) VALUES('old', 'Operator', 'names')")
        self.con.execute("INSERT INTO requests(session_id, recv_ms, facts) VALUES('old', ?, '{}')", (old,))
        self.con.execute("INSERT INTO batches(session_id, pv, seq, recv_ms, n_rrweb, n_raw, n_env) VALUES('old', 'p', 1, ?, 1, 1, 1)", (old,))
        streams.append(self.con, "old", "raw", [(old, {"ty": "click"})], old)  # an open window
        self.con.commit()
        self.assertEqual(self.cake.prune(self.con, 30, self.now), 1)
        self.con.commit()
        for table in ("chunks", "open_chunks", "events", "srv", "segments", "labels", "requests", "batches"):
            self.assertEqual(self.con.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id='old'").fetchone()[0], 0, table)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 11, "the younger ones stay")
        space.reclaim_if_due(self.con, self.now)
        self.assertFalse(os.path.exists(os.path.join(replay_chunks.replay_dir(), replay_chunks.file_for(old))))

    def test_a_nearly_full_disk_with_auto_free_off_stops_new_replays_and_frees_nothing(self):
        # K2 (11/12): with auto_free on the oldest replays make room instead (tests/test_space_disk.py)
        c = dict(self.cake.load_cfg(), budget_mb=self.used * 0.8 / MB)  # the budget is full as well
        floor = c["disk_min_free_mb"] * MB
        self.assertFalse(space.room_for_replay(self.con, dict(c, auto_free=False), self.now, usage=disk_with(floor - 1)))
        self.assertEqual([self.events(s) for s in HUMANS], [60] * 4, "nothing freed for a replay that is not stored")
        self.assertTrue(space.room_for_replay(self.con, c, self.now, usage=disk_with(floor)), "at the floor the budget rules")
        self.assertTrue(space.room_for_replay(self.con, dict(c, disk_min_free_mb=0), self.now, usage=disk_with(0)), "0: off")

    def test_status_reports_the_disk_and_why_new_replays_stop(self):
        c = dict(self.cake.load_cfg(), budget_mb=self.used * 0.6 / MB)
        floor = c["disk_min_free_mb"] * MB
        low = space.space_status(self.con, dict(c, auto_free=False), self.now, usage=disk_with(floor - 1))
        self.assertEqual(low["disk"], {"total": 2 * (floor - 1), "free": floor - 1, "min_free": floor, "low": True})
        self.assertEqual(low["replays_stopped"], "disk")
        freeing = space.space_status(self.con, c, self.now, usage=disk_with(floor - 1))
        self.assertIsNone(freeing["replays_stopped"], "K2: with auto_free on the oldest replays make room")
        self.assertIsNone(space.space_status(self.con, c, self.now, usage=ROOMY)["replays_stopped"], "it frees first")
        self.assertEqual(space.space_status(self.con, dict(c, auto_free=False), self.now, usage=ROOMY)["replays_stopped"], "budget")
        self.cake.free_space(self.con, self.tiny(), self.now)
        self.assertEqual(space.space_status(self.con, c, self.now, usage=ROOMY)["replays_stopped"], "budget", "nothing left to free")


class FullOverHttp(unittest.TestCase):
    """A real collect POST against a full cake, both ways, and against a nearly full disk."""

    def setUp(self):
        self.cake, self.home = fresh_cake()
        roomy = mock.patch("shutil.disk_usage", ROOMY)  # whatever this computer's disk has free
        roomy.start()
        self.addCleanup(roomy.stop)
        c = self.cake.ensure_cfg()
        self.key = c["site_key"]
        con = self.cake.db()
        now = int(time.time() * 1000)
        add_session(self.cake, con, "oldhuman", verdict="human", agent_pct=0, group="H1/L?", end_ms=now - 5 * DAY, n_events=200)
        add_session(self.cake, con, "oldagent", verdict="agent", agent_pct=100, group="L?/V?", end_ms=now - 4 * DAY, n_events=200)
        con.commit()
        self.used = self.cake.used_bytes(con)
        con.close()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self.cake.H)
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": SERVER_POLL_S}, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.url = self.base + "/collect"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, sid):
        ev = [{"type": 3, "timestamp": int(time.time() * 1000), "data": {"source": 2, "type": 2, "x": 1, "y": 1}}] * 5
        body = json.dumps({"k": self.key, "s": sid, "u": "https://example.com/", "ua": "Mozilla/5.0", "e": ev}).encode()
        return urllib.request.urlopen(urllib.request.Request(self.url, data=body, method="POST"), timeout=5).status

    def set_cfg(self, **kv):
        c = self.cake.load_cfg()
        c.update(kv)
        self.cake.save_cfg(c)

    def count(self, sql, *a):
        con = self.cake.db()
        v = con.execute(sql, a).fetchone()[0]
        con.close()
        return v

    def replay(self, sid):
        con = self.cake.db()
        try:
            return replay(con, sid)
        finally:
            con.close()

    def replay_events(self, sid):
        """The rrweb events collect kept for a visit: since S2.1 in chunks, no longer in the events table."""
        con = self.cake.db(); v = streams.event_count(con, sid, "rrweb"); con.close(); return v

    def test_auto_free_on_makes_room_from_the_person_only_replay(self):
        self.set_cfg(budget_mb=self.used * 0.7 / MB, auto_free=True)
        self.assertEqual(self.post("newvisit"), 204)
        self.assertEqual(self.replay("oldhuman"), 0)
        self.assertEqual(self.replay("oldagent"), 200)
        self.assertEqual(self.replay_events("newvisit"), 5)

    def test_auto_free_off_keeps_the_visit_but_no_new_replay(self):
        self.set_cfg(budget_mb=self.used * 0.7 / MB, auto_free=False)
        self.assertEqual(self.post("newvisit"), 204, "the visit is not refused")
        self.assertEqual(self.count("SELECT COUNT(*) FROM sessions WHERE id='newvisit'"), 1)
        self.assertIsNotNone(self.count("SELECT verdict FROM sessions WHERE id='newvisit'"), "and it is judged")
        self.assertEqual(self.replay_events("newvisit"), 0)
        self.assertEqual(self.count("SELECT events_dropped FROM sessions WHERE id='newvisit'"), 5)
        self.assertEqual(self.replay("oldhuman"), 200, "nothing removed")

    def test_a_nearly_full_disk_with_auto_free_off_keeps_the_visit_but_no_new_replay(self):
        # K2 (11/12): with auto_free on the new replay is stored (tests/test_space_disk.py, FloorOverHttp)
        self.set_cfg(auto_free=False)
        floor = self.cake.load_cfg()["disk_min_free_mb"] * MB  # the budget has room
        with mock.patch("shutil.disk_usage", disk_with(floor - 1)):
            self.assertEqual(self.post("newvisit"), 204, "the visit is not refused")
        self.assertIsNotNone(self.count("SELECT verdict FROM sessions WHERE id='newvisit'"), "and it is judged")
        self.assertEqual(self.replay("newvisit"), 0)
        self.assertEqual(self.count("SELECT events_dropped FROM sessions WHERE id='newvisit'"), 5)
        self.assertEqual(self.replay("oldhuman"), 200, "nothing removed")

    def test_health_reports_the_disk(self):
        self.set_cfg(auto_free=False)  # K2: stopped only with auto_free off or nothing left to free
        floor = self.cake.load_cfg()["disk_min_free_mb"] * MB
        with mock.patch("shutil.disk_usage", disk_with(floor - 1)):
            with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
                health = json.load(r)
        self.assertEqual(health["space"]["disk"], {"total": 2 * (floor - 1), "free": floor - 1, "min_free": floor, "low": True})
        self.assertEqual(health["space"]["replays_stopped"], "disk")


class Config(unittest.TestCase):
    def test_legacy_max_db_mb_becomes_the_budget(self):
        cake, home = fresh_cake()
        with open(os.path.join(home, "config.json"), "w") as f:
            json.dump({"max_db_mb": 3000, "site_key": "ck_abc"}, f)
        self.assertEqual(cake.load_cfg()["budget_mb"], 3000)
        self.assertNotIn("max_db_mb", cake.load_cfg())

    def test_choices(self):
        cake, _ = fresh_cake()
        self.assertEqual(cake.coerce("retention_days", "90"), 90)
        self.assertEqual(cake.coerce("retention_days", "0"), 0)
        with self.assertRaises(ValueError):
            cake.coerce("retention_days", "7")
        with self.assertRaises(ValueError):
            cake.coerce("budget_mb", "10")
        self.assertIs(cake.coerce("auto_free", "off"), False)
        self.assertEqual(cake.coerce("disk_min_free_mb", "0"), 0)
        with self.assertRaises(ValueError):
            cake.coerce("disk_min_free_mb", "-1")


if __name__ == "__main__":
    unittest.main()
