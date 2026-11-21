"""`doctor` in server mode: what sits in front of AgentCake, and how to change it.

identify(answer_headers, arrival_names) -> the platforms of data/doctor.json "platforms" whose headers are there, in
that file's order (the most specific first: a CDN before the load balancer behind it). A platform is known by a header
it adds to the self-check's answer, by name, or by name and a part of its value (Via: 1.1 google), or by the name of a
header it adds to the request, as collect keeps the names of every request header (values are kept for only a few).
by_range(label): the platform whose address ranges carry that label in the bundled lists (data/lists/ip_ranges.json).

What to change, as a sentence of data/copy.en.json, with the path prefix and the host filled in:
    headers_fix(platforms)        the first platform that has a "fix" (headers removed or replaced), else the general one
    address_fix(platforms, path)  AgentCake sees the platform's address instead of the visitor's: on the subdomain route
                                  its DNS change ("dns_fix"), on the same-site path its "address_fix"; else the general
                                  one of the route
    dns_fix(platform)             the DNS record of public_url leads to the platform
    status_fix(platforms, status) the upload didn't reach AgentCake and the answer has this status: the first platform's
                                  "status_fix" for it (CloudFront's 403: a method its behavior doesn't allow), else the
                                  general one, the path rule
"""
from agentcake.datafiles import load
from agentcake.wording import text

GENERAL_HEADERS_FIX = "doctor_public_fix_headers"
GENERAL_ADDRESS_FIX = {False: "doctor_public_fix_address", True: "doctor_public_fix_address_path"}  # by path route
GENERAL_STATUS_FIX = "doctor_public_fix_forward"


def platforms():
    return load("data/doctor.json")["platforms"]


def identify(answer_headers, arrival_names=()):
    answer = [(name.lower(), value.lower()) for name, value in answer_headers]
    names = {name.lower() for name in arrival_names} | {name for name, _ in answer}
    return [platform for platform in platforms() if any(_matches(rule, answer, names) for rule in platform["match"])]


def _matches(rule, answer, names):
    if "contains" not in rule:
        return rule["header"] in names
    return any(name == rule["header"] and rule["contains"] in value for name, value in answer)


def by_range(label):
    return next((platform for platform in platforms() if label and platform.get("range_label") == label), None)


def names(found):
    return ", ".join(platform["name"] for platform in found)


def headers_fix(found, **values):
    key = next((platform["fix"] for platform in found if platform.get("fix")), GENERAL_HEADERS_FIX)
    return text(key, **values)


def address_fix(found, path, **values):
    role = "address_fix" if path else "dns_fix"
    key = next((platform[role] for platform in found if platform.get(role)), GENERAL_ADDRESS_FIX[path])
    return text(key, **values)


def dns_fix(platform, **values):
    return text(platform.get("dns_fix") if platform and platform.get("dns_fix") else GENERAL_ADDRESS_FIX[False], **values)


def status_fix(found, status, **values):
    key = next((platform["status_fix"][str(status)] for platform in found
                if str(status) in platform.get("status_fix", {})), GENERAL_STATUS_FIX)
    return text(key, **values)
