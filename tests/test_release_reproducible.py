"""tools/releasing/reproducible.py: the same entries and time give the same zip and tar.gz bytes, and
every entry carries the given time, its mode and no owner.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import os
import tarfile
import time
import unittest
import zipfile

from release_trees import scratch

from tools.releasing import reproducible

EPOCH = 1794528000  # 2026-11-12 00:00:00 UTC, a made-up commit time
MODES = {"file": 0o644, "executable": 0o755, "folder": 0o755}
LEVEL = 9
ENTRIES = [("pkg/a.txt", b"alpha\n", False), ("pkg/run.sh", b"#!/bin/sh\n", True), ("pkg/z.json", b"{}\n", False)]
GZIP_FLAGS_BYTE = 3  # RFC 1952: ID1 ID2 CM FLG MTIME(4) XFL OS
GZIP_FNAME = 0x08
GZIP_MTIME = slice(4, 8)


def read(path):
    with open(path, "rb") as f:
        return f.read()


class Zip(unittest.TestCase):
    def setUp(self):
        self.out = scratch(self)

    def write(self, name, entries=ENTRIES, epoch=EPOCH, prefix=b""):
        path = os.path.join(self.out, name)
        reproducible.write_zip(path, entries, epoch, MODES, LEVEL, prefix=prefix)
        return path

    def test_the_same_entries_give_the_same_bytes(self):
        self.assertEqual(read(self.write("one.zip")), read(self.write("two.zip")))

    def test_another_time_gives_other_bytes(self):
        self.assertNotEqual(read(self.write("one.zip")), read(self.write("two.zip", epoch=EPOCH + 2)))

    def test_entries_carry_the_time_in_utc_and_their_modes(self):
        with zipfile.ZipFile(self.write("one.zip")) as archive:
            infos = archive.infolist()
        self.assertEqual([i.filename for i in infos], [name for name, _, _ in ENTRIES])
        for info, (_, _, executable) in zip(infos, ENTRIES):
            self.assertEqual(info.date_time, time.gmtime(EPOCH)[:6])
            self.assertEqual(info.create_system, reproducible.ZIP_HOST_UNIX)
            self.assertEqual((info.external_attr >> 16) & 0o777, 0o755 if executable else 0o644)

    def test_a_time_before_1980_is_stored_as_1980(self):
        self.assertEqual(reproducible.zip_time(0), reproducible.ZIP_EARLIEST)

    def test_a_prefix_comes_first_and_the_zip_still_reads(self):
        path = self.write("run.pyz", prefix=b"#!/usr/bin/env python3\n")
        self.assertTrue(read(path).startswith(b"#!/usr/bin/env python3\n"))
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read("pkg/a.txt"), b"alpha\n")


class TarGz(unittest.TestCase):
    ENTRIES = [("top", None, True), ("top/pkg", None, True)] + [(f"top/{n}", d, x) for n, d, x in ENTRIES]

    def setUp(self):
        self.out = scratch(self)

    def write(self, name, epoch=EPOCH):
        path = os.path.join(self.out, name)
        reproducible.write_tar_gz(path, self.ENTRIES, epoch, MODES, LEVEL)
        return path

    def test_the_same_entries_give_the_same_bytes(self):
        self.assertEqual(read(self.write("one.tar.gz")), read(self.write("two.tar.gz")))

    def test_members_carry_the_time_their_mode_and_no_owner(self):
        with tarfile.open(self.write("one.tar.gz")) as tar:
            members = tar.getmembers()
        self.assertEqual([m.name for m in members], [name for name, _, _ in self.ENTRIES])
        for member, (_, data, executable) in zip(members, self.ENTRIES):
            self.assertEqual((member.mtime, member.uid, member.gid, member.uname, member.gname), (EPOCH, 0, 0, "", ""))
            self.assertEqual(member.isdir(), data is None)
            self.assertEqual(member.mode, 0o755 if executable else 0o644)

    def test_the_gzip_header_has_no_file_name_and_no_time(self):
        header = read(self.write("one.tar.gz"))[:10]
        self.assertEqual(header[GZIP_FLAGS_BYTE] & GZIP_FNAME, 0)
        self.assertEqual(header[GZIP_MTIME], b"\0\0\0\0")


if __name__ == "__main__":
    unittest.main()
