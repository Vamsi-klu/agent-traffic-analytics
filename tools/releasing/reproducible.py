"""Zip and tar.gz files whose bytes depend only on what goes into them and one timestamp (S6.4).

Every entry gets the same time (the commit's, SOURCE_DATE_EPOCH: https://reproducible-builds.org/specs/source-date-epoch/),
the mode its kind has (release.json "modes": file, executable or folder), no owner (uid and gid 0, no user or group
name), and entries are written in the order given (the callers sort them). The gzip header carries no file name and
no time. zlib compresses at a fixed level: the same Python with the same zlib gives the same bytes, another zlib may
compress differently (release.json "toolchain" names what the release is built with).
"""
import gzip
import io
import stat
import tarfile
import time
import zipfile

ZIP_EARLIEST = (1980, 1, 1, 0, 0, 0)  # protocol: the zip format cannot store a time before 1980
ZIP_HOST_UNIX = 3  # protocol: zip "made by" host 3 (Unix), so that readers apply the stored modes
GZIP_NO_TIME = 0  # protocol: RFC 1952, MTIME 0 means no time stamp is available


def zip_time(epoch):
    """The zip date and time (UTC, so the same on every computer) of a POSIX time."""
    return max(tuple(time.gmtime(epoch)[:6]), ZIP_EARLIEST)


def zip_info(name, epoch, file_mode):
    info = zipfile.ZipInfo(name, zip_time(epoch))
    info.create_system = ZIP_HOST_UNIX
    info.external_attr = (stat.S_IFREG | file_mode) << 16  # protocol: a zip keeps the Unix mode in the high 16 bits
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def write_zip(path, entries, epoch, modes, compresslevel, prefix=b""):
    """Write a zip of entries, (name, bytes, executable) in the order given, after prefix (a shebang line, for a zip
    that Python runs). modes: {"file": 0o644, "executable": 0o755}."""
    with open(path, "wb") as f:
        f.write(prefix)
        with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED, compresslevel=compresslevel) as archive:
            for name, data, executable in entries:
                info = zip_info(name, epoch, modes["executable"] if executable else modes["file"])
                archive.writestr(info, data, compresslevel=compresslevel)


def write_tar_gz(path, entries, epoch, modes, compresslevel):
    """Write a .tar.gz of entries, (name, bytes or None for a folder, executable) in the order given.
    modes: {"file": 0o644, "executable": 0o755, "folder": 0o755}."""
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=compresslevel, mtime=GZIP_NO_TIME) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for name, data, executable in entries:
                    info = tarfile.TarInfo(name)
                    info.mtime, info.uid, info.gid, info.uname, info.gname = epoch, 0, 0, "", ""
                    if data is None:
                        info.type, info.mode = tarfile.DIRTYPE, modes["folder"]
                        tar.addfile(info)
                    else:
                        info.size, info.mode = len(data), modes["executable"] if executable else modes["file"]
                        tar.addfile(info, io.BytesIO(data))
