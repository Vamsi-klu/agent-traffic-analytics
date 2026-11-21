"""Websites whose HTTPS certificate Python's default check refuses, for doctor opening a page
(tests/test_doctor_live_certificates.py). Nothing here leaves 127.0.0.1.

SiteCertificates makes the certificates with the openssl command in a scratch folder for each run (no private key is
kept in the repository): a test certificate authority, ca, which the tests trust, and certificates for localhost:
good (signed by ca), expired (signed by ca, valid for one day of January 2020), self_signed, other_name (signed by ca
for other.example only), no_key_id (signed by ca without an Authority Key Identifier, which RFC 5280 asks every
certificate a CA signs to have and Python 3.13 and later check: ssl.create_default_context sets VERIFY_X509_STRICT) and
unknown_issuer (signed by a second authority that no test trusts, as behind a proxy that replaces certificates). None
of them when the openssl command is missing: available is False, and the tests that need them skip. `openssl ca` signs
them all: it alone sets past dates in every openssl the tests meet (OpenSSL 1.1.1 and 3, LibreSSL).

trusting(ca) installs urllib's default opener (the one doctor's urlopen uses) with Python's default certificate check,
trusting only the authority in the file ca, as doctor checks a site's certificate against the authorities Python
trusts. HTTPSPage and HTTPPage serve one page, over HTTPS with a certificate or over plain HTTP; HTTPRedirect sends
every request on to another address. Python's standard library only.
"""
import contextlib
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import urllib.request
from http import HTTPStatus
from http.server import ThreadingHTTPServer

from doctor_public_fixtures import LOOPBACK, OPENSSL_TIMEOUT_S, Quiet, TLSServer

HOST = "localhost"
OTHER_HOST = "other.example"
VALID_DAYS = 2  # made for this run only
EXPIRED = ("200101000000Z", "200102000000Z")  # notBefore, notAfter as openssl ca takes them (UTCTime): one day of 2020
POLL_S = 0.01
# OpenSSL's major version 3: its signing commands add an Authority Key Identifier unasked, and its strict check (from
# 3.0) refuses a certificate without one.
OPENSSL_3 = 3

OPENSSL_CONFIG = """[req]
distinguished_name = dn
[dn]
[ca]
default_ca = test
[test]
database = index.txt
new_certs_dir = .
serial = serial
default_md = sha256
policy = any_name
unique_subject = no
email_in_dn = no
[any_name]
commonName = supplied
[authority]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
[server]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:{host}
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
[other_name]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:{other}
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
[no_key_id]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:{host}
subjectKeyIdentifier = hash
{no_key_id}"""


class SiteCertificates:
    """ca: the test authority's certificate file; good, expired, self_signed, other_name, no_key_id, unknown_issuer:
    (certificate, key) files (the module docstring)."""

    def __init__(self):
        self.folder, self.available = None, bool(shutil.which("openssl"))
        if not self.available:
            return
        self.folder = tempfile.mkdtemp(prefix="cake-test-site-tls-")
        none = "authorityKeyIdentifier = none\n" if adds_key_id_unasked() else ""
        self._write("openssl.cnf", OPENSSL_CONFIG.format(host=HOST, other=OTHER_HOST, no_key_id=none))
        self._write("index.txt", "")
        self._write("serial", "01\n")
        self.ca = self._authority("ca")
        self.good = self._signed("good", "server")
        self.expired = self._signed("expired", "server", dates=EXPIRED)
        self.other_name = self._signed("other-name", "other_name")
        self.no_key_id = self._signed("no-key-id", "no_key_id")
        self._authority("untrusted")
        self.unknown_issuer = self._signed("unknown-issuer", "server", issuer="untrusted")
        self.self_signed = (self._path("self-signed.pem"), self._key("self-signed"))
        self._openssl("req", "-new", "-x509", "-key", self.self_signed[1], "-out", self.self_signed[0], "-subj",
                      "/CN=" + HOST, "-days", str(VALID_DAYS), "-config", "openssl.cnf", "-extensions", "server")

    def remove(self):
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)

    def _authority(self, name):
        """The certificate file of a new authority called name (its key in <name>.key)."""
        certificate = self._path(name + ".pem")
        self._openssl("req", "-new", "-x509", "-key", self._key(name), "-out", certificate, "-subj",
                      f"/CN=AgentCake test authority {name}", "-days", str(VALID_DAYS), "-config", "openssl.cnf",
                      "-extensions", "authority")
        return certificate

    def _signed(self, name, section, issuer="ca", dates=None):
        """(certificate, key) for HOST signed by the authority called issuer, with the extensions of section, valid
        for VALID_DAYS from now or from dates[0] to dates[1]."""
        key, request, certificate = self._key(name), name + ".csr", self._path(name + ".pem")
        self._openssl("req", "-new", "-key", key, "-out", request, "-subj", "/CN=" + HOST, "-config", "openssl.cnf")
        span = ["-startdate", dates[0], "-enddate", dates[1]] if dates else ["-days", str(VALID_DAYS)]
        self._openssl("ca", "-batch", "-notext", "-config", "openssl.cnf", "-cert", issuer + ".pem",
                      "-keyfile", issuer + ".key", "-in", request, "-out", certificate, "-extensions", section, *span)
        return certificate, key

    def _key(self, name):
        self._openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", name + ".key")
        return self._path(name + ".key")

    def _path(self, name):
        return os.path.join(self.folder, name)

    def _write(self, name, content):
        with open(self._path(name), "w", encoding="utf-8") as f:
            f.write(content)

    def _openssl(self, *args):
        """openssl in the scratch folder, where openssl ca keeps its database and serial number."""
        subprocess.run(("openssl",) + args, check=True, capture_output=True, timeout=OPENSSL_TIMEOUT_S, cwd=self.folder)


def adds_key_id_unasked():
    """Whether the openssl command adds an Authority Key Identifier to a certificate it signs unless the extensions
    say 'authorityKeyIdentifier = none': OpenSSL 3 does; OpenSSL 1.1.1 and LibreSSL add none they are not asked for,
    and refuse 'none'."""
    found = subprocess.run(("openssl", "version"), check=True, capture_output=True, text=True,
                           timeout=OPENSSL_TIMEOUT_S)
    name, version = found.stdout.split()[:2]  # "OpenSSL 3.6.4 25 Aug 2026", "LibreSSL 3.3.6"
    return name == "OpenSSL" and int(version.split(".")[0]) >= OPENSSL_3


def strict_check():
    """Whether Python's default certificate check refuses a certificate without an Authority Key Identifier: Python
    3.13 and later set VERIFY_X509_STRICT, and OpenSSL checks the identifier under it from OpenSSL 3.0 on."""
    strict = ssl.create_default_context().verify_flags & ssl.VERIFY_X509_STRICT
    return bool(strict) and ssl.OPENSSL_VERSION_INFO[0] >= OPENSSL_3


@contextlib.contextmanager
def trusting(ca):
    """urllib's default opener checks certificates as Python's default check does, trusting only the authority in the
    file ca; afterwards urllib makes its own default opener again."""
    context = ssl.create_default_context(cafile=ca)
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=context)))
    try:
        yield
    finally:
        urllib.request.install_opener(None)


class PageHandler(Quiet):
    """The website: every GET gets the server's page."""

    def do_GET(self):
        self.answer(HTTPStatus.OK, [("Content-Type", "text/html; charset=utf-8")], self.server.page)


class HTTPSPage(TLSServer):
    """page (bytes) over HTTPS with certificate ((certificate, key) files), on a free port of 127.0.0.1."""

    def __init__(self, certificate, page):
        self.page = page
        super().__init__(certificate, PageHandler)


class RedirectHandler(Quiet):
    """Every GET is sent on to the server's location."""

    def do_GET(self):
        self.answer(HTTPStatus.FOUND, [("Location", self.server.location)])


class PlainServer(ThreadingHTTPServer):
    """A plain HTTP server on a free port of 127.0.0.1, in a thread, until close()."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, handler):
        super().__init__((LOOPBACK, 0), handler)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, kwargs={"poll_interval": POLL_S}, daemon=True).start()

    def close(self):
        self.shutdown()
        self.server_close()


class HTTPPage(PlainServer):
    """page (bytes) over plain HTTP."""

    def __init__(self, page):
        self.page = page
        super().__init__(PageHandler)


class HTTPRedirect(PlainServer):
    """Every page redirects to location (302 Found), over plain HTTP."""

    def __init__(self, location):
        self.location = location
        super().__init__(RedirectHandler)
