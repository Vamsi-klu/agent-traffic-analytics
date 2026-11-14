"""What the Python site middleware's tests share: the shared vectors, a browser's page request, and a WSGI server
and an ASGI server written by hand, so tests/test_edge_python.py and tests/test_edge_python_mountings.py read the same
requests and responses. Not a test module: discovery leaves it alone.
"""
import asyncio, base64, io, json, os, re, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDGE_PYTHON = os.path.join(ROOT, "edge", "python")
sys.path.insert(0, ROOT)
sys.path.insert(0, EDGE_PYTHON)
import cake_edge  # noqa: E402  (the file a site copies, loaded from edge/python as the site would load it)
from agentcake import edge_token  # noqa: E402

with open(os.path.join(HERE, "vectors", "edge_token.json"), encoding="utf-8") as f:
    VECTORS = json.load(f)
SECRET = "test-only secret for the Python middleware, never used elsewhere"
NOW = VECTORS["mint"][0]["now_ms"]
CLIENT_IP = "203.0.113.77"  # RFC 5737 documentation range: nobody's address
CHROME_PAGE = VECTORS["mint"][0]["request"]["headers"]  # a page typed into Chrome, header lines in Chrome's order
EDGE_WHITESPACE = " \t\r\n"  # protocol: what a server trims around a header value
HTML = "text/html; charset=utf-8"
PAGE_BODY = b"<!doctype html><title>Shop</title><a href='/next'>next</a>"


def payload_of(token):
    """The payload as anyone reading the response can read it: no secret needed."""
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8"))


def token_in(server_timing):
    match = re.search(r'(?:^|,)\s*cake;desc="([^"]*)"', server_timing or "")
    return match.group(1) if match else None


def values_of(headers, name):
    """Every value of one header in a WSGI or ASGI header list, as text."""
    def text(value):
        return value.decode("latin-1") if isinstance(value, bytes) else value
    return [text(value) for key, value in headers if text(key).lower() == name]


def read_token(token, secret=SECRET):
    """What cake concludes from a token at NOW: ("ok" | "stale" | "bad", payload)."""
    return edge_token.read_token(secret.encode("utf-8"), token, NOW)


def vector_extras(vector):
    return dict(now_ms=vector["now_ms"], token_id=vector["id"], ip=vector["client_ip"], verdict=vector["verdict"],
                version=vector["version"])


# ---------------------------------------------------------------- WSGI: environ, a call, a page
def wsgi_environ(path="/", lines=CHROME_PAGE, method="GET", request_uri=True):
    """The environ a WSGI server builds: the header lines as HTTP_ keys in the order sent, each value trimmed, a repeated
    line joined (here with ", " as Node joins them; each server has its own separator: wsgiref uses ",")."""
    target, _, query = path.partition("?")
    environ = {"REQUEST_METHOD": method, "SCRIPT_NAME": "", "PATH_INFO": urllib.parse.unquote(target, "latin-1"),
               "QUERY_STRING": query, "SERVER_NAME": "shop.example", "SERVER_PORT": "443", "SERVER_PROTOCOL": "HTTP/1.1",
               "REMOTE_ADDR": CLIENT_IP, "wsgi.version": (1, 0), "wsgi.url_scheme": "https", "wsgi.input": io.BytesIO(),
               "wsgi.errors": io.StringIO(), "wsgi.multithread": False, "wsgi.multiprocess": False, "wsgi.run_once": False}
    if request_uri:
        environ["REQUEST_URI"] = path
    for name, value in lines:
        key, value = "HTTP_" + name.upper().replace("-", "_"), value.strip(EDGE_WHITESPACE)
        environ[key] = f"{environ[key]}, {value}" if key in environ else value
    return environ


def call_wsgi(app, environ):
    """(status, headers, body) of one call, closing the response as a server must."""
    got = {}

    def start_response(status, headers, exc_info=None):
        got.update(status=status, headers=headers)
        return lambda data: None
    result = app(environ, start_response)
    try:
        body = b"".join(result)
    finally:
        if hasattr(result, "close"):
            result.close()
    return got["status"], got["headers"], body


def html_page(environ, start_response):
    start_response("200 OK", [("Content-Type", HTML)])
    return [PAGE_BODY]


def wsgi_app_with(headers, status="200 OK"):
    def app(environ, start_response):
        start_response(status, list(headers))
        return [b"" if status.startswith("304") else PAGE_BODY]
    return app


def mount_wsgi(app=html_page, **options):
    settings = dict(secret=SECRET, now=lambda: NOW, random_id=lambda: "id-1", client_ip=lambda environ: CLIENT_IP)
    return cake_edge.CakeEdgeWSGI(app, **{**settings, **options})


# ---------------------------------------------------------------- ASGI: a hand-written server
def http_scope(path="/", lines=CHROME_PAGE, method="GET", raw_path=True):
    """The scope an ASGI server builds: header lines as sent (names lower-cased, repeats kept), raw_path as sent."""
    target, _, query = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "https",
             "path": urllib.parse.unquote(target), "query_string": query.encode("latin-1"), "root_path": "",
             "headers": [(name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in lines],
             "client": (CLIENT_IP, 50000), "server": ("127.0.0.1", 8000)}
    if raw_path:
        scope["raw_path"] = target.encode("latin-1")
    return scope


def call_asgi(app, scope):
    """Every message the app sends for one request, in order."""
    sent, incoming = [], [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        return incoming.pop(0) if incoming else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
    asyncio.run(app(scope, receive, send))
    return sent


def asgi_app_with(headers, chunks=(PAGE_BODY,), status=200):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": list(headers)})
        for chunk in chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
    return app


def mount_asgi(app=None, **options):
    settings = dict(secret=SECRET, now=lambda: NOW, random_id=lambda: "id-1", client_ip=lambda scope: CLIENT_IP)
    return cake_edge.CakeEdgeASGI(app or asgi_app_with([(b"content-type", HTML.encode())]), **{**settings, **options})


def asgi_head(messages):
    starts = [m for m in messages if m["type"] == "http.response.start"]
    return starts[0]["headers"] if starts else None
