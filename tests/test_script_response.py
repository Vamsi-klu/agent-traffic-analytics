"""The page script over HTTP: agentcake/script_response.py, and cake.js as both listeners of a real `agentcake serve`
send it.

    python3 -I -m unittest discover -s tests -p test_script_response.py -v      (from the AgentCake folder)

A client that accepts gzip (Accept-Encoding, RFC 9110 12.5.3; every browser does) gets the script gzipped, with
Content-Encoding: gzip; any other client gets it as it is. Both answers carry Vary: Accept-Encoding, so that a cache in
between keeps them apart, and the same weak ETag of the script's text: a browser whose copy is still current gets a
304 without the script (If-None-Match, RFC 9110 13.1.2). Each text of the script is compressed once and kept. On the
listeners everything else stays as it was: the type, the public listener's Cache-Control and nosniff, no CORS; collect,
/edge and the health checks are never compressed.
"""
import gzip
import http.client
import os
import sys
import unittest
from unittest import mock
from urllib.parse import urlsplit

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config, edge_api, routes, script_response  # noqa: E402  (needs the path above)
from agentcake.responses import JS, Request  # noqa: E402
from cake_server import SITE_KEY, START_TIMEOUT_S, CakeServer  # noqa: E402

BROWSER = "gzip, deflate, br, zstd"  # what Chrome sends
SCRIPT = ("/*! a page script */\n" + "var CFG = {\"batch\": {\"interval_min_ms\": 2000}};\n" * 400).encode()
UNCHANGED_BY_CODING = {"content-encoding", "content-length", "date"}


def ask(headers, script=SCRIPT):
    return script_response.answer(Request("/cake.js", {}, headers), script)


class AcceptsGzip(unittest.TestCase):
    def test_a_browser_or_a_list_with_gzip_above_0_accepts_it(self):
        for value in (BROWSER, "deflate, gzip, br, zstd", "gzip", "GZIP", "x-gzip", "br;q=1.0, gzip;q=0.8",
                      "gzip ; q=0.5", "*", "br, *;q=0.1", "gzip;q=1.000"):
            with self.subTest(value=value):
                self.assertTrue(script_response.accepts_gzip(value))

    def test_no_header_identity_or_a_weight_of_0_refuses_it(self):
        for value in (None, "", "identity", "br, zstd", "gzip;q=0", "gzip;q=0.000", "*;q=0", "gzip;q=0, *",
                      "x-gzip;q=0, *;q=1"):
            with self.subTest(value=value):
                self.assertFalse(script_response.accepts_gzip(value))

    def test_a_weight_that_cannot_be_read_refuses_it(self):
        for value in ("gzip;q=high", "gzip;q=2", "gzip;q=-1", "gzip;q=0.0001", "gzip;q="):
            with self.subTest(value=value):
                self.assertFalse(script_response.accepts_gzip(value))


class Answer(unittest.TestCase):
    def test_a_client_that_accepts_gzip_gets_the_script_gzipped(self):
        answer = ask({"Accept-Encoding": BROWSER})
        self.assertEqual((answer.status, answer.ctype), (200, JS))
        self.assertEqual(answer.headers["Content-Encoding"], "gzip")
        self.assertEqual(answer.headers["Vary"], "Accept-Encoding")
        self.assertEqual(gzip.decompress(answer.body), SCRIPT)
        self.assertLess(len(answer.body), len(SCRIPT))

    def test_any_other_client_gets_the_script_as_it_is(self):
        for headers in ({}, {"Accept-Encoding": "identity"}, {"Accept-Encoding": "br"}):
            with self.subTest(headers=headers):
                answer = ask(headers)
                self.assertEqual((answer.status, answer.body, answer.ctype), (200, SCRIPT, JS))
                self.assertNotIn("Content-Encoding", answer.headers)
                self.assertEqual(answer.headers["Vary"], "Accept-Encoding", "a cache keeps the two answers apart")

    def test_both_answers_carry_the_same_weak_etag_which_changes_with_the_text(self):
        etag = ask({}).headers["ETag"]
        self.assertEqual(ask({"Accept-Encoding": BROWSER}).headers["ETag"], etag)
        self.assertRegex(etag, r'^W/"[0-9a-f]+"$', "weak: the gzipped and the plain bytes are the same script")
        self.assertNotEqual(ask({}, SCRIPT + b"// a new site key\n").headers["ETag"], etag)

    def test_a_copy_that_is_still_current_gets_304_without_the_script(self):
        etag = ask({}).headers["ETag"]
        for if_none_match in (etag, etag[len("W/"):], f'"another", {etag}', "*"):
            with self.subTest(if_none_match=if_none_match):
                answer = ask({"If-None-Match": if_none_match, "Accept-Encoding": BROWSER})
                self.assertEqual((answer.status, answer.body), (304, b""))
                self.assertEqual(answer.headers, {"ETag": etag, "Vary": "Accept-Encoding"})

    def test_an_old_or_unreadable_etag_gets_the_script(self):
        for if_none_match in ('"another"', 'W/"another"', "", "not an etag"):
            with self.subTest(if_none_match=if_none_match):
                self.assertEqual(ask({"If-None-Match": if_none_match}).status, 200)

    def test_each_text_is_compressed_once(self):
        text = SCRIPT + b"// compressed once\n"
        with mock.patch.object(script_response.gzip, "compress", wraps=gzip.compress) as compress:
            first, again = ask({"Accept-Encoding": BROWSER}, text), ask({"Accept-Encoding": BROWSER}, text)
            self.assertEqual(compress.call_count, 1)
            self.assertIs(again.body, first.body)
            changed = ask({"Accept-Encoding": BROWSER}, text + b"// a setting changed\n")
        self.assertEqual(compress.call_count, 2)
        self.assertEqual(gzip.decompress(changed.body), text + b"// a setting changed\n")

    def test_the_gzipped_bytes_depend_only_on_the_text(self):
        """The gzip header's time is 0 (RFC 1952: none given), so the same text always gives the same bytes."""
        answer = ask({"Accept-Encoding": BROWSER}, SCRIPT + b"// no time\n")
        self.assertEqual(answer.body[4:8], bytes(4))
        self.assertEqual(answer.body, gzip.compress(SCRIPT + b"// no time\n", mtime=0))


def send(url, headers=None, method="GET", body=None):
    """(status, {lower-case name: value}, body) of one request carrying exactly these headers: http.client adds no
    Accept-Encoding of its own here, so the header is absent unless given."""
    parts = urlsplit(url)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=START_TIMEOUT_S)
    try:
        connection.putrequest(method, parts.path, skip_accept_encoding=True)
        sent = dict(headers or {})
        if body is not None:
            sent["Content-Length"] = str(len(body))
        for name, value in sent.items():
            connection.putheader(name, value)
        connection.endheaders(body)
        answer = connection.getresponse()
        return answer.status, {name.lower(): value for name, value in answer.getheaders()}, answer.read()
    finally:
        connection.close()


class BothListeners(unittest.TestCase):
    """cake.js and its short name /c.js, on the public listener (below path_prefix) and on the local one."""

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=False)
        cls.scripts = {f"{listener} {path}": base + path for listener, base in (("public", cls.server.public),
                                                                                ("local", cls.server.local))
                       for path in ("/cake.js", "/c.js")}

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def test_a_browser_gets_the_script_gzipped(self):
        for name, url in self.scripts.items():
            with self.subTest(script=name):
                status, headers, body = send(url, {"Accept-Encoding": BROWSER})
                plain = send(url)[2]
                self.assertEqual((status, headers["content-encoding"]), (200, "gzip"))
                self.assertEqual(headers["vary"], "Accept-Encoding")
                self.assertEqual(gzip.decompress(body), plain)
                self.assertEqual(int(headers["content-length"]), len(body))
                self.assertLess(len(body), len(plain) // 2)

    def test_without_accept_encoding_the_script_goes_as_it_is(self):
        for name, url in self.scripts.items():
            for headers in ({}, {"Accept-Encoding": "identity"}):
                with self.subTest(script=name, headers=headers):
                    status, answer, body = send(url, headers)
                    self.assertEqual(status, 200)
                    self.assertNotIn("content-encoding", answer)
                    self.assertIn(SITE_KEY.encode(), body)
                    self.assertEqual(int(answer["content-length"]), len(body))

    def test_its_other_headers_stay_as_they_were(self):
        """The same headers with and without gzip, besides the coding and the length; on the public listener the
        type, the cache time and nosniff, and no CORS for a page on another origin."""
        page = {"Origin": "https://www.example.com"}
        for name, url in self.scripts.items():
            with self.subTest(script=name):
                plain = send(url, page)[1]
                gzipped = send(url, {**page, "Accept-Encoding": BROWSER})[1]
                self.assertEqual({k: v for k, v in gzipped.items() if k not in UNCHANGED_BY_CODING},
                                 {k: v for k, v in plain.items() if k not in UNCHANGED_BY_CODING})
                self.assertEqual(plain["content-type"], JS)
                self.assertNotIn("access-control-allow-origin", plain)
        public = send(self.scripts["public /cake.js"], {"Accept-Encoding": BROWSER})[1]
        self.assertEqual(public["cache-control"], f"public, max-age={config.DEFAULTS['public_script_cache_s']}")
        self.assertEqual(public["x-content-type-options"], "nosniff")

    def test_a_copy_that_is_still_current_gets_304_with_the_same_cache_headers(self):
        """A 304 has no Content-Length: one would claim that the script is empty (RFC 9110 8.6)."""
        for name, url in self.scripts.items():
            with self.subTest(script=name):
                current = send(url, {"Accept-Encoding": BROWSER})[1]
                status, headers, body = send(url, {"Accept-Encoding": BROWSER, "If-None-Match": current["etag"]})
                self.assertEqual((status, body), (304, b""))
                self.assertEqual((headers["etag"], headers["vary"]), (current["etag"], "Accept-Encoding"))
                self.assertNotIn("content-length", headers)
                self.assertEqual(headers.get("cache-control"), current.get("cache-control"))

    def test_collect_edge_and_the_health_checks_are_not_compressed(self):
        browser = {"Accept-Encoding": BROWSER, "Origin": "https://www.example.com", "Content-Type": "text/plain"}
        batch = b'{"k":"' + SITE_KEY.encode() + b'","s":"notgzipped","u":"https://www.example.com/","e":[]}'
        answers = {"public collect": send(self.server.public + routes.COLLECT, browser, "POST", batch),
                   "public edge": send(self.server.public + edge_api.ROUTE, browser, "POST", b"{}"),
                   "public healthz": send(self.server.public + "/healthz", browser),
                   "local collect": send(self.server.local + routes.COLLECT, browser, "POST", batch),
                   "local health": send(self.server.local + "/api/health", browser)}
        for name, (status, headers, _) in answers.items():
            with self.subTest(answer=name):
                self.assertNotIn("content-encoding", headers)
                self.assertNotIn("Accept-Encoding", headers.get("vary", ""))
        self.assertEqual(answers["public collect"][1]["vary"], "Origin")
        self.assertEqual(answers["public healthz"][2], b"ok")


if __name__ == "__main__":
    unittest.main()
