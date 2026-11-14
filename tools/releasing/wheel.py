"""The wheel, agentcake-<version>-py3-none-any.whl, written with the standard library.

A wheel is a zip of the package and a <name>-<version>.dist-info folder
(https://packaging.python.org/specifications/binary-distribution-format/): METADATA (project.py), WHEEL (the format
version, pure Python, the py3-none-any tag), entry_points.txt (the agentcake command), licenses/ (PEP 639) and
RECORD, which lists every file with its sha256 and size. pyproject.toml's backend, flit_core, makes the same wheel
from a checkout (`pip wheel .`); the release writes it itself so that building it needs nothing but Python, and so
that every byte is fixed (reproducible.py): files in sorted order, the dist-info folder last, as the format suggests.
"""
import base64
import csv
import hashlib
import io
import os

from tools.releasing import project as project_module
from tools.releasing import reproducible
from tools.releasing.settings import modes

WHEEL_FILE = ("Wheel-Version: 1.0\n"  # protocol: the wheel format version this file follows
              "Generator: tools/release.py\n"
              "Root-Is-Purelib: true\n"
              f"Tag: {project_module.WHEEL_TAG}\n")
LICENSES_FOLDER = "licenses"  # protocol: PEP 639, .dist-info/licenses/ holds the license files


def record_hash(data):
    """RECORD's hash of a file: sha256=<urlsafe base64 without padding>."""
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def record(entries, record_name):
    """RECORD for entries (name, bytes, executable); RECORD itself is listed without a hash or size."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for name, data, _ in entries:
        writer.writerow([name, record_hash(data), len(data)])
    writer.writerow([record_name, "", ""])
    return out.getvalue().encode("utf-8")


def read(path):
    with open(path, "rb") as f:
        return f.read()


def entries(project):
    """Every file of the wheel, (name, bytes, executable) in the order they are written, RECORD last."""
    dist_info = project.dist_info()
    files = [(name, read(path), executable) for name, path, executable in project.package_files()]
    files.append((f"{dist_info}/METADATA", project.metadata().encode("utf-8"), False))
    files.append((f"{dist_info}/WHEEL", WHEEL_FILE.encode("utf-8"), False))
    files.append((f"{dist_info}/entry_points.txt", project.entry_points().encode("utf-8"), False))
    for name in project.license_files():
        files.append((f"{dist_info}/{LICENSES_FOLDER}/{name}", read(os.path.join(project.root, name)), False))
    record_name = f"{dist_info}/RECORD"
    files.append((record_name, record(files, record_name), False))
    return files


def build(project, out_dir, epoch, settings):
    """Write the wheel into out_dir; returns its path."""
    path = os.path.join(out_dir, project.wheel_name())
    reproducible.write_zip(path, entries(project), epoch, modes(settings), settings["zip_compresslevel"])
    return path
