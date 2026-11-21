"""SERVER.md's Backups section against the deploy files: a command block for each setup option, and a restore that
names the owner and mode the data folder needs.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

With Docker Compose, Backups once said only "copy the data volume". Upgrading a test server in place showed that an
ordinary user cannot: the volume's files belong to the image's user and the folder has mode 700. So the Docker Compose
block does what the systemd block does, on the volume that docker-compose.yml mounts at the data folder: make the
backup folder, stop the service, pack the folder as root into an archive beside systemd's, start the service. Each
restore names the user that serve runs as and the mode the data folder is made with. test_server_docs.py checks the
rest of SERVER.md; neither Docker nor systemd is needed here.
"""
import os
import re
import shlex
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from cake_server import ROOT, SERVER_MD, read  # noqa: E402  (needs the path above)
from deploy_files import (COMPOSE_FILE, compose_file, final_stage, instruction_values, mounts,  # noqa: E402
                          unit_data_folder, unit_file)
from test_server_docs import COMPOSE_SERVICE, VOLUME_INSPECT, build_commands, code_block_lines, section  # noqa: E402

ARCHIVE = re.compile(r"\star -C (.+?) -czf (.+) (\S+)$")  # a backup's `tar -C <folder> -czf <archive> <what>`


def shell_blocks(markdown):
    """The ```sh code blocks of a Markdown text, each as (its lines, the paragraph that follows it on one line)."""
    return [([line.strip() for line in body.splitlines() if line.strip()], " ".join(after.split()))
            for body, after in re.findall(r"^```sh\n(.*?)^```\n\n(.*?)(?=\n\n|\Z)", markdown, re.M | re.S)]


def made_folder_mode(commands, folder):
    """The mode that an `install -d … -m <mode> <folder>` among commands, run with sudo or not, makes folder with."""
    for command in (command for command in commands if "install -d" in command):
        words = shlex.split(command)
        words = words[1:] if words[:1] == ["sudo"] else words
        if words[:2] == ["install", "-d"] and words[-1] == folder and "-m" in words:
            return words[words.index("-m") + 1]
    return None


class BackupsMatchTheDeployFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(COMPOSE_FILE):
            raise unittest.SkipTest(f"{os.path.relpath(COMPOSE_FILE, ROOT)} not in this checkout: it comes with the "
                                    "subdomain route's code; SERVER.md already describes it")
        cls.server_md, compose = read(SERVER_MD), compose_file()
        cls.services, cls.volumes = compose["services"], compose.get("volumes") or {}

    def backup_blocks(self):
        """Backups' two command blocks, systemd's and Docker Compose's, each as (its lines, the paragraph after it)."""
        blocks = shell_blocks(section(self.server_md, "Backups"))
        systemd = [block for block in blocks if "sudo systemctl stop cake" in block[0]]
        compose = [block for block in blocks if any(COMPOSE_SERVICE.match(line) for line in block[0])]
        self.assertEqual(len(systemd), 1, "Backups has one systemd command block")
        self.assertEqual(len(compose), 1, "Backups has one Docker Compose command block, as systemd has")
        return systemd[0], compose[0]

    def test_the_compose_backup_is_a_command_block_as_systemd_has(self):
        """The block makes the backup folder as systemd's does, stops the service that mounts the data folder, packs as
        root the folder of that volume, which `docker volume inspect` names, into an archive beside systemd's, and
        starts the service again."""
        (systemd, _), (compose, _) = self.backup_blocks()
        service = next(name for name, settings in self.services.items() if unit_data_folder() in mounts(settings))
        volume = self.volumes[mounts(self.services[service])[unit_data_folder()]]["name"]
        self.assertEqual(len(compose), 5, compose)
        self.assertEqual(compose[0], systemd[0])
        self.assertEqual(compose[1], f"docker compose stop {service}")
        self.assertEqual(compose[4], f"docker compose start {service}")
        packed, systemd_packed = ARCHIVE.search(compose[2]), ARCHIVE.search(systemd[2])
        self.assertTrue(compose[2].startswith("sudo tar ") and packed, compose[2])
        self.assertEqual(VOLUME_INSPECT.findall(packed.group(1)), [volume])
        self.assertIn("{{ .Mountpoint }}", packed.group(1))
        self.assertEqual(packed.group(2), systemd_packed.group(2))
        self.assertEqual(packed.group(3), ".")

    def test_each_archive_is_readable_by_root_only(self):
        """tar writes the archive with the default mode 644: inside the 700 backup folder that's private, but a copy
        carries srv_secret and the visitors' sessions to wherever it lands. A server check found it; each block now
        sets the archive it just wrote to 600, as its own command (an agent runs one command per shell, so a umask
        line wouldn't reach tar), before the service starts again."""
        for lines, _ in self.backup_blocks():
            archive = ARCHIVE.search(lines[2]).group(2)
            self.assertEqual(lines[3], f"sudo chmod 600 {archive}", lines)
            self.assertIn(" start ", f" {lines[4]} ")
        self.assertIn("Only root can read the archive.", " ".join(section(self.server_md, "Backups").split()))

    def test_each_restore_names_the_owner_and_mode_serve_needs(self):
        """tar run as root puts the owner and mode back, but files copied back another way take the copier's: each
        restore names the user serve runs as (the unit's User, the image's user ID) and the mode the data folder is
        made with (SERVER.md's install -d for systemd, the Dockerfile's for the image)."""
        (_, systemd_restore), (_, compose_restore) = self.backup_blocks()
        home = unit_data_folder()
        image_user = instruction_values(final_stage()[1], "USER")[-1].split(":")[0]
        for restore, owner, mode in ((systemd_restore, f"`{unit_file()['Service']['User']}`",
                                      made_folder_mode(code_block_lines(self.server_md), home)),
                                     (compose_restore, f"user ID {image_user}", made_folder_mode(build_commands(), home))):
            self.assertTrue(mode, f"no install -d -m for {home}")
            self.assertIn("To restore", restore)
            self.assertIn(owner, restore)
            self.assertIn(f"mode {mode}", restore)

    def test_the_archives_are_copied_off_the_servers_own_disk(self):
        """Both blocks write the archive to a folder on the server's own disk, and Disk budget says to back up to a
        snapshot or another disk, not to that one: after the blocks, Backups says where to copy the archives."""
        (systemd, _), _ = self.backup_blocks()
        folder = os.path.dirname(ARCHIVE.search(systemd[2]).group(2))
        self.assertRegex(section(self.server_md, "Disk budget"), r"snapshot or another disk, not to this one")
        backups = section(self.server_md, "Backups")
        after = " ".join(backups[backups.rindex("```"):].split())
        self.assertIn(f"`{folder}`", after, "the folder the blocks write to, named in the words after them")
        self.assertRegex(after, r"\banother disk\b")


if __name__ == "__main__":
    unittest.main()
