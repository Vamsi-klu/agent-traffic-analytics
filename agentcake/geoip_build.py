"""Downloads DB-IP's IP to City Lite and converts it into the city database geoip.py reads. Like
detect/lists_build.py, this is a part that goes online: when someone runs `agentcake lists update`, and in the process
`agentcake serve` starts for the update while lists_auto_update is on (agentcake/updates.py; serve itself never imports
it), at the first check after a server starts without a database and then once a month. It fetches only the address
data/geo.json names.

    update(c=None, fetch=None, now=None) -> {"updated": folder, "month"} | {"current": month} | {"skipped": "local"}
        the update's part (updates.py): on an AgentCake that sees visitor addresses (geoip.sees_addresses), the newest
        published month into <CAKE_HOME>/geo, unless the database in use is that month already. Elsewhere it is
        skipped: every visit to AgentCake on this computer comes from 127.0.0.1, so a city database would never be read.
    download(root, fetch=None, now=None, have=None) -> {"updated": root, "month"} | {"current": have}
        This month's file, or the month before while this month's is not published yet (data/geo.json "source"),
        converted and swapped in whole: a reader sees the old database or the new one, never a mix. Raises
        BuildError, and changes nothing, when no month can be fetched or the file cannot be read. fetch(url, path)
        writes a body to path and returns False when the month is not published: tests pass their own, offline.
    convert(gz_path, folder, month, url, now) -> about   one downloaded file into the database's files

The conversion streams: rows are read from the gzip file one at a time and written as records as they come, so only
the table of places (about 194,000 in November 2026) is held in memory. Each range must start after the one before
it ends, as DB-IP orders them; a gap gets a record of no place, so an address in it finds none. What checks that the
file is what DB-IP published: gzip's own CRC, every row's shape and order, and the CSV's SHA-1, which DB-IP's download
page lists (about.json keeps it).
"""
import csv
import datetime
import gzip
import hashlib
import json
import os
import shutil
import socket
import urllib.error
import urllib.request
import uuid
import zlib

from agentcake import config, downloads, geoip
from agentcake.datafiles import sizes

SETTINGS = geoip.SETTINGS
SOURCE, FETCH, FOLDER, FILES, FORMAT = (SETTINGS[key] for key in ("source", "fetch", "folder", "files", "format"))
FAMILIES = {socket.AF_INET: "ipv4", socket.AF_INET6: "ipv6"}
IPV6_MARK = ":"  # protocol: of the two address families' texts, only IPv6's has colons
COUNTRY_LETTERS = 2  # protocol: an ISO 3166-1 alpha-2 country code
BITS_PER_BYTE = 8  # protocol: an address's bytes, as inet_pton packs it
RETIRED = "previous"  # the name a replaced database has inside its retired folder until it is removed


class BuildError(Exception):
    """The city database could not be fetched or read; nothing was changed."""


def http_fetch(settings=FETCH):
    """fetch(url, path) over HTTPS with the limits of data/geo.json "fetch": the body streamed to path, True; False
    when the address answers not_published_status (a month DB-IP has not published yet). A redirect is followed only
    on the same host, and a body cut short is a failed attempt (downloads.py)."""
    def fetch(url, path):
        def once():
            try:
                _copy(url, path, settings)
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == SOURCE["not_published_status"]:
                    return False
                raise  # another status: an attempt that failed
            return True
        return downloads.attempts(url, settings["retries"], once, BuildError)
    return fetch


def _copy(url, path, settings):
    request = urllib.request.Request(url, headers={"User-Agent": settings["user_agent"]})
    with downloads.urlopen(request, timeout=settings["timeout_s"]) as answer, open(path, "wb") as out:
        copied = 0
        for chunk in iter(lambda: answer.read(settings["chunk_bytes"]), b""):
            copied += len(chunk)
            if copied > settings["max_bytes"]:
                raise BuildError(f"{url}: larger than {settings['max_bytes']} bytes")
            out.write(chunk)
        downloads.check_whole(answer, copied)


def months(now):
    """The months to try, newest first: now's, then earlier_months before it, as the file names write them."""
    first, found = now.date().replace(day=1), []
    for _ in range(SOURCE["earlier_months"] + 1):
        found.append(first.strftime(SOURCE["month_format"]))
        first = (first - datetime.timedelta(days=1)).replace(day=1)
    return found


def update(c=None, fetch=None, now=None):
    if not geoip.sees_addresses(config.load_cfg() if c is None else c):
        return {"skipped": "local"}
    in_use = geoip.database()
    return download(geoip.user_folder(), fetch, now, have=in_use.month if in_use else None)


def download(root, fetch=None, now=None, have=None):
    fetch, now = fetch or http_fetch(), now or datetime.datetime.now(datetime.timezone.utc)
    parent, tried = os.path.dirname(os.path.abspath(root)), []
    try:
        os.makedirs(parent, exist_ok=True)
        _remove_leftovers(parent)
        for month in months(now):
            if have and have >= month:
                return {"current": have}
            url = SOURCE["url"].format(month=month)
            if _fetch_and_swap(fetch, url, month, parent, root, now):
                return {"updated": root, "month": month}
            tried.append(url)
    except OSError as error:  # a disk that is full or not writable, while downloading, converting or swapping
        raise BuildError(str(error)) from error
    raise BuildError(f"not published yet: {', '.join(tried)}")


def _fetch_and_swap(fetch, url, month, parent, root, now):
    """One month's file downloaded, converted and swapped in: True; False when it is not published yet."""
    staging = _new_folder(parent, FOLDER["staging_prefix"])
    try:
        downloaded = os.path.join(staging, FILES["download"])
        if not fetch(url, downloaded):
            return False
        convert(downloaded, staging, month, url, now)
        os.remove(downloaded)
        _swap(staging, root)
        return True
    finally:
        shutil.rmtree(staging, ignore_errors=True)  # gone already once swapped in


def _new_folder(parent, prefix):
    """A new folder with the default mode (the umask's), as everything else in the data folder, whose own mode keeps
    other users out; not tempfile.mkdtemp's owner-only one, so a database written by another user (root running
    `agentcake lists update`) can still be read by AgentCake's own."""
    folder = os.path.join(parent, prefix + uuid.uuid4().hex)
    os.mkdir(folder)
    return folder


def _remove_leftovers(parent):
    """Folders an update stopped halfway left behind (a download alone is 86 MB)."""
    for name in os.listdir(parent):
        if name.startswith((FOLDER["staging_prefix"], FOLDER["retired_prefix"])):
            shutil.rmtree(os.path.join(parent, name), ignore_errors=True)


def _swap(staging, root):
    """The new database in place of the old one, by renames on one disk. A process still reading the old files keeps
    them until it opens the new ones (geoip.py notices the new about.json)."""
    if not os.path.isdir(root):
        os.replace(staging, root)
        return
    retired = _new_folder(os.path.dirname(root), FOLDER["retired_prefix"])
    previous = os.path.join(retired, RETIRED)
    os.replace(root, previous)
    try:
        os.replace(staging, root)
    except OSError:
        os.replace(previous, root)  # the old database stays in use
        raise
    shutil.rmtree(retired, ignore_errors=True)


class _Records:
    """One record file as it is written: a record where a place begins, and one of no place for a gap or for the
    addresses after the last range (a record's range runs to the next record)."""

    def __init__(self, out):
        self.out, self.end, self.number, self.count, self.width = out, None, None, 0, None

    def add(self, first, last, number):
        start = int.from_bytes(first, geoip.BYTE_ORDER)
        if self.end is not None and start <= self.end:
            raise ValueError("a range that does not start after the one before it ends")
        self.width = len(first)
        if self.end is not None and start > self.end + 1:
            self._write_after_end()
        if number != self.number:  # neighbouring ranges of one place make one record
            self._write(first, number)
        self.end = int.from_bytes(last, geoip.BYTE_ORDER)

    def finish(self):
        """After the last range: no place up to the family's last address (DB-IP's ranges reach it; a file whose
        ranges stop short must not give their last place to every address above)."""
        if self.end is not None and self.end + 1 < 1 << (self.width * BITS_PER_BYTE):
            self._write_after_end()

    def _write_after_end(self):
        self._write((self.end + 1).to_bytes(self.width, geoip.BYTE_ORDER), geoip.NO_PLACE)

    def _write(self, first, number):
        self.out.write(first + number.to_bytes(FORMAT["place_bytes"], geoip.BYTE_ORDER))
        self.number, self.count = number, self.count + 1


def _lines(path, digest):
    """The CSV's lines as text, from the gzip file, each added to the digest as it was published."""
    with gzip.open(path, "rb") as f:
        for line in f:
            digest.update(line)
            yield line.decode("utf-8")


def _range(start, end):
    """(file, first, last) of a row's range: its family's file and its addresses as bytes."""
    family = socket.AF_INET6 if IPV6_MARK in start else socket.AF_INET
    first, last = socket.inet_pton(family, start), socket.inet_pton(family, end)
    if first > last:
        raise ValueError(f"a range that ends before it starts: {start} {end}")
    return FAMILIES[family], first, last


def _place_number(places, row):
    """The number of a row's place, numbered as first seen; NO_PLACE for a range DB-IP knows no country for."""
    columns, cap = SOURCE["columns"], sizes()["max_chars"]
    country = row[columns["country"]]
    if not country or country == SOURCE["unknown_country"]:
        return geoip.NO_PLACE
    if not (len(country) == COUNTRY_LETTERS and country.isascii() and country.isalpha() and country.isupper()):
        raise ValueError(f"not a country code: {country!r}")
    key = (country, row[columns["region"]][:cap["subdivision"]], row[columns["city"]][:cap["city"]])
    number = places.get(key)
    if number is None:
        if any(FORMAT["separator"] in part for part in key):
            raise ValueError("a name holds the separator of places.bin")
        number = places[key] = len(places) + 1
    return number


def convert(gz_path, folder, month, url, now):
    """Write the database's files into folder from one downloaded file; about.json last, with what was read."""
    places, digest, rows = {}, hashlib.sha1(), 0
    outs = {name: open(os.path.join(folder, FILES[name]), "wb") for name in FAMILIES.values()}
    try:
        records = {name: _Records(out) for name, out in outs.items()}
        columns = SOURCE["columns"]
        for row in csv.reader(_lines(gz_path, digest)):
            rows += 1
            name, first, last = _range(row[columns["start"]], row[columns["end"]])
            records[name].add(first, last, _place_number(places, row))
        for kept in records.values():
            kept.finish()
    except (OSError, EOFError, zlib.error, csv.Error, UnicodeDecodeError, IndexError, ValueError) as error:
        raise BuildError(f"{url}, row {rows}: {error}") from error
    finally:
        for out in outs.values():
            out.close()
    if not rows:
        raise BuildError(f"{url}: no rows")
    _write_places(places, os.path.join(folder, FILES["places"]))
    _write_text(os.path.join(folder, FILES["notice"]), SETTINGS["notice"].format(
        name=SOURCE["name"], month=month, page=SOURCE["page"], url=url, attribution_url=SETTINGS["attribution"]["url"],
        license_url=SETTINGS["license"]["url"]))
    about = {"format": FORMAT["version"], "source": SOURCE["name"], "month": month, "url": url,
             "built_at": now.isoformat(timespec="seconds"), "csv_sha1": digest.hexdigest(), "rows": rows,
             "records": {name: kept.count for name, kept in records.items()}, "places": len(places),
             "license": SETTINGS["license"]["name"]}
    _write_text(os.path.join(folder, FILES["about"]), json.dumps(about, indent=1) + "\n")
    return about


def _write_places(places, path):
    """places.bin: the offsets, then the texts (data/geo.json "format"); places are numbered as they were added."""
    texts = [FORMAT["separator"].join(key).encode("utf-8") for key in places]
    width, at = FORMAT["offset_bytes"], 0
    with open(path, "wb") as out:
        out.write(at.to_bytes(width, geoip.BYTE_ORDER))
        for encoded in texts:
            at += len(encoded)
            out.write(at.to_bytes(width, geoip.BYTE_ORDER))
        for encoded in texts:
            out.write(encoded)


def _write_text(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
