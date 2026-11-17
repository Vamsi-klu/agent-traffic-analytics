"""`agentcake doctor` opening a page of the user's website: agentcake/doctor_live.py.

    python3 -I -m unittest discover -s tests -p test_doctor_live.py -v      (from the AgentCake folder)

The website here is a WSGI app on a free port of 127.0.0.1, run by wsgiref, behind AgentCake's own Python middleware
(edge/python/cake_edge.py, the file a Flask or Django site copies) holding this scratch CAKE_HOME's secret. doctor asks
for the page the way a browser opens it and reads what came back: the page loads cake.js with this site key; the
response carries a token this AgentCake's secret signed, in its time window; the token holds the Sec-Fetch values and
the signature headers doctor sent. A middleware that is not mounted, a token signed with another secret or with a clock
far off, a proxy in front of the site that drops headers, a page without cake.js: each fails its own line and says why.
"""
import contextlib
import errno
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import wsgiref.simple_server
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "edge", "python"))
sys.path.insert(0, HERE)
import cake_edge  # noqa: E402  (the middleware file a site copies, loaded the way the site loads it)
from agentcake import config, doctor, doctor_lines, doctor_live, edge_secret, site_setup, wording  # noqa: E402
from agentcake.units import MS_PER_S  # noqa: E402
from cake_server import AGENTCAKE, POLL_S, free_port  # noqa: E402
from site_fixtures import make_site, page  # noqa: E402

SITE_KEY = "ck_doctorpage"
OTHER_SECRET = "another AgentCake's secret, long enough to sign with"
HOUR_MS = 3600 * MS_PER_S
SECRET_ENV = "CAKE_SERVER_TIMING_SECRET"
SOCKET_READ = 4096  # bytes: more than doctor's request
NAMES = ("doctor_live_script", "doctor_live_token", "doctor_live_sec_fetch", "doctor_live_signature")


class QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):
        pass


class Website:
    """A WSGI app served on a free port of 127.0.0.1 in a thread, until close()."""

    def __init__(self, app):
        self.server = wsgiref.simple_server.make_server("127.0.0.1", 0, app, handler_class=QuietHandler)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": POLL_S}, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def html_app(html):
    def app(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [html.encode("utf-8")]
    return app


def proxy_dropping(app, *names):
    """What reaches the site's server when a proxy in front of it removes these request headers."""
    dropped = {"HTTP_" + name.upper().replace("-", "_") for name in names}

    def proxy(environ, start_response):
        return app({key: value for key, value in environ.items() if key not in dropped}, start_response)
    return proxy


class PageChecks(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())}
        patched = mock.patch.dict(os.environ, self.env)
        patched.start()
        self.addCleanup(patched.stop)
        with open(os.path.join(self.home, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"site_key": SITE_KEY}, f)
        edge_secret.create_secret()
        self.secret = edge_secret.srv_secret()
        self.page = page("Brew Bean", site_setup.snippet(config.load_cfg()))

    def serve(self, app):
        site = Website(app)
        self.addCleanup(site.close)
        return site.url

    def mounted(self, html=None, secret=None, **options):
        return cake_edge.CakeEdgeWSGI(html_app(html or self.page), secret=secret or self.secret, **options)

    def checks(self, url, framework="flask"):
        return {name: (ok, info) for name, ok, info in doctor_live.page_checks(config.load_cfg(), url, framework)}

    def line(self, checks, name):
        return checks[wording.text(name)]


class Connected(PageChecks):
    def test_a_page_behind_the_middleware_passes_every_line(self):
        checks = self.checks(self.serve(self.mounted()))
        for name in NAMES:
            ok, info = self.line(checks, name)
            self.assertIs(ok, True, f"{name}: {info}")

    def test_doctor_url_on_the_command_line(self):
        url = self.serve(self.mounted())
        out = subprocess.run(AGENTCAKE + ["doctor", "--url", url], env=dict(os.environ, **self.env),
                             capture_output=True, text=True, timeout=60)
        for name in NAMES:
            self.assertIn(f"[PASS] {wording.text(name)}: ", out.stdout)

    def test_site_url_from_the_settings(self):
        url = self.serve(self.mounted())
        config.save_user(site_url=url)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            doctor.doctor()
        self.assertIn(f"[PASS] {wording.text('doctor_live_token')}: ", out.getvalue())


class Broken(PageChecks):
    def test_no_middleware_means_no_token_and_says_why(self):
        checks = self.checks(self.serve(html_app(self.page)))
        self.assertEqual(self.line(checks, "doctor_live_token"), (False, wording.text("doctor_live_token_none", env=SECRET_ENV)))
        self.assertEqual(self.line(checks, "doctor_live_sec_fetch")[0], doctor_lines.SKIP)

    def test_a_token_signed_with_another_secret_is_named(self):
        checks = self.checks(self.serve(self.mounted(secret=OTHER_SECRET)))
        ok, info = self.line(checks, "doctor_live_token")
        self.assertIs(ok, False)
        self.assertIn(wording.text("doctor_live_token_bad", launcher=doctor_live.paths.launcher()), info)

    def test_a_token_from_a_clock_an_hour_behind_is_stale(self):
        an_hour_ago = time.time_ns() // (MS_PER_S * MS_PER_S) - HOUR_MS
        checks = self.checks(self.serve(self.mounted(now=lambda: an_hour_ago)))
        ok, info = self.line(checks, "doctor_live_token")
        self.assertIs(ok, False)
        self.assertIn(wording.text("doctor_live_token_stale", minutes=60), info)

    def test_a_proxy_dropping_sec_fetch_is_named(self):
        url = self.serve(proxy_dropping(self.mounted(), "sec-fetch-site", "sec-fetch-user"))
        ok, info = self.line(self.checks(url), "doctor_live_sec_fetch")
        self.assertIs(ok, False)
        self.assertEqual(info, wording.text("doctor_live_lost", headers="Sec-Fetch-Site, Sec-Fetch-User"))

    def test_a_proxy_dropping_the_signature_headers_is_named(self):
        url = self.serve(proxy_dropping(self.mounted(), "signature", "signature-input", "signature-agent"))
        checks = self.checks(url)
        ok, info = self.line(checks, "doctor_live_signature")
        self.assertIs(ok, False)
        self.assertEqual(info, wording.text("doctor_live_lost", headers="Signature-Agent, Signature, Signature-Input"))
        self.assertIs(self.line(checks, "doctor_live_sec_fetch")[0], True)

    def test_a_page_without_cake_js_is_named(self):
        url = self.serve(self.mounted(html=page("Brew Bean", "")))
        ok, info = self.line(self.checks(url), "doctor_live_script")
        self.assertIs(ok, False)
        self.assertIn(wording.text("doctor_live_script_none"), info)

    def test_this_agentcake_without_a_secret_says_to_make_one(self):
        url = self.serve(self.mounted())
        os.remove(os.path.join(self.home, "srv_secret"))
        ok, info = self.line(self.checks(url), "doctor_live_token")
        self.assertIs(ok, False)
        self.assertEqual(info, wording.text("doctor_live_no_secret", launcher=doctor_live.paths.launcher()))

    def test_a_page_nobody_answers_says_it_could_not_be_opened(self):
        url = f"http://127.0.0.1:{free_port()}/"
        ok, info = self.line(self.checks(url), "doctor_live_script")
        self.assertIs(ok, False)
        self.assertIn(url, info)
        self.assertEqual(self.line(self.checks(url), "doctor_live_token")[0], doctor_lines.SKIP)

    def test_an_address_that_is_no_url_is_said_not_to_open(self):
        for url in ("localhost:3000", "http://127.0.0.1:notaport/"):
            with self.subTest(url=url):
                ok, info = self.line(self.checks(url), "doctor_live_script")
                self.assertIs(ok, False)
                self.assertIn(url, info)

    def test_a_port_that_does_not_speak_http_is_said_not_to_open(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        self.addCleanup(listener.close)

        def answer_garbage():
            connection, _ = listener.accept()
            with connection:
                connection.recv(SOCKET_READ)
                connection.sendall(b"not http at all\r\n\r\n")
        threading.Thread(target=answer_garbage, daemon=True).start()
        ok, info = self.line(self.checks(f"http://127.0.0.1:{listener.getsockname()[1]}/"), "doctor_live_script")
        self.assertIs(ok, False)

    def test_a_sandbox_that_forbids_the_connection_says_so(self):
        blocked = urllib.error.URLError(PermissionError(errno.EPERM, "Operation not permitted"))
        with mock.patch("urllib.request.urlopen", side_effect=blocked):
            ok, info = self.line(self.checks("http://localhost:3000/"), "doctor_live_script")
        self.assertIs(ok, False)
        self.assertIn(wording.text("doctor_live_blocked"), info)


class StaticSite(PageChecks):
    def test_a_static_site_without_a_token_skips_the_server_half(self):
        checks = self.checks(self.serve(html_app(self.page)), framework="static")
        self.assertIs(self.line(checks, "doctor_live_script")[0], True)
        self.assertEqual(self.line(checks, "doctor_live_token"), (doctor_lines.SKIP, wording.text("doctor_live_token_optional")))

    def test_the_folder_decides_the_framework(self):
        folder = tempfile.mkdtemp(prefix="cake-test-site-")
        self.addCleanup(shutil.rmtree, folder, True)
        make_site("static", folder, site_setup.snippet(config.load_cfg()))
        url = self.serve(html_app(self.page))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.doctor(folder, url)
        self.assertIn(f"[SKIP] {wording.text('doctor_live_token')}: ", out.getvalue())
        self.assertNotIn(f"[FAIL] {wording.text('doctor_live_token')}", out.getvalue())
        self.assertEqual(code, 1)  # no AgentCake runs in this test: its own lines fail


if __name__ == "__main__":
    unittest.main()
