"""The Python site middleware: edge/python/cake_edge.py makes the Node middleware's token, from one file.

    python3 -I -m unittest discover -s tests -v      (from the cake folder)

A Python site does not install cake, so the middleware is one file beside its settings (cake_edge.json), standard library
only. These tests hold mint_token() to the shared vectors (tests/vectors/edge_token.json) byte for byte, check that the
settings are the Node middleware's and that a site's options and mistakes behave as on Node, that the file stands alone
(standard library, no agentcake, Python 3.9 syntax, nothing that talks to the network), that cake's own mint()
(agentcake/edge_token.py) and the ASGI path make the same tokens for 300 more requests, and that the README says what
the token holds and never holds. The WSGI and ASGI mountings: tests/test_edge_python_mountings.py; PHP: edge/php/tests.
"""
import ast, json, os, random, re, unittest

from edge_python_helpers import (CHROME_PAGE, EDGE_PYTHON, HTML, ROOT, SECRET, VECTORS, asgi_head, cake_edge, call_asgi,
                                 call_wsgi, edge_token, http_scope, mount_asgi, mount_wsgi, payload_of, token_in, values_of,
                                 vector_extras, wsgi_environ)
from test_edge_vectors import random_case  # noqa: E402  (the 300 requests the Node cross-check uses too)
from tools.check_imports import stdlib_modules  # noqa: E402


class SharedVectors(unittest.TestCase):
    def test_mint_token_makes_every_vector_token_byte_for_byte(self):
        for v in VECTORS["mint"]:
            with self.subTest(v["name"]):
                r = v["request"]
                token = cake_edge.mint_token(VECTORS["secrets"][v["secret"]], r["method"], r["path"], r["headers"],
                                             **vector_extras(v))
                self.assertEqual(token, v["token"])
                if token:
                    self.assertEqual(payload_of(token), v["payload"])

    def test_every_network_key_vector_gives_its_prefix_and_key(self):
        for v in VECTORS["network_keys"]:
            with self.subTest(v["name"]):
                self.assertEqual(cake_edge.ip_prefix(v["ip"]), v["prefix"])
                self.assertEqual(cake_edge.network_key(VECTORS["secrets"][v["secret"]], v["ip"], v["now_ms"]), v["key"])


class Settings(unittest.TestCase):
    NODE_ONLY = {"verdict_wait_ms": "botscent's wait: botscent is a JavaScript library"}

    def test_the_values_are_the_node_middlewares(self):
        with open(os.path.join(ROOT, "edge", "node", "defaults.json"), encoding="utf-8") as f:
            node = json.load(f)
        with open(os.path.join(ROOT, "edge", "node", "headers.json"), encoding="utf-8") as f:
            node_headers = json.load(f)
        ours = cake_edge.SETTINGS
        self.assertEqual(ours["fixed"], node["fixed"])
        self.assertEqual(ours["headers"], node_headers)
        self.assertEqual(set(ours["options"]) | set(self.NODE_ONLY), set(node["options"]))
        for key, value in ours["options"].items():
            self.assertEqual(value, node["options"][key], key)

    def test_a_site_can_change_the_options(self):
        middleware = mount_wsgi(cut={"user_agent": 10}, max_header_names=2, skip_extensions=[".html"])
        payload = payload_of(token_in(values_of(call_wsgi(middleware, wsgi_environ("/about"))[1], "server-timing")[0]))
        self.assertEqual((len(payload["ua"]), payload["hn"]), (10, ["host", "connection"]))
        self.assertEqual(call_wsgi(middleware, wsgi_environ("/about.HTML"))[1], [("Content-Type", HTML)])

    def test_unknown_options_and_values_of_the_wrong_kind_are_named_once_and_the_defaults_kept(self):
        with self.assertLogs("cake_edge", "WARNING") as logs:
            middleware = mount_wsgi(nostore=True, max_header_names="40", cut={"user_agent": -1})
        self.assertEqual(len(logs.output), 2)
        self.assertIn("nostore", logs.output[0])
        self.assertIn("max_header_names, cut", logs.output[1], "named in the order given")
        payload = payload_of(token_in(values_of(call_wsgi(middleware, wsgi_environ())[1], "server-timing")[0]))
        self.assertEqual(len(payload["hn"]), len(CHROME_PAGE))


class StandsAlone(unittest.TestCase):
    SOURCE_PATH = os.path.join(EDGE_PYTHON, "cake_edge.py")

    def source(self):
        with open(self.SOURCE_PATH, encoding="utf-8") as f:
            return f.read()

    def test_it_imports_only_the_standard_library_never_agentcake_and_nothing_that_talks_to_the_network(self):
        modules = set()
        for node in ast.walk(ast.parse(self.source())):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module.split(".")[0])
        self.assertTrue(modules <= stdlib_modules(), modules - stdlib_modules())
        self.assertFalse(modules & {"agentcake", "socket", "ssl", "http", "subprocess"}, modules)
        self.assertNotIn("urllib.request", self.source())

    def test_it_reads_as_python_3_9(self):
        ast.parse(self.source(), feature_version=(3, 9))

    def test_no_response_gets_a_cookie_and_no_secret_leaves_the_server(self):
        _, headers, _ = call_wsgi(mount_wsgi(), wsgi_environ())
        self.assertEqual(values_of(headers, "set-cookie"), [])
        self.assertNotIn(SECRET, json.dumps(headers))
        self.assertNotIn(SECRET.encode(), b"".join(v for _, v in asgi_head(call_asgi(mount_asgi(), http_scope()))))


class CakeAndMiddlewareAgree(unittest.TestCase):
    def test_cakes_mint_and_both_python_paths_make_the_same_token_for_300_more_requests(self):
        rng = random.Random(4110)
        pages = 0
        for n in range(300):
            c = random_case(rng, n)
            with self.subTest(c["id"]):
                r, secret = c["request"], VECTORS["secrets"][c["secret"]]
                expected = edge_token.mint(secret.encode(), r["method"], r["path"], r["headers"], c["now_ms"],
                                           ip=c["client_ip"], token_id=c["id"], verdict=c["verdict"], version=c["version"])
                made = cake_edge.mint_token(secret, r["method"], r["path"], r["headers"], c["now_ms"], c["id"],
                                            ip=c["client_ip"], verdict=c["verdict"], version=c["version"])
                self.assertEqual(made, expected)
                if c["verdict"] is None and c["version"] is None:
                    middleware = mount_asgi(secret=secret, now=lambda: c["now_ms"], random_id=lambda: c["id"],
                                            client_ip=lambda scope: c["client_ip"])
                    timing = values_of(asgi_head(call_asgi(middleware, http_scope(r["path"], r["headers"], r["method"]))),
                                       "server-timing")
                    self.assertEqual(token_in(timing[0]) if timing else None, expected)
                pages += expected is not None
        self.assertGreater(pages, 80, "enough of them are pages")


class Readme(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(EDGE_PYTHON, "README.md"), encoding="utf-8") as f:
            self.TEXT = f.read()

    def test_it_names_every_field_of_the_token_in_its_table(self):
        for field in VECTORS["mint"][0]["payload"]:
            self.assertRegex(self.TEXT, rf"(?m)^\| `{field}` \|", field)

    def test_it_shows_the_flask_fastapi_and_django_mountings(self):
        for mounting in ("app.wsgi_app = CakeEdgeWSGI(app.wsgi_app", "app.add_middleware(CakeEdgeASGI",
                         "get_wsgi_application()", "get_asgi_application()"):
            self.assertIn(mounting, self.TEXT)

    def test_it_explains_caching_and_what_the_token_never_holds(self):
        prose = re.sub(r"\s+", " ", self.TEXT)
        for words in ("no_store", "304", "never holds an IP address", "no cookie", "cake_edge.json"):
            self.assertIn(words, prose)


if __name__ == "__main__":
    unittest.main()
