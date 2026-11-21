"""`agentcake setup --print --site`: the server middleware's mounting, in the language of the file it goes in.

    python3 -I -m unittest discover -s tests -p test_site_setup_language.py -v      (from the AgentCake folder)

A coding agent pastes the mounting setup prints into the site's file as it is. On a real Next.js site whose middleware.js
is JavaScript, the TypeScript mounting (type NextRequest, request: NextRequest) was a syntax error there. So the mounting
follows the file it goes in: TypeScript in a .ts file (a new Next.js middleware is middleware.ts where the site has a
tsconfig.json, middleware.js where it has none), import in a JavaScript module, require() in CommonJS. The Next.js
function is the file's default export, which Next.js runs from middleware.js and from proxy.js (Next.js 16, where a
function named middleware fails the build). node --check reads each JavaScript mounting as it is printed.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import site_setup  # noqa: E402
from site_fixtures import make_site, write  # noqa: E402
from test_site_setup import SetupSite  # noqa: E402

NODE_SUFFIX = {"esm": ".mjs", "cjs": ".cjs"}  # the ending that has node --check read a mounting as that language
EXPRESS_IMPORT = 'import { cakeExpress } from "@agentcake/edge/express"'
EXPRESS_REQUIRE = 'const { cakeExpress } = require("@agentcake/edge/express")'


def mounting(out, file):
    """The code lines printed under the line that names the file the mounting goes in."""
    lines = out.splitlines()
    start = next(index for index, line in enumerate(lines)
                 if file in line and line.endswith(":") and not line.startswith("    "))
    code = []
    for line in lines[start + 1:]:
        if not line.startswith("    "):
            break
        code.append(line[4:])
    return "\n".join(code)


class Mounting(SetupSite):
    def setup_for(self, kind, files=None, removed=()):
        """setup --print --site on a test site before setup, with some of its files written over or removed."""
        make_site(kind, self.folder, None, mounted=False)
        for name, content in (files or {}).items():
            write(self.folder, name, content)
        for name in removed:
            os.remove(os.path.join(self.folder, name))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            site_setup.setup_print_site(self.folder)
        return out.getvalue()

    def assert_javascript_next(self, code):
        self.assertNotIn("NextRequest", code)
        self.assertIn("export default async function middleware(request) {", code)
        self.assertIn('import { cakeNext } from "@agentcake/edge/next"', code)


class NextMiddleware(Mounting):
    def test_a_javascript_site_gets_javascript_for_its_own_middleware_js(self):
        out = self.setup_for("next-js")
        self.assertIn("Add this code to middleware.js:", out)
        self.assert_javascript_next(mounting(out, "middleware.js"))

    def test_a_typescript_site_gets_typescript_for_a_new_middleware_ts(self):
        out = self.setup_for("next-app")
        self.assertIn("Add this code to middleware.ts:", out)
        self.assertIn("If middleware.ts doesn't exist, create it. On Next.js 16 or later, name the new file proxy.ts.", out)
        self.assertIn("export default async function middleware(request: NextRequest) {", mounting(out, "middleware.ts"))

    def test_a_site_without_a_tsconfig_gets_a_new_middleware_js(self):
        out = self.setup_for("next-js", removed=["middleware.js"])
        self.assertIn("If middleware.js doesn't exist, create it. On Next.js 16 or later, name the new file proxy.js.", out)
        self.assert_javascript_next(mounting(out, "middleware.js"))

    def test_a_middleware_js_stays_javascript_in_a_site_with_a_tsconfig(self):
        out = self.setup_for("next-js", files={"tsconfig.json": json.dumps({"compilerOptions": {"allowJs": True}})})
        self.assert_javascript_next(mounting(out, "middleware.js"))

    def test_a_new_middleware_goes_beside_the_app_folder_in_src(self):
        out = self.setup_for("next-js", files={"src/app/layout.js": "export default function RootLayout() {}\n"},
                             removed=["middleware.js", os.path.join("app", "layout.js")])
        self.assertIn(f"Add this code to {os.path.join('src', 'middleware.js')}:", out)


class ExpressAndHono(Mounting):
    def test_express_in_commonjs_gets_require(self):
        code = mounting(self.setup_for("express"), "server.js")
        self.assertIn(EXPRESS_REQUIRE, code)
        self.assertNotIn("import", code)

    def test_express_in_a_javascript_module_gets_import(self):
        out = self.setup_for("express", files={"server.js": 'import express from "express"\nconst app = express()\n'})
        code = mounting(out, "server.js")
        self.assertIn(EXPRESS_IMPORT, code)
        self.assertNotIn("require", code)

    def test_express_in_typescript_gets_import(self):
        out = self.setup_for("express", files={"server.ts": 'import express from "express"\nconst app = express()\n'},
                             removed=["server.js"])
        self.assertIn(EXPRESS_IMPORT, mounting(out, "server.ts"))

    def test_hono_in_typescript_gets_import(self):
        code = mounting(self.setup_for("hono"), os.path.join("src", "index.ts"))
        self.assertIn('import { cakeHono } from "@agentcake/edge/hono"', code)

    def test_hono_in_commonjs_gets_require(self):
        index = os.path.join("src", "index.ts")
        out = self.setup_for("hono", files={"src/index.js": 'const { Hono } = require("hono")\nconst app = new Hono()\n'},
                             removed=[index])
        code = mounting(out, os.path.join("src", "index.js"))
        self.assertIn('const { cakeHono } = require("@agentcake/edge/hono")', code)
        self.assertNotIn("import", code)


@unittest.skipUnless(shutil.which("node"), "node is not installed: the JavaScript mountings cannot be read")
class NodeReadsThem(Mounting):
    """Each JavaScript mounting, as printed, is JavaScript node can read in its file's language."""

    CASES = (("next-js", {}, "middleware.js", "esm"),
             ("express", {}, "server.js", "cjs"),
             ("express", {"server.js": 'import express from "express"\nconst app = express()\n'}, "server.js", "esm"),
             ("hono", {"src/index.js": 'import { Hono } from "hono"\nconst app = new Hono()\n'},
              os.path.join("src", "index.js"), "esm"))

    def test_each_javascript_mounting_is_valid_where_it_goes(self):
        scratch = tempfile.mkdtemp(prefix="cake-test-mounting-")
        self.addCleanup(shutil.rmtree, scratch, True)
        for kind, files, file, language in self.CASES:
            with self.subTest(kind=kind, language=language):
                shutil.rmtree(self.folder)
                os.makedirs(self.folder)
                removed = [os.path.join("src", "index.ts")] if kind == "hono" else []
                code = mounting(self.setup_for(kind, files, removed), file)
                path = write(scratch, kind + NODE_SUFFIX[language], code + "\n")
                checked = subprocess.run(["node", "--check", path], capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, checked.stderr + code)


if __name__ == "__main__":
    unittest.main()
