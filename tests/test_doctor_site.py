"""`agentcake doctor --dir <site>`, the lines about the website's files: agentcake/doctor_site.py.

    python3 -I -m unittest discover -s tests -p test_doctor_site.py -v      (from the AgentCake folder)

On test copies of a static site, an Express, a Next.js and a Flask site (tests/site_fixtures.py), connected the way
setup --print --site says, every website line passes. With the cake.js line deleted from one file, or the
middleware's mounting line or one of its copied files deleted, doctor fails and names that file or that mounting. A
Node site needs the middleware's copy in its code (agentcake-edge) and package.json installing it from there: a copy
without a mounting, a mounting without the copy, or package.json installing it from a folder outside the site's code
(what `npm install <AgentCake's edge folder>/node` writes) fails and says what to do. In server mode the pages must load
/cake/cake.js from the site's own domain. No server runs here: these lines read files.
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
from agentcake import config, doctor, doctor_lines, doctor_site, paths, site_setup, wording  # noqa: E402
from cake_server import free_port  # noqa: E402
from site_fixtures import (NODE_COPY, NODE_KINDS, NODE_PACKAGE, T7_KINDS, WORDPRESS_PARTS,  # noqa: E402
                           copy_node_middleware, make_site)

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


class NodeCopy(Site):
    """The Node middleware, copied into the site as agentcake-edge and installed from there."""
    NAMES = {"express": "cakeExpress", "next-app": "cakeNext", "hono": "cakeHono"}

    def fresh(self, kind, mounted=True):
        shutil.rmtree(self.folder)
        os.makedirs(self.folder)
        return self.connect(kind, mounted)

    def depend_on(self, spec, key="dependencies"):
        path = os.path.join(self.folder, "package.json")
        with open(path, encoding="utf-8") as f:
            package = json.load(f)
        package["dependencies"].pop(NODE_PACKAGE, None)
        if spec is not None:
            package.setdefault(key, {})[NODE_PACKAGE] = spec
        with open(path, "w", encoding="utf-8") as f:
            json.dump(package, f)

    def test_each_node_site_passes_with_the_copy_installed_from_its_folder(self):
        for kind in NODE_KINDS:
            with self.subTest(kind=kind):
                self.fresh(kind)
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, True, info)

    def test_the_copy_alone_is_no_mounting(self):
        for kind in NODE_KINDS:
            with self.subTest(kind=kind):
                self.fresh(kind, mounted=False)
                copy_node_middleware(self.folder)
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, False)
                self.assertEqual(info, wording.text("doctor_site_middleware_none", middleware=self.NAMES[kind]))

    def test_a_mounting_without_the_copy_names_the_folder(self):
        for kind in NODE_KINDS:
            with self.subTest(kind=kind):
                self.fresh(kind)
                shutil.rmtree(os.path.join(self.folder, NODE_COPY))
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, False)
                self.assertEqual(info, wording.text("doctor_site_middleware_folder", folder=NODE_COPY,
                                                    launcher=paths.launcher()))

    def test_installed_from_a_folder_outside_the_site_fails_and_names_it(self):
        outside = ("file:../../../../Users/someone/agentcake/edge/node",  # npm install <AgentCake's edge folder>/node
                   "file:/opt/agentcake/agentcake/edge/node", "link:../agentcake/edge/node")
        for spec in outside:
            with self.subTest(spec=spec):
                self.fresh("express")
                self.depend_on(spec)
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, False)
                self.assertEqual(info, wording.text("doctor_site_middleware_package", package=NODE_PACKAGE, spec=spec,
                                                    folder=NODE_COPY))

    def test_not_in_the_dependencies_says_how_to_install_it(self):
        for key in (None, "devDependencies"):
            with self.subTest(listed_in=key):
                self.fresh("next-app")
                self.depend_on(None if key is None else "file:" + NODE_COPY, key or "dependencies")
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, False)
                self.assertEqual(info, wording.text("doctor_site_middleware_unlisted", package=NODE_PACKAGE,
                                                    folder=NODE_COPY))

    def test_a_dev_dependency_is_given_the_command_that_moves_it(self):
        """`npm install ./agentcake-edge` keeps a package devDependencies list where it is (npm 10.8.2: "up to date"),
        so the line would fail again after it; --save-prod moves it into dependencies, and adds it when it is
        missing."""
        for key in (None, "devDependencies"):
            with self.subTest(listed_in=key):
                self.fresh("express")
                self.depend_on(None if key is None else "file:" + NODE_COPY, key or "dependencies")
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, False)
                self.assertTrue(info.endswith(f"npm install --save-prod ./{NODE_COPY}"), info)

    def test_each_command_leaves_the_package_manager_to_the_site_as_setup_does(self):
        """setup says to install the copy with the site's own package manager (npm in a pnpm or Yarn site writes a
        package-lock.json of its own); doctor's lines say so too before they give npm's command."""
        setup = wording.text("setup_site_mw_express", edge="<edge>", file="<file>", beside="", folder=NODE_COPY,
                             mounting="")
        self.assertIn("the package manager that the site uses", setup)
        for entry in ("doctor_site_middleware_unlisted", "doctor_site_middleware_package"):
            with self.subTest(entry=entry):
                said = wording.text(entry, package=NODE_PACKAGE, spec="file:/opt/edge", folder=NODE_COPY)
                self.assertIn("the site's package manager. With npm, run this command:", said)

    def test_each_way_package_managers_write_the_folder_passes(self):
        for spec in ("file:./agentcake-edge", "link:agentcake-edge", "file:agentcake-edge/"):
            with self.subTest(spec=spec):
                self.fresh("hono")
                self.depend_on(spec)
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, True, info)

    def test_a_workspace_dependency_passes_while_the_copy_is_there(self):
        """pnpm's and Yarn's workspace: protocol installs the package of that name among the site's own: the copy.
        Which folders the workspace takes in is not read; one that leaves the copy out fails the site's own install."""
        for spec in ("workspace:*", "workspace:^", "workspace:agentcake-edge"):
            with self.subTest(spec=spec):
                self.fresh("express")
                self.depend_on(spec)
                ok, info = self.line("doctor_site_middleware")
                self.assertIs(ok, True, info)
        shutil.rmtree(os.path.join(self.folder, NODE_COPY))
        self.assertEqual(self.line("doctor_site_middleware"), (False, wording.text(
            "doctor_site_middleware_folder", folder=NODE_COPY, launcher=paths.launcher())))


class JavaScriptNext(Site):
    """A Next.js site written in JavaScript, connected with the mounting setup gives it (its own middleware.js), is
    checked as a TypeScript one is, its layout in app/ or src/app/, as .js or .jsx."""

    def test_every_website_line_passes_and_the_middleware_js_is_found(self):
        for layout in (None, os.path.join("src", "app", "layout.jsx")):
            with self.subTest(layout=layout):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.connect("next-js")
                if layout:
                    os.renames(os.path.join(self.folder, "app", "layout.js"), os.path.join(self.folder, layout))
                    os.renames(os.path.join(self.folder, "middleware.js"), os.path.join(self.folder, "src", "middleware.js"))
                for name, (ok, info) in self.checks().items():
                    self.assertIs(ok, True, f"{name}: {info}")


class PagesRouter(Site):
    """A Next.js site with the Pages Router, its pages/_app.js changed with the return line setup gives, as printed."""

    def test_the_return_line_setup_gives_passes_the_script_line(self):
        make_site("next-pages", self.folder, None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            site_setup.setup_print_site(self.folder)
        returned = next(line.strip() for line in out.getvalue().splitlines() if line.startswith("    return (<>"))
        app = os.path.join(self.folder, "pages", "_app.js")
        with open(app, encoding="utf-8") as f:
            source = f.read()
        with open(app, "w", encoding="utf-8") as f:
            f.write("import Script from 'next/script'\n" + source.replace("return <Component {...pageProps} />", returned))
        for name, (ok, info) in self.checks().items():
            self.assertIs(ok, True, f"{name}: {info}")


class WordPressParts(Site):
    """A folder that holds only a WordPress theme or plugin: AgentCake's plugin is installed on the WordPress site, never
    in this folder, so neither files line fails for its absence (a page opened with site_url checks it)."""

    def test_the_plugin_line_is_skipped_not_failed(self):
        for kind in WORDPRESS_PARTS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                make_site(kind, self.folder, None)
                ok, info = self.line("doctor_site_middleware")
                self.assertEqual(ok, doctor_lines.SKIP)
                self.assertEqual(info, wording.text("doctor_site_plugin_elsewhere"))
                ok, info = self.line("doctor_site_script")
                self.assertEqual(ok, doctor_lines.SKIP)
                self.assertEqual(info, wording.text("doctor_site_script_plugin"))

    def test_doctor_has_no_failing_website_line_on_a_theme_folder(self):
        make_site("wordpress-theme", self.folder, None)
        lines = run_doctor(self.folder)[0]
        site = lines[lines.index(wording.text("doctor_site_header")) + 1:]
        self.assertFalse([line for line in site if line.startswith("[FAIL]")], "\n".join(lines))


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


class SubdomainRoute(Site):
    """The 8th check of doctor_public.py: with public_url, pages load cake.js from AgentCake's own subdomain."""
    PUBLIC_URL = "https://cake." + DOMAIN

    def setUp(self):
        super().setUp()
        self.settings(public_listen="127.0.0.1:8080", path_prefix="/cake", public_url=self.PUBLIC_URL)

    def tag(self, src):
        return f'<script src="{src}" data-site="{SITE_KEY}" defer></script>'

    def test_pages_loading_the_script_from_public_url_pass(self):
        make_site("static", self.folder, self.tag(self.PUBLIC_URL + "/cake/cake.js"))
        ok, info = self.line("doctor_site_script")
        self.assertIs(ok, True, info)

    def test_pages_still_on_the_same_site_path_pass_while_a_site_moves(self):
        make_site("static", self.folder, self.tag("/cake/cake.js"))
        ok, info = self.line("doctor_site_script")
        self.assertIs(ok, True, info)

    def test_pages_loading_it_from_another_subdomain_fail(self):
        make_site("static", self.folder, self.tag("https://stats." + DOMAIN + "/cake/cake.js"))
        ok, _ = self.line("doctor_site_script")
        self.assertIs(ok, False)

    def test_a_computer_that_names_the_server_takes_public_url_too(self):
        self.settings(public_url=self.PUBLIC_URL, path_prefix="/cake")  # no public_listen: not the server itself
        make_site("static", self.folder, self.tag(self.PUBLIC_URL + "/cake/cake.js"))
        ok, info = self.line("doctor_site_script")
        self.assertIs(ok, True, info)


def run_doctor(folder=None, url=None):
    """doctor's printed lines and its exit code (no AgentCake runs: the first lines fail, the site's are read)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = doctor.doctor(folder, url)
    return out.getvalue().splitlines(), code


if __name__ == "__main__":
    unittest.main()
