"""`ping`: one self-check visit, marked as a test so it never counts as a real visit. It asks for the page
script first, as a page would, then sends one upload of an empty page view of the local page to collect (until
0.4.0 the visit went to the demo shop).

http_get(url, timeout) -> (status or None, text) is the small GET that ping and doctor use against the local server.
"""
import json
import secrets
import urllib.request

from agentcake import __version__
from agentcake.config import base_url, ensure_cfg
from agentcake.datafiles import sizes
from agentcake.site_setup import SCRIPT_PATH
from agentcake.wording import product, text


def http_get(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, str(e)


def ping():
    """One self-check visit, marked as a test (it never counts as a real session)."""
    c = ensure_cfg(); b = base_url(c)
    st, _ = http_get(b + SCRIPT_PATH, c["http_timeout_s"])
    body = json.dumps({"k": c["site_key"], "s": "selfcheck" + secrets.token_hex(sizes()["random_bytes"]["selfcheck_id"]),
                       "u": b + "/?cake=selfcheck", "ua": f"{product()['command']}-selfcheck/{__version__}",
                       "test": True, "e": []}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(b + "/collect", data=body, method="POST"), timeout=c["http_timeout_s"]):
            pass
        print(text("ping_sent", status=st)); return 0
    except Exception as e:
        print(text("ping_failed", error=e)); return 1
