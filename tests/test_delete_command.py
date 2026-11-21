"""`agentcake delete` and POST /api/delete: agentcake/delete_command.py, api/deletion.py, routes.py.

    python3 -I -m unittest discover -s tests -p test_delete_command.py -v      (from the AgentCake folder)

The command deletes in its own process when no cake runs on the data folder, and asks the running cake otherwise (a
real `agentcake serve` here, whose output goes to cake.log as `agentcake start` sets it up); --session and --visitor
name the same rows; --dry-run changes nothing; ids cake never makes, and a pid file of a live process that does not
answer, stop it. The endpoint deletes only for this computer's own pages, and only the local listener has it.
"""
import json
import os
import subprocess
import sys
import unittest
from http import HTTPStatus
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cake_server import START_TIMEOUT_S, free_port  # noqa: E402
from delete_fixtures import ROOT, Planted, chunk_texts, every_cell, http_status, read_text, run, wait_for  # noqa: E402
from agentcake import cli, config, paths, routes, store, streams  # noqa: E402
from agentcake.api import answers, deletion  # noqa: E402
from agentcake.responses import Request  # noqa: E402

class DeleteCommand(Planted):
    def test_session_and_visitor_name_the_same_rows(self):
        code, out = run("--visitor", self.gone)
        self.assertEqual(code, 0, out)
        self.assert_gone_everywhere()
        self.assert_kept_as_before()
        code, out = run("--session", self.gone)
        self.assertEqual(code, 1, "nothing is left under that id")
        self.assertIn(self.gone, out)

    def test_a_dry_run_changes_nothing(self):
        before = (every_cell(paths.db_file()), chunk_texts(self.home), read_text(paths.log_file()))
        code, out = run("--session", self.gone, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("would delete", out)
        self.assertEqual((every_cell(paths.db_file()), chunk_texts(self.home), read_text(paths.log_file())), before)

    def test_ids_cake_never_makes_are_refused(self):
        for bad in ("../x", "a b", "x" * 41, ""):
            code, out = run("--session", bad)
            self.assertEqual(code, cli.EXIT_USAGE, bad)
        self.assertEqual(run()[0], cli.EXIT_USAGE, "an id is needed")
        self.assertIn(self.gone, every_cell(paths.db_file()), "nothing was deleted")

    def test_a_running_cake_is_asked_to_delete(self):
        answer = {"sessions": [{"id": self.gone, "found": True, "rows": {"sessions": 1}, "chunks": 3, "chunk_bytes": 99}],
                  "reclaim": None, "database": {"vacuumed": True, "log_cleared": True}, "backups": [], "log_lines": 0}
        with mock.patch("agentcake.daemon.running", return_value={"home": self.home}), \
                mock.patch("agentcake.delete_command.ask_running_cake", return_value=answer) as ask:
            code, out = run("--session", self.gone)
        self.assertEqual(code, 0, out)
        ask.assert_called_once()
        self.assertIn(self.gone, every_cell(paths.db_file()), "the running cake deletes, not this process")

    def test_a_pid_file_of_a_live_process_that_does_not_answer_stops_the_command(self):
        with open(paths.pid_file(), "w") as f:
            f.write(str(os.getpid()))
        code, out = run("--session", self.gone)
        self.assertEqual(code, 1)
        self.assertIn(str(os.getpid()), out)
        self.assertIn(self.gone, every_cell(paths.db_file()), "nothing was deleted")


class DeleteWhileRunning(Planted):
    """A real `agentcake serve` on a free port, its output appended to cake.log as `agentcake start` sets it up: the
    command asks it, and it deletes while it runs (the settings page's way too)."""

    def test_the_running_cake_deletes_and_keeps_running(self):
        port = str(free_port())
        os.environ["CAKE_PORT"] = port  # restored by Planted's patch of os.environ
        config.save_user(lists_auto_update=False)  # a test never goes online (agentcake/updates.py)
        command = [sys.executable, "-I", os.path.join(ROOT, "agentcake", "__main__.py"), "serve"]
        with open(paths.log_file(), "a") as log:
            server = subprocess.Popen(command, env=dict(os.environ), stdout=log, stderr=log)
        self.addCleanup(server.wait, START_TIMEOUT_S)
        self.addCleanup(server.terminate)
        base = f"http://127.0.0.1:{port}"
        wait_for(lambda: http_status(base + "/api/health") == HTTPStatus.OK)
        inode = os.stat(paths.log_file()).st_ino
        code, out = run("--session", self.gone)
        self.assertEqual(code, 0, out)
        self.assertEqual(http_status(base + "/api/health"), HTTPStatus.OK, "still running")
        for tag in (self.gone, self.gone_canary):
            self.assertNotIn(tag, every_cell(paths.db_file()))
            self.assertNotIn(tag, chunk_texts(self.home))
            self.assertNotIn(tag, every_cell(self.backup))
        log = read_text(paths.log_file())
        self.assertNotIn(self.gone, log)
        self.assertIn(f"note {self.kept}", log)
        self.assertIn("serving", log.split("end\n", 1)[1], "the server's own line, written after the planted ones")
        self.assertEqual(os.stat(paths.log_file()).st_ino, inode, "the server still writes to the same file")
        con = store.db()
        try:
            self.assertEqual(list(streams.read_events(con, self.kept)), self.kept_events)
        finally:
            con.close()


class DeleteEndpoint(Planted):
    def post(self, body, **headers):
        port = os.environ["CAKE_PORT"]
        sent = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json", **headers}
        return deletion.view(Request("/api/delete", {}, sent, json.dumps(body).encode()))

    def test_this_computers_page_deletes(self):
        port = os.environ["CAKE_PORT"]
        answer = self.post({"sessions": [self.gone]}, Origin=f"http://localhost:{port}")
        self.assertEqual(answer.status, HTTPStatus.OK, answer.body)
        self.assertEqual(json.loads(answer.body)["sessions"][0]["found"], True)
        self.assert_gone_everywhere()

    def test_the_settings_page_deletes_everything_at_once(self):
        # the settings page's "Delete all data", after its Dialog: every session in the database, each as thoroughly as one
        port = os.environ["CAKE_PORT"]
        answer = self.post({"all": True}, Origin=f"http://127.0.0.1:{port}")
        self.assertEqual(answer.status, HTTPStatus.OK, answer.body)
        self.assertEqual(sorted(s["id"] for s in json.loads(answer.body)["sessions"]), sorted([self.gone, self.kept]))
        self.assert_gone_everywhere()
        for tag in (self.kept, self.kept_canary):
            self.assertNotIn(tag, every_cell(paths.db_file()))
        self.assertEqual(json.loads(self.post({"all": True}).body)["sessions"], [], "nothing left: nothing to do")

    def test_anything_else_is_refused_and_nothing_is_deleted(self):
        port = os.environ["CAKE_PORT"]
        refused = [(self.post({"sessions": [self.gone]}, Origin="https://evil.example"), HTTPStatus.FORBIDDEN),
                   (self.post({"sessions": [self.gone]}, Host=f"evil.example:{port}"), HTTPStatus.FORBIDDEN),
                   (self.post({"sessions": [self.gone]}, **{"Content-Type": "text/plain"}), HTTPStatus.UNSUPPORTED_MEDIA_TYPE),
                   (self.post({"sessions": ["../x"]}), HTTPStatus.BAD_REQUEST),
                   (self.post({"sessions": []}), HTTPStatus.BAD_REQUEST),
                   (self.post(["not", "an", "object"]), HTTPStatus.BAD_REQUEST),
                   (self.post({"all": "yes"}), HTTPStatus.BAD_REQUEST),
                   (self.post({"all": True, "sessions": [self.gone]}), HTTPStatus.BAD_REQUEST)]
        for answer, status in refused:
            self.assertEqual(answer.status, status, answer.body)
            self.assertIn("error", json.loads(answer.body))
        self.assertIn(self.gone, every_cell(paths.db_file()))

    def test_only_the_local_listener_has_it(self):
        self.assertIs(routes.resolve(routes.LOCAL, "POST", "/api/delete"), deletion.view)
        self.assertIsNone(routes.resolve(routes.PUBLIC, "POST", "/api/delete"))
        self.assertIs(routes.resolve(routes.LOCAL, "GET", "/api/delete"), answers.no_route)  # a JSON 404


if __name__ == "__main__":
    unittest.main()
