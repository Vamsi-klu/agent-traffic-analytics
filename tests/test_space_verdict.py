"""Freeing space by the four layers' verdict (agentcake.space.HUMAN_ONLY).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Sessions the four layers judged are freed by their class: a Human only, never an Agent, Mixed, Bot, Not sure or Too
little data, even where cake 0.3.4's columns still say human. Sessions cake 0.3.4's judge decided keep 0.3.4's test
(tests/test_space.py).
"""
import os, sys, time, unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from space_sessions import DAY, ROOMY, add_session, fresh_cake, replay  # noqa: E402  (shared with test_space.py)
from agentcake import space  # noqa: E402


class FourLayersVerdict(unittest.TestCase):
    """Sessions the four layers judged are freed by their class, a Human only; an Agent, Mixed, Bot, Not
    sure or Too little data never, even where cake 0.3.4's columns still say human."""

    CLASSES = (("newHuman", "human"), ("newAgent", "agent"), ("newMixed", "mixed"), ("newBot", "bot"),
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

    def test_only_the_human_is_freed(self):
        with mock.patch.object(space.shutil, "disk_usage", ROOMY):
            self.cake.free_space(self.con, dict(self.cake.load_cfg(), budget_mb=0.0001), self.now)
        self.con.commit()
        freed = [sid for (sid,) in self.con.execute("SELECT id FROM sessions WHERE replay_freed_ms IS NOT NULL")]
        self.assertEqual(freed, ["newHuman"])
        self.assertEqual(self.events("newHuman"), 0)
        for sid, _ in self.CLASSES[1:]:
            self.assertGreater(self.events(sid), 0, sid)

    def events(self, sid):
        return replay(self.con, sid)


if __name__ == "__main__":
    unittest.main()
