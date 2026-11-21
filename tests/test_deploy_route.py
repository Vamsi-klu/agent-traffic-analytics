"""docker-compose.yml and deploy/Caddyfile, the subdomain route's deploy files, against the code they front.

    python3 -I -m unittest discover -s tests -p test_deploy_route.py -v      (from the AgentCake folder)

test_server_docs.py checks that the two files do what SERVER.md says. This file checks them against AgentCake itself.
Compose restarts both services and caps AgentCake's memory, mounts the Caddyfile read-only, and keeps one project
name, so a later release folder takes over the same containers instead of starting a second Caddy next to the first.
The Caddyfile forwards the page script and collect, below the path prefix, to the public listener that the home page's
"On a server" settings set, and its site address is the one that tab's install command replaces. It writes the
visitor's address and the HTTP version into the headers AgentCake trusts, and never sets and removes the same one. It
trusts exactly the Cloudflare ranges of the bundled lists, and keeps no access log. When a Caddy is at hand (CAKE_CADDY,
or caddy on PATH), the real Caddy also reads the file (`caddy adapt`, `caddy fmt`) and runs copies of it in front of a
stand-in for AgentCake on 127.0.0.1; through them the page script, which AgentCake gzips for a browser that accepts
gzip, comes back as AgentCake sent it.
"""
import gzip
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import netfacts, routes, site_setup  # noqa: E402  (needs the path above)
from agentcake.detect import lists  # noqa: E402
from cake_server import ROOT, read  # noqa: E402
from deploy_files import (CADDYFILE, caddyfile_directives, compose_file, directives, server_settings,  # noqa: E402
                          unit_file)

SED = re.compile(r"s/([^/]+)/([^/]+)/")  # the install command's sed expression: s/<from>/<to>/
CLOUDFLARE = "cloudflare"  # the bundled lists' entry (agentcake/data/lists/ip_ranges.json)
CADDY_TIMEOUT_S = 60
POLL_S = 0.05
BROWSER = "gzip, deflate, br, zstd"  # the Accept-Encoding Chrome sends


def lb_header_names():
    return set(netfacts.lb_headers().values())


def cloudflare_ranges():
    with open(os.path.join(lists.BUNDLED_DIR, "ip_ranges.json"), encoding="utf-8") as f:
        entry = next(e for e in json.load(f)["ranges"] if e["id"] == CLOUDFLARE)
    return entry["v4"] + entry["v6"]


def install_commands():
    with open(os.path.join(ROOT, "agentcake", "data", "api.en.json"), encoding="utf-8") as f:
        return json.load(f)["setup_server"]["install"]


class Compose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.file = compose_file()
        cls.services = cls.file["services"]

    def test_both_restart_unless_stopped_and_agentcakes_memory_is_capped(self):
        for name, service in self.services.items():
            with self.subTest(service=name):
                self.assertEqual(service["restart"], "unless-stopped")
        self.assertRegex(self.services["agentcake"]["mem_limit"], r"^\d+m$")

    def test_agentcake_can_gain_no_privileges_as_with_systemd(self):
        """Neither serve nor the update process it starts can gain privileges through a setuid program or a file
        capability, as NoNewPrivileges=true has it in deploy/cake.service: both ways of installing run AgentCake the
        same way."""
        self.assertEqual(unit_file()["Service"]["NoNewPrivileges"], "true")
        self.assertIn("no-new-privileges:true", self.services["agentcake"].get("security_opt") or [])

    def test_serve_outlives_its_update_process_killed_for_memory_as_in_docker(self):
        """At the memory limit the kernel kills the largest process, the monthly update's own (agentcake/updates.py):
        serve goes on and records the failed update. Docker keeps a container running while PID 1 lives, but
        systemd's default OOMPolicy, stop, stops the whole service, before serve records anything, and its first check
        after the restart started the same download again."""
        self.assertIn("mem_limit", self.services["agentcake"])
        self.assertTrue(unit_file()["Service"]["MemoryMax"])
        self.assertEqual(unit_file()["Service"].get("OOMPolicy"), "continue")

    def test_caddy_cannot_change_its_caddyfile(self):
        self.assertIn(f"./{os.path.relpath(CADDYFILE, ROOT)}:/etc/caddy/Caddyfile:ro", self.services["caddy"]["volumes"])

    def test_the_project_has_one_name_whichever_folder_compose_runs_from(self):
        """Compose names a project after its folder unless told. A later release folder would then be another
        project: its `docker compose up -d` would start a second Caddy and AgentCake next to the running ones, which
        hold ports 80, 443 and the local page's, instead of replacing them."""
        self.assertEqual(self.file["name"], "agentcake")


class Caddyfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        found = caddyfile_directives()
        cls.found = found
        cls.globals = next(d for d in found if d.tokens == ())
        cls.site = next(d for d in found if d.tokens != ())
        cls.settings = server_settings()

    def proxy(self):
        (proxied,) = [h for h in directives(self.site.block, "handle") if len(h.tokens) == 2]
        (proxy,) = directives(proxied.block, "reverse_proxy")
        return proxied, proxy

    def header_up(self):
        return [d.tokens[1:] for d in directives(self.proxy()[1].block, "header_up")]

    def test_the_page_script_and_collect_go_to_the_public_listener_the_home_page_sets(self):
        proxied, proxy = self.proxy()
        (matcher,) = [d for d in self.site.block if d.tokens[0] == proxied.tokens[1]]
        prefix = self.settings["path_prefix"]
        self.assertEqual(matcher.tokens[1:], ("path", prefix + site_setup.SCRIPT_PATH, prefix + routes.COLLECT))
        self.assertEqual(proxy.tokens[1:], (self.settings["public_listen"],))

    def test_the_visitors_address_and_protocol_are_written_and_nothing_is_both_written_and_removed(self):
        names = netfacts.lb_headers()
        self.assertIn((names["ip"], "{client_ip}"), self.header_up())
        self.assertIn((names["proto"], "{http.request.proto}"), self.header_up())
        written = {tokens[0] for tokens in self.header_up() if not tokens[0].startswith("-")}
        removed = {tokens[0][1:] for tokens in self.header_up() if tokens[0].startswith("-")}
        self.assertEqual(written & removed, set())

    def test_cloudflares_proxies_are_trusted_exactly_as_the_bundled_lists_have_them(self):
        (servers,) = directives(self.globals.block, "servers")
        (trusted,) = directives(servers.block, "trusted_proxies", "static")
        self.assertEqual(list(trusted.tokens[2:]), cloudflare_ranges())
        self.assertEqual([d.tokens for d in directives(servers.block, "client_ip_headers")],
                         [("client_ip_headers", "CF-Connecting-IP")])

    def test_the_site_address_is_the_one_the_home_pages_install_command_replaces(self):
        (sed,) = [line for line in install_commands() if line.startswith("sed ")]
        old, new = SED.search(sed).groups()
        self.assertEqual(self.site.tokens, (old.replace("\\.", "."),), "a regular expression: its dots escaped")
        self.assertIn(os.path.relpath(CADDYFILE, ROOT), sed)
        self.assertEqual(new, self.settings["public_url"].split("://")[1], "the public_url host the settings give")

    def test_no_access_log_keeps_the_visitors_addresses(self):
        def every(found):
            for directive in found:
                yield directive
                yield from every(directive.block or [])
        self.assertEqual([d.tokens for d in every(self.found) if d.tokens and d.tokens[0] == "log"], [])


def caddy():
    return os.environ.get("CAKE_CADDY") or shutil.which("caddy")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(caddy(), "needs Caddy (set CAKE_CADDY to its executable)")
class RealCaddy(unittest.TestCase):
    """The real Caddy reads deploy/Caddyfile as it is, and runs two copies of it on 127.0.0.1, changed only so that
    they run on a test computer: an http:// address on a free port for the site's name (no certificate), no admin
    endpoint, and a stand-in for AgentCake's public listener that answers with the request it received. The second
    copy also counts 127.0.0.1 among Cloudflare's ranges, so the test can act as Cloudflare's proxy."""

    @classmethod
    def setUpClass(cls):
        cls.adapted = subprocess.run([caddy(), "adapt", "--config", CADDYFILE, "--adapter", "caddyfile"],
                                     capture_output=True, text=True, timeout=CADDY_TIMEOUT_S)
        cls.formatted = subprocess.run([caddy(), "fmt", CADDYFILE], capture_output=True, text=True,
                                       timeout=CADDY_TIMEOUT_S)
        cls.folder = tempfile.mkdtemp(prefix="agentcake-caddy-")
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), EchoRequest)
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.upstream.server_close)
        cls.addClassCleanup(cls.upstream.shutdown)
        cls.plain, cls.as_cloudflare = cls.run_copy("plain"), cls.run_copy("cloudflare")

    @classmethod
    def run_copy(cls, name):
        """A copy of the Caddyfile running on a free port; "cloudflare": with 127.0.0.1 among Cloudflare's ranges."""
        site = next(d for d in caddyfile_directives() if d.tokens != ()).tokens[0]
        port = free_port()
        text = read(CADDYFILE).replace(f"\n{site} {{", f"\nhttp://{site}:{port} {{")
        text = text.replace(server_settings()["public_listen"], f"127.0.0.1:{cls.upstream.server_port}")
        text = text.replace("{\n\tservers {", "{\n\tadmin off\n\tservers {", 1)  # no admin endpoint on :2019
        if name == "cloudflare":
            text = text.replace("trusted_proxies static ", "trusted_proxies static 127.0.0.1/32 ")
        path = os.path.join(cls.folder, f"Caddyfile.{name}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        log = open(path + ".log", "w+", encoding="utf-8")  # Caddy's own log, read only if it stops
        cls.addClassCleanup(log.close)
        process = subprocess.Popen([caddy(), "run", "--config", path, "--adapter", "caddyfile"], stdout=log,
                                   stderr=subprocess.STDOUT, env=dict(os.environ, HOME=cls.folder,
                                                                      XDG_DATA_HOME=cls.folder, XDG_CONFIG_HOME=cls.folder))
        cls.addClassCleanup(process.wait, CADDY_TIMEOUT_S)
        cls.addClassCleanup(process.terminate)
        deadline = time.monotonic() + CADDY_TIMEOUT_S
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.seek(0)
                raise RuntimeError("caddy run stopped: " + log.read())
            try:
                socket.create_connection(("127.0.0.1", port), timeout=POLL_S).close()
                return f"http://{site}:{port}", port
            except OSError:
                time.sleep(POLL_S)
        raise RuntimeError(f"caddy did not listen within {CADDY_TIMEOUT_S} s")

    def ask(self, path, method="GET", headers=None, copy=None):
        """(status, the request the stand-in received, or None) of one request to a copy (default: plain)."""
        address, port = copy or self.plain
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                         data=b"{}" if method == "POST" else None,
                                         headers={"Host": address.split("//")[1], **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=CADDY_TIMEOUT_S) as answer:
                return answer.status, json.loads(answer.read() or b"null")
        except urllib.error.HTTPError as error:
            with error:
                return error.code, None

    def test_caddy_reads_the_file_as_written_and_formatted(self):
        self.assertEqual(self.adapted.returncode, 0, self.adapted.stderr)
        self.assertNotIn("not formatted", self.adapted.stderr)
        self.assertEqual(self.formatted.stdout, read(CADDYFILE))

    def test_the_page_script_and_collect_reach_agentcake_with_the_prefix_and_host_unchanged(self):
        prefix = server_settings()["path_prefix"]
        for path, method in ((prefix + site_setup.SCRIPT_PATH, "GET"), (prefix + routes.COLLECT, "POST"),
                             (prefix + routes.COLLECT, "OPTIONS")):
            with self.subTest(path=path, method=method):
                status, received = self.ask(path, method)
                self.assertEqual((status, received["method"], received["path"]), (200, method, path))
                self.assertEqual(received["headers"]["host"], self.plain[0].split("//")[1])

    def test_anything_else_is_404_and_never_reaches_agentcake(self):
        prefix = server_settings()["path_prefix"]
        for path in ("/", prefix + "/", prefix + "/api/settings", prefix + "/healthz", "/cake.js", prefix + "/edge"):
            with self.subTest(path=path):
                self.assertEqual(self.ask(path), (404, None))

    def test_a_visitor_cannot_write_agentcakes_headers(self):
        names = netfacts.lb_headers()
        forged = {name: "203.0.113.9" for name in lb_header_names()}
        forged["CF-Connecting-IP"] = "203.0.113.9"  # from an address that is not Cloudflare's
        received = self.ask(server_settings()["path_prefix"] + site_setup.SCRIPT_PATH, headers=forged)[1]["headers"]
        self.assertEqual(received[names["ip"].lower()], "127.0.0.1", "the address the request came from")
        self.assertRegex(received[names["proto"].lower()], r"^HTTP/1\.1$")
        for name in lb_header_names() - {names["ip"], names["proto"]}:
            self.assertNotIn(name.lower(), received)

    def test_behind_cloudflares_proxy_the_visitor_is_cf_connecting_ip(self):
        received = self.ask(server_settings()["path_prefix"] + site_setup.SCRIPT_PATH,
                            headers={"CF-Connecting-IP": "198.51.100.7"}, copy=self.as_cloudflare)[1]["headers"]
        self.assertEqual(received[netfacts.lb_headers()["ip"].lower()], "198.51.100.7")

    def test_the_page_script_reaches_a_browser_gzipped_as_agentcake_sent_it(self):
        """AgentCake gzips the page script itself for a browser that accepts it (script_response.py), so Caddy has
        to pass the browser's Accept-Encoding on, and the answer back as it came: not compressed again, its
        Content-Encoding and Vary kept. The stand-in answers the page script the way AgentCake does."""
        address, port = self.plain
        path = server_settings()["path_prefix"] + site_setup.SCRIPT_PATH
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                         headers={"Host": address.split("//")[1], "Accept-Encoding": BROWSER})
        with urllib.request.urlopen(request, timeout=CADDY_TIMEOUT_S) as answer:
            status, headers, body = answer.status, answer.headers, answer.read()
        self.assertEqual((status, headers.get_all("Content-Encoding")), (200, ["gzip"]))
        self.assertEqual(headers.get_all("Vary"), ["Accept-Encoding"])
        self.assertEqual(json.loads(gzip.decompress(body))["headers"]["accept-encoding"], BROWSER)


class EchoRequest(http.server.BaseHTTPRequestHandler):
    """A stand-in for AgentCake's public listener: answers 200 with the method, path and headers it received, the
    page script's answer gzipped for a client that accepts gzip, as AgentCake gzips it."""

    def log_message(self, *args):
        pass

    def answer(self):
        if self.headers.get("Content-Length"):
            self.rfile.read(int(self.headers["Content-Length"]))
        body = json.dumps({"method": self.command, "path": self.path,
                           "headers": {name.lower(): value for name, value in self.headers.items()}}).encode()
        gzipped = self.path.endswith(site_setup.SCRIPT_PATH) and "gzip" in self.headers.get("Accept-Encoding", "")
        if gzipped:
            body = gzip.compress(body, mtime=0)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if gzipped:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_OPTIONS = answer


if __name__ == "__main__":
    unittest.main()
