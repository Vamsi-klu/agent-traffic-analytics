"""The updates' HTTPS requests follow a redirect only on the host they asked, and a body cut short fails them:
agentcake/downloads.py.

    python3 -I -m unittest discover -s tests -p test_downloads.py -v      (from the AgentCake folder)

An update promises to reach only the addresses sources.json and geo.json name, and urllib on its own follows a redirect
to any host (DigitalOcean's address answered with one to www.digitalocean.com). A stand-in on 127.0.0.1 answers each
path with a redirect: one on the same host is followed; one to another host name (localhost, the same computer, so the
test stays offline) is refused before anything is asked there, and the lists' and the city database's downloads fail
with it, leaving what is in use as it was. Another stand-in ends its answers early: a body shorter than its
Content-Length (which http.client hands over as if whole) and a chunked body cut off (IncompleteRead, which is not an
OSError) fail both downloads, after their retries, with their own BuildError.
"""
import http.server
import os
import socket
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import downloads, geoip_build  # noqa: E402
from agentcake.detect import lists_build  # noqa: E402

LOOPBACK, OTHER_NAME = "127.0.0.1", "localhost"  # protocol: two names of this computer, two hosts to a URL
BODY = b"the file"


class Redirects:
    """A local server: /same redirects to /file on the same host, /elsewhere to /file on another host name; every
    request is noted with the Host it named."""

    def __init__(self):
        self.asked = []
        stand_in = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                stand_in.asked.append((self.headers["Host"].split(":")[0], self.path))
                port = self.server.server_port
                targets = {"/same": f"http://{LOOPBACK}:{port}/file", "/elsewhere": f"http://{OTHER_NAME}:{port}/file"}
                if self.path in targets:
                    self.send_response(302)
                    self.send_header("Location", targets[self.path])
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(BODY)))
                self.end_headers()
                self.wfile.write(BODY)

        self.server = http.server.ThreadingHTTPServer((LOOPBACK, 0), Handler)
        self.server.daemon_threads = True
        self.base = f"http://{LOOPBACK}:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class SameHostOnly(unittest.TestCase):
    def setUp(self):
        self.stand_in = Redirects()
        self.addCleanup(self.stand_in.close)

    def test_a_redirect_on_the_same_host_is_followed(self):
        with downloads.urlopen(self.stand_in.base + "/same", timeout=5) as answer:
            self.assertEqual(answer.read(), BODY)
        self.assertEqual(self.stand_in.asked, [(LOOPBACK, "/same"), (LOOPBACK, "/file")])

    def test_a_redirect_to_another_host_is_refused_before_anything_is_asked_there(self):
        with self.assertRaises(downloads.RedirectElsewhere):
            downloads.urlopen(self.stand_in.base + "/elsewhere", timeout=5)
        self.assertEqual(self.stand_in.asked, [(LOOPBACK, "/elsewhere")])

    def test_the_lists_download_fails_on_a_redirect_elsewhere(self):
        fetch = lists_build.http_fetch({"user_agent": "test", "timeout_s": 5, "retries": 0, "max_bytes": 1000})
        with self.assertRaises(lists_build.BuildError) as raised:
            fetch(self.stand_in.base + "/elsewhere")
        self.assertIn(OTHER_NAME, str(raised.exception))
        self.assertEqual(fetch(self.stand_in.base + "/same").body, BODY)

    def test_the_city_database_download_fails_on_a_redirect_elsewhere(self):
        fetch = geoip_build.http_fetch(dict(geoip_build.FETCH, retries=0, timeout_s=5))
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(geoip_build.BuildError) as raised:
            fetch(self.stand_in.base + "/elsewhere", os.path.join(folder, "download"))
        self.assertIn(OTHER_NAME, str(raised.exception))
        self.assertNotIn((OTHER_NAME, "/file"), self.stand_in.asked)


class CutShort:
    """A local server whose answers end early: /length announces more bytes than it sends, /chunked stops in the
    middle of a chunk; each closes the connection then. Every request is counted."""

    def __init__(self):
        self.asked = []
        stand_in = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # protocol: chunked transfer coding needs HTTP/1.1

            def log_message(self, *args):
                pass

            def do_GET(self):
                stand_in.asked.append(self.path)
                self.send_response(200)
                if self.path == "/chunked":
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    self.wfile.write(f"{2 * len(BODY):x}\r\n".encode() + BODY)  # half of the chunk it announced
                else:
                    self.send_header("Content-Length", str(2 * len(BODY)))
                    self.end_headers()
                    self.wfile.write(BODY)
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)

        self.server = http.server.ThreadingHTTPServer((LOOPBACK, 0), Handler)
        self.server.daemon_threads = True
        self.base = f"http://{LOOPBACK}:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class BodyCutShort(unittest.TestCase):
    def setUp(self):
        self.stand_in = CutShort()
        self.addCleanup(self.stand_in.close)

    def test_the_lists_download_fails_after_its_retries(self):
        fetch = lists_build.http_fetch({"user_agent": "test", "timeout_s": 5, "retries": 1, "max_bytes": 1000})
        for path in ("/length", "/chunked"):
            with self.subTest(path=path), self.assertRaises(lists_build.BuildError):
                fetch(self.stand_in.base + path)
        self.assertEqual(self.stand_in.asked, ["/length", "/length", "/chunked", "/chunked"])

    def test_the_city_database_download_fails_before_anything_is_converted(self):
        fetch = geoip_build.http_fetch(dict(geoip_build.FETCH, retries=0, timeout_s=5))
        for path in ("/length", "/chunked"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as folder, \
                    self.assertRaises(geoip_build.BuildError):
                fetch(self.stand_in.base + path, os.path.join(folder, "download"))


if __name__ == "__main__":
    unittest.main()
