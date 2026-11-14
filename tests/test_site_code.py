"""Reading a website's code folder: agentcake/site_code.py.

    python3 -I -m unittest discover -s tests -p test_site_code.py -v      (from the Agent Cake folder)

Each test site (tests/site_fixtures.py) is recognised as its framework; the files that must carry the cake.js line are
the ones setup names (every page of a static site, the Next.js layout, every template with </head>); the server
half's middleware is found where the site mounts it, and is missing when the mounting line or one of the files copied
beside it is gone. Installed packages and virtual environments are never read.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import site_code  # noqa: E402
from site_fixtures import KINDS, make_site, write  # noqa: E402

TAG = '<script src="http://127.0.0.1:7878/cake.js" data-site="ck_sitecodetest" defer></script>'


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cake-test-site-")
        self.addCleanup(shutil.rmtree, self.folder, True)

    def site(self, kind, tag=TAG, mounted=True):
        make_site(kind, self.folder, tag, mounted)
        return site_code.SiteCode(self.folder)


class Frameworks(Folder):
    def test_each_test_site_is_its_framework(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.assertEqual(self.site(kind).framework, kind)

    def test_a_folder_with_nothing_known_is_unknown(self):
        write(self.folder, "notes.txt", "hello\n")
        self.assertEqual(site_code.SiteCode(self.folder).framework, "unknown")

    def test_flask_is_found_by_its_import_without_a_requirements_file(self):
        write(self.folder, "app.py", "from flask import Flask\napp = Flask(__name__)\n")
        self.assertEqual(site_code.SiteCode(self.folder).framework, "flask")

    def test_a_virtual_environment_is_not_read(self):
        write(self.folder, "index.html", "<html><head></head></html>")
        write(self.folder, ".venv/lib/site-packages/flask/__init__.py", "import flask\n")
        self.assertEqual(site_code.SiteCode(self.folder).framework, "static")

    def test_a_flask_project_with_a_manage_py_is_still_flask(self):
        self.site("flask")
        write(self.folder, "manage.py", "from flask_script import Manager\n")  # Flask-Script's, not Django's
        self.assertEqual(site_code.SiteCode(self.folder).framework, "flask")

    def test_a_package_json_that_is_no_object_is_read_as_no_dependencies(self):
        write(self.folder, "package.json", '["express"]')
        write(self.folder, "index.html", "<html><head></head></html>")
        self.assertEqual(site_code.SiteCode(self.folder).framework, "static")


class ScriptTargets(Folder):
    def test_a_static_site_needs_every_page(self):
        code = self.site("static")
        self.assertEqual(code.script_targets(), ["about.html", "contact.html", "index.html"])

    def test_next_needs_its_layout(self):
        self.assertEqual(self.site("next-app").script_targets(), [os.path.join("app", "layout.tsx")])

    def test_a_server_framework_needs_every_template_with_a_head(self):
        self.assertEqual(self.site("express").script_targets(), [os.path.join("views", "layout.ejs")])
        shutil.rmtree(self.folder)
        os.makedirs(self.folder)
        self.assertEqual(self.site("flask").script_targets(), [os.path.join("templates", "base.html")])

    def test_a_browser_library_with_a_head_tag_is_no_template(self):
        self.site("express")
        write(self.folder, "public/js/editor.min.js", 'var frame="<html><head></head><body></body></html>";')
        self.assertEqual(site_code.SiteCode(self.folder).script_targets(), [os.path.join("views", "layout.ejs")])

    def test_wordpress_needs_no_file_the_plugin_adds_the_line(self):
        self.assertEqual(self.site("wordpress").script_targets(), [])

    def test_files_that_load_the_script_are_found(self):
        self.site("static")
        write(self.folder, "contact.html", "<html><head></head></html>")
        found = site_code.SiteCode(self.folder).files_loading(["http://127.0.0.1:7878/cake.js"], "ck_sitecodetest")
        self.assertEqual(found, ["about.html", "index.html"])


class AppFile(Folder):
    def test_the_file_that_makes_the_app(self):
        expected = {"express": "server.js", "flask": "app.py", "fastapi": "main.py", "hono": os.path.join("src", "index.ts"),
                    "django": os.path.join("brewbean", "wsgi.py"), "php": "index.php"}
        for kind, path in expected.items():
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.assertEqual(self.site(kind).app_file(), path)

    def test_next_names_its_middleware_file_once_there_is_one(self):
        self.assertEqual(self.site("next-app").app_file(), "middleware.ts")
        shutil.rmtree(self.folder)
        os.makedirs(self.folder)
        self.assertIsNone(self.site("next-app", mounted=False).app_file())


class Middleware(Folder):
    def test_found_where_each_site_mounts_it(self):
        expected = {"express": ["server.js"], "next-app": ["middleware.ts"], "flask": ["app.py"],
                    "hono": [os.path.join("src", "index.ts")], "fastapi": ["main.py"],
                    "django": [os.path.join("brewbean", "wsgi.py")], "php": ["index.php"],
                    "wordpress": [os.path.join("wp-content", "plugins", "agentcake", "agentcake.php")]}
        for kind, files in expected.items():
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                code = self.site(kind)
                self.assertEqual(code.middleware_files(), files)
                self.assertEqual(code.missing_beside(), [])

    def test_missing_when_the_mounting_line_is_gone(self):
        for kind in ("express", "next-app", "flask", "php", "wordpress"):
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.assertEqual(self.site(kind, mounted=False).middleware_files(), [])

    def test_a_file_missing_beside_cake_edge_py_is_named(self):
        self.site("flask")
        os.remove(os.path.join(self.folder, "cake_edge.json"))
        self.assertEqual(site_code.SiteCode(self.folder).missing_beside(), ["cake_edge.json"])

    def test_every_copied_file_is_named_when_none_was_copied(self):
        self.site("php")
        shutil.rmtree(os.path.join(self.folder, "cake"))
        self.assertEqual(site_code.SiteCode(self.folder).missing_beside(),
                         ["cake_edge.php", "cake_edge_format.php", "cake_edge.json"])

    def test_a_static_site_has_no_middleware(self):
        code = self.site("static")
        self.assertIsNone(code.middleware())


if __name__ == "__main__":
    unittest.main()
