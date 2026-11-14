"""Requests and responses as plain values (S1.1): a view takes a Request and returns a Response.

server.py builds the Request from the socket and writes the Response back, so each resource (collect.py, the
modules of api/, assets.py) is a module of small functions, like PostHog 1.0's posthog/api/<resource>.py.
"""
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Union

HTML = "text/html; charset=utf-8"
TEXT = "text/plain"
JSON = "application/json"
JS = "application/javascript"
CSS = "text/css"
FONT_TTF = "font/ttf"


@dataclass
class Request:
    path: str                      # below the listener's path prefix, e.g. "/collect"
    query: dict                    # urllib.parse.parse_qs of the query string
    headers: object                # the request's headers (http.client.HTTPMessage: get() ignores case)
    body: bytes = b""


@dataclass
class Response:
    status: int
    body: Union[str, bytes] = b""  # a str is sent as UTF-8
    ctype: str = HTML
    headers: dict = field(default_factory=dict)


def not_found():
    return Response(HTTPStatus.NOT_FOUND, "not found", TEXT)
