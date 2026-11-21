"""The visitor's country, region and city, looked up in the city database on this computer.

The database is DB-IP's IP to City Lite (CC BY 4.0, data/geo.json), downloaded and converted by geoip_build.py on a
server, into <CAKE_HOME>/geo: at the first check after AgentCake starts, then once a month (agentcake/updates.py), and
when `agentcake lists update` runs. It is not part of the package or of the Docker image. PostHog looks addresses up
the same way, in a GeoLite2 database its own server downloads (PostHog 1.0 had no places at all); DB-IP's Lite
database needs no account.

    place(address) -> {"country", "subdivision", "city"} or None
        The ISO 3166-1 country code, region and city DB-IP gives the range holding the address (None for a region or
        a city it does not know); None when there is no database, the text is not an address, DB-IP knows no
        country for it, or the database's entry for it is damaged. An IPv4-mapped IPv6 address is looked up as its IPv4. The address itself is not kept: no
        cache, attribute or log holds it.
    sees_addresses(c) -> bool     whether this AgentCake gets visitor addresses at all: the public listener with
                                  trust_lb (netfacts.client_address); on this computer every visit is 127.0.0.1
    source(c) -> NONE | MISSING | DATABASE   where the dashboard's places come from (api/web.py)
    status(today=None) -> {month, months_old, stale, built_at, folder} of the database in use, or None
    user_folder()                 <CAKE_HOME>/geo: where the updates and `agentcake lists update` put it

Each lookup is a binary search over fixed-length records read through mmap: a few pages of the files, never the
files whole, so the database costs a 600 MB process no Python objects. A database that an update replaced is noticed
at the next lookup by its about.json (inode, size, time), so no restart is needed. Nothing here opens a connection.
"""
import datetime
import ipaddress
import json
import mmap
import os

from agentcake import paths
from agentcake.datafiles import load

SETTINGS = load("data/geo.json")
FILES, FORMAT = SETTINGS["files"], SETTINGS["format"]
FAMILIES = {ipaddress.IPV4LENGTH: "ipv4", ipaddress.IPV6LENGTH: "ipv6"}  # an address's length in bits: its file
NONE, MISSING, DATABASE = "none", "missing", "database"
NO_PLACE = 0  # the place number of a range DB-IP knows no country for
BYTE_ORDER = "big"  # protocol: the record files' numbers are big-endian (data/geo.json "format")
MONTHS_PER_YEAR = 12  # protocol: calendar months


class DatabaseError(Exception):
    """A folder's city database is not one this version reads, or its files do not fit together."""


class _Records:
    """One record file: the first address of each range and its place number, in order of the address."""

    def __init__(self, path, start_bytes, count):
        self.start_bytes, self.size = start_bytes, start_bytes + FORMAT["place_bytes"]
        self.map, length = _map(path)
        if length % self.size:
            raise DatabaseError(f"{path}: {length} bytes is not a whole number of {self.size}-byte records")
        self.count = length // self.size
        if self.count != count:  # cut short by whole records, the last place left would reach every address above
            raise DatabaseError(f"{path}: {self.count} records, not the {count} records {FILES['about']} counts")

    def find(self, packed):
        """The place number of the range holding the address (its bytes, start_bytes long), NO_PLACE when none."""
        low, high, records, size, width = 0, self.count, self.map, self.size, self.start_bytes
        while low < high:  # the first record whose address is above this one
            middle = (low + high) >> 1
            if records[middle * size:middle * size + width] <= packed:
                low = middle + 1
            else:
                high = middle
        if not low:
            return NO_PLACE
        at = (low - 1) * size + width
        return int.from_bytes(records[at:at + FORMAT["place_bytes"]], BYTE_ORDER)


class _Places:
    """places.bin: each place's country, region and city, read by its number."""

    def __init__(self, path, count):
        width = FORMAT["offset_bytes"]
        self.map, length = _map(path)
        self.count, self.width, self.text_at = count, width, (count + 1) * width
        if length < self.text_at or self._offset(count) != length - self.text_at:
            raise DatabaseError(f"{path}: its offsets do not match its {count} places")

    def _offset(self, index):
        return int.from_bytes(self.map[index * self.width:(index + 1) * self.width], BYTE_ORDER)

    def get(self, number):
        if not NO_PLACE < number <= self.count:
            raise DatabaseError(f"place {number} is not one of {self.count}")
        text = self.map[self.text_at + self._offset(number - 1):self.text_at + self._offset(number)].decode("utf-8")
        country, region, city = text.split(FORMAT["separator"])
        return {"country": country, "subdivision": region or None, "city": city or None}


class Database:
    """The city database of one folder (geoip_build.py wrote it): about.json, the two record files and places.bin."""

    def __init__(self, folder):
        self.folder = folder
        try:
            with open(os.path.join(folder, FILES["about"]), encoding="utf-8") as f:
                about = json.load(f)
        except ValueError as error:
            raise DatabaseError(f"{folder}: {error}") from error
        if not isinstance(about, dict):
            raise DatabaseError(f"{folder}: {FILES['about']} holds no JSON object")
        if about.get("format") != FORMAT["version"]:
            raise DatabaseError(f"{folder}: format {about.get('format')!r}, not {FORMAT['version']}")
        self.month, self.built_at = about["month"], about["built_at"]
        _month_start(self.month)  # a month that is not one: ValueError, so the folder's database is not used
        self.records = {family: _Records(os.path.join(folder, FILES[family]), FORMAT["start_bytes"][family],
                                         about["records"][family])
                        for family in FAMILIES.values()}
        self.places = _Places(os.path.join(folder, FILES["places"]), about["places"])

    def place(self, ip):
        number = self.records[FAMILIES[ip.max_prefixlen]].find(ip.packed)
        return self.places.get(number) if number != NO_PLACE else None


def _map(path):
    """(a read-only map of the file, its length); an empty file maps to b"" (mmap cannot map nothing)."""
    with open(path, "rb") as f:
        length = os.fstat(f.fileno()).st_size
        return (mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) if length else b""), length


def user_folder():
    return os.path.join(paths.home(), SETTINGS["folder"]["user_dir"])


_OPENED = {}  # folder -> (its about.json's (inode, size, time), its Database or the error that stopped it)


def _signature(folder):
    """(inode, size, time) of the folder's about.json, which a database swapped in changes; None without one."""
    try:
        found = os.stat(os.path.join(folder, FILES["about"]))
    except OSError:
        return None
    return found.st_ino, found.st_size, found.st_mtime_ns


def _opened(folder):
    """The Database of a folder, or the error that stops it, or None for a folder without one; opened again only
    when its about.json changed (a new database was swapped in). One swapped in while its files were being opened is
    not used, since they may come from both databases; the next lookup opens the new one."""
    signature = _signature(folder)
    if signature is None:
        _OPENED.pop(folder, None)
        return None
    kept = _OPENED.get(folder)
    if kept is None or kept[0] != signature:
        try:
            opened = Database(folder)
        except (DatabaseError, OSError, KeyError, TypeError, ValueError) as error:
            opened = DatabaseError(f"{folder}: {error}")
        if _signature(folder) != signature:
            return None
        kept = _OPENED[folder] = (signature, opened)
    return kept[1]


def database():
    """The readable database in user_folder(), or None."""
    found = _opened(user_folder())
    return found if isinstance(found, Database) else None


def place(address):
    found = database()
    if found is None:
        return None
    try:
        ip = ipaddress.ip_address(str(address).strip())
    except ValueError:
        return None
    try:
        return found.place(getattr(ip, "ipv4_mapped", None) or ip)
    except (DatabaseError, ValueError):  # ValueError: a text that does not decode or split into three
        # A damaged record or place shows only when an address finds it (opening checks only what fits together
        # cheaply): that address has no place, as one DB-IP knows nothing of, and the upload is taken as usual.
        return None


def sees_addresses(c):
    return bool(c.get("public_listen") and c.get("trust_lb"))


def source(c):
    if not sees_addresses(c):
        return NONE
    return DATABASE if database() else MISSING


def _month_start(month):
    """The first day of a month as the file names write it (data/geo.json "month_format")."""
    return datetime.datetime.strptime(month, SETTINGS["source"]["month_format"]).date()


def months_between(earlier, later):
    """Whole calendar months from the month earlier ("2026-11") to the date later."""
    first = _month_start(earlier)
    return (later.year - first.year) * MONTHS_PER_YEAR + later.month - first.month


def status(today=None):
    """The database in use: its month, how many months old it is (stale past max_months_old), when it was downloaded
    and its folder; None without one. A database this version cannot read is named in errors."""
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    found = _opened(user_folder())
    if isinstance(found, DatabaseError):
        return {"errors": [paths.tilde(str(found))]}
    if found is None:
        return None
    old = months_between(found.month, today)
    return {"month": found.month, "months_old": old, "stale": old > SETTINGS["max_months_old"],
            "built_at": found.built_at, "folder": paths.tilde(found.folder)}
