"""K2, the floor of free disk (disk_min_free_mb, 10 GB): below it Agent Cake keeps storing new replays and deletes the
oldest ones to get back above it (S2.5's rule as the user changed it on 11/12: GOAL K2 and T9), unless deleting every
one it may would not get back above it (D34: other files fill the disk).

    python3 -I -m unittest discover -s tests -p test_space_disk.py -v      (from the repository folder)

Each test works on a copy of one CAKE_HOME holding space_sessions.MIX (human-only, agent, mixed, unsure, a
self-declared agent with a 0% agent share, a human-only session still active), every replay sealed in chunk files.
The disk is a stand-in for shutil.disk_usage (space_sessions.disk_with): nothing is filled. A disk `n` bytes short
of its floor is disk_with(floor - n). Below the floor, with auto_free on, the replays of the oldest human-only
sessions quiet for an hour go first, then those of the oldest other sessions quiet for an hour, until the free space
plus what the next reclaim gives back reaches the floor; that reclaim compacts every chunk file with dead bytes. When
the free space, those dead bytes and every replay quiet for an hour together stay below the floor, no replay is
deleted, new replays stop (space_status: "disk_full_other") and start again once there is room. With auto_free off
new replays stop ("disk") and nothing is deleted.
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
from agentcake import config, space, store, streams  # noqa: E402  (needs the path above)
from agentcake.storage_config import SETTINGS  # noqa: E402
from api_client import Client, contract_problems  # noqa: E402
from space_sessions import (DAY, MB, MIX, add_mix, add_session, chunk_file_bytes, disk_with, fresh_cake,  # noqa: E402
                            recorded, replay)

HUMANS = ["human1", "human2", "human3", "human4"]  # the human-only sessions, oldest first
OTHERS = ["agent1", "mixed1", "unsure1", "named1", "agent2", "mixed2"]  # the rest of MIX quiet for an hour, oldest first
EVENTS = 60  # replay events of each session of MIX
HOUR = 3600_000
SERVER_POLL_S = 0.01  # how often a test server's loop checks for shutdown()


class DiskFloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # recorded once; every test works on a copy (sealing eleven sessions is most of what a setup costs)
        cls.cake, cls.recorded_home = fresh_cake()
        cls.addClassCleanup(shutil.rmtree, cls.recorded_home, True)
        cls.now = int(time.time() * 1000)
        con = cls.cake.db()
        add_mix(cls.cake, con, cls.now)
        con.commit()
        con.close()  # the last connection: its write-ahead log goes into cake.db, so the folder copies whole

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        shutil.copytree(self.recorded_home, self.home, dirs_exist_ok=True)
        os.environ["CAKE_HOME"] = self.home
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.c = config.load_cfg()
        self.floor = self.c["disk_min_free_mb"] * MB
        self.size = {sid: streams.replay_bytes(self.con, sid) for sid, *_ in MIX}
        self.quiet = sum(self.size[sid] for sid in HUMANS + OTHERS)  # every replay that may go: quiet for an hour

    def short_by(self, missing):
        """A disk `missing` bytes short of the floor, as space.disk_space describes it."""
        return space.disk_space(self.c, disk_with(self.floor - missing))

    def replays(self):
        return {sid: replay(self.con, sid) for sid, *_ in MIX}

    def free(self, missing, c=None, now=None):
        return space.free_disk(self.con, c or self.c, self.short_by(missing), self.now if now is None else now)

    def test_the_default_floor_is_10_gb(self):
        self.assertEqual(self.c["disk_min_free_mb"], 10240, "K2")
        self.assertTrue(self.c["auto_free"])

    def test_below_the_floor_a_new_replay_is_still_stored(self):
        self.assertTrue(space.room_for_replay(self.con, self.c, self.now, usage=disk_with(self.floor - 1)))
        self.assertEqual(replay(self.con, "human1"), 0, "room was made from the oldest replay")

    def test_the_oldest_human_only_replay_goes_first(self):
        room, removed = self.free(1)
        self.assertTrue(room)
        self.assertEqual(removed, ["human1"], "one byte short: one replay, the oldest human-only one")
        self.assertEqual(self.replays(), dict({sid: EVENTS for sid, *_ in MIX}, human1=0))

    def test_freeing_stops_once_the_floor_is_reached(self):
        room, removed = self.free(self.size["human1"] + self.size["human2"] // 2)
        self.assertTrue(room)
        self.assertEqual(removed, ["human1", "human2"], "no more than needed")
        self.assertEqual([replay(self.con, sid) for sid in HUMANS], [0, 0, EVENTS, EVENTS])

    def test_when_no_human_only_replay_is_left_the_oldest_of_the_others_go(self):
        missing = sum(self.size[sid] for sid in HUMANS) + self.size["agent1"] + 1
        room, removed = self.free(missing)
        self.assertTrue(room)
        self.assertEqual(removed, HUMANS + ["agent1", "mixed1"], "human-only first, then the others, oldest first")
        for sid in OTHERS[2:] + ["humanLive"]:
            self.assertEqual(replay(self.con, sid), EVENTS, sid)

    def test_a_session_active_in_the_last_hour_keeps_its_replay(self):
        add_session(self.cake, self.con, "agentLive", verdict="agent", agent_pct=100, group="L?/V?",
                    end_ms=self.now - 10 * 60_000)
        room, removed = self.free(self.quiet, dict(self.c, auto_free_batch_sessions=len(MIX) + 1))
        self.assertEqual(removed, HUMANS + OTHERS, "every session quiet for an hour, in this order")
        self.assertEqual(replay(self.con, "humanLive"), EVENTS)
        self.assertEqual(replay(self.con, "agentLive"), EVENTS)

    # D34: deleting cannot be undone, and it cannot fix a disk that other files fill

    def test_when_deleting_every_replay_would_not_reach_the_floor_none_is_deleted(self):
        room, removed = self.free(self.quiet + 1, dict(self.c, auto_free_batch_sessions=len(MIX)))
        self.assertEqual((room, removed), (False, []))
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})

    def test_short_by_exactly_every_replay_that_may_go_they_all_go(self):
        room, removed = self.free(self.quiet, dict(self.c, auto_free_batch_sessions=len(MIX)))
        self.assertTrue(room)
        self.assertEqual(removed, HUMANS + OTHERS)

    def test_a_replay_still_being_recorded_does_not_count_as_room(self):
        # humanLive was active 10 minutes ago: its replay may not go, so its bytes cannot make room
        self.assertGreater(self.size["humanLive"], 1)
        self.assertEqual(self.free(self.quiet + 1, dict(self.c, auto_free_batch_sessions=len(MIX))), (False, []))
        self.assertEqual(replay(self.con, "humanLive"), EVENTS)

    def test_bytes_waiting_for_the_next_reclaim_count_as_room(self):
        self.assertEqual(self.free(self.size["human1"])[1], ["human1"])
        self.con.commit()
        c = dict(self.c, auto_free_batch_sessions=len(MIX))
        # human1's bytes come back at the next round: with every other replay they reach the floor, and no further
        self.assertEqual(self.free(self.quiet + 1, c, now=self.now + 1), (False, []))
        self.assertEqual(self.free(self.quiet, c, now=self.now + 1), (True, HUMANS[1:] + OTHERS))

    def test_then_new_replays_stop_and_the_status_says_other_files_fill_the_disk(self):
        usage = disk_with(self.floor - self.quiet - 1)
        self.assertFalse(space.room_for_replay(self.con, self.c, self.now, usage=usage))
        status = space.space_status(self.con, self.c, self.now, usage=usage)
        self.assertEqual(status["replays_stopped"], "disk_full_other")
        self.assertEqual(status["disk"]["free"], self.floor - self.quiet - 1)
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})

    def test_once_there_is_room_again_new_replays_are_stored_on_their_own(self):
        full_of_other_files = disk_with(self.floor - self.quiet - 1)
        self.assertFalse(space.room_for_replay(self.con, self.c, self.now, usage=full_of_other_files))
        freed_elsewhere = disk_with(self.floor)  # the other files were deleted
        self.assertIsNone(space.space_status(self.con, self.c, self.now + 1, usage=freed_elsewhere)["replays_stopped"])
        self.assertTrue(space.room_for_replay(self.con, self.c, self.now + 1, usage=freed_elsewhere), "at once")
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})

    def test_with_auto_free_off_new_replays_stop_and_nothing_is_freed(self):
        c = dict(self.c, auto_free=False)
        self.assertFalse(space.room_for_replay(self.con, c, self.now, usage=disk_with(self.floor - 1)))
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})
        self.assertEqual(space.space_status(self.con, c, self.now, usage=disk_with(self.floor - 1))["replays_stopped"],
                         "disk")

    def test_while_something_can_be_freed_new_replays_are_not_stopped(self):
        status = space.space_status(self.con, self.c, self.now, usage=disk_with(self.floor - 1))
        self.assertTrue(status["disk"]["low"])
        self.assertIsNone(status["replays_stopped"])
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX}, "the status deletes nothing")

    def test_freed_sessions_keep_their_verdicts_timelines_and_server_half(self):
        self.con.execute("INSERT INTO segments(session_id, t_start, t_end, actor) VALUES('agent1', 1, 2, 'agent')")
        self.con.execute("INSERT INTO labels(session_id, name, layer) VALUES('agent1', 'Operator', 'names')")
        kept = self.everything_but_replays()
        self.free(self.quiet, dict(self.c, auto_free_batch_sessions=len(MIX)))
        self.assertEqual(self.everything_but_replays(), kept)
        for sid in HUMANS + OTHERS:
            self.assertEqual(replay(self.con, sid), 0, sid)
            self.assertIsNotNone(self.con.execute("SELECT replay_freed_ms FROM sessions WHERE id=?", (sid,)).fetchone()[0])

    def test_the_replay_page_says_a_freed_agent_replay_was_deleted_to_make_room(self):
        self.free(sum(self.size[sid] for sid in HUMANS) + 1)  # human-only ones, then agent1
        self.con.commit()
        self.assertEqual(Client().get("/api/session/agent1").body["replay"]["missing"], "freed")

    def test_bytes_waiting_for_the_next_reclaim_are_not_freed_twice(self):
        missing = self.size["human1"]
        self.assertEqual(self.free(missing)[1], ["human1"])
        self.con.commit()
        # the same disk again before the maintenance round gave human1's bytes back: they are on their way
        self.assertEqual(self.free(missing, now=self.now + 1), (True, []))
        self.assertEqual(replay(self.con, "human2"), EVENTS)

    def test_a_round_removes_at_most_auto_free_batch_sessions(self):
        room, removed = self.free(self.quiet, dict(self.c, auto_free_batch_sessions=2))
        self.assertEqual(removed, ["human1", "human2"])
        self.assertTrue(room, "more can go at the next batch")

    def test_while_a_full_batch_went_and_the_disk_is_still_short_collect_frees_again_at_once(self):
        c, usage = dict(self.c, auto_free_batch_sessions=2), disk_with(self.floor - self.quiet)
        self.assertTrue(space.room_for_replay(self.con, c, self.now, usage=usage))
        self.assertTrue(space.room_for_replay(self.con, c, self.now + 1, usage=usage))
        self.assertEqual([replay(self.con, sid) for sid in HUMANS], [0] * 4)

    def test_otherwise_collect_asks_again_only_after_a_maintenance_tick(self):
        c, usage = dict(self.c, auto_free_batch_sessions=len(MIX)), disk_with(self.floor - self.quiet - 1)
        self.assertFalse(space.room_for_replay(self.con, c, self.now, usage=usage), "other files fill the disk")
        # another session goes quiet: with its replay, deleting can make room now
        add_session(self.cake, self.con, "late", verdict="agent", agent_pct=100, group="L?/V?", end_ms=self.now - 2 * HOUR)
        self.assertFalse(space.room_for_replay(self.con, c, self.now + 1, usage=usage), "the same answer")
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})
        tick = SETTINGS["maintenance_tick_ms"]
        self.assertTrue(space.room_for_replay(self.con, c, self.now + tick, usage=usage), "asked again after a tick")
        self.assertEqual(replay(self.con, "late"), 0)

    def test_a_floor_of_zero_turns_the_rule_off(self):
        self.assertTrue(space.room_for_replay(self.con, dict(self.c, disk_min_free_mb=0), self.now, usage=disk_with(0)))
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})

    def everything_but_replays(self):
        """Every row of every table but the replay chunks, and every session's raw input and environment signals."""
        rows = {}
        for (table,) in self.con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN "
                                         "('chunks', 'open_chunks', 'totals', 'settings')").fetchall():
            columns = [r[1] for r in self.con.execute(f"PRAGMA table_info({table})") if r[1] != "replay_freed_ms"]
            rows[table] = sorted(map(repr, self.con.execute(f"SELECT {', '.join(columns)} FROM {table}")))
        rows["raw_env"] = {sid: recorded(self.con, sid, ["raw", "env"]) for sid, *_ in MIX}
        return rows


class SharedFile(unittest.TestCase):
    """A dropped replay that is a small part of its chunk file: S2.2's lab sessions store about a quarter of their
    bytes as replay (sizes.json: 7.35 of 31.95 KB a minute), so a file whose replays were all dropped stays under
    compact_min_dead_share dead. The reclaim after freeing for the disk compacts it all the same."""

    def setUp(self):
        self.cake, self.home = fresh_cake()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.now = int(time.time() * 1000)
        self.con = store.db()
        self.addCleanup(self.con.close)
        hour = (self.now - 2 * DAY) // HOUR * HOUR  # both sessions end in this hour: their chunks share its file
        add_session(self.cake, self.con, "human", verdict="human", agent_pct=0, group="H1/L?", end_ms=hour + 600_000)
        add_session(self.cake, self.con, "agent", verdict="agent", agent_pct=100, group="L?/V?", end_ms=hour + 660_000,
                    n_events=6 * EVENTS)
        self.con.commit()
        self.c, self.dropped = config.load_cfg(), streams.replay_bytes(self.con, "human")
        self.agent = recorded(self.con, "agent")
        self.assertLess(self.dropped, SETTINGS["compact_min_dead_share"] * chunk_file_bytes(), "under the share")

    def test_freeing_for_the_budget_leaves_such_a_file_as_it_is(self):
        before = chunk_file_bytes()
        space.free_space(self.con, dict(self.c, budget_mb=0.0001), self.now)
        self.con.commit()
        self.assertIsNotNone(space.reclaim_if_due(self.con, self.now))
        self.assertEqual(chunk_file_bytes(), before, "S2.5: under compact_min_dead_share a file is not rewritten")

    def test_freeing_for_the_disk_gets_every_dropped_byte_back_at_the_next_reclaim(self):
        before, floor = chunk_file_bytes(), self.c["disk_min_free_mb"] * MB
        room, removed = space.free_disk(self.con, self.c, space.disk_space(self.c, disk_with(floor - 1)), self.now)
        self.assertEqual((room, removed), (True, ["human"]))
        self.con.commit()
        self.assertEqual(chunk_file_bytes(), before, "dropping deletes rows; the file changes at the next round")
        self.assertIsNotNone(space.reclaim_if_due(self.con, self.now))
        self.assertEqual(chunk_file_bytes(), before - self.dropped)
        self.assertEqual(recorded(self.con, "agent"), self.agent, "moved, not lost")
        self.assertIsNone(space.reclaim_if_due(self.con, self.now), "once")


class DataFolderNotThereYet(unittest.TestCase):
    """doctor runs before the first start, or after ~/.cake was deleted: the disk is the one the data will go to."""

    def test_the_disk_of_the_nearest_existing_parent_is_measured(self):
        parent = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, parent, True)
        asked = []

        def usage(path):
            asked.append(path)
            return disk_with(10 ** 12)(path)

        with mock.patch.dict(os.environ, {"CAKE_HOME": os.path.join(parent, "not", "there")}):
            disk = space.disk_space(config.load_cfg(), usage)
        self.assertEqual(asked, [parent])
        self.assertEqual(disk["free"], 10 ** 12)
        self.assertFalse(disk["low"])

    def test_a_missing_folder_with_the_real_disk_does_not_fail(self):
        parent = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, parent, True)
        with mock.patch.dict(os.environ, {"CAKE_HOME": os.path.join(parent, "not", "there")}):
            disk = space.disk_space(config.load_cfg())
        self.assertGreater(disk["total"], 0)


class FloorOverHttp(unittest.TestCase):
    """A real collect POST while the disk is below its floor, auto_free on (off: tests/test_space.py)."""

    def setUp(self):
        self.cake, self.home = fresh_cake()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.key = config.ensure_cfg()["site_key"]
        con = store.db()
        now = int(time.time() * 1000)
        add_session(self.cake, con, "oldhuman", verdict="human", agent_pct=0, group="H1/L?", end_ms=now - 5 * DAY, n_events=200)
        add_session(self.cake, con, "oldagent", verdict="agent", agent_pct=100, group="L?/V?", end_ms=now - 4 * DAY, n_events=200)
        con.commit()
        con.close()
        self.floor = config.load_cfg()["disk_min_free_mb"] * MB
        low = mock.patch("shutil.disk_usage", disk_with(self.floor - 1))
        low.start()
        self.addCleanup(low.stop)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self.cake.H)
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": SERVER_POLL_S}, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def post(self, sid):
        ev = [{"type": 3, "timestamp": int(time.time() * 1000), "data": {"source": 2, "type": 2, "x": 1, "y": 1}}] * 5
        body = json.dumps({"k": self.key, "s": sid, "u": "https://example.com/", "ua": "Mozilla/5.0", "e": ev}).encode()
        return urllib.request.urlopen(urllib.request.Request(self.base + "/collect", data=body, method="POST"), timeout=5).status

    def health(self):
        with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
            body = json.load(r)
        self.assertEqual(contract_problems(body, "health"), [])
        return body["space"]

    def look(self, sql, *args):
        con = store.db()
        try:
            return con.execute(sql, args).fetchone()[0]
        finally:
            con.close()

    def replay(self, sid):
        con = store.db()
        try:
            return replay(con, sid)
        finally:
            con.close()

    def test_the_new_replay_is_stored_and_the_oldest_human_only_one_goes(self):
        self.assertIsNone(self.health()["replays_stopped"])
        self.assertEqual(self.post("newvisit"), 204)
        self.assertEqual(self.replay("newvisit"), 5)
        self.assertEqual(self.look("SELECT events_dropped FROM sessions WHERE id='newvisit'"), 0)
        self.assertEqual(self.replay("oldhuman"), 0)
        self.assertEqual(self.replay("oldagent"), 200, "one byte short: one replay is enough")

    def test_a_disk_full_of_other_files_keeps_every_replay_and_stores_new_ones_once_there_is_room(self):
        con = store.db()
        try:
            quiet = streams.replay_bytes(con, "oldhuman") + streams.replay_bytes(con, "oldagent")
        finally:
            con.close()
        with mock.patch("shutil.disk_usage", disk_with(self.floor - quiet - 1)):
            self.assertEqual(self.health()["replays_stopped"], "disk_full_other")
            self.assertEqual(self.post("newvisit"), 204, "the visit is not refused")
        self.assertEqual(self.replay("newvisit"), 0)
        self.assertEqual(self.look("SELECT events_dropped FROM sessions WHERE id='newvisit'"), 5)
        self.assertEqual((self.replay("oldhuman"), self.replay("oldagent")), (200, 200), "none deleted")
        with mock.patch("shutil.disk_usage", disk_with(self.floor)):  # the other files were deleted
            self.assertIsNone(self.health()["replays_stopped"])
            self.assertEqual(self.post("newvisit"), 204)
        self.assertEqual(self.replay("newvisit"), 5, "stored again, nobody turned anything on")
        self.assertEqual((self.replay("oldhuman"), self.replay("oldagent")), (200, 200))


if __name__ == "__main__":
    unittest.main()
