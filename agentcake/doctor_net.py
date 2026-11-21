"""How `doctor` reaches addresses on the internet in server mode (doctor_public.py): one HTTP exchange at a time.

Network is the system's: its resolver (socket.getaddrinfo, the hosts file included), a TCP connection, and Python's
default certificate check (ssl.create_default_context: the chain up to a trusted authority and the host name, as a
browser checks them). A test stands its own in (tests/doctor_public_fixtures.FakeNet): made-up DNS leading to servers on
127.0.0.1, and a certificate check that trusts only a test authority.

exchange(net, url, method, headers, body, timeout) -> Exchange(answer, error, certificate): the answer (status, its
headers in order, its body), or the error that kept the request from being answered (no DNS record, no connection, a
certificate the check refused, an answer that is not HTTP), and for https the certificate that passed the check (the
dictionary ssl.SSLSocket.getpeercert() gives). The request goes to the addresses the resolver gives, in order, with the
URL's host name as Host and as the TLS server name.
"""
import errno
import http.client
import os
import socket
import ssl
import time
from collections import namedtuple
from urllib.parse import urlsplit

from agentcake import __version__
from agentcake.datafiles import load
from agentcake.wording import product

HTTPS = "https"
DEFAULT_PORTS = {"http": 80, HTTPS: 443}  # protocol: the default ports of the URI schemes (RFC 9110 4.2)
DAY_FORMAT = "%Y-%m-%d"
# Why a request got no answer: no address, no connection, a refused certificate (ssl.SSLError is an OSError), an
# address that is no URL (ValueError), an answer that is not HTTP (http.client.HTTPException).
UNANSWERED = (OSError, ValueError, http.client.HTTPException)

Answer = namedtuple("Answer", "status headers body")  # headers: [(name, value)] as they came
Exchange = namedtuple("Exchange", "answer error certificate")


class Network:
    """The system's resolver, TCP and certificate check (the module docstring)."""

    def __init__(self):
        self._tls = None

    def resolve(self, host, port):
        """The addresses of host, in the resolver's order, each once; socket.gaierror when it has none."""
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return list(dict.fromkeys(address[0] for *_, address in found))

    def connect(self, address, port, timeout):
        return socket.create_connection((address, port), timeout)

    def tls(self):
        if self._tls is None:
            self._tls = ssl.create_default_context()
        return self._tls


class _Connection(http.client.HTTPConnection):
    """One HTTP connection to host, made through net to the first of addresses that accepts it; for https, wrapped in
    TLS checked for host by net's certificate check."""

    def __init__(self, net, scheme, host, port, addresses, timeout):
        super().__init__(host, port, timeout=timeout)
        self.net, self.scheme, self.addresses, self.certificate = net, scheme, addresses, None
        self.default_port = DEFAULT_PORTS[scheme]  # Host carries the port only when it is not the scheme's own

    def connect(self):
        connection = self._open()
        if self.scheme == HTTPS:
            connection = self.net.tls().wrap_socket(connection, server_hostname=self.host)
            self.certificate = connection.getpeercert()
        self.sock = connection

    def _open(self):
        refused = ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))  # when there is none
        for address in self.addresses:
            try:
                return self.net.connect(address, self.port, self.timeout)
            except OSError as error:
                refused = error
        raise refused


def exchange(net, url, method, headers, body=None, timeout=None):
    """One request and its answer (the module docstring)."""
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port or DEFAULT_PORTS[parts.scheme]
        connection = _Connection(net, parts.scheme, host, port, net.resolve(host, port), timeout)
        try:
            connection.request(method, (parts.path or "/") + ("?" + parts.query if parts.query else ""), body, headers)
            response = connection.getresponse()
            return Exchange(Answer(response.status, response.getheaders(), response.read()), None,
                            connection.certificate)
        finally:
            connection.close()
    except UNANSWERED as error:
        return Exchange(None, error, None)


def header(answer, name):
    """The first value of a header of an answer, or None."""
    return next((value for key, value in answer.headers if key.lower() == name.lower()), None) if answer else None


def valid_until(certificate):
    """The day (UTC) a certificate expires, from getpeercert()'s notAfter; None without one."""
    if not certificate or not certificate.get("notAfter"):
        return None
    return time.strftime(DAY_FORMAT, time.gmtime(ssl.cert_time_to_seconds(certificate["notAfter"])))


def user_agent():
    """doctor's own User-Agent, {command}-doctor/{version} (data/doctor.json)."""
    return load("data/doctor.json")["user_agent"].format(command=product()["command"], version=__version__)
