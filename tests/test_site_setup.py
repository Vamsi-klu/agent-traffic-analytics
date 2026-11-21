"""`agentcake setup --print --site`: agentcake/site_setup.py, what a coding agent follows to connect a website.

    python3 -I -m unittest discover -s tests -p test_site_setup.py -v      (from the AgentCake folder)

For each framework it names the files to change and the line to add: every page of a static site, the Next.js layout,
the templates with </head> of a server framework; then how to mount the server half's middleware from this
installation's edge folder (the file that makes the app, the files to copy), where its secret comes from, and how to
check it all with doctor. A Node site copies edge/node into its own code as agentcake-edge and installs it from that
relative path, never from this installation's folder, so the site builds on any computer. With public_url (the
subdomain route) the page script is public_url + path_prefix + /cake.js, an absolute address, on a server and on a
computer that names its server alike, and the steps say which DNS record the site owner adds; in server mode without
it (the same-site path) the page script is /cake/cake.js on the site's own domain; never 127.0.0.1 in either. Every
run uses a scratch CAKE_HOME and a free port.
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
from site_fixtures import NODE_COPY, NODE_KINDS, WORDPRESS_PARTS, copy_node_middleware, make_site  # noqa: E402

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
        self.assertIn(f"npm install ./{NODE_COPY}", out)
        self.assertIn("In server.js, right after the app is made", out)
        self.assertIn("app.use(cakeExpress({ clientIp: (req) => req.ip }))", out)
        self.assertIn(SECRET_ENV, out)
        self.assertIn(os.path.join(EDGE, "node", "README.md"), out)

    def test_next_edits_the_layout_and_adds_middleware_ts(self):
        out = self.printed("next-app")
        self.assertIn(f"Edit {os.path.join('app', 'layout.tsx')}", out)
        self.assertIn(f'<Script src="{self.local_script}" data-site="{SITE_KEY}" strategy="afterInteractive" />', out)
        self.assertIn("Add this code to middleware.ts:", out)
        self.assertIn('import { cakeNext } from "@agentcake/edge/next"', out)

    def test_a_node_site_copies_the_middleware_into_its_code_and_installs_it_from_there(self):
        for kind in NODE_KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                out = self.printed(kind)
                installs = [line for line in out.splitlines() if "npm install" in line]
                self.assertEqual(len(installs), 1, out)
                self.assertIn(f"npm install ./{NODE_COPY}", installs[0])
                self.assertNotIn(EDGE, installs[0])
                self.assertIn(f"{os.path.join(EDGE, 'node')} folder", out)  # what to copy
                self.assertIn(f"Make sure that the {NODE_COPY} folder is part of the site's Git repository.", out)

    def test_a_site_that_holds_the_copy_already_is_told_the_same_files(self):
        expected = {"express": "In server.js, right after the app is made", "next-app": "Add this code to middleware.ts:",
                    "hono": f"In {os.path.join('src', 'index.ts')}, right after the app is made"}
        for kind, line in expected.items():
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                copy_node_middleware(self.folder)
                out = self.printed(kind)
                self.assertIn(line, out)
                self.assertNotIn(f"{NODE_COPY}{os.sep}", out)

    def test_a_pages_router_site_puts_the_tag_beside_the_page_in_app(self):
        """The Pages Router's pages/_app has no <body>: Next.js's guide loads a script for every page there, beside
        <Component {...pageProps} />, in a fragment (nextjs.org/docs/pages/guides/scripts)."""
        out = self.printed("next-pages")
        self.assertIn("Detected:     next-pages", out)
        self.assertIn(f"Edit {os.path.join('pages', '_app.js')}.", out)
        self.assertNotIn("<body>", out)
        tag = f'<Script src="{self.local_script}" data-site="{SITE_KEY}" strategy="afterInteractive" />'
        self.assertIn(f"    return (<><Component {{...pageProps}} />{tag}</>)\n", out)

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

    def test_a_theme_or_plugin_folder_gets_the_plugin_on_the_site_not_php_middleware(self):
        for kind in WORDPRESS_PARTS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                out = self.printed(kind)
                self.assertIn("Detected:     wordpress", out)
                self.assertIn("config set framework wordpress", out)
                self.assertIn(self.uploaded_plugin(), out)
                self.assertIn(f"cd {os.path.join(EDGE, 'wordpress')} && zip -r ~/agentcake.zip agentcake", out)
                self.assertIn(f"{wording.product()['name']} address: {config.base_url()}", out)
                self.assertIn(f"Site key:           {SITE_KEY}", out)
                self.assertIn(wording.text("setup_site_mw_wordpress"), out)
                for php_route in ("cake_edge.php", "AgentCake\\Edge", "index.php", "header.php"):
                    self.assertNotIn(php_route, out)

    def test_a_whole_wordpress_site_is_not_told_its_plugin_goes_elsewhere(self):
        out = self.printed("wordpress")
        self.assertNotIn(self.uploaded_plugin(), out)
        self.assertIn(wording.text("setup_site_plugin", plugin=os.path.join(EDGE, "wordpress", "agentcake"),
                                   address=config.base_url(), site_key=SITE_KEY), out)

    def uploaded_plugin(self):
        """Step 2 for a theme's or a plugin's own folder: the plugin zipped and uploaded to the WordPress site."""
        return wording.text("setup_site_plugin_elsewhere", folder=os.path.join(EDGE, "wordpress"), zip_name="agentcake",
                            address=config.base_url(), site_key=SITE_KEY)

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
        answer in the site owner's language."""
        flat = " ".join(self.printed("static").split())
        for words in ("note its process ID", "stop only that process", "never by port or name",
                      "Use the site owner's language"):
            self.assertIn(words, flat)

    def test_an_unknown_folder_gets_the_line_for_the_shared_head(self):
        with open(os.path.join(self.folder, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("hello\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            site_setup.setup_print_site(self.folder)
        self.assertIn("Could not detect the framework", out.getvalue())


class SettingsStep(SetupSite):
    """Step 1 saves the settings doctor needs. On a real site, step 1 still asked for the site's domain after the
    server's config had it: a site_domain that is set is given as it is."""

    def test_a_site_domain_that_is_set_is_given_as_it_is(self):
        self.settings(site_key=SITE_KEY, site_domain="brewbean.example")
        out = self.printed("static")
        self.assertIn("config set site_domain brewbean.example\n", out)
        self.assertNotIn("<the site's domain", out)

    def test_without_one_it_says_where_to_find_it(self):
        out = self.printed("static")
        self.assertIn("config set site_domain " + wording.raw("setup_site_domain_unknown") + "\n", out)


class OnThisComputer(SetupSite):
    """No public_listen and no public_url: step 5 names each step left for a public website without the agent having
    to fetch SERVER.md: deploying the change, a server for public visitors on the default route (a subdomain of the
    site, Caddy in front, an A record at the site owner's DNS provider), and the privacy policy. Who does each of them
    is test_site_setup_owner_tasks.py's."""

    def test_step_5_names_each_step_left_and_the_default_route(self):
        out = self.printed("static")
        step5 = " ".join(out[out.index(wording.text("setup_site_tell").strip().split(".")[0]):].split()).lower()
        for fact in ("deploy", "server for public visitors", "privacy policy", "subdomain", "cake.<", "caddy",
                     "add an a record for the subdomain at your dns provider"):
            self.assertIn(fact, step5)


class SubdomainRoute(SetupSite):
    """public_url: visitors' browsers load the page script from AgentCake's own subdomain and send their visits there,
    through Caddy on the server (docker-compose.yml, deploy/Caddyfile)."""

    ADDRESS = "https://cake.brewbean.example"

    def setUp(self):
        super().setUp()
        self.settings(site_key=SITE_KEY, public_listen="127.0.0.1:8080", path_prefix="/cake", site_domain="brewbean.example",
                      public_url=self.ADDRESS)

    def test_the_page_script_and_collect_are_on_the_subdomain(self):
        out = self.printed("static")
        self.assertIn(f'<script src="{self.ADDRESS}/cake/cake.js" data-site="{SITE_KEY}" defer></script>', out)
        self.assertIn(f"Page script:  {self.ADDRESS}/cake/cake.js", out)
        self.assertIn(f"Collect URL:  {self.ADDRESS}/cake/collect", out)
        self.assertNotIn(self.local_script, out)

    def test_snippet_and_the_nextjs_tag_give_the_same_address(self):
        self.assertEqual(site_setup.snippet(), f'<script src="{self.ADDRESS}/cake/cake.js" data-site="{SITE_KEY}" defer></script>')
        self.assertIn(f'<Script src="{self.ADDRESS}/cake/cake.js"', self.printed("next-app"))

    def test_wordpress_gets_the_subdomain_as_its_address(self):
        out = self.printed("wordpress")
        self.assertIn(f"{wording.product()['name']} address: {self.ADDRESS}/cake", out)

    def test_server_mode_says_where_browsers_reach_it(self):
        flat = " ".join(self.printed("static").split())
        self.assertIn("Server mode: The public listener runs at 127.0.0.1:8080, with the path /cake", flat)
        self.assertIn(f"{self.ADDRESS}/cake/", flat)
        self.assertIn(wording.product()["source"] + "/deploy/Caddyfile", flat)
        self.assertNotIn("load balancer", flat)

    def test_the_dns_record_goes_at_the_owners_dns_provider_and_doctor_checks_it(self):
        """The A record for the subdomain, in the site owner's DNS account (who adds it: test_site_setup_owner_tasks.py),
        DNS only on Cloudflare, and doctor on the server to check the setup."""
        flat = " ".join(self.printed("static").split())
        self.assertIn("Add an A record for cake.brewbean.example at your DNS provider", flat)
        self.assertIn("DNS only", flat)
        self.assertIn(f"{wording.product()['command']} doctor", flat)

    def test_a_computer_that_names_its_server_gives_the_same_line(self):
        """No public_listen here: this computer's AgentCake only says where the server's is, so the coding agent adds
        the line that server takes."""
        self.settings(site_key=SITE_KEY, path_prefix="/cake", site_domain="brewbean.example", public_url=self.ADDRESS)
        out = self.printed("static")
        self.assertIn(f'<script src="{self.ADDRESS}/cake/cake.js" data-site="{SITE_KEY}" defer></script>', out)
        self.assertNotIn("Server mode:", out)
        self.assertIn("Add an A record for cake.brewbean.example at your DNS provider", " ".join(out.split()))
        self.assertNotIn(wording.text("setup_site_tell_local").splitlines()[0], out)


class SameSitePath(SetupSite):
    """public_listen + path_prefix without public_url: visitors reach AgentCake at /cake on the site's own domain,
    through the site's own load balancer (SERVER.md's advanced route)."""

    def setUp(self):
        super().setUp()
        self.settings(site_key=SITE_KEY, public_listen="0.0.0.0:8080", path_prefix="/cake", site_domain="brewbean.example")

    def test_the_page_script_is_on_the_sites_own_domain(self):
        out = self.printed("static")
        self.assertIn(f'<script src="/cake/cake.js" data-site="{SITE_KEY}" defer></script>', out)
        self.assertNotIn(self.local_script, out)
        self.assertIn(wording.text("setup_site_tell_server_path", prefix="/cake").splitlines()[0], out)
        self.assertIn(wording.text("setup_site_server_mode_path", listen="0.0.0.0:8080", prefix="/cake"), out)

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
            self.assertIn(f"{elsewhere}/node folder", self.printed("express"))

    def test_without_one_it_says_this_installation_has_no_middleware_files(self):
        with mock.patch.object(site_setup, "edge_dir", return_value=None):
            out = self.printed("express")
        self.assertIn(wording.text("setup_site_no_edge"), out)
        self.assertNotIn("npm install", out)


if __name__ == "__main__":
    unittest.main()
