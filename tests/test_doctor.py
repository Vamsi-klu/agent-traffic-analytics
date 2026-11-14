"""`agentcake doctor` (S1.1, S2.2): agentcake/doctor.py's replay storage line and its checks of the user's own website.

    python3 -I -m unittest discover -s tests -p test_doctor.py -v      (from the cake folder)

The checks of the running server need a running cake and are covered in tests/test_cli.py. Here: a fresh data folder
passes, and so does one not made yet whose nearest existing folder above can be written (doctor before the first
start), but not one below a file or a read-only folder, and the line says why; a Python without compression.zstd still
passes but says replays go to zlib; zstd chunks on such a Python fail. A write refused with EPERM or EACCES in a folder
whose permissions allow it is a sandbox's doing (GOAL T7: Codex's showed replay storage as FAIL and the user was told to
look into the storage): that line is a SKIP that says so and asks for doctor in the user's own terminal, also under a
real macOS sandbox (sandbox-exec, where it can run).
The website checks (`doctor --dir`) need no server: every page of a static site must load this cake's page script with
its site key; a page without it is named; a data folder with no site key yet fails the check instead of crashing.
Reaching Agent Cake (S6.1): nothing listening is "not running, start it"; a connection a sandbox forbids (EPERM, EACCES,
ENETUNREACH) is said to be the sandbox's doing, never "not running", and the lines that need the server are skipped.
The running server's lines, with its answers made up (D37: there is no demo shop to check): the page script line
passes when /cake.js answers with this installation's site key in it, and a visit has arrived once a self-check or a
real session has.
WARN and SKIP lines are printed and do not fail doctor. The other lines S6.1 added have their own test files:
test_doctor_machine.py, test_doctor_site.py, test_doctor_live.py.
"""
import contextlib
import errno
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import codecs, config, doctor, doctor_lines, paths, store, streams, wording  # noqa: E402
from cake_server import free_port  # noqa: E402

BASE = 1794517500000
SITE_KEY = "ck_doctortest"
SANDBOX_EXEC = "/usr/bin/sandbox-exec"  # macOS's command-line sandbox, the mechanism under Codex's and Claude Code's
# A sandbox profile that allows everything but writing in one folder, as an AI tool's allows writing only in its own.
DENY_WRITING_IN = '(version 1)(allow default)(deny file-write* (subpath "{folder}"))'


class ScratchHome(unittest.TestCase):
    """A scratch CAKE_HOME, and a $CAKE_PORT nothing listens on (doctor finds no running cake)."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        env.start()
        self.addCleanup(env.stop)


class ReplayStorage(ScratchHome):
    def test_a_fresh_data_folder_passes(self):
        name, ok, info = doctor.replay_storage()
        self.assertEqual(name, "replay storage")
        self.assertTrue(ok, info)
        self.assertIn(codecs.writer_codec(), info)

    def test_before_the_data_folder_exists_it_passes_when_it_can_be_made(self):
        # doctor before the first start, or after the data folder was deleted: start makes it in the folder above
        with mock.patch.dict(os.environ, {"CAKE_HOME": os.path.join(self.home, "not", "there")}):
            _, ok, info = doctor.replay_storage()
        self.assertTrue(ok, info)
        self.assertFalse(os.path.exists(os.path.join(self.home, "not")), "doctor makes no folder")

    def test_a_file_where_the_data_folder_would_go_fails(self):
        blocker = os.path.join(self.home, "file")
        open(blocker, "w").close()
        with mock.patch.dict(os.environ, {"CAKE_HOME": os.path.join(blocker, "cake")}):
            _, ok, info = doctor.replay_storage()
        self.assertFalse(ok, info)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root may write in any folder")
    def test_a_data_folder_that_cannot_be_made_fails(self):
        locked = os.path.join(self.home, "locked")
        os.mkdir(locked)
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)  # readable, not writable
        self.addCleanup(os.chmod, locked, stat.S_IRWXU)
        with mock.patch.dict(os.environ, {"CAKE_HOME": os.path.join(locked, "cake")}):
            _, ok, info = doctor.replay_storage()
        self.assertIs(ok, False, info)
        self.assertIn(wording.text("doctor_replays_not_writable", error=os.strerror(errno.EACCES)), info)

    def refused(self, error_number):
        """replay_storage() while every write in the data folder is refused with error_number."""
        refusal = OSError(error_number, os.strerror(error_number))
        with mock.patch.object(doctor, "write_refusal", return_value=refusal):
            return doctor.replay_storage()

    def test_a_write_a_sandbox_refuses_is_skipped_not_failed(self):
        # the folder's permissions allow writing (a fresh data folder), yet the write is refused: a sandbox's doing
        os.makedirs(os.path.join(self.home, "replays"))
        for error_number in (errno.EPERM, errno.EACCES):
            with self.subTest(error=errno.errorcode[error_number]):
                _, verdict, info = self.refused(error_number)
                self.assertEqual(verdict, doctor_lines.SKIP)
                self.assertEqual(info, wording.text(
                    "doctor_replays_blocked", folder=paths.tilde(os.path.join(self.home, "replays")),
                    error=os.strerror(error_number), launcher=paths.launcher()))

    def test_another_refused_write_fails_with_its_words(self):
        _, verdict, info = self.refused(errno.EROFS)
        self.assertIs(verdict, False)
        self.assertIn(wording.text("doctor_replays_not_writable", error=os.strerror(errno.EROFS)), info)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root may write in any folder")
    def test_a_refused_write_where_the_permissions_forbid_it_fails(self):
        replays = os.path.join(self.home, "replays")
        os.mkdir(replays, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, replays, stat.S_IRWXU)
        _, verdict, info = self.refused(errno.EACCES)
        self.assertIs(verdict, False, info)

    def test_under_a_real_sandbox_that_forbids_writing_the_line_is_a_skip(self):
        if not os.access(SANDBOX_EXEC, os.X_OK):
            self.skipTest("needs macOS's sandbox-exec")
        allowed = subprocess.run([SANDBOX_EXEC, "-p", "(version 1)(allow default)", sys.executable, "-c", ""],
                                 capture_output=True)
        if allowed.returncode:  # already inside a sandbox, which cannot start another
            self.skipTest("sandbox-exec cannot start a sandbox here")
        home = os.path.realpath(self.home)  # the profile matches real paths (/var is /private/var)
        os.makedirs(os.path.join(home, "replays"))
        profile = DENY_WRITING_IN.format(folder=home)
        main = os.path.join(HERE, "agentcake", "__main__.py")
        done = subprocess.run([SANDBOX_EXEC, "-p", profile, sys.executable, "-I", main, "doctor"],
                              env=dict(os.environ, CAKE_HOME=home), capture_output=True, text=True)
        line = next(line for line in done.stdout.splitlines() if f"] {wording.text('doctor_replays')}: " in line)
        self.assertEqual(line, wording.text(
            "doctor_line", verdict=wording.text("doctor_skip"), check=wording.text("doctor_replays"),
            info=wording.text("doctor_replays_blocked", folder=paths.tilde(os.path.join(home, "replays")),
                              error=os.strerror(errno.EPERM), launcher=paths.launcher())))

    def test_without_zstd_it_passes_and_says_zlib(self):
        with mock.patch.object(codecs, "ZSTD", None):
            _, ok, info = doctor.replay_storage()
        self.assertTrue(ok)
        self.assertIn("zlib", info)
        self.assertIn("compression.zstd", info)

    def test_zstd_chunks_on_a_python_without_zstd_fail(self):
        if codecs.ZSTD is None:
            self.skipTest("writing a zstd chunk needs compression.zstd")
        con = store.db()
        streams.append(con, "s1", "rrweb", [(BASE, '{"type":3}')], BASE)
        streams.seal(con, BASE, force=True)
        con.commit()
        con.close()
        with mock.patch.object(codecs, "ZSTD", None):
            _, ok, info = doctor.replay_storage()
        self.assertFalse(ok)
        self.assertIn("1 stored chunks are zstd", info)


class WebsiteChecks(ScratchHome):
    """`agentcake doctor --dir <site>` on a static site of two pages."""

    def setUp(self):
        super().setUp()
        self.site = tempfile.mkdtemp(prefix="cake-test-site-")
        self.addCleanup(shutil.rmtree, self.site, True)

    def page(self, name, carries_script):
        tag = f'<script src="{config.base_url()}/cake.js" data-site="{SITE_KEY}" defer></script>'
        if not carries_script:
            tag = ""
        with open(os.path.join(self.site, name), "w", encoding="utf-8") as f:
            f.write(f"<html><head>{tag}</head><body></body></html>")

    def settings(self, **values):
        with open(os.path.join(self.home, "config.json"), "w", encoding="utf-8") as f:
            json.dump(values, f)

    def doctor_lines(self):
        """doctor's printed lines for the site, and its exit code."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.doctor(self.site)
        return out.getvalue().splitlines(), code

    def script_line(self, lines):
        name = wording.text("doctor_site_script")
        return next(line for line in lines if f"] {name}: " in line)

    def test_every_page_with_the_script_passes(self):
        self.settings(site_key=SITE_KEY, site_domain="example.com", site_dir=self.site)
        self.page("index.html", True)
        self.page("about.html", True)
        lines, _ = self.doctor_lines()
        self.assertEqual(self.script_line(lines), wording.text(
            "doctor_line", verdict="PASS", check=wording.text("doctor_site_script"), info="about.html, index.html"))
        self.assertIn(wording.text("doctor_line", verdict="PASS", check=wording.text("doctor_site_settings"),
                                   info=wording.text("doctor_site_domain", domain="example.com")), lines)

    def test_a_page_without_the_script_is_named(self):
        self.settings(site_key=SITE_KEY, site_domain="example.com", site_dir=self.site)
        self.page("index.html", True)
        self.page("about.html", False)
        lines, code = self.doctor_lines()
        self.assertTrue(self.script_line(lines).startswith("[FAIL]"))
        self.assertIn(wording.text("doctor_site_missing_in", files="about.html"), self.script_line(lines))
        self.assertEqual(code, 1)

    def test_no_site_key_yet_fails_the_check_instead_of_crashing(self):
        self.page("index.html", True)  # config.json does not exist yet: no site key
        lines, code = self.doctor_lines()
        self.assertEqual(self.script_line(lines), wording.text(
            "doctor_line", verdict="FAIL", check=wording.text("doctor_site_script"),
            info=wording.text("doctor_site_found_none") + wording.text("doctor_site_missing_in", files="index.html")))
        self.assertEqual(code, 1)


class Reach(ScratchHome):
    """How doctor tells "nothing listens on 127.0.0.1" from "this process may not connect there" (GOAL T2: a sandbox
    without network, such as Codex's workspace-write, fails the connection with EPERM while Agent Cake runs outside)."""

    def doctor_output(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.doctor()
        return out.getvalue(), code

    def test_nothing_listening_says_not_running_and_to_start_it(self):
        reached = doctor.reach(config.load_cfg())
        self.assertEqual((reached.health, reached.problem), (None, doctor.REFUSED))
        output, code = self.doctor_output()
        self.assertIn(wording.text("doctor_start_it", launcher=paths.launcher()), output)
        self.assertEqual(code, 1)

    def test_a_sandbox_that_forbids_the_connection_is_not_called_agent_cake_down(self):
        for error in (errno.EPERM, errno.EACCES, errno.ENETUNREACH):
            with self.subTest(error=errno.errorcode[error]):
                refused = OSError(error, os.strerror(error))
                with mock.patch("socket.create_connection", side_effect=refused):
                    self.assertEqual(doctor.reach(config.load_cfg()).problem, doctor.BLOCKED)
                    output, code = self.doctor_output()
                self.assertIn(wording.text("doctor_blocked", base=config.base_url(), error=os.strerror(error)), output)
                self.assertIn(wording.text("doctor_blocked_next", launcher=paths.launcher()), output)
                self.assertNotIn(wording.text("doctor_start_it", launcher=paths.launcher()), output)
                self.assertNotIn(wording.text("doctor_not_running"), output)
                self.assertIn(f"[SKIP] {wording.text('doctor_page')}: {wording.text('doctor_not_checked_blocked')}", output)
                self.assertEqual(code, 1)

    def test_another_error_is_reported_as_it_is(self):
        with mock.patch("socket.create_connection", side_effect=TimeoutError("timed out")):
            reached = doctor.reach(config.load_cfg())
        self.assertIsNone(reached.health)
        self.assertEqual(reached.problem, "timed out")


class ServerChecks(ScratchHome):
    """doctor.server_checks() on a cake that answered its health check; the local page and cake.js answers made up."""

    def setUp(self):
        super().setUp()
        config.save_user(site_key=SITE_KEY)
        self.c, self.base = config.load_cfg(), config.base_url()

    def lines(self, script=(200, f'window.cake={{"site_key":"{SITE_KEY}"}}'), selfcheck=0, real=0):
        answers = {self.base + "/": (200, "<html>"), self.base + "/cake.js": script}
        health = {"ok": True, "selfcheck_visits": selfcheck, "real_sessions": real}
        with mock.patch.object(doctor, "http_get", side_effect=lambda url, timeout: answers[url]) as asked:
            checks = doctor.server_checks(self.c, doctor.Reach(health, None, None), self.base)
        self.assertNotIn(self.base + "/demo", [call.args[0] for call in asked.call_args_list], "no demo shop to open")
        return {check: (verdict, info) for check, verdict, info in checks}

    def test_the_page_script_line_passes_with_this_site_key(self):
        verdict, info = self.lines()[wording.text("doctor_script")]
        self.assertIs(verdict, True)
        self.assertEqual(info, wording.text("doctor_script_info", base=self.base, status=200))

    def test_the_page_script_line_fails_without_the_script_or_the_site_key(self):
        for script in ((404, "not found"), (None, "connection refused"), (200, "window.cake={}")):
            with self.subTest(script=script):
                self.assertIs(self.lines(script=script)[wording.text("doctor_script")][0], False)

    def test_a_visit_has_arrived_once_a_self_check_or_a_real_session_has(self):
        visit = wording.text("doctor_visit")
        self.assertIs(self.lines()[visit][0], False)
        self.assertIs(self.lines(selfcheck=1)[visit][0], True)
        self.assertIs(self.lines(real=2)[visit][0], True, "a server that records real visits never needs ping")
        self.assertEqual(self.lines(selfcheck=1, real=2)[visit][1],
                         wording.text("doctor_visit_info", selfcheck=1, real=2))

    def test_the_words_name_no_demo_shop(self):
        for check, (_, info) in self.lines(selfcheck=1).items():
            self.assertNotIn("demo", (check + info).lower())


class Verdicts(unittest.TestCase):
    def test_warn_and_skip_are_printed_and_do_not_fail(self):
        checks = [("a", True, "x"), ("b", doctor_lines.WARN, "y"), ("c", doctor_lines.SKIP, "z")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            doctor_lines.print_checks(checks)
        self.assertEqual(out.getvalue().splitlines(), ["[PASS] a: x", "[WARN] b: y", "[SKIP] c: z"])
        self.assertTrue(doctor_lines.passed(checks))
        self.assertFalse(doctor_lines.passed(checks + [("d", False, "w")]))


if __name__ == "__main__":
    unittest.main()
