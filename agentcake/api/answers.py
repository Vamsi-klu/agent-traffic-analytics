"""What every /api view answers with: JSON, an error body, and the check that the local page itself asks.

    view(handler)                 wraps a view: refuses a request from anywhere but this computer's own pages, and
                                  answers a Refused raised by a check
    ok(value)                     200, value as JSON
    error(status, entry, **values) {"error": <api.en.json errors[entry]>} (web/src/data/schema/error.schema.json)
    error_text(status, message)   the same with a sentence from elsewhere (copy.en.json, an exception's own words)
    local_only(request)           raises Refused (403) unless the request comes from this computer's own pages
    json_object(request)          the body of a JSON request as a dict, else Refused (415 not JSON, 400 unreadable)
    choice(request, name, keys)   one query parameter, None when absent, else Refused (400) when not one of keys
    text_param(request, name)     a free-text query parameter (an agent's name), None when absent or empty
    given_param(request, name)    a query parameter as sent, "" when sent empty, None when absent (a table row's key)
    no_route(request)             404 for an /api address no view answers

local_only() is the guard against cross-site requests and DNS rebinding (a site whose name resolves to 127.0.0.1):
the Host header must name this computer, and an Origin header, when the browser sends one, must be a page of this
computer on that Host's port: the local page itself, whichever port a tunnel shows it on (SERVER.md opens it through
SSH). A program on this computer, such as `agentcake delete`, sends no Origin. The local listener answers
cross-origin requests only for collect (server.py), so another site cannot read these answers either.
"""
import json
from http import HTTPStatus
from urllib.parse import urlsplit

from agentcake.datafiles import load
from agentcake.responses import JSON, Response
from agentcake.site_origin import LOOPBACK_NAMES
from agentcake.wording import product

LOCAL_SCHEME = "http"  # protocol: the local listener speaks plain HTTP on 127.0.0.1


class Refused(Exception):
    """A request a view will not answer; .response is what it says instead."""

    def __init__(self, response):
        super().__init__(response.body)
        self.response = response


def words():
    return load("data/api.en.json")


def numbers():
    return load("data/api.json")


def ok(value):
    return Response(HTTPStatus.OK, json.dumps(value, ensure_ascii=False), JSON)


def error(status, entry, **values):
    return error_text(status, words()["errors"][entry].format(name=product()["name"], **values))


def error_text(status, message):
    return Response(status, json.dumps({"error": message}, ensure_ascii=False), JSON)


def view(handler):
    """handler(request) -> Response, answered only for this computer's own pages; a Refused becomes its answer."""
    def answer(request):
        try:
            local_only(request)
            return handler(request)
        except Refused as refused:
            return refused.response
    answer.__name__, answer.__doc__ = handler.__name__, handler.__doc__
    return answer


def local_only(request):
    _, host, port = _place(LOCAL_SCHEME + "://" + (request.headers.get("Host") or ""))
    origin = request.headers.get("Origin")
    if host not in LOOPBACK_NAMES or (origin is not None and not _this_computer(_place(origin), port)):
        raise Refused(error(HTTPStatus.FORBIDDEN, "not_local"))


def _this_computer(origin, port):
    """Whether an Origin is a page of this computer on the port the request was sent to."""
    scheme, host, origin_port = origin
    return scheme == LOCAL_SCHEME and host in LOOPBACK_NAMES and origin_port == port


def json_object(request):
    kind = (request.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if kind != JSON:
        raise Refused(error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "json_only"))
    try:
        body = json.loads(request.body or b"")
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise Refused(error(HTTPStatus.BAD_REQUEST, "bad_json"))
    return body


def choice(request, name, keys):
    value = (request.query.get(name) or [""])[0]
    if not value:
        return None
    if value not in keys:
        raise Refused(error(HTTPStatus.BAD_REQUEST, "bad_choice", field=name, choices=", ".join(keys)))
    return value


def text_param(request, name):
    return (request.query.get(name) or [""])[0] or None


def given_param(request, name):
    return (request.query.get(name) or [None])[0]


@view
def no_route(request):
    return error(HTTPStatus.NOT_FOUND, "no_route", path=request.path)


def _place(url):
    """(scheme, host, port) of a URL, host lower case; a URL that cannot be read names no place."""
    try:
        parts = urlsplit(url)
        return parts.scheme, parts.hostname, parts.port
    except ValueError:
        return None, None, None
