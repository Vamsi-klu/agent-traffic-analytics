"""Freeing space whatever the four layers' verdict (agentcake.space.free_space).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Sessions the four layers judged are freed by age alone, the oldest first: a Human, an Agent, a Mixed, a Bot, a Not sure
or a Too little data session gives up its replay in its turn. tests/test_space.py checks the rest of the rule on
sessions of every kind.
"""
import os, sys, time, unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from space_sessions import DAY, MB, ROOMY, add_session, fresh_cake, replay  # noqa: E402  (shared with test_space.py)
from agentcake import space  # noqa: E402


class FourLayersVerdict(unittest.TestCase):
    """Sessions the four layers judged, oldest first, one of each class: the replays go by age, whatever the class."""

    CLASSES = (("oldAgent", "agent"), ("newHuman", "human"), ("newMixed", "mixed"), ("newBot", "bot"),
               ("newNotSure", "not_sure"), ("newTooLittle", "too_little_data"))

    def setUp(self):
        self.cake, self.home = fresh_cake()
        self.now = int(time.time() * 1000)
        self.con = self.cake.db()
        self.addCleanup(self.con.close)
        for n, (sid, cls) in enumerate(self.CLASSES):
            add_session(self.cake, self.con, sid, verdict="human", agent_pct=0, group="H1/L?",
                        end_ms=self.now - (10 - n) * DAY)
            self.con.execute("UPDATE sessions SET verdict_class=? WHERE id=?", (cls, sid))
        self.con.commit()

    def freed(self):
        return [sid for (sid,) in self.con.execute("SELECT id FROM sessions WHERE replay_freed_ms IS NOT NULL ORDER BY end_ms")]

    def test_every_class_is_freed_in_its_turn(self):
        with mock.patch.object(space.shutil, "disk_usage", ROOMY):
            self.cake.free_space(self.con, dict(self.cake.load_cfg(), budget_mb=0.0001), self.now)
        self.con.commit()
        self.assertEqual(self.freed(), [sid for sid, _ in self.CLASSES])
        self.assertTrue(all(replay(self.con, sid) == 0 for sid, _ in self.CLASSES))

    def test_the_oldest_goes_first_even_an_agent_session(self):
        used = self.cake.used_bytes(self.con)
        with mock.patch.object(space.shutil, "disk_usage", ROOMY):
            self.cake.free_space(self.con, dict(self.cake.load_cfg(), budget_mb=used * 0.95 / MB), self.now)
        self.con.commit()
        self.assertEqual(self.freed()[:1], ["oldAgent"])
        self.assertGreater(replay(self.con, "newTooLittle"), 0, "the youngest stays")


if __name__ == "__main__":
    unittest.main()
