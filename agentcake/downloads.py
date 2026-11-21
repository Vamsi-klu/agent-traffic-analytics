"""The HTTP requests of the updates (detect/lists_build.py and geoip_build.py): urllib's, except that a redirect is
followed only on the host that was asked, and that a body cut short fails the attempt.

An update reaches only the public addresses data/lists/sources.json and data/geo.json name (PRIVACY.md, "Where it goes,
and what goes online"), and urllib on its own follows a redirect to any host: DigitalOcean's list answered its address
with one to another host name. A redirect elsewhere fails that download, before anything is asked there, and the update
with it, leaving what is in use as it was; the address in sources.json or geo.json is then changed to where the file
moved. A connection that ends before the body does fails the attempt too, so that a file cut short never passes for the
whole one: http.client's read(amt) hands over a body shorter than its Content-Length as if it were whole, and raises
IncompleteRead (an HTTPException, not an OSError) for a chunked one cut off.

    urlopen(request, timeout) -> the answer, as urllib.request.urlopen gives it
    check_whole(answer, received)   CutShort when fewer bytes came than the answer's Content-Length announced
    attempts(url, retries, once, failed) -> once()'s answer, tried retries + 1 times while it fails with one of
                              ATTEMPT_ERRORS; after the last, failed(<url>: <its error>) is raised (each fetcher's
                              BuildError)
    RedirectElsewhere         a redirect to another host (an urllib.error.URLError)
"""
import http.client
import urllib.error
import urllib.request
from urllib.parse import urlsplit

CONTENT_LENGTH = "Content-Length"  # protocol: RFC 9110 8.6
ATTEMPT_ERRORS = (urllib.error.URLError, http.client.HTTPException, OSError, ValueError)


class RedirectElsewhere(urllib.error.URLError):
    """A source answered with a redirect to a host it doesn't name."""


class CutShort(http.client.HTTPException):
    """A body that ended before the length its answer announced."""


def attempts(url, retries, once, failed):
    for attempt in range(retries + 1):
        try:
            return once()
        except ATTEMPT_ERRORS as error:
            if attempt == retries:
                raise failed(f"{url}: {error}") from error


def check_whole(answer, received):
    announced = answer.headers.get(CONTENT_LENGTH, "")
    if announced.isdigit() and received < int(announced):
        raise CutShort(f"{answer.url}: {received} of the {announced} bytes announced came before the connection ended")


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            fp.close()  # the redirect's own answer: nothing more is read from it
            raise RedirectElsewhere(f"{req.full_url} redirects to {newurl}, another host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameHostRedirects)  # the default handlers, this one in place of the redirects'


def urlopen(request, timeout):
    return _OPENER.open(request, timeout=timeout)
