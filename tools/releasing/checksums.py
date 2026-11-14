"""SHA256SUMS (S6.4): one line per release file, as `shasum -a 256` and `sha256sum` write and check them.

A line is the hex sha256, two spaces (the second one says text mode, which is how both tools write it by default) and
the file name; lines are sorted by name. `shasum -a 256 -c SHA256SUMS` in the download folder checks every file;
`sha256sum -c SHA256SUMS --ignore-missing` checks only the ones that were downloaded (SERVER.md).
"""
import hashlib
import os

from tools.releasing.settings import file_name

CHUNK_BYTES = 1 << 20  # read files a megabyte at a time


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(paths):
    """The SHA256SUMS text for these files (only their names are written)."""
    return "".join(f"{sha256_of(path)}  {os.path.basename(path)}\n"
                   for path in sorted(paths, key=os.path.basename))


def write(paths, out_dir, settings, project):
    """Write SHA256SUMS for paths into out_dir; returns its path."""
    path = os.path.join(out_dir, file_name(settings, "checksums", project.name, project.version))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text(paths))
    return path
