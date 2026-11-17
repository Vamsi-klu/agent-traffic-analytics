"""The floor of free disk (disk_min_free_mb, 10 GB): below it AgentCake stores no new replay and deletes none for it,
with auto_free on or off; new replays start again on their own once there is room. A floor of 0 turns the check off.

    python3 -I -m unittest discover -s tests -p test_space_disk.py -v      (from the repository folder)

Each test works on a copy of one CAKE_HOME holding space_sessions.MIX (sessions of every kind), every replay sealed in
chunk files. The disk is a stand-in for shutil.disk_usage (space_sessions.disk_with): nothing is filled. A disk `n`
bytes short of its floor is disk_with(floor - n). Freeing room in the budget leaves a chunk file that is less than
compact_min_dead_share dead as it is; the disk's free space doesn't change what is deleted.
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

    def replays(self):
        return {sid: replay(self.con, sid) for sid, *_ in MIX}

    def test_the_default_floor_is_10_gb(self):
        self.assertEqual(self.c["disk_min_free_mb"], 10240, "the floor is 10 GB")
        self.assertTrue(self.c["auto_free"])

    def test_below_the_floor_no_new_replay_is_stored_and_none_is_deleted_whatever_auto_free_says(self):
        for auto_free in (True, False):
            c = dict(self.c, auto_free=auto_free)
            self.assertFalse(space.room_for_replay(self.con, c, self.now, usage=disk_with(self.floor - 1)), auto_free)
            status = space.space_status(self.con, c, self.now, usage=disk_with(self.floor - 1))
            self.assertEqual(status["replays_stopped"], "disk", auto_free)
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX}, "nothing deleted for the disk")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sessions WHERE replay_freed_ms IS NOT NULL").fetchone()[0], 0)

    def test_once_there_is_room_again_new_replays_are_stored_on_their_own(self):
        self.assertFalse(space.room_for_replay(self.con, self.c, self.now, usage=disk_with(self.floor - 1)))
        self.assertTrue(space.room_for_replay(self.con, self.c, self.now, usage=disk_with(self.floor)), "at the floor")
        self.assertIsNone(space.space_status(self.con, self.c, self.now, usage=disk_with(self.floor))["replays_stopped"])

    def test_a_floor_of_zero_turns_the_rule_off(self):
        self.assertTrue(space.room_for_replay(self.con, dict(self.c, disk_min_free_mb=0), self.now, usage=disk_with(0)))
        self.assertEqual(self.replays(), {sid: EVENTS for sid, *_ in MIX})

    def test_the_settings_page_and_health_say_why_new_replays_stop(self):
        with mock.patch("shutil.disk_usage", disk_with(self.floor - 1)):
            storage = Client().get("/api/settings").body["storage"]
            self.assertEqual(storage["replays_stopped"], "disk")
            self.assertEqual(Client().get("/api/health").body["space"]["replays_stopped"], "disk")


class SharedFile(unittest.TestCase):
    """A dropped replay that is a small part of its chunk file: the lab's sessions store about a quarter of their
    bytes as replay (sizes.json: 7.35 of 31.95 KB a minute), so a file whose replays were all dropped stays under
    compact_min_dead_share dead, and the next reclaim leaves it as it is."""

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
        self.c, self.dropped = config.load_cfg(), streams.replay_bytes(self.con, "human")  # the older of the two
        self.agent = recorded(self.con, "agent")
        self.assertLess(self.dropped, SETTINGS["compact_min_dead_share"] * chunk_file_bytes(), "under the share")

    def test_freeing_for_the_budget_leaves_such_a_file_as_it_is(self):
        before = chunk_file_bytes()
        budget_mb = (space.used_bytes(self.con) - self.dropped / 2) / self.c["auto_free_target_ratio"] / MB
        self.assertEqual(space.free_space(self.con, dict(self.c, budget_mb=budget_mb), self.now), 1, "the oldest, human, goes")
        self.assertEqual(recorded(self.con, "agent"), self.agent)
        self.con.commit()
        self.assertIsNotNone(space.reclaim_if_due(self.con, self.now))
        self.assertEqual(chunk_file_bytes(), before, "under compact_min_dead_share a file is not rewritten")


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
    """A real collect POST while the disk is below its floor, auto_free on (off too: tests/test_space.py)."""

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
        with urllib.request.urlopen(urllib.request.Request(self.base + "/collect", data=body, method="POST"),
                                    timeout=5) as response:
            return response.status

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

    def test_the_visit_is_kept_without_its_replay_none_is_deleted_and_replays_resume_once_there_is_room(self):
        self.assertEqual(self.health()["replays_stopped"], "disk")
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
