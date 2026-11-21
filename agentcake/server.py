"""The two listeners: the local page on 127.0.0.1, and server mode's public listener (0.3.3).

serve() runs the local listener on 127.0.0.1:<port>, when public_listen is set the public one in a thread, the upkeep of
the replay chunks in another (maintenance.py), and in a third the daily check for the monthly update of the lists and
the city database (updates.py, while lists_auto_update is on), which runs the update in a process of its own. Each
request is answered by the view routes.py names for it. The local listener lets any origin post to collect (a site on
this computer, such as a dev server on another port, sends its visits there) and to nothing else: no other answer
carries CORS headers, so no other site's page can read the local pages' data (/api also checks Host and Origin,
api/answers.py). The public listener answers only below path_prefix. Both read a POST's body only when one
Content-Length of digits frames it, within public_max_body_bytes or local_max_body_bytes (body_length): anything else is
refused unread, 400, 411 for Transfer-Encoding (http.server reads no chunked body) or 413, and the connection closed,
since what is left of the body on it could be taken for the next request. On the subdomain route the website's
pages (https://www.example.com) send to another origin (https://cake.example.com), so its collect, and only collect,
answers CORS the way PostHog 1.0.0's capture did (posthog/api/capture.py cors_response, MIT; the approach, not its
code): the request's own Origin may read the answer, which is empty, and a preflight gets 204. That is any origin:
whether a visit counts as the website's is site_domain's to say (site_origin.py), and an answer a page could not read
would only make cake.js send the same batch again on every tick. Without credentials: cake.js sends no cookie.
SIGINT and SIGTERM end serve() cleanly.
"""
import re
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from agentcake import __version__, addresses, maintenance, paths, routes, updates
from agentcake.config import LOCAL_HOST, base_url, ensure_cfg, load_cfg
from agentcake.edge_secret import srv_secret
from agentcake.netfacts import ranges
from agentcake.responses import HTML, JS, TEXT, Request, not_found
from agentcake.wording import text

# What a browser writes in Origin (RFC 6454, section 7): "null" for an opaque origin (a sandboxed page, a file), else
# scheme://host[:port], the host a name, an IPv4 address or an IPv6 one in brackets. Only such a value is sent back:
# a header's value goes into the answer as it is.
SCHEME, HOST, PORT = r"[A-Za-z][A-Za-z0-9+.-]*", r"(?:[A-Za-z0-9._~-]+|\[[0-9A-Fa-f:.]+\])", r"(?::[0-9]+)?"
ORIGIN = re.compile(f"null|{SCHEME}://{HOST}{PORT}")  # protocol: RFC 6454's serialized origin
PREFLIGHT = {"Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type"}  # what cake.js sends
CONTENT_LENGTH, TRANSFER_ENCODING = "Content-Length", "Transfer-Encoding"  # protocol: a body's framing (RFC 9112 6)
DIGITS = re.compile("[0-9]+")  # protocol: Content-Length = 1*DIGIT (RFC 9110 8.6)
REFUSED_BODY = {HTTPStatus.BAD_REQUEST: "bad length", HTTPStatus.LENGTH_REQUIRED: "length required",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "too large"}  # answer bodies, as "not found" is
# The answers a browser may keep: the page script, and a 304 for it, which carries the Cache-Control its 200 would
# (RFC 9110 15.4.5). Any other answer of the public listener is no-store.
SCRIPT_KEPT = (HTTPStatus.OK, HTTPStatus.NOT_MODIFIED)


def answer(table, method, request):
    view = routes.resolve(table, method, request.path)
    return view(request) if view else not_found()


class LocalHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def parse_request(self):
        """The request line as http.server reads it, with a target urllib can read: one it cannot (an unclosed IPv6
        bracket, "GET http://[ HTTP/1.1", which anyone can send) is answered 400 the way http.server answers any
        request line it cannot read, before a view sees it. Both listeners read their request lines here."""
        if not super().parse_request():
            return False
        if addresses.split(self.path) is None:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return False
        return True

    def out(self, code, body, ctype=HTML, extra=None, cors=False):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.content_headers(code, ctype, b)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers(); self.wfile.write(b)

    def content_headers(self, code, ctype, body):
        """Content-Type and Content-Length, except on a 304 (the page script's, script_response.py): it has no content,
        and a Content-Length there would say that the script is empty (RFC 9110 8.6)."""
        if code != HTTPStatus.NOT_MODIFIED:
            self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))

    def send(self, response, cors=False):
        return self.out(response.status, response.body, response.ctype, response.headers, cors)

    def body_length(self, limit, cors=False):
        """How many bytes of body to read (0 without a Content-Length), or None once the request is refused unread
        (the module docstring): a length that is not one line of digits, one over limit, or Transfer-Encoding."""
        lengths = [value.strip() for value in self.headers.get_all(CONTENT_LENGTH) or []]
        if self.headers.get(TRANSFER_ENCODING) is not None:
            refusal = HTTPStatus.LENGTH_REQUIRED
        elif len(lengths) > 1 or (lengths and not DIGITS.fullmatch(lengths[0])):
            refusal = HTTPStatus.BAD_REQUEST
        elif lengths and int(lengths[0]) > limit:
            refusal = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        else:
            return int(lengths[0]) if lengths else 0
        self.close_connection = True  # the body is not read
        self.out(refusal, REFUSED_BODY[refusal], TEXT, cors=cors)
        return None

    def do_OPTIONS(self):
        if urlsplit(self.path).path != routes.COLLECT:
            return self.out(HTTPStatus.NOT_FOUND, "not found", TEXT)
        self.send_response(HTTPStatus.NO_CONTENT); self.send_header("Access-Control-Allow-Origin", "*")
        for name, value in PREFLIGHT.items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self):
        u = urlsplit(self.path)
        # A parameter sent empty stays: an empty key is a value of its own (api/sessions.py: no referrer, Direct).
        request = Request(u.path, parse_qs(u.query, keep_blank_values=True), self.headers)
        return self.send(answer(routes.LOCAL, "GET", request))

    def do_POST(self):
        u = urlsplit(self.path)
        cors = u.path == routes.COLLECT
        n = self.body_length(load_cfg()["local_max_body_bytes"], cors)
        if n is None:
            return None
        return self.send(answer(routes.LOCAL, "POST", Request(u.path, parse_qs(u.query), self.headers,
                                                              self.rfile.read(n))), cors=cors)


class PublicHandler(LocalHandler):
    """Server mode's public listener: the page script, collect and a health check, under path_prefix.
    Nothing else: the local page (dashboard, replay, settings) is never served here. cors: collect's answer, which
    the request's own Origin may read (the module docstring says why)."""

    def out(self, code, body, ctype=HTML, extra=None, cors=False):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.content_headers(code, ctype, b)
        self.send_header("Cache-Control", "no-store" if code not in SCRIPT_KEPT or ctype != JS
                         else f"public, max-age={load_cfg()['public_script_cache_s']}")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in {**(extra or {}), **(self.cors_headers() if cors else {})}.items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def cors_headers(self):
        """The request's own Origin as the one that may read the answer, or nothing for a value no browser sends."""
        origin = self.headers.get("Origin") or ""
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if ORIGIN.fullmatch(origin) else {}

    def do_OPTIONS(self):
        if self.sub() != routes.COLLECT:
            return self.out(HTTPStatus.NOT_FOUND, "not found", TEXT)
        return self.out(HTTPStatus.NO_CONTENT, b"", TEXT, PREFLIGHT, cors=True)

    def sub(self, c=None):
        pre = (c or load_cfg()).get("path_prefix", "")
        p = urlsplit(self.path).path
        if pre and not (p == pre or p.startswith(pre + "/")):
            return None
        return p[len(pre):] or "/"

    def do_GET(self):
        return self.send(answer(routes.PUBLIC, "GET", Request(self.sub(), {}, self.headers)))

    def do_POST(self):
        c = load_cfg()
        p = self.sub(c)
        view = routes.resolve(routes.PUBLIC, "POST", p)
        if not view:
            self.close_connection = True  # the body is not read
            return self.out(HTTPStatus.NOT_FOUND, "not found", TEXT)
        cors = p == routes.COLLECT  # a refusal too: cake.js reads its status as final instead of sending it again
        n = self.body_length(c["public_max_body_bytes"], cors)
        if n is None:
            return None
        return self.send(view(Request(p, {}, self.headers, self.rfile.read(n))), cors=cors)


class Listener(ThreadingHTTPServer):
    """A listener whose close does not wait for the requests still being answered: their threads are daemon threads
    (ThreadingHTTPServer), so a client that keeps an idle connection open cannot hold serve() up when it stops."""
    block_on_close = False


def make_listeners(c):
    """The local listener on 127.0.0.1:<port> and, in server mode, the public one on public_listen (else None)."""
    local, public = Listener((LOCAL_HOST, c["port"]), LocalHandler), None
    if c.get("public_listen"):
        host, _, port = c["public_listen"].rpartition(":")
        public = Listener((host.strip("[]"), int(port)), PublicHandler)
    return local, public


def stop_on_signals(listeners):
    """SIGINT (Ctrl+C) and SIGTERM (systemd, `agentcake stop`, a container's stop: there Python is PID 1, which gets no
    default action for SIGTERM) end serve() cleanly instead of with a KeyboardInterrupt traceback. shutdown()
    waits for serve_forever() to return, so it runs in a thread of its own, never in the handler on the main thread."""
    def on_signal(signum, frame):
        for listener in listeners:
            threading.Thread(target=listener.shutdown, daemon=True).start()

    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(stop_signal, on_signal)


def serve():
    c = ensure_cfg()
    local, public = make_listeners(c)
    listeners = [listener for listener in (local, public) if listener]
    stop_on_signals(listeners)
    print(text("serving", version=__version__, base=base_url(c), home=paths.home()), flush=True)
    upkeep = maintenance.start()  # sealing replay chunks, and the nightly recompression
    checks = updates.start()  # the monthly update of the lists and, on a server, the city database
    if public:
        threading.Thread(target=public.serve_forever, daemon=True).start()
        print(text("public_listening", listen=c["public_listen"], prefix=c.get("path_prefix") or "/",
                   trust_lb=bool(c.get("trust_lb")), half="on" if srv_secret() else "off", ranges=ranges()["built"]), flush=True)
    try:
        local.serve_forever()
    finally:
        upkeep.set()  # no new upkeep round starts; one under way ends with the process (each round commits as it goes)
        checks.set()  # no new check starts; an update under way ends by itself in its own process
        if public:
            public.shutdown()  # its loop runs in another thread: wait for it to end before its socket is closed
        for listener in listeners:
            listener.server_close()
    print(text("serve_stopped"), flush=True)
