"""The Python site middleware's mountings: CakeEdgeWSGI and CakeEdgeASGI on each page response.

    python3 -I -m unittest discover -s tests -v      (from the cake folder)

Every vector reaches the WSGI middleware as a server's environ (both sides checked by wsgiref.validate) and the ASGI
middleware from a hand-written server (scope, receive, send), and gets the vector's token. Then what
edge/node/test/express.test.js checks for Node: one cake entry per page, the site's own Server-Timing kept and an
inherited cake entry replaced, nothing on anything else or without a secret, the secret from the environment, no_store
for HTML only, a 304 with a fresh token, a failing client_ip costing the network key and never the page, and streaming:
a real wsgiref server sending a page in chunks, an ASGI app whose head goes out before its first chunk.
"""
import asyncio, http.client, json, os, threading, unittest
import wsgiref.simple_server, wsgiref.validate
from unittest import mock

from edge_python_helpers import (CHROME_PAGE, CLIENT_IP, HTML, NOW, PAGE_BODY, SECRET, VECTORS, asgi_app_with, asgi_head,
                                 cake_edge, call_asgi, call_wsgi, html_page, http_scope, mount_asgi, mount_wsgi,
                                 payload_of, read_token, token_in, values_of, wsgi_app_with, wsgi_environ)
from cake_server import POLL_S


class WSGIMounting(unittest.TestCase):
    @staticmethod
    def vector_token(v):
        """The token the WSGI middleware puts on the vector's request, given as a server's environ; both sides of the
        middleware are checked by wsgiref.validate."""
        middleware = cake_edge.CakeEdgeWSGI(wsgiref.validate.validator(html_page), secret=VECTORS["secrets"][v["secret"]],
                                            now=lambda: v["now_ms"], random_id=lambda: v["id"],
                                            client_ip=lambda environ: v["client_ip"])
        r = v["request"]
        _, headers, body = call_wsgi(wsgiref.validate.validator(middleware), wsgi_environ(r["path"], r["headers"], r["method"]))
        assert body == PAGE_BODY
        timing = values_of(headers, "server-timing")
        return token_in(timing[0]) if timing else None

    def test_every_vector_as_a_wsgi_environ_gets_its_token_and_passes_wsgiref_validate(self):
        for v in VECTORS["mint"]:
            # botscent is a JavaScript library, so the Python middleware has no verdict to add; a repeated line: below
            if v["verdict"] or len({n.lower() for n, _ in v["request"]["headers"]}) < len(v["request"]["headers"]):
                continue
            with self.subTest(v["name"]):
                self.assertEqual(self.vector_token(v), v["token"])

    def test_a_repeated_line_reaches_wsgi_joined_by_the_server_so_its_name_is_listed_once(self):
        v = next(v for v in VECTORS["mint"] if v["name"].startswith("a header line sent twice"))
        expected = dict(v["payload"], hn=list(dict.fromkeys(v["payload"]["hn"])))
        self.assertLess(len(expected["hn"]), len(v["payload"]["hn"]))
        self.assertEqual(payload_of(self.vector_token(v)), expected)

    def test_a_page_gets_one_cake_entry_whose_token_verifies_with_the_facts_of_the_request(self):
        _, headers, _ = call_wsgi(mount_wsgi(), wsgi_environ())
        timing = values_of(headers, "server-timing")
        self.assertEqual(len(timing), 1)
        result, payload = read_token(token_in(timing[0]))
        self.assertEqual(result, "ok")
        self.assertEqual(payload["sf"], {"s": "none", "m": "navigate", "d": "document", "u": "?1"})
        self.assertEqual(payload["hn"], [name.lower() for name, _ in CHROME_PAGE], "the header names in the order sent")
        self.assertIsNotNone(payload["ik"])

    def test_the_sites_own_server_timing_is_kept_and_an_inherited_cake_entry_replaced(self):
        site = wsgi_app_with([("Content-Type", HTML), ("Server-Timing", 'db;dur=53, cake;desc="c1.old.old"'),
                              ("server-timing", "app;dur=2")])
        _, headers, _ = call_wsgi(mount_wsgi(site), wsgi_environ())
        timing = values_of(headers, "server-timing")
        self.assertEqual(len(timing), 1, "one Server-Timing header")
        self.assertTrue(timing[0].startswith("db;dur=53, app;dur=2, cake;desc="), timing[0])
        self.assertNotIn("c1.old.old", timing[0])

    def test_a_static_file_a_frame_a_post_and_a_head_get_nothing(self):
        cases = {"a static file": wsgi_environ("/logo.png"), "a POST": wsgi_environ(method="POST"),
                 "a HEAD": wsgi_environ(method="HEAD"), "a dot-file": wsgi_environ("/.env"),
                 "a frame": wsgi_environ(lines=[[n, "iframe" if n.lower() == "sec-fetch-dest" else val] for n, val in CHROME_PAGE])}
        for why, environ in cases.items():
            with self.subTest(why):
                self.assertEqual(call_wsgi(mount_wsgi(), environ)[1], [("Content-Type", HTML)])

    def test_with_no_secret_or_a_short_one_every_request_passes_through_and_a_short_one_is_named_once(self):
        self.assertFalse(mount_wsgi(secret=None, secret_env="CAKE_TEST_UNSET_VARIABLE").enabled)
        self.assertEqual(call_wsgi(mount_wsgi(secret=None, secret_env="CAKE_TEST_UNSET_VARIABLE"), wsgi_environ())[1],
                         [("Content-Type", HTML)])
        short = "x" * (cake_edge.SETTINGS["fixed"]["min_secret_bytes"] - 1)
        with self.assertLogs("cake_edge", "WARNING") as logs:
            middleware = mount_wsgi(secret=short)
            for _ in range(3):
                self.assertEqual(call_wsgi(middleware, wsgi_environ())[1], [("Content-Type", HTML)])
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn(short, logs.output[0], "the secret is never part of a message")

    def test_the_secret_can_come_from_the_environment_variable_named_in_the_settings(self):
        with mock.patch.dict(os.environ, {cake_edge.SETTINGS["options"]["secret_env"]: SECRET}):
            middleware = mount_wsgi(secret=None)
        token = token_in(values_of(call_wsgi(middleware, wsgi_environ())[1], "server-timing")[0])
        self.assertEqual(read_token(token)[0], "ok")

    def test_no_store_makes_html_private_and_unstored_and_leaves_every_other_type_alone(self):
        cached = [("Content-Type", HTML), ("Cache-Control", "public, max-age=600")]
        _, headers, _ = call_wsgi(mount_wsgi(wsgi_app_with(cached), no_store=True), wsgi_environ())
        self.assertEqual(values_of(headers, "cache-control"), [cake_edge.SETTINGS["fixed"]["no_store_value"]])
        json_reply = [("Content-Type", "application/json"), ("Cache-Control", "public, max-age=600")]
        _, headers, _ = call_wsgi(mount_wsgi(wsgi_app_with(json_reply), no_store=True), wsgi_environ())
        self.assertEqual(values_of(headers, "cache-control"), ["public, max-age=600"])
        _, headers, _ = call_wsgi(mount_wsgi(wsgi_app_with(cached)), wsgi_environ())
        self.assertEqual(values_of(headers, "cache-control"), ["public, max-age=600"], "left alone by default")

    def test_a_304_for_a_page_carries_a_fresh_token_too(self):
        _, headers, _ = call_wsgi(mount_wsgi(wsgi_app_with([("ETag", '"v1"')], "304 Not Modified")), wsgi_environ())
        self.assertEqual(read_token(token_in(values_of(headers, "server-timing")[0]))[0], "ok")

    def test_without_request_uri_the_path_comes_from_path_info_percent_encoded_again(self):
        _, headers, _ = call_wsgi(mount_wsgi(), wsgi_environ("/caf%C3%A9/menu?x=1", request_uri=False))
        self.assertEqual(payload_of(token_in(values_of(headers, "server-timing")[0]))["p"], "/caf%C3%A9/menu")

    def test_a_client_ip_that_fails_costs_the_network_key_never_the_page(self):
        def broken(environ):
            raise KeyError("HTTP_X_REAL_IP")
        with self.assertLogs("cake_edge", "WARNING"):
            status, headers, body = call_wsgi(mount_wsgi(client_ip=broken), wsgi_environ())
        self.assertEqual((status, body), ("200 OK", PAGE_BODY))
        self.assertIsNone(payload_of(token_in(values_of(headers, "server-timing")[0]))["ik"])

    def test_a_streamed_page_from_a_real_wsgiref_server_carries_the_token_with_the_header_order_sent(self):
        def streamed(environ, start_response):
            start_response("200 OK", [("Content-Type", HTML)])
            yield from (b"<!doctype html>", b"<p>one</p>", b"<p>two</p>")
        server = wsgiref.simple_server.make_server("127.0.0.1", 0, mount_wsgi(streamed, client_ip=None),
                                                   handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": POLL_S}, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            connection.putrequest("GET", "/products/cake?ref=home", skip_host=True, skip_accept_encoding=True)
            for name, value in CHROME_PAGE:
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            body, timing = response.read(), response.getheader("Server-Timing")
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(body, b"<!doctype html><p>one</p><p>two</p>")
        result, payload = read_token(token_in(timing))
        self.assertEqual((result, payload["p"]), ("ok", "/products/cake"))
        self.assertEqual(payload["hn"], [name.lower() for name, _ in CHROME_PAGE])
        self.assertIsNone(payload["ik"], "no client_ip: no network key")


class QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):
        """No access log lines in the test output."""


class ASGIMounting(unittest.TestCase):
    def test_every_vector_through_the_asgi_middleware_gets_its_token(self):
        for v in VECTORS["mint"]:
            if v["verdict"]:
                continue  # botscent is a JavaScript library: the Python middleware never has a verdict to add
            with self.subTest(v["name"]):
                r = v["request"]
                middleware = mount_asgi(secret=VECTORS["secrets"][v["secret"]], now=lambda: v["now_ms"],
                                        random_id=lambda: v["id"], client_ip=lambda scope: v["client_ip"])
                timing = values_of(asgi_head(call_asgi(middleware, http_scope(r["path"], r["headers"], r["method"]))),
                                   "server-timing")
                self.assertEqual(token_in(timing[0]) if timing else None, v["token"])

    def test_a_streaming_response_gets_the_entry_in_its_head_before_the_first_chunk_and_is_not_buffered(self):
        sent_before_first_chunk = []
        chunks = [b"<!doctype html>", b"<p>one</p>", b"<p>two</p>"]
        sent = []

        async def streaming(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", HTML.encode())]})
            sent_before_first_chunk.extend(sent)
            for chunk in chunks:
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        asyncio.run(mount_asgi(streaming)(http_scope(), receive, send))
        self.assertEqual([m["type"] for m in sent_before_first_chunk], ["http.response.start"], "the head went out first")
        token = token_in(values_of(sent[0]["headers"], "server-timing")[0])
        self.assertEqual(read_token(token)[0], "ok")
        self.assertEqual([m["body"] for m in sent[1:]], chunks + [b""], "every chunk passed on unchanged")

    def test_the_sites_own_server_timing_is_kept_and_an_inherited_cake_entry_replaced(self):
        site = asgi_app_with([(b"content-type", HTML.encode()), (b"server-timing", b'db;dur=53, cake;desc="c1.old.old"')])
        timing = values_of(asgi_head(call_asgi(mount_asgi(site), http_scope())), "server-timing")
        self.assertEqual(len(timing), 1)
        self.assertTrue(timing[0].startswith("db;dur=53, cake;desc="), timing[0])
        self.assertNotIn("c1.old.old", timing[0])

    def test_non_pages_and_other_scopes_pass_through_untouched(self):
        head = [(b"content-type", HTML.encode())]
        for why, scope in {"a POST": http_scope(method="POST"), "a static file": http_scope("/app.js"),
                           "a HEAD": http_scope(method="HEAD")}.items():
            with self.subTest(why):
                self.assertEqual(asgi_head(call_asgi(mount_asgi(asgi_app_with(head)), scope)), head)
        seen = []

        async def lifespan_app(scope, receive, send):
            seen.append((scope["type"], receive, send))
        receive, send = object(), object()
        asyncio.run(mount_asgi(lifespan_app)({"type": "lifespan"}, receive, send))
        self.assertEqual(seen, [("lifespan", receive, send)], "the app gets the server's own receive and send")

    def test_with_no_secret_every_request_passes_through(self):
        head = [(b"content-type", HTML.encode())]
        middleware = mount_asgi(asgi_app_with(head), secret=None, secret_env="CAKE_TEST_UNSET_VARIABLE")
        self.assertEqual(asgi_head(call_asgi(middleware, http_scope())), head)

    def test_no_store_makes_html_private_and_unstored_and_leaves_every_other_type_alone(self):
        for kind, expected in ((HTML, cake_edge.SETTINGS["fixed"]["no_store_value"]), ("application/json", "max-age=600")):
            with self.subTest(kind):
                site = asgi_app_with([(b"content-type", kind.encode()), (b"cache-control", b"max-age=600")])
                head = asgi_head(call_asgi(mount_asgi(site, no_store=True), http_scope()))
                self.assertEqual(values_of(head, "cache-control"), [expected])

    def test_without_raw_path_the_path_comes_from_path_percent_encoded_again(self):
        head = asgi_head(call_asgi(mount_asgi(), http_scope("/caf%C3%A9/menu", raw_path=False)))
        self.assertEqual(payload_of(token_in(values_of(head, "server-timing")[0]))["p"], "/caf%C3%A9/menu")

    def test_the_network_key_comes_from_the_address_client_ip_reads_from_the_scope(self):
        head = asgi_head(call_asgi(mount_asgi(client_ip=lambda scope: scope["client"][0]), http_scope()))
        payload = payload_of(token_in(values_of(head, "server-timing")[0]))
        self.assertEqual(payload["ik"], cake_edge.network_key(SECRET, CLIENT_IP, NOW))
        self.assertNotIn(CLIENT_IP, json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
