"""The two listeners: the local page on 127.0.0.1, and server mode's public listener (0.3.3).

serve() runs the local listener on 127.0.0.1:<port>, when public_listen is set the public one in a thread, and the
upkeep of the replay chunks in another (maintenance.py). Each request is answered by the view routes.py names for
it. The local listener lets any origin post to collect (a site on this computer, such as a dev server on another port,
sends its visits there) and to nothing else: no other answer carries CORS headers, so no other site's page can read the
local pages' data (/api also checks Host and Origin, api/answers.py). The public listener answers only below
path_prefix, refuses a body over public_max_body_bytes before reading it, and sends no CORS header (cake sits on a path
of the site's own domain). SIGINT and SIGTERM end serve() cleanly.
"""
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from agentcake import __version__, addresses, maintenance, paths, routes
from agentcake.config import LOCAL_HOST, base_url, ensure_cfg, load_cfg
from agentcake.edge_secret import srv_secret
from agentcake.netfacts import ranges
from agentcake.responses import HTML, JS, TEXT, Request, not_found
from agentcake.wording import text


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
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers(); self.wfile.write(b)

    def send(self, response, cors=False):
        return self.out(response.status, response.body, response.ctype, response.headers, cors)

    def do_OPTIONS(self):
        if urlsplit(self.path).path != routes.COLLECT:
            return self.out(HTTPStatus.NOT_FOUND, "not found", TEXT)
        self.send_response(HTTPStatus.NO_CONTENT); self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST"); self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self):
        u = urlsplit(self.path)
        # A parameter sent empty stays: an empty key is a value of its own (api/sessions.py: no referrer, Direct).
        request = Request(u.path, parse_qs(u.query, keep_blank_values=True), self.headers)
        return self.send(answer(routes.LOCAL, "GET", request))

    def do_POST(self):
        u = urlsplit(self.path)
        raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), load_cfg()["local_max_body_bytes"]))
        return self.send(answer(routes.LOCAL, "POST", Request(u.path, parse_qs(u.query), self.headers, raw)),
                         cors=u.path == routes.COLLECT)


class PublicHandler(LocalHandler):
    """Server mode's public listener: the page script, the recorder, collect and a health check, under path_prefix.
    Nothing else: the local page (dashboard, replay, settings) is never served here."""

    def out(self, code, body, ctype=HTML, extra=None, cors=False):  # no CORS here: cake is on the site's own domain
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store" if code != HTTPStatus.OK or ctype != JS
                         else f"public, max-age={load_cfg()['public_script_cache_s']}")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def do_OPTIONS(self):
        return self.out(HTTPStatus.NOT_FOUND, "not found", TEXT)

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
        n = int(self.headers.get("Content-Length") or 0)
        view = routes.resolve(routes.PUBLIC, "POST", p)
        if not view:
            return self.out(HTTPStatus.NOT_FOUND, "not found", TEXT)
        if n > c["public_max_body_bytes"]:
            self.close_connection = True  # the body is not read
            return self.out(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "too large", TEXT)
        return self.send(view(Request(p, {}, self.headers, self.rfile.read(n))))


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
    if public:
        threading.Thread(target=public.serve_forever, daemon=True).start()
        print(text("public_listening", listen=c["public_listen"], prefix=c.get("path_prefix") or "/",
                   trust_lb=bool(c.get("trust_lb")), half="on" if srv_secret() else "off", ranges=ranges()["built"]), flush=True)
    try:
        local.serve_forever()
    finally:
        upkeep.set()  # no new upkeep round starts; one under way ends with the process (each round commits as it goes)
        if public:
            public.shutdown()  # its loop runs in another thread: wait for it to end before its socket is closed
        for listener in listeners:
            listener.server_close()
    print(text("serve_stopped"), flush=True)
