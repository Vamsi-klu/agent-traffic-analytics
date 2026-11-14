"""Background upkeep of the replay chunks (S2.2): agentcake/maintenance.py.

    python3 -I -m unittest discover -s tests -p test_maintenance.py -v      (from the cake folder)

Every round seals the windows that went quiet; the heavy night work (recompress, reclaim) runs only at night, on AC
power, with the computer idle and cake quiet. The clock and the power and load probes are passed in: nothing sleeps.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import maintenance, replay_chunks, store, streams  # noqa: E402
from agentcake.storage_config import EPOCH, ONE_MS, SETTINGS, ms_from_days  # noqa: E402

DAY = ms_from_days(1)


def local_ms(hour):
    """Epoch ms of 2026-11-12 at `hour`:30 local time."""
    return (datetime(2026, 11, 12, hour, 30).astimezone() - EPOCH) // ONE_MS


class Probes:
    def __init__(self, ac=True, load=0.0):
        self.ac, self.load = ac, load

    def on_ac_power(self):
        return self.ac

    def load_per_cpu(self):
        return self.load


class Rounds(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        self.night = local_ms(SETTINGS["recompress_night_hours"][0])
        con = store.db()
        old = self.night - 20 * DAY
        streams.append(con, "old", "rrweb", [(old + i, json.dumps({"type": 3, "i": i})) for i in range(0, 30_000, 100)], old)
        streams.seal(con, old + 60_000, force=True)
        arrived = self.night - SETTINGS["seal_idle_ms"]  # the open session's last batch, as collect records it
        con.execute("INSERT INTO sessions(id, start_ms, end_ms) VALUES('open', ?, ?)", (arrived, arrived))
        streams.append(con, "open", "raw", [(self.night, {"ty": "click"})], arrived)
        con.commit()
        con.close()

    def count(self, sql):
        con = store.db()
        try:
            return con.execute(sql).fetchone()[0]
        finally:
            con.close()

    def test_a_round_seals_quiet_windows(self):
        upkeep = maintenance.Upkeep(probes=Probes(ac=False))
        upkeep.tick(self.night)
        self.assertEqual(self.count("SELECT COUNT(*) FROM open_chunks"), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM chunks WHERE session_id='open'"), 1)

    def test_the_night_work_runs_at_night_on_ac_power_when_idle(self):
        quiet = self.night + SETTINGS["recompress_quiet_ms"]
        for probes, now, ran in ((Probes(), quiet, True), (Probes(ac=False), quiet, False),
                                 (Probes(load=SETTINGS["recompress_max_load_per_cpu"]), quiet, False),
                                 (Probes(), local_ms(SETTINGS["recompress_night_hours"][1]), False),
                                 (Probes(), self.night, False)):  # a batch arrived 30 s ago
            with self.subTest(ac=probes.ac, load=probes.load, now=now):
                self.setUp()
                maintenance.Upkeep(probes=probes).tick(now)
                self.assertEqual(self.count("SELECT MIN(archived) FROM chunks WHERE session_id='old'"), int(ran))

    def test_a_round_gives_back_the_files_of_dropped_chunks_by_day_as_well(self):
        morning = local_ms(SETTINGS["recompress_night_hours"][1])  # the night has just ended; on battery and busy too
        old = self.night - 40 * DAY
        con = store.db()
        con.execute("INSERT INTO sessions(id, start_ms, end_ms) VALUES('gone', ?, ?)", (old, old))
        streams.append(con, "gone", "rrweb", [(old, json.dumps({"type": 3}))], old)
        streams.seal(con, old, force=True, session_id="gone")
        self.assertEqual(store.prune(con, 30, morning), 1)  # a chosen retention: dropped rows, the file still there
        con.commit()
        con.close()
        gone = os.path.join(replay_chunks.replay_dir(), replay_chunks.file_for(old))
        self.assertTrue(os.path.exists(gone))
        maintenance.Upkeep(probes=Probes(ac=False, load=1.0)).tick(morning)
        self.assertFalse(os.path.exists(gone))
        self.assertEqual(self.count("SELECT MIN(archived) FROM chunks WHERE session_id='old'"), 0, "no night work")

    def test_the_night_work_is_checked_at_its_own_pace(self):
        upkeep = maintenance.Upkeep(probes=Probes(ac=False))
        self.assertTrue(upkeep.heavy_due(self.night))
        upkeep.tick(self.night)
        self.assertFalse(upkeep.heavy_due(self.night + SETTINGS["maintenance_tick_ms"]))
        self.assertTrue(upkeep.heavy_due(self.night + SETTINGS["maintenance_recompress_every_ms"]))


class Conditions(unittest.TestCase):
    def test_night_hours_may_wrap_around_midnight(self):
        self.assertTrue(maintenance.is_night(local_ms(2), dict(SETTINGS, recompress_night_hours=[1, 6])))
        self.assertFalse(maintenance.is_night(local_ms(6), dict(SETTINGS, recompress_night_hours=[1, 6])))
        late = dict(SETTINGS, recompress_night_hours=[22, 5])
        self.assertTrue(maintenance.is_night(local_ms(23), late))
        self.assertTrue(maintenance.is_night(local_ms(4), late))
        self.assertFalse(maintenance.is_night(local_ms(12), late))

    def test_macos_power_source(self):
        self.assertFalse(maintenance.pmset_on_ac("Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t80%;"))
        self.assertTrue(maintenance.pmset_on_ac("Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%;"))

    def test_linux_power_supplies(self):
        root = tempfile.mkdtemp(prefix="cake-power-")

        def write(name, field, value):
            os.makedirs(os.path.join(root, name), exist_ok=True)
            with open(os.path.join(root, name, field), "w") as f:
                f.write(value + "\n")

        self.assertTrue(maintenance.sysfs_on_ac(root), "no battery at all: a server or a desktop")
        write("BAT0", "type", "Battery")
        write("AC", "type", "Mains")
        write("AC", "online", "0")
        self.assertFalse(maintenance.sysfs_on_ac(root))
        write("AC", "online", "1")
        self.assertTrue(maintenance.sysfs_on_ac(root))


if __name__ == "__main__":
    unittest.main()
