"""Web Bot Auth key directories: which public keys speak for which signer (S3.2).

In draft-ietf-webbotauth-httpsig-protocol-01 a signer is the HTTPS URL its Signature-Agent member names, where it
publishes a JWK Set (section 4.1). A verifier looks a key up by the pair (that URL, keyid), never by keyid alone
(section 5.4): otherwise a key of one signer would vouch for any other. keyid is the JWK SHA-256 thumbprint (RFC 7638,
and RFC 8037 A.3 for Ed25519); a directory may also label a key with a kid (section 5.5).

KeyDirectory takes {signer: keys}. The keys of a signer are a JWK Set ({"keys": [...]}), a list of JWKs, or
{keyid: 32-byte Ed25519 public key}. A signer is named by its host (with the port when it is not the default), which
stands for both the origin's well-known directory and the bare origin that deployed agents send
(Signature-Agent: "https://chatgpt.com"); a directory at another path is named by its full URL without the query.
signer_identifier() turns a Signature-Agent value into the same name (RFC 3986 6.2.2 and 6.2.3 normalisation).

Keys that cannot be used are handled as the draft asks (section 5.5.1, "reject malformed entries"): a malformed JWK
is left out; a well-formed key of another type (RSA, EC, X25519) is kept without key material, so that a signature
made with it can be told apart from one whose key is unknown. The keys come from S3.1's bundled lists; this module
never fetches anything.
"""
import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass

from agentcake.detect import ed25519, sfv
from agentcake.detect.httpsig import DEFAULT_PORTS

# the members a thumbprint hashes, per key type (RFC 7638 3.2; RFC 8037 2 for OKP)
THUMBPRINT_MEMBERS = {"OKP": ("crv", "kty", "x"), "EC": ("crv", "kty", "x", "y"), "RSA": ("e", "kty", "n")}
URL = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<host>[A-Za-z0-9.-]+)(?::(?P<port>[0-9]+))?"
                 r"(?P<path>/[^?#]*)?(?:\?[^#]*)?")
HOST = re.compile(r"[a-z0-9.-]+(?::[0-9]+)?")
PATH = re.compile(r"(?:[A-Za-z0-9\-._~!$&'()*+,;=:@/]|%[0-9A-Fa-f]{2})*")
PERCENT_ENCODED = re.compile(r"%([0-9A-Fa-f]{2})")
UNRESERVED = re.compile(r"[A-Za-z0-9\-._~]")
BASE64URL = re.compile(r"[A-Za-z0-9_-]*=*")


@dataclass(frozen=True)
class Key:
    """One key of a signer. public_key is None for a key type Agent Cake cannot verify (RSA, EC, X25519)."""

    thumbprint: str
    kid: object
    public_key: object
    not_before: object = None
    expires: object = None


class KeyDirectory:
    """The bundled keys of every known signer, looked up per signer."""

    def __init__(self, signers, settings):
        self._keys = {}
        for name, keys in signers.items():
            signer = _signer_name(name, settings)
            self._keys[signer] = self._keys.get(signer, ()) + tuple(_keys_of(name, keys))

    def knows(self, signer):
        return signer in self._keys

    def keys(self, signer):
        return self._keys.get(signer, ())

    def find(self, signer, keyid):
        """The key of ``signer`` whose thumbprint, or failing that whose kid, is ``keyid``; None when there is none."""
        keys = self.keys(signer)
        for key in keys:
            if key.thumbprint == keyid:
                return key
        return next((key for key in keys if key.kid == keyid), None)

    def holders(self, keyid):
        """[(signer, key)] for every signer that publishes a key with this keyid, for a signature naming no signer."""
        found = ((signer, self.find(signer, keyid)) for signer in self._keys)
        return [(signer, key) for signer, key in found if key is not None]


def thumbprint(jwk):
    """The JWK SHA-256 thumbprint (RFC 7638), base64url without padding; ValueError without the required members."""
    members = THUMBPRINT_MEMBERS.get(jwk.get("kty"))
    if members is None or not all(isinstance(jwk.get(member), str) for member in members):
        raise ValueError(f"no thumbprint for a JWK of type {jwk.get('kty')!r} without its required members")
    canonical = json.dumps({member: jwk[member] for member in members}, separators=(",", ":"), sort_keys=True,
                           ensure_ascii=False)
    return base64.urlsafe_b64encode(hashlib.sha256(canonical.encode("utf-8")).digest()).decode("ascii").rstrip("=")


def signer_identifier(value, settings):
    """The signer a Signature-Agent value names, or None when it is not an URL Agent Cake accepts.

    The scheme must be one of settings.signature_agent_schemes; no user information, fragment or IP literal. The
    query is dropped (draft -01 section 5.5). The bare origin and the well-known directory path give the host.
    """
    match = URL.fullmatch(value)
    if not match or match["scheme"].lower() not in settings.signature_agent_schemes:
        return None
    path = match["path"] or "/"
    if not PATH.fullmatch(path):
        return None
    scheme, host, port = match["scheme"].lower(), match["host"].lower(), match["port"]
    authority = host if port is None or int(port) == DEFAULT_PORTS.get(scheme) else f"{host}:{int(port)}"
    path = _remove_dot_segments(PERCENT_ENCODED.sub(_normalise_percent_encoding, path))
    if path in ("/", settings.directory_well_known_path):
        return authority
    return f"{scheme}://{authority}{path}"


def _signer_name(name, settings):
    signer = signer_identifier(name, settings) if "://" in name else name.lower()
    if signer is None or ("://" not in signer and not HOST.fullmatch(signer)):
        raise ValueError(f"not a signer name: {name!r}")
    return signer


def _keys_of(name, keys):
    if isinstance(keys, dict) and "keys" in keys:
        keys = keys["keys"]
    if isinstance(keys, dict):
        return [_raw_key(name, keyid, public_key) for keyid, public_key in keys.items()]
    return [key for key in map(_jwk_key, keys) if key is not None]


def _raw_key(name, keyid, public_key):
    if not isinstance(public_key, bytes) or not ed25519.is_valid_public_key(public_key):
        raise ValueError(f"key {keyid!r} of {name!r} is not a 32-byte Ed25519 public key")
    x = base64.urlsafe_b64encode(public_key).decode("ascii").rstrip("=")
    return Key(thumbprint({"kty": "OKP", "crv": "Ed25519", "x": x}), keyid, public_key)


def _jwk_key(jwk):
    """The Key of one JWK, or None when the JWK is malformed."""
    if not isinstance(jwk, dict):
        return None
    not_before, expires = jwk.get("nbf"), jwk.get("exp")
    for date in (not_before, expires):
        if date is not None and (isinstance(date, bool) or not isinstance(date, (int, float))):
            return None
    try:
        key_thumbprint = thumbprint(jwk)
    except ValueError:
        return None
    public_key = None
    if jwk["kty"] == "OKP" and jwk["crv"] == "Ed25519":
        public_key = _base64url_decode(jwk["x"])
        if public_key is None or not ed25519.is_valid_public_key(public_key):
            return None
    return Key(key_thumbprint, jwk.get("kid"), public_key, not_before, expires)


def _base64url_decode(text):
    if not BASE64URL.fullmatch(text):
        return None
    unpadded = text.rstrip("=")
    try:
        return base64.urlsafe_b64decode(unpadded + "=" * (-len(unpadded) % sfv.BASE64_QUANTUM))
    except binascii.Error:
        return None


def _normalise_percent_encoding(match):
    """RFC 3986 6.2.2.1-6.2.2.2: unreserved characters decoded, other escapes in upper case."""
    character = chr(int(match.group(1), 16))  # protocol: RFC 3986 2.1, two hexadecimal digits
    return character if UNRESERVED.fullmatch(character) else match.group(0).upper()


def _remove_dot_segments(path):
    """RFC 3986 5.2.4 for an absolute path."""
    output = []
    segments = path.split("/")[1:]
    for segment in segments:
        if segment == "..":
            if output:
                output.pop()
        elif segment != ".":
            output.append(segment)
    result = "/" + "/".join(output)
    if segments[-1] in (".", "..") and not result.endswith("/"):
        result += "/"
    return result
