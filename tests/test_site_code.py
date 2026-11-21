"""Reading a website's code folder: agentcake/site_code.py.

    python3 -I -m unittest discover -s tests -p test_site_code.py -v      (from the AgentCake folder)

Each test site (tests/site_fixtures.py) is recognised as its framework, a folder that holds only a WordPress theme or
plugin as WordPress; the files that must carry the cake.js line are
the ones setup names (every page of a static site, the Next.js layout, every template with </head>); the server
half's middleware is found where the site mounts it, and is missing when the mounting line or one of the files copied
beside it is gone. Installed packages, virtual environments and the Node middleware's copy in the site are never read
as the site's code; package.json's dependency on that copy is read as written.
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
from site_fixtures import (KINDS, NODE_COPY, NODE_KINDS, NODE_PACKAGE, THEME_HEADER, WORDPRESS_PARTS,  # noqa: E402
                           copy_node_middleware, make_site, write)

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


class WordPressParts(Folder):
    """A repository that holds one theme or one plugin, without the WordPress that runs it: WordPress, not PHP or a
    static site, recognised the way WordPress itself does (a header in the first 8 KB of the theme's style.css or of a
    plugin's main PHP file)."""

    def test_a_theme_or_plugin_folder_is_wordpress(self):
        for kind in WORDPRESS_PARTS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                self.assertEqual(self.site(kind).framework, "wordpress")

    def test_a_theme_with_a_build_step_is_still_wordpress(self):
        self.site("wordpress-theme")
        write(self.folder, "package.json", '{"devDependencies": {"express": "^4.21.2", "@wordpress/scripts": "^30.0.0"}}')
        self.assertEqual(site_code.SiteCode(self.folder).framework, "wordpress")

    def test_the_plugin_adds_the_line_and_is_not_in_the_folder(self):
        code = self.site("wordpress-theme")
        self.assertEqual(code.script_targets(), [])
        self.assertEqual(code.middleware_files(), [])
        self.assertTrue(code.middleware()["installed_elsewhere"])

    def test_the_header_counts_only_at_the_top_of_the_stylesheet(self):
        self.site("php")
        write(self.folder, "style.css", "body { margin: 0; }\n" * 500 + THEME_HEADER)  # past the first 8 KB
        self.assertEqual(site_code.SiteCode(self.folder).framework, "php")

    def test_the_first_8_kb_are_the_files_own_bytes_whatever_its_line_endings(self):
        """WordPress's get_file_data() reads 8 KB of the file as it is, then turns carriage returns into line ends: a
        header that starts past 8 KB on Windows line endings is no header, though it would be within 8 KB on Unix
        ones."""
        self.site("php")
        with open(os.path.join(self.folder, "style.css"), "wb") as f:
            f.write(b"/*\r\n" + b" x\r\n" * 2048 + THEME_HEADER.replace("\n", "\r\n").encode())  # starts at byte 8196
        self.assertEqual(site_code.SiteCode(self.folder).framework, "php")

    def test_a_theme_name_inside_a_rule_is_no_header(self):
        self.site("php")
        write(self.folder, "style.css", 'main::after { content: "Theme Name: Brew Bean"; }\n')
        self.assertEqual(site_code.SiteCode(self.folder).framework, "php")

    def test_a_stylesheet_below_the_top_of_the_folder_is_no_theme(self):
        self.site("php")
        write(self.folder, "assets/style.css", THEME_HEADER)
        self.assertEqual(site_code.SiteCode(self.folder).framework, "php")

    def test_a_header_with_no_name_is_no_theme(self):
        self.site("static")
        write(self.folder, "style.css", "/*\nTheme Name:\n*/\n")
        self.assertEqual(site_code.SiteCode(self.folder).framework, "static")

    def test_a_php_header_after_the_opening_tag_names_a_plugin(self):
        write(self.folder, "main.php", "<?php /* Plugin Name: Brew Bean Extras */ add_action( 'init', 'brew' );\n")
        self.assertEqual(site_code.SiteCode(self.folder).framework, "wordpress")


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

    def test_an_address_counts_only_as_a_whole(self):
        page = '<script src="{}" data-site="ck_sitecodetest" defer></script>'
        self.assertTrue(site_code.loads_from(page.format("/cake/cake.js"), "/cake/cake.js"))
        self.assertTrue(site_code.loads_from(page.format("https://cake.example.com/cake/cake.js?v=2"),
                                             "https://cake.example.com/cake/cake.js"))
        for elsewhere in ("https://stats.example.com/cake/cake.js", "/shop/cake/cake.js", "/cake/cake.jsx"):
            with self.subTest(src=elsewhere):
                self.assertFalse(site_code.loads_from(page.format(elsewhere), "/cake/cake.js"))


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


class NodeCopy(Folder):
    """edge/node copied into the site: its own files name cakeExpress( and the others, and its tests make apps, so it is
    never read as the site's code; package.json's dependency on it is what doctor checks."""

    def test_the_copy_is_never_read_as_the_sites_code(self):
        for kind in NODE_KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                code = self.site(kind)
                self.assertTrue(os.path.isfile(os.path.join(self.folder, NODE_COPY, "package.json")))
                self.assertEqual([path for path in code.files if path.startswith(NODE_COPY + os.sep)], [])

    def test_the_copy_alone_is_no_mounting(self):
        for kind in NODE_KINDS:
            with self.subTest(kind=kind):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                make_site(kind, self.folder, TAG, mounted=False)
                copy_node_middleware(self.folder)
                self.assertEqual(site_code.SiteCode(self.folder).middleware_files(), [])

    def test_the_copy_is_found_by_its_package_name(self):
        self.assertTrue(self.site("express").has_copied_folder())
        write(self.folder, os.path.join(NODE_COPY, "package.json"), '{"name": "something-else"}')
        self.assertFalse(site_code.SiteCode(self.folder).has_copied_folder())
        shutil.rmtree(os.path.join(self.folder, NODE_COPY))
        self.assertFalse(site_code.SiteCode(self.folder).has_copied_folder())

    def test_the_dependency_is_read_from_dependencies_as_written(self):
        self.assertEqual(self.site("express").dependency(NODE_PACKAGE), "file:" + NODE_COPY)
        write(self.folder, "package.json", '{"devDependencies": {"%s": "file:%s"}}' % (NODE_PACKAGE, NODE_COPY))
        self.assertIsNone(site_code.SiteCode(self.folder).dependency(NODE_PACKAGE))

    def test_a_relative_local_spec_names_its_folder_and_nothing_else_does(self):
        named = {"file:agentcake-edge": NODE_COPY, "file:./agentcake-edge": NODE_COPY, "link:agentcake-edge": NODE_COPY,
                 "portal:./agentcake-edge/": NODE_COPY, "file:vendor/edge": os.path.join("vendor", "edge"),
                 "file:../../Users/someone/agentcake/edge/node": None, "file:/opt/agentcake/edge/node": None,
                 "^0.0.0": None, "github:tartini-ai/agent-traffic-analytics": None, "file:": None}
        for spec, folder in named.items():
            with self.subTest(spec=spec):
                self.assertEqual(site_code.local_folder(spec), folder)


class Language(Folder):
    """What a mounting must be written in to be pasted into a file of the site (setup --print --site): the file's ending,
    else the module syntax it already uses, else package.json's "type"; a file not made yet is TypeScript where the site
    has a tsconfig.json."""

    def language(self, path, files):
        for name, content in files.items():
            write(self.folder, name, content)
        return site_code.SiteCode(self.folder).language(path)

    def test_a_typescript_ending_is_typescript(self):
        for name in ("server.ts", "app.tsx", "server.mts", "server.cts"):
            with self.subTest(name=name):
                self.assertEqual(self.language(name, {name: 'const express = require("express")\n'}), "ts")

    def test_a_javascript_file_is_read_for_the_module_syntax_it_uses(self):
        files = {"package.json": "{}", "esm.js": 'import express from "express"\n',
                 "exports.js": "export default function middleware(request) {}\n",
                 "cjs.js": 'const express = require("express")\n', "lazy.js": 'const page = import("./page.js")\n'}
        expected = {"esm.js": "esm", "exports.js": "esm", "cjs.js": "cjs", "lazy.js": "cjs", "x.mjs": "esm", "x.cjs": "cjs"}
        for name, language in expected.items():
            with self.subTest(name=name):
                self.assertEqual(self.language(name, files), language)

    def test_a_file_with_neither_follows_package_json(self):
        self.assertEqual(self.language("server.js", {"server.js": "app.listen(3000)\n"}), "cjs")
        self.assertEqual(self.language("server.js", {"package.json": '{"type": "module"}'}), "esm")

    def test_a_file_not_made_yet_is_typescript_where_the_site_has_a_tsconfig(self):
        self.assertEqual(self.language(None, {"package.json": "{}"}), "cjs")
        self.assertEqual(self.language(None, {"tsconfig.json": "{}"}), "ts")

    def test_a_javascript_file_stays_javascript_in_a_site_with_a_tsconfig(self):
        files = {"tsconfig.json": "{}", "middleware.js": 'import { NextResponse } from "next/server"\n'}
        self.assertEqual(self.language("middleware.js", files), "esm")


class JavaScriptSites(Folder):
    """A site written in JavaScript is recognised and its mounting found as a TypeScript one is."""

    def test_each_next_layout_in_javascript_is_next(self):
        layouts = {"src/app/layout.jsx": "next-app", "pages/_app.jsx": "next-pages", "src/pages/_app.js": "next-pages",
                   "src/pages/_app.jsx": "next-pages"}
        for layout, framework in layouts.items():
            with self.subTest(layout=layout):
                shutil.rmtree(self.folder)
                write(self.folder, layout, "export default function App() {}\n")
                self.assertEqual(site_code.SiteCode(self.folder).framework, framework)

    def test_the_javascript_next_site_is_next_with_its_middleware_js(self):
        code = self.site("next-js")
        self.assertEqual(code.framework, "next-app")
        self.assertEqual(code.middleware_files(), ["middleware.js"])

    def test_hono_mounted_in_jsx_is_found(self):
        make_site("hono", self.folder, TAG, mounted=False)
        os.remove(os.path.join(self.folder, "src", "index.ts"))
        write(self.folder, "src/index.jsx", 'import { Hono } from "hono"\nimport { cakeHono } from "@agentcake/edge/hono"\n'
              "const app = new Hono()\napp.use(cakeHono({ clientIp: (c) => null }))\n")
        code = site_code.SiteCode(self.folder)
        self.assertEqual(code.app_file(), os.path.join("src", "index.jsx"))
        self.assertEqual(code.middleware_files(), [os.path.join("src", "index.jsx")])


if __name__ == "__main__":
    unittest.main()
