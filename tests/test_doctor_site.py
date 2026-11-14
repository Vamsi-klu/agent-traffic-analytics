"""`agentcake doctor --dir <site>`, the lines about the website's files (S6.1): agentcake/doctor_site.py.

    python3 -I -m unittest discover -s tests -p test_doctor_site.py -v      (from the Agent Cake folder)

On test copies of a static site, an Express, a Next.js and a Flask site (tests/site_fixtures.py), connected the way
setup --print --site says, every website line passes. With the cake.js line deleted from one file, or the
middleware's mounting line or one of its copied files deleted, doctor fails and names that file or that mounting. In
server mode the pages must load /cake/cake.js from the site's own domain. No server runs here: these lines read files.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import config, doctor, doctor_lines, doctor_site, site_setup, wording  # noqa: E402
from cake_server import free_port  # noqa: E402
from site_fixtures import T7_KINDS, make_site  # noqa: E402

SITE_KEY = "ck_doctorsite"
DOMAIN = "brewbean.example"
MOUNTED_IN = {"express": "server.js", "next-app": "middleware.ts", "flask": "app.py"}
SCRIPT_IN = {"static": "about.html", "express": os.path.join("views", "layout.ejs"),
             "next-app": os.path.join("app", "layout.tsx"), "flask": os.path.join("templates", "base.html")}


class Site(unittest.TestCase):
    """A scratch CAKE_HOME with a site key, and a test copy of a website connected to it."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.folder = tempfile.mkdtemp(prefix="cake-test-site-")
        for folder in (self.home, self.folder):
            self.addCleanup(shutil.rmtree, folder, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        env.start()
        self.addCleanup(env.stop)
        self.settings()

    def settings(self, **more):
        values = {"site_key": SITE_KEY, "site_domain": DOMAIN, "site_dir": self.folder, **more}
        with open(os.path.join(self.home, "config.json"), "w", encoding="utf-8") as f:
            json.dump(values, f)

    def connect(self, kind, mounted=True):
        """The site, with the line setup --print --site gives for its framework."""
        c = config.load_cfg()
        tag = site_setup.next_tag(c) if kind.startswith("next") else site_setup.snippet(c)
        return make_site(kind, self.folder, tag, mounted)

    def checks(self):
        return {name: (ok, info) for name, ok, info in doctor_site.website_checks(config.load_cfg(), self.folder)}

    def line(self, name):
        return self.checks()[wording.text(name)]

    def remove_line(self, relative, needle):
        path = os.path.join(self.folder, relative)
        with open(path, encoding="utf-8") as f:
            kept = [line for line in f.read().splitlines(keepends=True) if needle not in line]
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(kept))


class FourSites(Site):
    def test_every_website_line_passes_on_each_connected_site(self):
        for kind in T7_KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.connect(kind)
                for name, (ok, info) in self.checks().items():
                    self.assertIn(ok, (True, doctor_lines.SKIP), f"{kind}: {name}: {info}")

    def test_doctor_passes_on_each_connected_site(self):
        for kind in T7_KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.connect(kind)
                lines = run_doctor(self.folder)[0]
                site = lines[lines.index(wording.text("doctor_site_header")) + 1:]
                self.assertFalse([line for line in site if line.startswith("[FAIL]")], "\n".join(lines))

    def test_the_static_site_needs_no_middleware(self):
        self.connect("static")
        ok, info = self.line("doctor_site_middleware")
        self.assertEqual(ok, doctor_lines.SKIP)
        self.assertEqual(info, wording.text("doctor_site_middleware_static"))


class DeletedScript(Site):
    def test_the_file_without_the_line_is_named(self):
        for kind in T7_KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.connect(kind)
                self.remove_line(SCRIPT_IN[kind], SITE_KEY)
                ok, info = self.line("doctor_site_script")
                self.assertIs(ok, False)
                self.assertIn(wording.text("doctor_site_missing_in", files=SCRIPT_IN[kind]), info)


class DeletedMiddleware(Site):
    def test_the_mounting_that_is_gone_is_named(self):
        names = {"express": "cakeExpress", "next-app": "cakeNext", "flask": "CakeEdgeWSGI"}
        for kind, mounted_in in MOUNTED_IN.items():
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.connect(kind)
                self.remove_line(mounted_in, names[kind] + "(")
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, False)
                self.assertEqual(info, wording.text("doctor_site_middleware_none", middleware=names[kind]))

    def test_a_middleware_file_deleted_beside_the_app_is_named(self):
        self.connect("flask")
        os.remove(os.path.join(self.folder, "cake_edge.json"))
        ok, info = self.line("doctor_site_middleware")
        self.assertIs(ok, False)
        self.assertIn(wording.text("doctor_site_middleware_beside", files="cake_edge.json"), info)

    def test_doctor_fails_and_says_which_line(self):
        self.connect("express", mounted=False)
        lines, code = run_doctor(self.folder)
        self.assertEqual(code, 1)
        self.assertIn(wording.text("doctor_line", verdict="FAIL", check=wording.text("doctor_site_middleware"),
                                   info=wording.text("doctor_site_middleware_none", middleware="cakeExpress")), lines)

    def test_wordpress_without_the_plugin_is_named(self):
        make_site("wordpress", self.folder, None, mounted=False)
        ok, info = self.line("doctor_site_middleware")
        self.assertIs(ok, False)
        self.assertEqual(info, wording.text("doctor_site_plugin_none"))


class ServerMode(Site):
    def setUp(self):
        super().setUp()
        self.settings(public_listen="0.0.0.0:8080", path_prefix="/cake")

    def test_pages_loading_the_script_from_the_sites_own_path_pass(self):
        self.connect("static")
        ok, info = self.line("doctor_site_script")
        self.assertIs(ok, True, info)

    def test_pages_still_loading_it_from_127_0_0_1_fail(self):
        tag = f'<script src="{config.base_url()}/cake.js" data-site="{SITE_KEY}" defer></script>'
        make_site("static", self.folder, tag)
        ok, _ = self.line("doctor_site_script")
        self.assertIs(ok, False)


def run_doctor(folder=None, url=None):
    """doctor's printed lines and its exit code (no Agent Cake runs: the first lines fail, the site's are read)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = doctor.doctor(folder, url)
    return out.getvalue().splitlines(), code


if __name__ == "__main__":
    unittest.main()
