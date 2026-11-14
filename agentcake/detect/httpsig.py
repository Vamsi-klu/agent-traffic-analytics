"""HTTP Message Signatures (RFC 9421): the signature base a verifier rebuilds from the request it received.

A signature covers an ordered list of components, named in its Signature-Input member. The verifier derives each
component's value from the request (section 2.1 for header fields, 2.2 for derived components), joins them into the
signature base of section 2.5 and checks the signature over those bytes. This module derives the values and builds
the base. A component that cannot be derived exactly as RFC 9421 says (an absent field, an unknown component, a
parameter not supported here, a value that may not appear in a base) raises ComponentError: the caller then cannot
tell whether the signature is right or wrong, which is a different answer from a signature that does not verify.

Supported: the derived components @method, @target-uri, @authority, @scheme, @request-target, @path, @query and
@query-param (with name), and header fields, whole or as one Dictionary member (key). Not supported, so an error: the
sf and bs field parameters, trailers (tr), and req and @status, which only apply to responses.

Input: a Request and the parsed Inner List of one Signature-Input member. Output: the signature base (str).
Part of Web Bot Auth verification, used by agentcake.detect.webbotauth. Written from RFC 9421; @query-param follows the
application/x-www-form-urlencoded rules of the WHATWG URL Standard that RFC 9421 section 2.2.8 points to.
"""
import re
import urllib.parse
from dataclasses import dataclass
from functools import cached_property

from agentcake.detect import sfv

# @authority leaves out the default port of the scheme (RFC 9421 2.2.3)
DEFAULT_PORTS = {"http": 80, "https": 443}  # protocol: RFC 9110 4.2.1 and 4.2.2, default ports
FORM_SAFE_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*-._")
OBSOLETE_FOLD = re.compile(r"[ \t]*\r?\n[ \t]+")
FIELD_VALUE = re.compile(r"[\t -~]*")
DERIVED_VALUE = re.compile(r"[ -~]*")


class ComponentError(ValueError):
    """A covered component whose value cannot be derived from the request (RFC 9421 section 2.5)."""


@dataclass(frozen=True)
class Request:
    """A request as its client sent it, which is what the client signed.

    scheme and authority are those the client used: behind a TLS-terminating proxy, the forwarded scheme and the
    original Host. target is the request target of the request line ("/path?query", or the absolute form).
    headers are (name, value) pairs in the order received, a mapping of name to a value or a list of values, or
    anything whose items() yields such pairs (http.client.HTTPMessage yields every field line).
    """

    method: str
    scheme: str
    authority: str
    target: str
    headers: object = ()

    def field_values(self, name):
        """The values of every line of the field ``name`` (lowercase), in order, or None when it is absent."""
        return self._fields.get(name)

    def field(self, name):
        """The lines of the field ``name`` combined with ", " (RFC 9110 5.3), or None when it is absent."""
        values = self._fields.get(name)
        return None if values is None else ", ".join(value.strip(" \t") for value in values)

    @cached_property
    def _fields(self):
        pairs = self.headers.items() if hasattr(self.headers, "items") else self.headers
        fields = {}
        for name, value in pairs:
            values = value if isinstance(value, (list, tuple)) else [value]
            fields.setdefault(name.lower(), []).extend(values)
        return fields


def signature_base(request, covered):
    """The signature base (RFC 9421 section 2.5) of the signature whose Signature-Input member is ``covered``."""
    if not isinstance(covered, sfv.InnerList):
        raise ComponentError("a Signature-Input member must be an inner list")
    lines, seen = [], set()
    for component in covered.items:
        value = component_value(request, component)
        identity = (component.value, frozenset(component.params.items()))  # parameter order does not count (section 2)
        if identity in seen:
            raise ComponentError(f"{sfv.serialize(component)} is covered twice")
        seen.add(identity)
        lines.append(f"{sfv.serialize(component)}: {value}")
    lines.append(f'"@signature-params": {sfv.serialize(covered)}')
    return "\n".join(lines)


def component_value(request, component):
    """The value of one covered component (an sfv.Item whose value is the component name)."""
    name = component.value
    if not isinstance(name, str) or isinstance(name, sfv.Token):
        raise ComponentError(f"a component identifier must be a string, not {name!r}")
    if name.startswith("@"):
        value = _derived_value(request, name, component.params)
        if not DERIVED_VALUE.fullmatch(value):
            raise ComponentError(f"{name} holds characters a signature base cannot hold")
        return value
    return _field_value(request, name, component.params)


def _derived_value(request, name, params):
    if name == "@query-param":
        _only(params, {"name"}, name)
        return _query_param(request, params.get("name"))
    _only(params, set(), name)
    if name == "@method":
        return request.method
    if name == "@scheme":
        return request.scheme.lower()
    if name == "@authority":
        return _authority(request)
    if name == "@request-target":
        return request.target
    path, query = _split_target(request.target)
    if name == "@path":
        return path or "/"
    if name == "@query":
        return "?" + (query or "")
    if name == "@target-uri":
        return f"{request.scheme.lower()}://{_authority(request)}{path or '/'}" + ("" if query is None else "?" + query)
    raise ComponentError(f"{name} is not a derived component of a request")


def _field_value(request, name, params):
    if name != name.lower():
        raise ComponentError(f"field names are lowercase in component identifiers: {name}")
    _only(params, {"key"}, name)
    values = request.field_values(name)
    if values is None:
        raise ComponentError(f"the {name} field is absent")
    combined = ", ".join(_canonical_line(name, value) for value in values)
    if "key" not in params:
        return combined
    key = params["key"]
    if not isinstance(key, str) or isinstance(key, sfv.Token):
        raise ComponentError(f"the key of {name} must be a string")
    try:
        members = sfv.parse_dictionary(combined)
    except sfv.ParseError as error:
        raise ComponentError(f"the {name} field is not a Dictionary: {error}") from error
    if key not in members:
        raise ComponentError(f'the {name} field has no member "{key}"')
    return sfv.serialize(members[key])


def _canonical_line(name, value):
    """One field line as RFC 9421 2.1 combines it: trimmed, obsolete line folding replaced by a space."""
    value = OBSOLETE_FOLD.sub(" ", value).strip(" \t")
    if not FIELD_VALUE.fullmatch(value):
        raise ComponentError(f"the {name} field holds characters a signature base cannot hold")
    return value


def _authority(request):
    """The authority, lowercased and without the scheme's default port (RFC 9421 2.2.3, RFC 9110 4.2.3)."""
    authority = request.authority.strip().lower()
    if not authority:
        raise ComponentError("the request has no authority")
    host, _, port = authority.rpartition(":")
    is_port = port.isdigit() and (host.endswith("]") or "[" not in host)  # an IPv6 literal keeps its colons in [ ]
    if is_port and int(port) == DEFAULT_PORTS.get(request.scheme.lower()):
        return host
    return authority


def _split_target(target):
    """(path, query or None) of an origin-form or absolute-form request target."""
    if target.startswith("/"):
        path, mark, query = target.partition("?")
        return path, (query if mark else None)
    parts = urllib.parse.urlsplit(target)
    if not (parts.scheme and parts.netloc):
        raise ComponentError(f"the request target {target!r} has no path")
    return parts.path, (parts.query if "?" in target else None)


def _query_param(request, encoded_name):
    """The value of one query parameter, decoded then re-encoded (RFC 9421 2.2.8)."""
    if not isinstance(encoded_name, str) or isinstance(encoded_name, sfv.Token):
        raise ComponentError("@query-param needs a string name parameter")
    _, query = _split_target(request.target)
    values = [value for name, value in _form_pairs(query or "") if _form_encode(name) == encoded_name]
    if len(values) != 1:
        raise ComponentError(f'@query-param "{encoded_name}" occurs {len(values)} times, not once')
    return _form_encode(values[0])


def _form_pairs(query):
    """application/x-www-form-urlencoded parsing (WHATWG URL Standard 5.1): (name, value) strings."""
    for part in query.split("&"):
        if part:
            name, _, value = part.partition("=")
            yield _form_decode(name), _form_decode(value)


def _form_decode(text):
    return urllib.parse.unquote_to_bytes(text.replace("+", " ")).decode("utf-8", "replace")


def _form_encode(text):
    """Percent-encode every UTF-8 byte except ALPHA, DIGIT and *-._, spaces as %20 (RFC 9421 2.2.8 examples)."""
    return "".join(chr(byte) if byte in FORM_SAFE_BYTES else f"%{byte:02X}" for byte in text.encode("utf-8"))


def _only(params, allowed, name):
    for parameter in params:
        if parameter not in allowed:
            raise ComponentError(f"the parameter ;{parameter} on {name} is not supported for a request")
