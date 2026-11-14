"""Registering this AgentCake with Tartini AI, once per data folder (S5.8, D32; PRIVACY.md "Registration").

The first time the local dashboard opens, it shows a card (web/src/pages/register.tsx) that asks for an e-mail address,
a company if the owner gives one, and whether to send product update e-mails. Its "See what is sent" shows the JSON
that "Register & Continue" sends: the page posts that very text to /api/register (api/registration.py), payload()
checks it, and send() passes the same bytes on, in one request, to register_url (defaults.json). Nothing else is ever
sent there and nothing is sent before the press. PostHog 1.0.0 is the counter-example: it sent a new admin's e-mail,
name and company to PostHog by itself (posthog/urls.py setup_admin, with a key written into posthog/apps.py).

    rules()                     what an e-mail address, a company and a consent version must look like
                                (data/registration.json), and where to write to have a registration deleted
    payload(body)               the text of a POST body when it is a registration in the one form the page writes it
                                in; else Invalid, naming what is wrong (an entry of data/api.en.json "errors")
    send(body, url, timeout_s)  one POST of body to url, no redirect followed; NotSent saying why when it could not be
                                sent or the receiver did not accept it
    kept(con) / keep(con, body, now_ms)    what this data folder sent and when, kept in its database

There is no retry and no queue (D32): a registration that cannot be sent is dropped, the page says why and lets the
owner in, and the card asks again the next time the dashboard is opened.
"""
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from agentcake import store
from agentcake.datafiles import load
from agentcake.responses import JSON
from agentcake.wording import product

SETTING = "registration"  # the key of the settings table (store.setting) that holds what this data folder sent
FIELDS = ("email", "company", "product_updates", "consent_version")  # in the order the page writes them
REQUIRED = ("email", "product_updates", "consent_version")
INDENT = 2  # protocol: the page writes the body with JSON.stringify(payload, null, 2)
SCHEMES = ("http", "https")  # protocol: the receiving address is a web address


class Invalid(ValueError):
    """A POST body that is not a registration the page writes. entry names what is wrong (api.en.json "errors")."""

    def __init__(self, entry, **values):
        super().__init__(entry)
        self.entry, self.values = entry, values


class NotSent(Exception):
    """A registration that did not reach the receiver, or that it did not accept. entry and values say why."""

    def __init__(self, entry, **values):
        super().__init__(entry)
        self.entry, self.values = entry, values


def rules():
    return load("data/registration.json")


def payload(body):
    """The body as text, when it is exactly what the page writes for a registration; else Invalid."""
    try:
        text = body.decode("utf-8")
        fields = json.loads(text)
    except ValueError:  # UnicodeDecodeError and JSONDecodeError are both ValueErrors
        raise Invalid("bad_json") from None
    if not isinstance(fields, dict):
        raise Invalid("bad_json")
    _check(fields)
    written = json.dumps({key: fields[key] for key in FIELDS if key in fields}, indent=INDENT, ensure_ascii=False)
    if written != text:  # another order or layout, a key given twice, anything around it: not what the page showed
        raise Invalid("register_not_as_shown")
    return text


def _check(fields):
    r = rules()
    for key in fields:
        if key not in FIELDS:
            raise Invalid("register_unknown_field", field=key)
    email = fields.get("email")
    if not isinstance(email, str) or len(email) > r["email_max_chars"] or not re.fullmatch(r["email_pattern"], email):
        raise Invalid("register_bad_email")
    if "company" in fields:
        company = fields["company"]
        if not isinstance(company, str) or not company.strip() or not company.isprintable() \
                or len(company) > r["company_max_chars"]:
            raise Invalid("register_bad_company", max=r["company_max_chars"])
    if type(fields.get("product_updates")) is not bool:  # 1 is not true in JSON
        raise Invalid("register_bad_updates")
    version = fields.get("consent_version")
    if not isinstance(version, str) or not re.fullmatch(r["consent_version_pattern"], version):
        raise Invalid("register_bad_version")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an answer, not a second address to send the registration to: it ends as an HTTPError."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(body, url, timeout_s=None):
    """POST body (the text payload() returned) to url once; NotSent when it did not get a 2xx answer."""
    parts = urlsplit(url)
    host = parts.netloc or url
    if parts.scheme not in SCHEMES or not parts.hostname:
        raise NotSent("register_unreachable", host=host, reason=url)
    request = urllib.request.Request(url, data=body.encode("utf-8"), method="POST",
                                     headers={"Content-Type": JSON, "User-Agent": product()["name"]})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=rules()["send_timeout_s"] if timeout_s is None else timeout_s):
            return
    except urllib.error.HTTPError as answer:  # an HTTPError is a URLError: this comes first
        answer.close()
        raise NotSent("register_refused", host=host, code=answer.code) from None
    except urllib.error.URLError as failed:
        raise NotSent("register_unreachable", host=host, reason=str(failed.reason)) from None
    except (OSError, ValueError) as failed:  # a timeout while reading the answer; an address http.client refuses
        raise NotSent("register_unreachable", host=host, reason=str(failed) or type(failed).__name__) from None


def kept(con):
    """{"body": the text sent, "sent_ms": when}, or None before this data folder registered."""
    return store.setting(con, SETTING)


def keep(con, body, now_ms):
    store.set_setting(con, SETTING, {"body": body, "sent_ms": now_ms}, now_ms)
    con.commit()
