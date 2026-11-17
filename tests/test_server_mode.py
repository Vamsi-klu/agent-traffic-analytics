"""Server mode as SERVER.md describes it, on this computer: case T8 without Docker or a load balancer.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

A real `agentcake serve` (cake_server.CakeServer) with its local page and its public listener on two free ports. The
test plays the load balancer by sending its headers itself. It checks what SERVER.md promises: every local page path
is 404 on the public port; the local page does not answer on this computer's network address; the load balancer's
headers count only on the public listener and only with trust_lb on, X-Forwarded-For and the like never; the
visitor's address is in no file of CAKE_HOME, in no stored event and not in the server's output.
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
from agentcake import edge_api, netfacts, routes, streams  # noqa: E402  (needs the path above)
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
    """The headers a load balancer adds in front of AgentCake (data/lb_headers.json), with made-up values."""
    names = netfacts.lb_headers()
    return {names["ip"]: address, names["region"]: "US", names["ja4"]: "t13d1516h2_8daaf6152771_d8a2da3f94cd",
            names["proto"]: "HTTP/2", "Content-Type": "text/plain"}


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
        self.assertEqual((net["range"], net["country"], net["proto"]), (self.expected_range, "US", "HTTP/2"))

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


if __name__ == "__main__":
    unittest.main()
