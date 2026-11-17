"""Addresses that pages and log lines send, read without failing on the ones that cannot be read.

urlsplit raises ValueError on some addresses anyone can send (an unclosed IPv6 bracket: "https://["). Such an address
is no address here, so it cannot stop the judging of a session or the matching of server log lines.

    split(url) -> urlsplit(url), or None when url is empty or cannot be read
    path(url)  -> its path ("" when it has none), or None when url is empty or cannot be read
"""
from urllib.parse import urlsplit


def split(url):
    if not url:
        return None
    try:
        return urlsplit(url)
    except ValueError:
        return None


def path(url):
    parts = split(url)
    return parts.path if parts else None
