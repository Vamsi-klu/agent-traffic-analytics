"""`agentcake session-counts`: a database's sessions one per tab and across tabs, read only
(agentcake/visit_stats.py).

    python3 -I -m unittest discover -s tests -p test_visit_stats.py -v

On an older AgentCake's database it counts what 0.6.2 makes of it: once upgraded, the visits it holds are the
sessions it counted, verdict by verdict, and counting again gives the same. It changes nothing (a copy without its
write-ahead log is opened immutable: no file appears or changes), prints no id, and a visit of one tab counts as that
tab did.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zoneinfo
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_visit_join import BS, MINUTE_MS, OTHER_VISITOR, T0, VISITOR, JoinCase, tab  # noqa: E402
from cake_server import free_port  # noqa: E402
from web_uploads import KEY  # noqa: E402
from agentcake import cli, config, paths, store, visit_stats, visit_upgrade, visit_verdict  # noqa: E402

UTC = zoneinfo.ZoneInfo("UTC")
NOW = T0 + 60 * MINUTE_MS  # an hour after the visits began: all of them in the last 7 days
GROUPS = visit_stats.GROUPS


class Counts(JoinCase):
    def setUp(self):
        super().setUp()
        os.environ["CAKE_PORT"] = str(free_port())  # no AgentCake answers there: never the person's own
        self.addCleanup(os.environ.pop, "CAKE_PORT", None)
        for n, minutes in enumerate((0, 20, 70, 85)):
            self.send(tab(n), T0 + minutes * MINUTE_MS, page={})
        self.send(tab(4), T0, visitor=OTHER_VISITOR, page={})
        self.send(tab(5), T0, bs=BS, page={})
        self.send(tab(6), T0 + MINUTE_MS, bs=BS, page={})
        self.send(tab(7), T0, visitor=None, page={})
        self.con.commit()

    def counted(self, path=None):
        con = visit_stats.connect_readonly(path or paths.db_file())
        try:
            return visit_stats.counts(con, NOW, UTC)
        finally:
            con.close()

    def visits_by_verdict(self):
        """What the visits table holds: its sessions by verdict, as the pages read a class."""
        found = {"all": 0, **dict.fromkeys(GROUPS, 0)}
        for (cls,) in self.rows("SELECT verdict_class FROM visits"):
            verdict = visit_verdict.CONTRACT["verdicts"].get(cls or visit_verdict.NEVER_JUDGED)
            if verdict is None:
                continue
            found["all"] += 1
            found[next(group for group, name in GROUPS.items() if name == verdict)] += 1
        return found

    def test_one_per_tab_and_across_tabs(self):
        found = self.counted()["7d"]
        self.assertEqual(found["one_per_tab"]["sessions"]["all"], 8)
        self.assertEqual(found["across_tabs"]["sessions"]["all"], 5, "[0, 1], [2, 3], [4], [5, 6], [7]")
        self.assertEqual((found["one_per_tab"]["sessions"]["with_visitor_id"],
                          found["across_tabs"]["sessions"]["with_visitor_id"]), (7, 4))
        self.assertEqual(found["across_tabs"]["tabs"], {"sessions_with_several": 3, "tab_sessions_in_them": 6,
                                                        "most_in_one": 2, "by_count": {2: 3}})
        for key in ("visitors", "page_views"):
            self.assertEqual(found["one_per_tab"][key]["all"], found["across_tabs"][key]["all"], key)
        self.assertEqual(found["across_tabs"]["pages_per_session"]["all"], found["across_tabs"]["page_views"]["all"] / 5)
        self.assertEqual(self.counted()["all"], self.counted()["7d"])

    def test_an_older_database_counts_as_its_upgrade_makes_it(self):
        expected = self.counted()
        self.con.execute("DELETE FROM visits")
        self.con.execute("UPDATE session_web SET visit_id=NULL")
        self.con.commit()
        self.assertEqual(self.counted(), expected, "visits or none, the same tab sessions count the same")
        self.con.close()
        visit_upgrade.step(T0)
        self.con = visit_stats.connect_readonly(paths.db_file())
        self.addCleanup(self.con.close)
        across = self.counted()["all"]["across_tabs"]["sessions"]
        self.assertEqual({key: across[key] for key in ("all", *GROUPS)}, self.visits_by_verdict())
        self.assertEqual(self.counted(), expected)

    def test_a_copy_is_read_without_a_file_changing_or_appearing_and_no_id_is_printed(self):
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        folder = tempfile.mkdtemp(prefix="cake-copy-")
        self.addCleanup(shutil.rmtree, folder, True)
        copy = os.path.join(folder, "cake.db")
        shutil.copyfile(paths.db_file(), copy)
        with open(copy, "rb") as f:
            before = hashlib.sha256(f.read()).hexdigest()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["session-counts", "--db", copy]), 0)
        with open(copy, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), before)
        self.assertEqual(os.listdir(folder), ["cake.db"])
        printed = out.getvalue()
        self.assertIn("across_tabs", json.loads(printed)["all"])
        for name in [tab(n) for n in range(8)] + [BS, VISITOR, OTHER_VISITOR, folder]:
            self.assertNotIn(name, printed)

    def test_a_database_an_agentcake_runs_on_is_read_beside_it_never_immutable(self):
        """Immutable, SQLite takes no lock and reads no write-ahead log: only for a database nothing writes meanwhile.
        A running AgentCake closes its last connection after an upload, which writes the log into cake.db and removes
        it, so no log (or an empty one) alone is no such sign."""
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        opened, connect = [], sqlite3.connect
        for running, immutable in ((True, False), (False, True)):
            def recorded(address, **kwargs):
                opened.append(address)
                return connect(address, **kwargs)
            with self.subTest(running=running), mock.patch("agentcake.daemon.running_here", return_value=running), \
                    mock.patch("agentcake.visit_stats.sqlite3.connect", recorded):
                visit_stats.connect_readonly(paths.db_file()).close()
            self.assertEqual("immutable=1" in opened[-1], immutable)

    def test_a_tab_that_does_not_count_still_joins_tabs_as_the_collector_joins_them(self):
        self.send(tab(10), T0 + 200 * MINUTE_MS, page={})
        self.send(tab(11), T0 + 225 * MINUTE_MS, page={})  # a prefetch: it counts for nothing, but its page loaded
        self.send(tab(12), T0 + 250 * MINUTE_MS, page={})
        self.con.execute("UPDATE sessions SET verdict_class='excluded' WHERE id=?", (tab(11),))
        self.con.execute("DELETE FROM visits")
        self.con.execute("UPDATE session_web SET visit_id=NULL")
        self.con.commit()
        found = self.counted()["all"]["across_tabs"]
        self.con.close()
        visit_upgrade.step(T0)
        self.con = visit_stats.connect_readonly(paths.db_file())
        self.addCleanup(self.con.close)
        self.assertEqual(self.one("SELECT visit_id FROM session_web WHERE session_id=?", tab(12)), (tab(10),),
                         "25 minutes from tab 10 to the prefetch, 25 more to tab 12: one session")
        self.assertEqual({key: found["sessions"][key] for key in ("all", *GROUPS)}, self.visits_by_verdict())
        self.assertEqual(found["tabs"]["sessions_with_several"], 4, "[0, 1], [2, 3], [5, 6] and [10, 12]")

    def test_sessions_of_one_tab_count_the_same_both_ways(self):
        self.con.close()
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-visit-stats-test-")
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)
        for n, minutes in enumerate((0, 40, 90)):  # 40 and 50 minutes apart: three sessions of one tab each
            self.send(tab(n), T0 + minutes * MINUTE_MS, page={})
        self.send(tab(3), T0, visitor=OTHER_VISITOR, page={})
        self.con.commit()
        found = self.counted()["7d"]
        self.assertEqual(found["across_tabs"], found["one_per_tab"])
        self.assertEqual(found["across_tabs"]["sessions"]["all"], 4)

    def test_no_database_is_an_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["session-counts", "--db", os.path.join(tempfile.mkdtemp(), "cake.db")]), 1)
        self.assertIn("no database", out.getvalue())


if __name__ == "__main__":
    unittest.main()
