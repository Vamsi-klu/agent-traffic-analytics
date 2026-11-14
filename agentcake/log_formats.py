"""Web server access log formats: each described by the web server's own format string, compiled into a parser.

    named(name) -> LogFormat              a format data/logs.json names: the recommended ones, combined, Caddy's JSON
    from_nginx(text) -> LogFormat         a site's own nginx log_format (the string, or the directive pasted whole)
    from_apache(text) -> LogFormat        a site's own Apache LogFormat (the string, or the directive pasted whole)
    detect(lines) -> LogFormat or None    the named format most of a log's first lines are in

LogFormat.parse(line) gives a LogRecord or None: the time (epoch ms), the client's address, method, request target,
protocol, status, Host, scheme and every logged request header (lower-case name -> value). nginx's and Apache's
escapes (\\xHH, \\", \\\\, \\n...) and nginx's escape=json are undone, and their "-" for an empty value is no value.
A line that is not in the format is None, never an error that repeats it: log lines hold visitors' addresses.
LogFormat.missing() lists the recommended fields (data/logs.json "recommended") the format does not log. A format
string without what matching a line to a visit needs (time, address, request, status, User-Agent) raises
FormatError naming what it lacks.

Describing a format by the server's own format string and compiling that into a parser is the idea GoAccess uses
(github.com/allinurl/goaccess, MIT); no GoAccess code is used, this is written anew.
"""
import datetime
import decimal
import functools
import ipaddress
import json
import math
import re
from dataclasses import dataclass, field
from typing import Optional

from agentcake.datafiles import load
from agentcake.edge_token import request_path
from agentcake.units import MS_PER_S
from agentcake.wording import text

SPEC = load("data/logs.json")
REQUIRED = ("time", "ip", "request", "status", "user-agent")  # what matching a line to a visit reads
TIME_ROLES = {"time_s", "time_ms", "time_sec", "time_us", "time_clf", "time_clf_bracketed", "time_iso"}
NGINX_VARIABLE = re.compile(r"\$(?:\{([A-Za-z0-9_]+)\}|([A-Za-z0-9_]+))")
APACHE_DIRECTIVE = re.compile(r"%[<>!0-9,]*(?:\{([^}]*)\})?([A-Za-z%])")
SINGLE_QUOTED = re.compile(r"'([^']*)'")
DOUBLE_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
QUOTED, BRACKETED, BARE = r'(?:[^"\\]|\\.)*', r"[^\]]*", r"\S*"
SHAPES = {"ip": r"[0-9A-Fa-f:.]+", "status": r"[0-9]{3}", "time_s": r"[0-9]+\.[0-9]+", "time_ms": r"[0-9]+",
          "time_sec": r"[0-9]+", "time_us": r"[0-9]+",
          "time_clf": r"[0-9]{2}/[A-Za-z]{3}/[0-9]{4}:[0-9]{2}:[0-9]{2}:[0-9]{2} [+-][0-9]{4}",
          "time_clf_bracketed": r"\[([^\]]+)\]", "time_iso": r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(?:Z|[+-][0-9:]+)",
          "path": r'[^?\s"]*', "query_marked": r'(?:\?[^\s"]*)?'}
CLF_TIME = re.compile(r"([0-9]{2})/([A-Za-z]{3})/([0-9]{4}):([0-9]{2}):([0-9]{2}):([0-9]{2}) "
                      r"([+-])([0-9]{2})([0-9]{2})")
CLF_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")  # protocol: CLF
REQUEST_LINE = re.compile(r"([A-Za-z]+) (\S+)(?: (HTTP/[0-9.]+))?")
ESCAPE = re.compile(r"\\(?:x([0-9A-Fa-f]{2})|u([0-9A-Fa-f]{4})|(.))", re.S)
ESCAPED_CHARACTERS = {'"': b'"', "\\": b"\\", "/": b"/", "n": b"\n", "r": b"\r", "t": b"\t", "b": b"\b", "f": b"\f",
                      "v": b"\v"}  # nginx escape=json and Apache's ap_escape_logitem
HEX = 16  # protocol: \xHH and \uHHHH are hexadecimal
US_PER_MS = 1000  # protocol: 1 ms = 1000 microseconds


class FormatError(ValueError):
    """A format string without a field that matching needs; lacking: those fields' names."""

    def __init__(self, lacking):
        self.lacking = list(lacking)
        super().__init__(text("logs_format_lacks", fields=", ".join(self.lacking)))


@dataclass(frozen=True)
class LogRecord:
    t_ms: int
    ip: str
    method: Optional[str]
    target: Optional[str]
    protocol: Optional[str]
    status: Optional[int]
    host: Optional[str]
    scheme: Optional[str]
    headers: dict = field(default_factory=dict)

    @property
    def path(self):
        """The target's path as sent, without its query (an absolute-form target loses its scheme and host), the way
        the site middleware reads a page request's target."""
        return None if self.target is None else request_path(self.target)


class LogFormat:
    """name, the web server it is of, and which recommended fields it logs (all_headers: every request header)."""

    def __init__(self, name, server, logged, all_headers=False):
        self.name, self.server, self.logged, self.all_headers = name, server, frozenset(logged), all_headers

    def parse(self, line):
        raise NotImplementedError

    def missing(self):
        return [name for name in SPEC["recommended"]["fields"]
                if name not in self.logged and not (self.all_headers and name != "host")]


class TemplateFormat(LogFormat):
    """A format string compiled into one regular expression; fields: (group, role or None, header name or None)."""

    def __init__(self, name, server, pattern, fields):
        logged = {header for _, _, header in fields if header}
        if any(role == "host" for _, role, _ in fields):
            logged.add("host")
        super().__init__(name, server, logged)
        self.regex, self.fields = re.compile(pattern), fields

    def parse(self, line):
        line = line.rstrip("\r\n")
        found = self.regex.fullmatch(line) if len(line) <= SPEC["max_line_chars"] else None
        if found is None:
            return None
        roles, headers = {}, {}
        for group, role, header in self.fields:
            value = _value(found.group(group))
            if header:
                if value is not None:
                    headers[header] = value
            elif role and roles.get(role) is None:  # $host and $http_host both: the first with a value
                roles[role] = value
        return _record(roles, headers)


class JsonFormat(LogFormat):
    """A JSON access log (Caddy's): where each field is, as dotted paths into one line's object."""

    def __init__(self, name, spec):
        super().__init__(name, spec["server"], {"host"}, all_headers=True)
        self.paths, self.schemes = spec["json"], spec["schemes"]

    def parse(self, line):
        if len(line) > SPEC["max_line_chars"] or not line.lstrip().startswith("{"):
            return None
        try:
            entry = json.loads(line)
        except ValueError:
            return None
        if not isinstance(entry, dict):
            return None
        get = functools.partial(_dig, entry)
        ip = next((v for v in map(get, self.paths["ip"]) if isinstance(v, str) and _is_address(v)), None)
        status = get(self.paths["status"])
        t_ms = _json_time(get(self.paths["time"]))
        if ip is None or t_ms is None or type(status) is not int:
            return None
        listed = get(self.paths["headers"])
        headers = {str(name).lower(): ", ".join(v for v in values if isinstance(v, str))
                   for name, values in (listed.items() if isinstance(listed, dict) else ()) if isinstance(values, list)}
        return LogRecord(t_ms, ip, _text(get(self.paths["method"])), _text(get(self.paths["target"])),
                         _text(get(self.paths["protocol"])), status, _text(get(self.paths["host"])),
                         self.schemes["tls" if get(self.paths["tls"]) else "plain"],
                         {name: value for name, value in headers.items() if value})


@functools.lru_cache(maxsize=None)
def named(name):
    spec = SPEC["formats"][name]  # KeyError: no such format
    if "json" in spec:
        return JsonFormat(name, spec)
    return {"nginx": from_nginx, "apache": from_apache}[spec["server"]](spec["template"], name)


def detect(lines):
    sample = [line for line in lines if line.strip()][:SPEC["detect"]["sample_lines"]]
    best, best_count = None, 0
    for name in SPEC["detect"]["order"]:
        count = sum(1 for line in sample if named(name).parse(line) is not None)
        if count > best_count:
            best, best_count = named(name), count
    return best


def from_nginx(given, name=None):
    template, spec, parts = _nginx_template(given), SPEC["nginx"], []
    for found in NGINX_VARIABLE.finditer(template):
        braced, bare = found.groups()  # ${name} or $name
        variable = braced or bare
        role = spec["roles"].get(variable)
        header = variable[len(spec["header_prefix"]):].replace("_", "-") \
            if role is None and variable.startswith(spec["header_prefix"]) else None
        parts.append((found.start(), found.end(), role, header))
    return _compile(template, parts, name or SPEC["custom"]["nginx"], "nginx")


def from_apache(given, name=None):
    template, spec, parts = _apache_template(given), SPEC["apache"], []
    for found in APACHE_DIRECTIVE.finditer(template):
        argument, letter = found.groups()
        role, header = None, None
        if letter == "%":
            role = "%"
        elif letter == spec["header_letter"] and argument:
            role, header = ("host", None) if argument.lower() == "host" else (None, argument.lower())
        elif letter == "t" and argument:
            role = spec["time_arguments"].get(argument)
        else:
            role = spec["roles"].get(letter)
        parts.append((found.start(), found.end(), role, header))
    return _compile(template, parts, name or SPEC["custom"]["apache"], "apache")


# ---------------------------------------------------------------- compiling
def _nginx_template(given):
    """The format string: given as it is, or the single-quoted parts of a pasted log_format directive, joined."""
    quoted = SINGLE_QUOTED.findall(given)
    return "".join(quoted) if quoted else given.strip()


def _apache_template(given):
    """The format string: given as it is, or the first double-quoted string of a pasted LogFormat directive."""
    stripped = given.strip()
    if stripped.startswith('"') or stripped.split(" ", 1)[0].lower() == "logformat":
        found = DOUBLE_QUOTED.search(stripped)
        if found:
            return re.sub(r'\\(["\\])', r"\1", found.group(1))
    return stripped


def _compile(template, parts, name, server):
    pattern, fields, at = [], [], 0
    for start, end, role, header in parts:
        pattern.append(re.escape(template[at:start]))
        at = end
        if role == "%":
            pattern.append(re.escape("%"))
            continue
        group = f"f{len(fields)}"
        before, after = template[start - 1:start], template[end:end + 1]
        shape = SHAPES.get(role) or (QUOTED if (before, after) == ('"', '"') else
                                     BRACKETED if (before, after) == ("[", "]") else BARE)
        if role == "time_clf_bracketed":
            pattern.append(shape.replace("(", f"(?P<{group}>", 1))
        else:
            pattern.append(f"(?P<{group}>{shape})")
        fields.append((group, role, header))
    pattern.append(re.escape(template[at:]))
    _require({role for _, role, _ in fields}, {header for _, _, header in fields})
    return TemplateFormat(name, server, "".join(pattern), fields)


def _require(roles, headers):
    have = {"time": bool(roles & TIME_ROLES), "ip": "ip" in roles, "status": "status" in roles,
            "request": "request" in roles or ("method" in roles and bool(roles & {"target", "path"})),
            "user-agent": "user-agent" in headers}
    lacking = [name for name in REQUIRED if not have[name]]
    if lacking:
        raise FormatError(lacking)


# ---------------------------------------------------------------- reading a line's values
def _value(raw):
    """A logged value with its escapes undone; None for nginx's and Apache's empty values."""
    return None if raw is None or raw in SPEC["empty_values"] else unescape(raw)


def unescape(value):
    """nginx's \\xHH (each byte of the UTF-8), Apache's \\" \\\\ \\n \\t \\xhh, and nginx escape=json's \\uHHHH."""
    if "\\" not in value:
        return value
    out, at = bytearray(), 0
    for found in ESCAPE.finditer(value):
        out += value[at:found.start()].encode("utf-8", "surrogateescape")
        byte, code, character = found.groups()
        if byte is not None:
            out.append(int(byte, HEX))
        elif code is not None:
            out += chr(int(code, HEX)).encode("utf-8", "surrogatepass")
        else:
            out += ESCAPED_CHARACTERS.get(character, ("\\" + character).encode("utf-8", "surrogateescape"))
        at = found.end()
    out += value[at:].encode("utf-8", "surrogateescape")
    return out.decode("utf-8", "replace")


def _record(roles, headers):
    ip, t_ms = roles.get("ip"), _time(roles)
    if ip is None or not _is_address(ip) or t_ms is None:
        return None
    method, target, protocol = roles.get("method"), roles.get("target"), roles.get("protocol")
    if roles.get("request"):
        line = REQUEST_LINE.fullmatch(roles["request"])
        method, target, protocol = line.groups() if line else (None, None, None)
    elif target is None and roles.get("path"):
        query = roles.get("query_marked") or (f"?{roles['query']}" if roles.get("query") else "")
        target = roles["path"] + query
    status = roles.get("status")
    return LogRecord(t_ms, ip, method, target, protocol, int(status) if status else None, roles.get("host"),
                     roles.get("scheme"), headers)


def _time(roles):
    try:
        if roles.get("time_s"):
            return int(decimal.Decimal(roles["time_s"]) * MS_PER_S)
        if roles.get("time_ms"):
            return int(roles["time_ms"])
        if roles.get("time_sec"):
            return int(roles["time_sec"]) * MS_PER_S
        if roles.get("time_us"):
            return int(roles["time_us"]) // US_PER_MS
        clf = roles.get("time_clf") or roles.get("time_clf_bracketed")
        if clf:
            return _clf_ms(clf)
        if roles.get("time_iso"):
            return _iso_ms(roles["time_iso"])
    except (ValueError, decimal.InvalidOperation):
        return None
    return None


def _clf_ms(value):
    found = CLF_TIME.fullmatch(value)
    if not found:
        return None
    day, month, year, hour, minute, second, sign, offset_hours, offset_minutes = found.groups()
    if month not in CLF_MONTHS:
        return None
    offset = datetime.timedelta(hours=int(offset_hours), minutes=int(offset_minutes))
    moment = datetime.datetime(int(year), CLF_MONTHS.index(month) + 1, int(day), int(hour), int(minute), int(second),
                               tzinfo=datetime.timezone(-offset if sign == "-" else offset))
    return int(moment.timestamp()) * MS_PER_S


def _iso_ms(value):
    moment = datetime.datetime.fromisoformat(value)
    return round(moment.timestamp() * MS_PER_S) if moment.tzinfo else None


def _json_time(value):
    if type(value) in (int, float) and math.isfinite(value):  # json.loads reads NaN and Infinity too
        return round(value * MS_PER_S)
    if isinstance(value, str):
        try:
            return _iso_ms(value)
        except ValueError:
            return None
    return None


def _dig(entry, dotted):
    for key in dotted.split("."):
        entry = entry.get(key) if isinstance(entry, dict) else None
    return entry


def _text(value):
    return value if isinstance(value, str) and value else None


def _is_address(value):
    try:
        ipaddress.ip_address(value)
    except ValueError:  # its message holds the value: dropped here
        return False
    return True
