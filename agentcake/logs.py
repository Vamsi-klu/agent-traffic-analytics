"""`agentcake logs import` and `agentcake logs formats`: a web server's access log, read where it lies.

logs_command(args) -> exit code: 0, 1 when an error stops the import, 2 on a usage error.

`logs import <file>... [--format NAME | --nginx-format 'FORMAT' | --apache-format 'FORMAT'] [--since 10m] [--to URL]`
reads each file line by line in the format named, given as the web server's own format string, or detected from the
first lines (log_formats.py). Its page requests (is_page_request: a GET, not a redirect, not a static file, a document
when the log says) go to /edge (edge_api.py) in batches signed with the server half's secret of this CAKE_HOME: to
this computer's AgentCake, or with --to to the public listener of an AgentCake server (http://192.0.2.10:8080/cake),
whose secret must then be in this CAKE_HOME's srv_secret. A record holds the line's time, address, method, target,
status, Host, scheme and the headers data/logs.json "send_headers" lists, never cookies or credentials; AgentCake keeps
what the matched ones say and never the address. The file is not copied, and nothing of it is written or printed
here. --since 10m sends only the lines of the last 10 minutes (units s, m, h, d), for a run every few minutes; Agent
Cake keeps a line sent twice once.

One summary per file: lines, page requests sent, matched, already imported, dropped, other lines, older, unreadable;
then the recommended headers the format lacks and those empty on every page request, which also go to AgentCake with
every batch for doctor (log_report.py). `logs formats` prints the formats and the recommended configuration lines.
"""
import itertools
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from http import HTTPStatus
from typing import Optional

from agentcake import log_formats, paths
from agentcake.config import base_url, load_cfg
from agentcake.datafiles import load
from agentcake.edge_secret import ensure_secret, srv_secret
from agentcake.edge_signature import HEADER, sign
from agentcake.edge_token import skipped_path
from agentcake.responses import JSON
from agentcake.storage_config import now_ms as clock_ms
from agentcake.units import MS_PER_S
from agentcake.wording import text

SPEC = load("data/logs.json")
EDGE = SPEC["edge"]
ENVELOPE_VERSION = EDGE["version"]
BATCH_RECORDS = EDGE["batch_records"]
SINCE = re.compile(r"([0-9]+)([a-z])")
FORMAT_FLAGS = ("--format", "--nginx-format", "--apache-format")
VALUE_FLAGS = FORMAT_FLAGS + ("--since", "--to")
ANSWER_COUNTS = ("matched", "duplicates", "unmatched")
RECORD_SEPARATOR = b","  # between two records of a JSON list
EXIT_USAGE = 2  # protocol: exit status of a command-line usage error (POSIX utilities, argparse)


class UsageError(Exception):
    """A command line `logs import` cannot run; the message says why."""


class ImportStopped(Exception):
    """An error that ends the import; the message is the text to print."""


@dataclass
class Options:
    files: list
    log_format: Optional[log_formats.LogFormat]
    since_s: Optional[int]
    to: Optional[str]


def logs_command(args):
    sub, rest = (args[0] if args else ""), list(args[1:])
    if sub == "import":
        return import_command(rest)
    if sub == "formats" and not rest:
        print_formats()
        return 0
    print(text("logs_usage"))
    return EXIT_USAGE


def import_command(args):
    try:
        options = parse_options(args)
    except UsageError as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    c = load_cfg()
    secret = srv_secret() if options.to else ensure_secret()  # a cake on this computer reads the same secret file
    if not secret:
        print(text("logs_no_secret", path=paths.tilde(paths.secret_file())), file=sys.stderr)
        return 1
    sender = Sender((options.to or base_url(c)).rstrip("/") + EDGE["route"], secret, c)
    now_ms = clock_ms()
    since_ms = None if options.since_s is None else now_ms - options.since_s * MS_PER_S
    for path in options.files:
        try:
            print(import_file(path, options.log_format, since_ms, sender))
        except ImportStopped as stop:
            print(stop, file=sys.stderr)
            return 1
    return 0


def parse_options(args):
    files, given, since_s, to, words = [], None, None, None, list(args)
    while words:
        word = words.pop(0)
        if word in VALUE_FLAGS:
            if not words or (word in FORMAT_FLAGS and given):
                raise UsageError(text("logs_usage"))
            value = words.pop(0)
            if word == "--since":
                since_s = parse_since(value)
            elif word == "--to":
                to = value
            else:
                given = (word, value)
        elif word.startswith("--"):
            raise UsageError(text("logs_usage"))
        else:
            files.append(word)
    if not files:
        raise UsageError(text("logs_usage"))
    return Options(files, _given_format(given), since_s, to)


def parse_since(value):
    found, units = SINCE.fullmatch(value), SPEC["duration_units"]
    number, unit = found.groups() if found else (None, None)
    if unit not in units:
        raise UsageError(text("logs_bad_since"))
    return int(number) * units[unit]


def _given_format(given):
    if given is None:
        return None
    flag, value = given
    if flag == "--format":
        if value not in SPEC["formats"]:
            raise UsageError(text("logs_unknown_format", format=value, formats=", ".join(SPEC["formats"])))
        return log_formats.named(value)
    compile_format = log_formats.from_nginx if flag == "--nginx-format" else log_formats.from_apache
    try:
        return compile_format(value)
    except log_formats.FormatError as error:
        raise UsageError(str(error)) from None


def import_file(path, log_format, since_ms, sender):
    """Read one log and send its page requests; the summary to print. ImportStopped when it cannot go on."""
    try:
        with open(path, encoding="utf-8", errors="replace") as log:
            head = list(itertools.islice(log, SPEC["detect"]["sample_lines"]))
            log_format = log_format or log_formats.detect(head)
            if log_format is None:
                raise ImportStopped(text("logs_no_format", file=paths.tilde(path)))
            run = Run(log_format, sender, since_ms)
            for line in itertools.chain(head, log):
                run.add(line)
    except OSError as error:  # the file; a network error is ImportStopped already (Sender)
        raise ImportStopped(text("logs_cannot_read", file=paths.tilde(path), error=error.strerror or error)) from None
    run.finish()
    return run.summary(path)


def is_page_request(record):
    """A line worth sending: a GET of a document that is not a redirect, a static file or a dot-file."""
    page = SPEC["page"]
    if record.method != page["method"] or record.status in page["redirect_statuses"] or record.target is None:
        return False
    if skipped_path(record.path):
        return False
    dest = record.headers.get(page["dest_header"])
    return dest is None or dest.lower() == page["dest"]


def to_json(record):
    """The record as /edge reads it; only the headers data/logs.json lets go to AgentCake."""
    names = SPEC["send_headers"]["names"]
    return {"t": record.t_ms, "ip": record.ip, "m": record.method, "u": record.target, "s": record.status,
            "h": record.host, "sc": record.scheme,
            "hd": {name: value for name, value in record.headers.items() if name in names}}


def fits(sent):
    """Whether /edge reads this record: its texts within data/logs.json's caps (a longer one is unreadable)."""
    caps = EDGE["max_chars"]
    texts = (("ip", sent["ip"]), ("method", sent["m"]), ("target", sent["u"]), ("host", sent["h"]),
             ("scheme", sent["sc"]), *(("header", value) for value in sent["hd"].values()))
    return all(value is None or len(value) <= caps[kind] for kind, value in texts)


class Run:
    """One log's import: its counts, the batch being filled and how many page requests had each recommended field."""

    def __init__(self, log_format, sender, since_ms):
        self.format, self.sender, self.since_ms = log_format, sender, since_ms
        self.id = secrets.token_hex(EDGE["run_id_bytes"])
        self.counts, self.seen, self.batch, self.batch_bytes = Counter(), Counter(), [], 0
        self.room = sender.max_body - len(self.encode([]))

    def add(self, line):
        if not line.strip():
            return
        self.counts["lines"] += 1
        record = self.format.parse(line)
        if record is None:
            self.counts["unreadable"] += 1
        elif not is_page_request(record):
            self.counts["skipped"] += 1
        elif self.since_ms is not None and record.t_ms < self.since_ms:
            self.counts["older"] += 1
        else:
            self._send_later(record)

    def finish(self):
        """Send what is left: always once more, so that the last batch carries the whole report."""
        self._flush()

    def summary(self, path):
        lines = [text("logs_imported", file=paths.tilde(path), format=self.format.name,
                      **{name: self.counts[name] for name in ("lines", "sent", "matched", "duplicates", "unmatched",
                                                              "skipped", "older", "unreadable")})]
        fields = self.fields()
        if fields["missing"]:
            lines.append(text("logs_missing", fields=", ".join(fields["missing"])))
        if fields["empty"]:
            lines.append(text("logs_empty", fields=", ".join(fields["empty"])))
        return "\n".join(lines)

    def fields(self):
        """The recommended fields the format lacks, and the always-sent ones no page request had (once enough came)."""
        missing, recommended = self.format.missing(), SPEC["recommended"]
        enough = self.counts["sent"] >= recommended["empty_min_requests"]
        empty = [name for name, spec in recommended["fields"].items()
                 if enough and spec["always_sent"] and name not in missing and not self.seen[name]]
        return {"missing": missing, "empty": empty}

    def encode(self, records):
        return json.dumps({"v": ENVELOPE_VERSION, "run": self.id, "format": self.format.name, "fields": self.fields(),
                           "records": records}, separators=(",", ":")).encode()

    def _send_later(self, record):
        sent = to_json(record)
        size = len(json.dumps(sent, separators=(",", ":")).encode()) + len(RECORD_SEPARATOR)
        if not fits(sent) or size > self.room:
            self.counts["unreadable"] += 1
            return
        if self.batch and (len(self.batch) >= BATCH_RECORDS or self.batch_bytes + size > self.room):
            self._flush()
        self.counts["sent"] += 1
        for name in SPEC["recommended"]["fields"]:
            self.seen[name] += bool(record.host if name == "host" else record.headers.get(name))
        self.batch.append(sent)
        self.batch_bytes += size

    def _flush(self):
        answer = self.sender.post(self.encode(self.batch))
        for name in ANSWER_COUNTS:
            self.counts[name] += answer.get(name, 0)
        self.counts["unreadable"] += answer.get("bad", 0)
        self.batch, self.batch_bytes = [], 0


class Sender:
    """POSTs signed envelopes to one /edge."""

    def __init__(self, url, secret, c):
        self.url, self.secret, self.timeout = url, secret, EDGE["timeout_s"]
        self.max_body = c["public_max_body_bytes"]

    def post(self, body):
        signature = sign(self.secret, body, clock_ms())
        request = urllib.request.Request(self.url, data=body, method="POST",
                                         headers={"Content-Type": JSON, HEADER: signature})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                return json.loads(answer.read())
        except urllib.error.HTTPError as error:
            entry = "logs_refused_secret" if error.code == HTTPStatus.FORBIDDEN else "logs_refused"
            raise ImportStopped(text(entry, url=self.url, status=error.code,
                                     path=paths.tilde(paths.secret_file()))) from None
        except (urllib.error.URLError, OSError, ValueError) as error:  # no answer, or not the JSON of /edge
            raise ImportStopped(text("logs_unreachable", url=self.url,
                                     error=getattr(error, "reason", None) or error)) from None


def print_formats():
    for name, spec in SPEC["formats"].items():
        server = SPEC["servers"][spec["server"]]
        print(text("logs_format_line", format=name, server=server, about=spec["about"]))
        if spec.get("config"):
            print(text("logs_format_config", server=server))
            for line in spec["config"]:
                print("    " + line)
