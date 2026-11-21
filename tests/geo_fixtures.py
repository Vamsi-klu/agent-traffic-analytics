"""What the city database tests share: a small database in DB-IP's CSV format, converted by
geoip_build.convert as `agentcake lists update` converts the real one.

Its places are made up, on the documentation ranges (RFC 5737 for IPv4, RFC 3849 for IPv6), which DB-IP itself places
nowhere; like DB-IP's file, its rows cover each address family from its first address to its last, the unknown parts
as DB-IP writes them (country ZZ).

    ROWS, MONTH, NOW            the example database's rows (DB-IP's CSV columns), its month, and a time in that month
    PLACES                      {address: what geoip.place gives it} for addresses of ROWS
    csv_gz(rows) -> bytes       a gzipped CSV of rows, as DB-IP publishes it
    install(folder, rows=ROWS, month=MONTH) -> about    the database converted into folder (made if missing)
    single(address, country, region, city) -> rows      one address placed, every other one unknown
"""
import csv
import datetime
import gzip
import io
import ipaddress
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import geoip_build  # noqa: E402

MONTH = "2026-11"
NOW = datetime.datetime(2026, 11, 18, 12, tzinfo=datetime.timezone.utc)
UNKNOWN = ("ZZ", "ZZ", "", "")  # continent, country, region, city of a range DB-IP knows nothing of


def beside(address, step):
    """The address step places from a documentation address: the edges of the ranges these tests need, computed so
    that no public address is written in a published file."""
    return str(ipaddress.ip_address(address) + step)


ROWS = [
    ("0.0.0.0", beside("192.0.2.0", -1), *UNKNOWN),
    ("192.0.2.0", "192.0.2.127", "NA", "US", "California", "Mountain View"),
    ("192.0.2.128", "192.0.2.255", "EU", "DE", "", "Berlin"),
    (beside("192.0.2.255", 1), beside("198.51.100.0", -1), *UNKNOWN),
    ("198.51.100.0", "198.51.100.255", "AS", "JP", "Tokyo", "Tokyo"),
    (beside("198.51.100.255", 1), beside("203.0.113.0", -1), *UNKNOWN),
    ("203.0.113.0", "203.0.113.63", "EU", "FR", "Île-de-France", "Paris"),
    ("203.0.113.64", "203.0.113.127", "EU", "FR", "Île-de-France", "Paris"),
    ("203.0.113.128", "203.0.113.255", "OC", "AU", "", ""),
    (beside("203.0.113.255", 1), "255.255.255.255", *UNKNOWN),
    ("::", "2001:db7:ffff:ffff:ffff:ffff:ffff:ffff", *UNKNOWN),
    ("2001:db8::", "2001:db8:0:ffff:ffff:ffff:ffff:ffff", "NA", "CA", "Quebec", "Montreal"),
    ("2001:db8:1::", "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff", "EU", "GB", "England", "London"),
    ("2001:db9::", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", *UNKNOWN),
]
PLACES = {
    "192.0.2.10": {"country": "US", "subdivision": "California", "city": "Mountain View"},
    "192.0.2.200": {"country": "DE", "subdivision": None, "city": "Berlin"},
    "198.51.100.7": {"country": "JP", "subdivision": "Tokyo", "city": "Tokyo"},
    "203.0.113.5": {"country": "FR", "subdivision": "Île-de-France", "city": "Paris"},
    "203.0.113.100": {"country": "FR", "subdivision": "Île-de-France", "city": "Paris"},
    "203.0.113.200": {"country": "AU", "subdivision": None, "city": None},
    "2001:db8::17": {"country": "CA", "subdivision": "Quebec", "city": "Montreal"},
    "2001:db8:5::1": {"country": "GB", "subdivision": "England", "city": "London"},
    "::ffff:192.0.2.10": {"country": "US", "subdivision": "California", "city": "Mountain View"},
}
NOWHERE = (beside("192.0.2.0", -255), beside("198.51.100.255", 2), "10.0.0.1", "127.0.0.1", "255.255.255.255", "::1", "2001:db9::1")
COORDINATES = ("0", "0")  # latitude and longitude: DB-IP's last two columns, which the conversion leaves out


def csv_gz(rows):
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    for row in rows:
        writer.writerow(list(row) + list(COORDINATES))
    return gzip.compress(text.getvalue().encode("utf-8"))


def install(folder, rows=ROWS, month=MONTH):
    os.makedirs(folder, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cake-geo-download-") as scratch:
        downloaded = os.path.join(scratch, "download.csv.gz")
        with open(downloaded, "wb") as f:
            f.write(csv_gz(rows))
        return geoip_build.convert(downloaded, folder, month, f"https://example.com/{month}.csv.gz", NOW)


def single(address, country, region="", city=""):
    """Rows that place one address and no other."""
    ip = ipaddress.ip_address(address)
    return [(str(ip), str(ip), "NA", country, region, city)]
