"""`agentcake setup --print --site`: agentcake/site_setup.py, what a coding agent follows to connect a website.

    python3 -I -m unittest discover -s tests -p test_site_setup.py -v      (from the AgentCake folder)

For each framework it names the files to change and the line to add: every page of a static site, the Next.js layout,
the templates with </head> of a server framework; then how to mount the server half's middleware from this
installation's edge folder (the file that makes the app, the files to copy), where its secret comes from, and how to
check it all with doctor. In server mode (public_listen + path_prefix) the page script is /cake/cake.js on the site's
own domain, never 127.0.0.1. Every run uses a scratch CAKE_HOME and a free port.
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from agentcake import config, site_setup, wording  # noqa: E402
from cake_server import free_port  # noqa: E402
from site_fixtures import make_site  # noqa: E402

SITE_KEY = "ck_setuptest"
EDGE = os.path.join(ROOT, "edge")
SECRET_ENV = "CAKE_SERVER_TIMING_SECRET"


class SetupSite(unittest.TestCase):
    """setup --print --site in a scratch CAKE_HOME, on a test copy of a site of each kind."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.folder = tempfile.mkdtemp(prefix="cake-test-site-")
        for folder in (self.home, self.folder):
            self.addCleanup(shutil.rmtree, folder, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        env.start()
        self.addCleanup(env.stop)
        self.settings(site_key=SITE_KEY)

    def settings(self, **values):
        with open(os.path.join(self.home, "config.json"), "w", encoding="utf-8") as f:
            json.dump(values, f)

    def printed(self, kind, mounted=False):
        make_site(kind, self.folder, None, mounted)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            site_setup.setup_print_site(self.folder)
        return out.getvalue()

    @property
    def local_script(self):
        return f"{config.base_url()}/cake.js"


class Frameworks(SetupSite):
    def test_static_site_every_page_and_no_server_half(self):
        out = self.printed("static")
        self.assertIn("Detected:     static", out)
        self.assertIn(f'<script src="{self.local_script}" data-site="{SITE_KEY}" defer></script>', out)
        self.assertIn("every .html page (3 found)", out)
        self.assertIn(wording.text("setup_site_half_none"), out)
        self.assertNotIn(SECRET_ENV, out)

    def test_express_names_the_template_and_mounts_cake_express_where_the_app_is_made(self):
        out = self.printed("express")
        self.assertIn("Detected:     express", out)
        self.assertIn(os.path.join("views", "layout.ejs"), out)
        self.assertIn(f"npm install {os.path.join(EDGE, 'node')}", out)
        self.assertIn("In server.js, right after the app is made", out)
        self.assertIn("app.use(cakeExpress({ clientIp: (req) => req.ip }))", out)
        self.assertIn(SECRET_ENV, out)
        self.assertIn(os.path.join(EDGE, "node", "README.md"), out)

    def test_next_edits_the_layout_and_adds_middleware_ts(self):
        out = self.printed("next-app")
        self.assertIn(f"Edit {os.path.join('app', 'layout.tsx')}", out)
        self.assertIn(f'<Script src="{self.local_script}" data-site="{SITE_KEY}" strategy="afterInteractive" />', out)
        self.assertIn("Create middleware.ts", out)
        self.assertIn('import { cakeNext } from "@agentcake/edge/next"', out)

    def test_flask_copies_the_middleware_beside_the_app_and_wraps_wsgi_app(self):
        out = self.printed("flask")
        self.assertIn(os.path.join("templates", "base.html"), out)
        self.assertIn(f"Copy {os.path.join(EDGE, 'python', 'cake_edge.py')} and cake_edge.json", out)
        self.assertIn("In app.py, right after app = Flask(__name__):", out)
        self.assertIn("app.wsgi_app = CakeEdgeWSGI(app.wsgi_app", out)

    def test_fastapi_adds_the_asgi_middleware(self):
        out = self.printed("fastapi")
        self.assertIn("In main.py, right after app = FastAPI():", out)
        self.assertIn("app.add_middleware(CakeEdgeASGI", out)

    def test_django_wraps_the_wsgi_application_and_copies_beside_manage_py(self):
        out = self.printed("django")
        self.assertIn(f"In {os.path.join('brewbean', 'wsgi.py')}, wrap the application", out)
        self.assertIn("into the folder that has manage.py (.)", out)

    def test_php_puts_the_line_in_the_header_and_sends_the_token_from_the_front_controller(self):
        out = self.printed("php")
        self.assertIn("header.php", out)
        self.assertIn("At the top of index.php, before any output", out)
        self.assertIn("cake_edge.php, cake_edge_format.php and cake_edge.json", out)

    def test_wordpress_uses_the_plugin_with_this_address_and_key(self):
        out = self.printed("wordpress")
        self.assertIn(os.path.join(EDGE, "wordpress", "agentcake"), out)
        self.assertIn(f"{wording.product()['name']} address: {config.base_url()}", out)
        self.assertIn(f"Site key:           {SITE_KEY}", out)
        self.assertIn("wp-config.php", out)

    def test_every_site_with_server_code_is_checked_on_a_running_page(self):
        for kind in ("express", "next-app", "flask", "php"):
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                out = self.printed(kind)
                self.assertIn("config set site_url", out)
                self.assertIn(" doctor", out)

    def test_the_check_stops_only_the_server_the_agent_started_and_the_answer_is_in_the_users_language(self):
        """In a trial run Claude Code started a server for the static site to check it, then stopped it with
        `lsof -ti tcp:<port> | xargs kill`, which stops whatever listens there, perhaps the user's own program; in
        another it answered a Chinese request in English. Step 4 says to stop it by its process ID only, step 5 to
        answer in the user's language."""
        flat = " ".join(self.printed("static").split())
        for words in ("note its process ID", "stop only that process", "never by port or name",
                      "Tell the user, in their language"):
            self.assertIn(words, flat)

    def test_an_unknown_folder_gets_the_line_for_the_shared_head(self):
        with open(os.path.join(self.folder, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("hello\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            site_setup.setup_print_site(self.folder)
        self.assertIn("Could not detect the framework", out.getvalue())


class ServerMode(SetupSite):
    """public_listen + path_prefix: visitors reach AgentCake at /cake on the site's own domain."""

    def setUp(self):
        super().setUp()
        self.settings(site_key=SITE_KEY, public_listen="0.0.0.0:8080", path_prefix="/cake", site_domain="brewbean.example")

    def test_the_page_script_is_on_the_sites_own_domain(self):
        out = self.printed("static")
        self.assertIn(f'<script src="/cake/cake.js" data-site="{SITE_KEY}" defer></script>', out)
        self.assertNotIn(self.local_script, out)
        self.assertIn(wording.text("setup_site_tell_server", prefix="/cake").splitlines()[0], out)

    def test_snippet_gives_the_same_address(self):
        self.assertEqual(site_setup.snippet(), f'<script src="/cake/cake.js" data-site="{SITE_KEY}" defer></script>')

    def test_wordpress_gets_the_full_address(self):
        out = self.printed("wordpress")
        self.assertIn(f"{wording.product()['name']} address: https://brewbean.example/cake", out)

    def test_without_a_domain_the_address_says_what_to_fill_in(self):
        self.settings(site_key=SITE_KEY, public_listen="0.0.0.0:8080", path_prefix="/cake")
        out = self.printed("wordpress")
        self.assertIn(wording.text("setup_site_address_unknown", prefix="/cake"), out)


class EdgeFolder(SetupSite):
    """Where the sites' middleware is: $CAKE_EDGE_DIR, else inside the package (a release), else beside it."""

    def package_with_edge(self, inside):
        package = os.path.join(tempfile.mkdtemp(prefix="cake-test-package-"), "agentcake")
        self.addCleanup(shutil.rmtree, os.path.dirname(package), True)
        edge = os.path.join(package, "edge") if inside else os.path.join(os.path.dirname(package), "edge")
        os.makedirs(os.path.join(edge, "node"))
        return package, edge

    def test_a_release_carries_it_inside_the_package(self):
        package, edge = self.package_with_edge(inside=True)
        with mock.patch.object(site_setup.paths, "PACKAGE_DIR", package):
            self.assertEqual(site_setup.edge_dir(), edge)

    def test_a_checkout_has_it_beside_the_package(self):
        self.assertEqual(site_setup.edge_dir(), EDGE)

    def test_cake_edge_dir_comes_first(self):
        package, _ = self.package_with_edge(inside=True)
        elsewhere = tempfile.mkdtemp(prefix="cake-test-edge-")
        self.addCleanup(shutil.rmtree, elsewhere, True)
        with mock.patch.dict(os.environ, {"CAKE_EDGE_DIR": elsewhere}):
            with mock.patch.object(site_setup.paths, "PACKAGE_DIR", package):
                self.assertEqual(site_setup.edge_dir(), elsewhere)
            self.assertIn(f"npm install {elsewhere}/node", self.printed("express"))

    def test_without_one_it_says_this_installation_has_no_middleware_files(self):
        with mock.patch.object(site_setup, "edge_dir", return_value=None):
            out = self.printed("express")
        self.assertIn(wording.text("setup_site_no_edge"), out)
        self.assertNotIn("npm install", out)


if __name__ == "__main__":
    unittest.main()
