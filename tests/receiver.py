"""A stand-in for Tartini AI's registration address (S5.8), and a guard that notes every connection a test tries.

    Receiver(status=200)          an HTTP server on a free port of this computer that answers every POST with status
                                  (a 3xx with a Location), keeps each request it got (method, path, headers, body),
                                  and .url is its address: what a test writes into register_url
    Receiver(hang=True)           one that reads the request and never answers (a receiver that times out)
    closed_url()                  the address of a port of this computer where nothing listens
    OutsideGuard()                with it: socket connections and name lookups for anything but this computer are
                                  refused and noted in .outside; those for this computer go ahead, noted in .local

The addresses are made when a test runs, from free ports of 127.0.0.1: nothing here names a fixed address or port.
"""
import http.server
import ipaddress
import socket
import threading
from unittest import mock

LOOPBACK = "127.0.0.1"  # protocol: the loopback address, where every stand-in listens
LOCAL_NAMES = ("localhost",)


def free_port():
    with socket.socket() as s:
        s.bind((LOOPBACK, 0))
        return s.getsockname()[1]


def closed_url():
    return f"http://{LOOPBACK}:{free_port()}/register"


class Receiver:
    def __init__(self, status=200, hang=False):
        self.requests, self.status, self.hang = [], status, hang
        self._release = threading.Event()
        receiver = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                receiver.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers),
                                          "body": body})
                if receiver.hang:
                    receiver._release.wait()
                    return
                self.send_response(receiver.status)
                if 300 <= receiver.status < 400:
                    self.send_header("Location", f"http://{LOOPBACK}:{self.server.server_port}/elsewhere")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                receiver.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers),
                                          "body": b""})
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.server = http.server.ThreadingHTTPServer((LOOPBACK, 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://{LOOPBACK}:{self.server.server_port}/register"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self._release.set()
        self.server.shutdown()
        self.server.server_close()


def _is_local(host):
    if host in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


class OutsideGuard:
    """Refuses (and notes) every connection or name lookup that would leave this computer."""

    def __init__(self):
        self.outside, self.local = [], []
        real_getaddrinfo, real_connect, real_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex
        real_sendto = socket.socket.sendto
        guard = self

        def check(where):
            host = where[0] if isinstance(where, tuple) else where
            if _is_local(host):
                guard.local.append(where)
                return
            guard.outside.append(where)
            raise ConnectionRefusedError(f"the test's guard refused a connection to {where!r}")

        def getaddrinfo(host, *args, **kwargs):
            check(host if isinstance(host, str) else str(host))
            return real_getaddrinfo(host, *args, **kwargs)

        def connect(sock, address):
            check(address)
            return real_connect(sock, address)

        def connect_ex(sock, address):
            check(address)
            return real_connect_ex(sock, address)

        def sendto(sock, data, *args):
            check(args[-1])
            return real_sendto(sock, data, *args)

        self._patches = [mock.patch.object(socket, "getaddrinfo", getaddrinfo),
                         mock.patch.object(socket.socket, "connect", connect),
                         mock.patch.object(socket.socket, "connect_ex", connect_ex),
                         mock.patch.object(socket.socket, "sendto", sendto)]

    def __enter__(self):
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in reversed(self._patches):
            patch.stop()
        return False
