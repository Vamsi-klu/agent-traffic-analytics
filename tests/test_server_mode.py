"""Server mode as SERVER.md describes it, on this computer: case T8 without Docker or a load balancer.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

A real `agentcake serve` (cake_server.CakeServer) with its local page and its public listener on two free ports. The
test plays the load balancer by sending its headers itself. It checks what SERVER.md promises: every local page path
is 404 on the public port; the local page does not answer on this computer's network address; the load balancer's
headers count only on the public listener and only with trust_lb on, X-Forwarded-For and the like never; the
visitor's place comes from the city database (one copied in while the server runs is used at once), never from a
header; the visitor's address is in no file of CAKE_HOME, in no stored event and not in the server's output; collect,
and only collect, answers a page on another origin (the subdomain route) with CORS, and its preflight with 204.
"""
import ipaddress
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
import geo_fixtures  # noqa: E402
from agentcake import config, edge_api, geoip, netfacts, routes, streams  # noqa: E402  (needs the path above)
from agentcake.detect import lists  # noqa: E402
from cake_server import (PREFIX, SERVER_MD, SITE_KEY, START_TIMEOUT_S, CakeServer, documented_public_routes,  # noqa: E402
                         free_port, http, read, run_cli)

CONNECT_TIMEOUT_S = 1
FORWARDING_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP")  # what a client can write anything into


def network_address():
    """This computer's address on its network, or None when it has none. Connecting a UDP socket sends nothing: it
    only picks the route, and getsockname() tells which local address that route uses."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1 (RFC 5737), the discard port: never answered, nothing is sent
            address = s.getsockname()[0]
    except OSError:
        return None
    return None if ipaddress.ip_address(address).is_loopback else address


def published_agent_address():
    """The first address of the first agent range in the release's lists (agentcake/data/lists/ip_ranges.json):
    published by an AI company for its agents, so it is no visitor's address."""
    with open(os.path.join(lists.BUNDLED_DIR, "ip_ranges.json"), encoding="utf-8") as f:
        ranges = json.load(f)["ranges"]
    block = next(r["v4"][0] for r in ranges if r["kind"] == "agent" and r["v4"])
    return str(ipaddress.ip_network(block, strict=False).network_address)


def visit(session_id):
    """One batch from cake.js, as a visitor's browser on the site sends it."""
    return json.dumps({"k": SITE_KEY, "s": session_id, "u": "https://example.com/", "ua": "Mozilla/5.0",
                       "e": [{"type": 4, "timestamp": int(time.time() * 1000),
                              "data": {"href": "https://example.com/"}}]}).encode()


def load_balancer_headers(address):
    """The headers a load balancer adds in front of AgentCake (data/lb_headers.json), with made-up values, and the
    place headers AgentCake 0.5 read, which a visitor can send too and which nothing reads any more."""
    names = netfacts.lb_headers()
    return {names["ip"]: address, names["ja4"]: "t13d1516h2_8daaf6152771_d8a2da3f94cd", names["proto"]: "HTTP/2",
            "X-Cake-Region": "FR", "X-Cake-City": "Paris", "Content-Type": "text/plain"}


def status_of_raw_request(port, request_line):
    """The status a listener on 127.0.0.1:port answers a request line with, or None when it closes the connection
    without an answer."""
    with socket.create_connection(("127.0.0.1", port), timeout=START_TIMEOUT_S) as s:
        s.sendall(f"{request_line}\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 0\r\n\r\n".encode("latin-1"))
        first = s.makefile("rb").readline().decode("latin-1")
    return int(first.split()[1]) if first else None


class PublicListener(unittest.TestCase):
    """What answers where: the public listener serves only the page script, the recorder, collect and the health
    check; the local page answers only on 127.0.0.1."""

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def test_public_port_serves_the_page_script_recorder_collect_and_health_check(self):
        """And /edge, which refuses a request not signed with the server half's secret (test_edge_api.py signs)."""
        expected = {edge_api.ROUTE: (403,)}
        for route in routes.PUBLIC:
            body = visit("publicroute") if route.method == "POST" else None
            status = http(self.server.public + route.path, body, {"Content-Type": "text/plain"}, route.method)[0]
            self.assertIn(status, expected.get(route.path, (200, 204)), f"{route.method} {PREFIX}{route.path}")

    def test_every_local_page_path_is_404_on_the_public_port(self):
        """Every path of the local listener that SERVER.md does not list as public, with and without the prefix."""
        public = documented_public_routes(read(SERVER_MD))
        local_only = [r for r in routes.LOCAL if (r.method, PREFIX + r.path) not in public]
        self.assertTrue(local_only)
        for route in local_only:
            path = route.path + ("x" if route.is_prefix else "")  # /api/session/ is /api/session/<id>
            for url in (self.server.public + path, f"http://127.0.0.1:{self.server.public_port}{path}"):
                body = b"{}" if route.method == "POST" else None
                self.assertEqual(http(url, body, method=route.method)[0], 404, f"{route.method} {url}")

    def test_local_page_answers_on_127_0_0_1(self):
        self.assertEqual(http(self.server.local + "/")[0], 200)

    def test_local_page_does_not_answer_on_this_computers_network_address(self):
        address = network_address()
        if address is None:
            self.skipTest("this computer has no network address besides 127.0.0.1")
        with self.assertRaises(OSError):
            socket.create_connection((address, self.server.local_port), timeout=CONNECT_TIMEOUT_S).close()

    def test_status_exits_0_while_serving_and_1_when_nothing_answers(self):
        """The image's HEALTHCHECK runs `agentcake status`; Docker reads exit code 0 as healthy and 1 as unhealthy
        (2 is reserved)."""
        self.assertEqual(run_cli(self.server.env, "status").returncode, 0)
        idle_home = tempfile.mkdtemp(prefix="agentcake-server-mode-idle-")
        self.addCleanup(shutil.rmtree, idle_home, True)
        idle = dict(os.environ, CAKE_HOME=idle_home, CAKE_PORT=str(free_port()))  # a port nothing listens on
        self.assertEqual(run_cli(idle, "status").returncode, 1)


class CrossOriginCollect(unittest.TestCase):
    """The subdomain route puts the website's pages and AgentCake's public listener on two origins
    (https://www.example.com and https://cake.example.com). collect answers as PostHog 1.0's capture did: the request's
    own Origin may read the answer, which is empty, whichever site sent it (whether a visit counts as the website's is
    site_domain's to say, not CORS's); its preflight is 204. Nothing else on the public listener carries CORS."""

    PAGE = "https://www.example.com"
    PREFLIGHT = {"Origin": PAGE, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def post(self, origin, body):
        headers = {"Content-Type": "text/plain", **({"Origin": origin} if origin else {})}
        return http(self.server.public + routes.COLLECT, body, headers, "POST")

    def test_collect_answers_the_requests_own_origin(self):
        status, headers, _ = self.post(self.PAGE, visit("cors-site"))
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), self.PAGE)
        self.assertEqual(headers.get("Vary"), "Origin")
        self.assertNotIn("Access-Control-Allow-Credentials", headers, "cake.js sends no cookie")

    def test_any_origin_may_read_the_answer_a_sandboxed_page_too(self):
        for number, origin in enumerate(("http://localhost:5173", "https://shop.elsewhere.example", "null")):
            with self.subTest(origin=origin):
                headers = self.post(origin, visit(f"cors-any-{number}"))[1]
                self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin)

    def test_an_origin_no_browser_sends_is_not_echoed_and_the_visit_still_counts(self):
        for number, origin in enumerate(("https://www.example.com/a/page", "javascript:alert(1)",
                                         "https://a.example, https://b.example", None)):
            with self.subTest(origin=origin):
                status, headers, _ = self.post(origin, visit(f"cors-odd-{number}"))
                self.assertEqual(status, 204)
                self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_a_refusal_carries_cors_too_so_the_page_reads_it_as_final(self):
        """cake.js sends a batch again only for its retry statuses (transport.js); without CORS a refusal reads as a
        network error, and the page would send the refused batch again on every tick."""
        status, headers, _ = self.post(self.PAGE, json.dumps({"k": "ck_another_site", "s": "cors-refused"}).encode())
        self.assertEqual((status, headers.get("Access-Control-Allow-Origin")), (403, self.PAGE))

    def test_a_preflight_of_collect_is_204(self):
        status, headers, body = http(self.server.public + routes.COLLECT, None, self.PREFLIGHT, "OPTIONS")
        self.assertEqual((status, body), (204, b""))
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), self.PAGE)
        self.assertEqual(headers.get("Access-Control-Allow-Methods"), "POST")
        self.assertEqual(headers.get("Access-Control-Allow-Headers"), "Content-Type")

    def test_no_other_public_path_carries_cors_and_their_preflights_are_404(self):
        for route in (r for r in routes.PUBLIC if r.path != routes.COLLECT):
            with self.subTest(route=f"{route.method} {route.path}"):
                body = b"" if route.method == "POST" else None
                headers = http(self.server.public + route.path, body, self.PREFLIGHT, route.method)[1]
                self.assertNotIn("Access-Control-Allow-Origin", headers)
                self.assertEqual(http(self.server.public + route.path, None, self.PREFLIGHT, "OPTIONS")[0], 404)

    def test_a_preflight_outside_the_prefix_is_404(self):
        outside = f"http://127.0.0.1:{self.server.public_port}{routes.COLLECT}"
        self.assertEqual(http(outside, None, self.PREFLIGHT, "OPTIONS")[0], 404)


class LoadBalancerHeaders(unittest.TestCase):
    """The load balancer's headers count only on the public listener, only with trust_lb on; X-Forwarded-For and the
    like never. The visitor's address is looked up and dropped: no file, stored event or output line keeps it."""

    SESSIONS = ("public", "forwarded", "local", "untrusted")

    @classmethod
    def setUpClass(cls):
        cls.address = published_agent_address()
        cls.expected_range = netfacts.published_range(cls.address)[0]
        trusting, not_trusting = CakeServer(trust_lb=True), CakeServer(trust_lb=False)
        cls.servers = (trusting, not_trusting)
        with mock.patch.dict(os.environ, {"CAKE_HOME": trusting.home}):  # while the server runs, as lists update does
            geo_fixtures.install(geoip.user_folder(), geo_fixtures.single(cls.address, "US", "Texas", "San Antonio"))
        headers = load_balancer_headers(cls.address)
        forwarded = {name: cls.address for name in FORWARDING_HEADERS} | {"Content-Type": "text/plain"}
        cls.answers = {
            "public": http(trusting.public + "/collect", visit("public"), headers, "POST")[0],
            "forwarded": http(trusting.public + "/collect", visit("forwarded"), forwarded, "POST")[0],
            "local": http(trusting.local + "/collect", visit("local"), headers, "POST")[0],
            "untrusted": http(not_trusting.public + "/collect", visit("untrusted"), headers, "POST")[0]}
        cls.outputs = [server.stop() for server in cls.servers]
        cls.trusting, cls.not_trusting = trusting, not_trusting

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.remove()

    def test_every_visit_was_accepted(self):
        self.assertEqual(set(self.answers.values()), {204}, self.answers)

    def test_public_listener_with_trust_lb_reads_them(self):
        net = self.trusting.net_of("public")
        self.assertEqual((net["range"], net["country"], net["city"], net["proto"]),
                         (self.expected_range, "US", "San Antonio", "HTTP/2"))

    def test_local_listener_ignores_them(self):
        self.assertIsNone(self.trusting.net_of("local"))

    def test_public_listener_without_trust_lb_ignores_them(self):
        self.assertIsNone(self.not_trusting.net_of("untrusted"))

    def test_forwarding_headers_are_never_read(self):
        self.assertIsNone(self.trusting.net_of("forwarded")["range"])

    def test_address_is_in_no_file_of_cake_home(self):
        for server in self.servers:
            for folder, _, files in os.walk(server.home):
                for name in files:
                    with open(os.path.join(folder, name), "rb") as f:
                        self.assertNotIn(self.address, f.read().decode("latin-1"), name)

    def test_address_is_in_no_stored_event(self):
        """The same, decoded: replay chunks are compressed, so the bytes on disk alone would not show it."""
        for server in self.servers:
            con = server.database()
            self.addCleanup(con.close)
            with mock.patch.dict(os.environ, {"CAKE_HOME": server.home}):
                for session_id in self.SESSIONS:
                    for _, _, text in streams.read_events(con, session_id):
                        self.assertNotIn(self.address, text, session_id)

    def test_address_is_not_in_the_server_output(self):
        for output in self.outputs:
            self.assertIn("public listener", output)
            self.assertNotIn(self.address, output)


class UnreadableRequestTarget(unittest.TestCase):
    """Anyone can send a request target urllib cannot read (an unclosed IPv6 bracket: GET http://[ HTTP/1.1). Both
    listeners answer it 400, as they answer any request line they cannot read, and the server writes no traceback."""

    UNREADABLE = "http://["

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=False)
        cls.statuses = {(listener, method): status_of_raw_request(port, f"{method} {cls.UNREADABLE} HTTP/1.1")
                        for listener, port in (("local", cls.server.local_port), ("public", cls.server.public_port))
                        for method in ("GET", "POST", "OPTIONS")}
        cls.health = (http(cls.server.local + "/api/health")[0], http(cls.server.public + "/healthz")[0])
        cls.output = cls.server.stop()

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def test_both_listeners_answer_400(self):
        self.assertEqual(self.statuses, {key: 400 for key in self.statuses})

    def test_the_listeners_go_on_answering(self):
        self.assertEqual(self.health, (200, 200))

    def test_the_server_writes_no_traceback(self):
        self.assertNotIn("Traceback", self.output)


def status_of_post(port, path, framing):
    """The status a listener answers a POST with these framing header lines and no body with; None when it closes
    the connection without an answer or is still waiting for a body after START_TIMEOUT_S."""
    lines = [f"POST {path} HTTP/1.1", f"Host: 127.0.0.1:{port}", "Content-Type: text/plain"] + framing
    with socket.create_connection(("127.0.0.1", port), timeout=START_TIMEOUT_S) as s:
        s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        try:
            first = s.makefile("rb").readline().decode("latin-1")
        except TimeoutError:
            return None
    return int(first.split()[1]) if first else None


class BodyFraming(unittest.TestCase):
    """A POST whose body is not framed by one Content-Length of digits within the listener's limit is refused before
    its body is read, on both listeners: anyone can send one to the public port. A negative length used to make the
    server read until the client hung up, and text made it write a traceback and answer nothing."""

    REFUSED = {("Content-Length: -1",): 400, ("Content-Length: ten",): 400, ("Content-Length: 5, 5",): 400,
               ("Content-Length: 5", "Content-Length: 5"): 400, ("Transfer-Encoding: chunked",): 411}

    @classmethod
    def setUpClass(cls):
        cls.server = CakeServer(trust_lb=False)
        listeners = {"local": (cls.server.local_port, "", config.DEFAULTS["local_max_body_bytes"]),
                     "public": (cls.server.public_port, PREFIX, config.DEFAULTS["public_max_body_bytes"])}
        cls.statuses = {(name, framing): status_of_post(port, prefix + routes.COLLECT, list(framing))
                        for name, (port, prefix, _) in listeners.items() for framing in cls.REFUSED}
        cls.too_large = {name: status_of_post(port, prefix + routes.COLLECT, [f"Content-Length: {limit + 1}"])
                         for name, (port, prefix, limit) in listeners.items()}
        cls.health = (http(cls.server.local + "/api/health")[0], http(cls.server.public + "/healthz")[0])
        cls.output = cls.server.stop()

    @classmethod
    def tearDownClass(cls):
        cls.server.remove()

    def test_each_framing_is_refused_on_both_listeners(self):
        self.assertEqual(self.statuses, {(name, framing): self.REFUSED[framing] for name, framing in self.statuses})

    def test_a_length_over_the_limit_is_413_on_both_listeners(self):
        self.assertEqual(self.too_large, {"local": 413, "public": 413})

    def test_the_listeners_go_on_answering_and_write_no_traceback(self):
        self.assertEqual(self.health, (200, 200))
        self.assertNotIn("Traceback", self.output)


if __name__ == "__main__":
    unittest.main()
