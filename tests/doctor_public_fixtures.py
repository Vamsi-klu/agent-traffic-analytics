"""Stand-ins for the internet between a website's visitors and AgentCake, for doctor's server-mode checks
(tests/test_doctor_public.py). Nothing here leaves 127.0.0.1.

Certificates: a test certificate authority and two server certificates, made with the openssl command in a scratch
folder for each run (no private key is kept in the repository): one signed by the test authority for cake.example.com,
example.com and www.example.com, and a self-signed one for cake.example.com. FakeNet is what doctor_public.Network is
for doctor: its resolver gives the addresses a test names, its connections go to the local server standing at that
address, and its certificate check is Python's default one, trusting only the test authority. Front is an HTTPS server
on a free port of 127.0.0.1 that forwards every request to AgentCake's public listener the way a platform does
(Platform: which request headers it removes, replaces or adds, whether it keeps Host, which address it writes into
X-Cake-Client-IP, which headers it adds to its answers, which paths it does not pass on, which methods it refuses). Elsewhere is a server that
answers 404 to everything, where a wrong DNS record leads; Former is another AgentCake with the same site key (a server
the site moved from), which takes every upload and keeps none here. cdn_addresses() takes addresses from the bundled list's CDN ranges, so no address is written
here. Python's standard library only.
"""
import errno
import http.client
import ipaddress
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agentcake.detect import lists

LOOPBACK = "127.0.0.1"
SITE_NAMES = ("cake.example.com", "example.com", "www.example.com")
OPENSSL_TIMEOUT_S = 30
UPSTREAM_TIMEOUT_S = 10
CERTIFICATE_DAYS = 2  # made for this run only
HOP_BY_HOP = {"connection", "keep-alive", "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade"}
COLLECT_SUFFIX = "/collect"
# What AgentCake 0.6 answers on its public listener's collect (the request's own Origin; OPTIONS 204).
CORS_0_6 = {"Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"}
# How the front treats CORS: as AgentCake answers it; as 0.6 answers it (CORS_0_6), for an AgentCake that does not
# yet; or as 0.5 did (no CORS header at all, OPTIONS 404).
CORS_PASS, CORS_AS_0_6, CORS_NONE = "pass", "as-0.6", "none"

OPENSSL_CONFIG = """[req]
distinguished_name = dn
[dn]
[authority]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
[server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = {names}
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
"""


class Certificates:
    """The test authority (ca), and (certificate, key) files: site (signed by it), self_signed. None of them when the
    openssl command is missing: available is False, and the tests that need them skip."""

    def __init__(self):
        self.folder, self.available = None, bool(shutil.which("openssl"))
        if not self.available:
            return
        self.folder = tempfile.mkdtemp(prefix="cake-test-tls-")
        config = self._path("openssl.cnf")
        with open(config, "w", encoding="utf-8") as f:
            f.write(OPENSSL_CONFIG.format(names=", ".join("DNS:" + name for name in SITE_NAMES)))
        self.ca = self._path("ca.pem")
        self._openssl("req", "-new", "-x509", "-key", self._key("ca.key"), "-out", self.ca, "-subj", "/CN=Test CA",
                       "-days", str(CERTIFICATE_DAYS), "-config", config, "-extensions", "authority")
        self.site = self._signed("site", config)
        self.self_signed = (self._path("self.pem"), self._key("self.key"))
        self._openssl("req", "-new", "-x509", "-key", self.self_signed[1], "-out", self.self_signed[0],
                      "-subj", "/CN=" + SITE_NAMES[0], "-days", str(CERTIFICATE_DAYS), "-config", config,
                      "-extensions", "server")

    def remove(self):
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)

    def _signed(self, name, config):
        key, request, certificate = self._key(name + ".key"), self._path(name + ".csr"), self._path(name + ".pem")
        self._openssl("req", "-new", "-key", key, "-out", request, "-subj", "/CN=" + SITE_NAMES[0], "-config", config)
        self._openssl("x509", "-req", "-in", request, "-CA", self.ca, "-CAkey", self._path("ca.key"),
                      "-set_serial", str(int.from_bytes(os.urandom(8), "big")), "-out", certificate,
                      "-days", str(CERTIFICATE_DAYS), "-extfile", config, "-extensions", "server")
        return certificate, key

    def _key(self, name):
        self._openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", self._path(name))
        return self._path(name)

    def _path(self, name):
        return os.path.join(self.folder, name)

    def _openssl(self, *args):
        subprocess.run(("openssl",) + args, check=True, capture_output=True, timeout=OPENSSL_TIMEOUT_S)


class FakeNet:
    """doctor_public.Network with made-up DNS: names maps a host name to its addresses (a missing name has no
    record), servers maps an address to the port of the local server standing there (anything else refuses)."""

    def __init__(self, ca, names, servers):
        self.ca, self.names, self.servers = ca, names, servers

    def resolve(self, host, port):
        if host not in self.names:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return list(self.names[host])

    def connect(self, address, port, timeout):
        if address not in self.servers:
            raise ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
        return socket.create_connection((LOOPBACK, self.servers[address]), timeout)

    def tls(self):
        return ssl.create_default_context(cafile=self.ca)


class Platform:
    """How whatever is in front of AgentCake passes a request on. drop: request headers it removes; replace: request
    headers it sets to its own value; add: request headers it adds; keep_host: False sends the upstream's address as
    Host (nginx's and Apache's default); client_ip: the address it writes into X-Cake-Client-IP (None: it writes none
    and passes on what came); clear_ja4: it removes a visitor's X-Cake-JA4 (deploy/Caddyfile does); ja4: the value it
    writes there instead; answer: headers it adds to its answers; cors: CORS_PASS, CORS_AS_0_6 or CORS_NONE; blocked:
    the ends of paths it answers 404 to itself, as a reverse proxy without a rule for them; refused: the methods it
    answers 403 to itself, as a CloudFront behavior whose Allowed HTTP methods leave them out ("Invalid method")."""

    def __init__(self, drop=(), replace=None, add=None, keep_host=True, client_ip=None, clear_ja4=True, ja4=None,
                 answer=None, cors=CORS_PASS, blocked=(), refused=()):
        self.drop = {name.lower() for name in drop}
        self.replace, self.add, self.answer = dict(replace or {}), dict(add or {}), dict(answer or {})
        self.keep_host, self.client_ip, self.clear_ja4, self.ja4, self.cors = keep_host, client_ip, clear_ja4, ja4, cors
        self.blocked, self.refused = tuple(blocked), tuple(refused)


class TLSServer(ThreadingHTTPServer):
    """An HTTPS server on a free port of 127.0.0.1, in a thread, until close(). The TLS handshake is made in each
    request's own thread, so a client that refuses the certificate holds nothing up."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, certificate, handler):
        super().__init__((LOOPBACK, 0), handler)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(*certificate)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def finish_request(self, request, client_address):
        try:
            secure = self.context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):  # the client refused the certificate, or left
            return
        with secure:
            super().finish_request(secure, client_address)

    def close(self):
        self.shutdown()
        self.server_close()


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, headers, body=b""):
        self.send_response_only(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ElsewhereHandler(Quiet):
    """Another server: whatever is asked, 404."""

    def do_GET(self):
        self.answer(HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")], b"not found")

    do_POST = do_OPTIONS = do_GET


class FrontHandler(Quiet):
    def do_GET(self):
        platform, origin = self.server.platform, self.headers.get("Origin")
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        collect = self.path.endswith(COLLECT_SUFFIX)
        own = list(platform.answer.items())  # on the answers it makes itself too
        if platform.blocked and self.path.endswith(platform.blocked):
            return self.answer(HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")] + own, b"not found")
        if self.command in platform.refused:
            return self.answer(HTTPStatus.FORBIDDEN, [("Content-Type", "text/html")] + own, b"method not allowed here")
        if self.command == "OPTIONS" and collect and platform.cors != CORS_PASS:
            if platform.cors == CORS_NONE:
                return self.answer(HTTPStatus.NOT_FOUND, [("Content-Type", "text/plain")] + own, b"not found")
            return self.answer(HTTPStatus.NO_CONTENT, cors_0_6(origin) + list(CORS_0_6.items()) + own)
        status, headers, answer = self.forward(platform, body)
        headers = [(n, v) for n, v in headers if n.lower() not in HOP_BY_HOP | {"content-length"}]
        if platform.cors == CORS_NONE:
            headers = [(n, v) for n, v in headers if not n.lower().startswith("access-control-")]
        elif platform.cors == CORS_AS_0_6 and collect and origin:
            headers += cors_0_6(origin)
        replaced = {name.lower() for name in platform.answer}
        self.answer(status, [(n, v) for n, v in headers if n.lower() not in replaced] + own, answer)

    do_POST = do_OPTIONS = do_GET

    def forward(self, platform, body):
        upstream = self.server.upstream
        headers = [(n, v) for n, v in self.headers.items() if n.lower() not in HOP_BY_HOP | platform.drop]
        host = next((v for n, v in headers if n.lower() == "host"), "") if platform.keep_host else \
            f"{LOOPBACK}:{upstream}"
        changed = {name.lower() for name in platform.replace} | {"host"}
        if platform.clear_ja4 or platform.ja4:
            changed.add("x-cake-ja4")
        if platform.client_ip:
            changed.add("x-cake-client-ip")
        headers = [("Host", host)] + [(n, v) for n, v in headers if n.lower() not in changed]
        headers += list(platform.replace.items()) + list(platform.add.items())
        if platform.ja4:
            headers.append(("X-Cake-JA4", platform.ja4))
        if platform.client_ip:
            headers.append(("X-Cake-Client-IP", platform.client_ip))
        connection = http.client.HTTPConnection(LOOPBACK, upstream, timeout=UPSTREAM_TIMEOUT_S)
        try:
            connection.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders(body or None)
            response = connection.getresponse()
            return response.status, response.getheaders(), response.read()
        except OSError:  # nothing listens there: a reverse proxy answers 502, as Caddy does
            return HTTPStatus.BAD_GATEWAY, [("Content-Type", "text/plain")], b"bad gateway"
        finally:
            connection.close()


class FormerHandler(Quiet):
    """Another AgentCake with this site key: cake.js carries it, and every upload is answered 204 with CORS."""

    def do_GET(self):
        self.answer(HTTPStatus.OK, [("Content-Type", "text/javascript")], f'var key="{self.server.site_key}";'.encode())

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.answer(HTTPStatus.NO_CONTENT, cors_0_6(self.headers.get("Origin")))

    def do_OPTIONS(self):
        self.answer(HTTPStatus.NO_CONTENT, cors_0_6(self.headers.get("Origin")) + list(CORS_0_6.items()))


def cors_0_6(origin):
    return [("Access-Control-Allow-Origin", origin), ("Vary", "Origin")] if origin else []


class Front(TLSServer):
    """An HTTPS server passing every request on to AgentCake's public listener (on upstream, a port of 127.0.0.1)
    the way platform does; 502 when nothing listens there."""

    def __init__(self, certificate, upstream, platform):
        self.upstream, self.platform = upstream, platform
        super().__init__(certificate, FrontHandler)


class Elsewhere(TLSServer):
    def __init__(self, certificate):
        super().__init__(certificate, ElsewhereHandler)


class Former(TLSServer):
    def __init__(self, certificate, site_key):
        self.site_key = site_key
        super().__init__(certificate, FormerHandler)


def cdn_addresses(count):
    """count addresses inside the first CDN range of the bundled lists (Cloudflare's, in this release)."""
    entry = next(spec for spec in lists.current().raw_ranges() if spec["kind"] == "cdn")
    network = ipaddress.ip_network(entry["v4"][0])
    return [str(network.network_address + offset) for offset in range(1, count + 1)]
