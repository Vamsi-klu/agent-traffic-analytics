"""The compiled local pages, served by agentcake/assets.py.

    python3 -I -m unittest discover -s tests -p test_assets.py -v      (from the Agent Cake folder)

/ is the build's index.html, asked for again each time; the other files of the build are served by their suffix, the
content-named ones under assets/ kept by the browser, and the favicon at /favicon.ico, where browsers ask for it. A path outside the build, or a suffix cake does not serve, is
404. Without a build, / says how to make one (503). The pages are found through paths.web_folder (tests/test_paths.py).
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import routes  # noqa: E402
from agentcake.responses import Request  # noqa: E402

INDEX = b"<!doctype html><title>pages</title>"
ICON = b"\x00\x00\x01\x00"  # the start of an .ico file


def get(path):
    return routes.resolve(routes.LOCAL, "GET", path)(Request(path, {}, {}))


class LocalPages(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp(prefix="cake-web-")
        self.addCleanup(shutil.rmtree, root, True)
        self.dist = os.path.join(root, "dist")
        os.makedirs(os.path.join(self.dist, "assets"))
        for name, body in (("index.html", INDEX), ("demo.html", b"<p>demo</p>"), ("assets/main-AbC123.js", b"go()"),
                           ("assets/main-AbC123.css", b"a{}"), ("favicon.ico", ICON), ("notes.exe", b"MZ")):
            with open(os.path.join(self.dist, name), "wb") as f:
                f.write(body)
        with open(os.path.join(root, "secret.txt"), "w") as f:
            f.write("outside the build")
        env = mock.patch.dict(os.environ, {"CAKE_WEB_DIR": self.dist})
        env.start()
        self.addCleanup(env.stop)

    def test_the_root_is_the_builds_index_asked_for_again_each_time(self):
        answer = get("/")
        self.assertEqual((answer.status, answer.body, answer.ctype), (200, INDEX, "text/html; charset=utf-8"))
        self.assertEqual(answer.headers["Cache-Control"], "no-cache")

    def test_content_named_files_are_kept_by_the_browser(self):
        script, style = get("/assets/main-AbC123.js"), get("/assets/main-AbC123.css")
        self.assertEqual((script.status, script.body, script.ctype), (200, b"go()", "text/javascript; charset=utf-8"))
        self.assertEqual(style.ctype, "text/css; charset=utf-8")
        self.assertIn("immutable", script.headers["Cache-Control"])
        self.assertEqual(get("/demo.html").headers["Cache-Control"], "no-cache")

    def test_the_favicon_is_where_browsers_ask_for_it(self):
        answer = get("/favicon.ico")
        self.assertEqual((answer.status, answer.body, answer.ctype), (200, ICON, "image/x-icon"))

    def test_nothing_outside_the_build_and_no_other_suffix(self):
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/notes.exe", "/missing.js"):
            self.assertEqual(get(path).status, 404, path)

    def test_the_demo_shop_and_the_api_keep_their_own_routes(self):
        self.assertIs(routes.resolve(routes.LOCAL, "GET", "/demo"), routes.resolve(routes.LOCAL, "GET", "/demo/"))
        self.assertNotEqual(get("/api/nothing").ctype, "text/html; charset=utf-8")

    def test_without_a_build_the_root_says_how_to_make_one(self):
        shutil.rmtree(self.dist)
        answer = get("/")
        self.assertEqual(answer.status, 503)
        self.assertIn("npm ci && npm run build", answer.body)


if __name__ == "__main__":
    unittest.main()
