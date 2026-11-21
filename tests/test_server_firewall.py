"""What SERVER.md opens to the network: step 1 opens only the ports that visitors' browsers use, 80 and 443, to the
internet, and keeps SSH on port 22 for the site owner, as the Firewall table says ("Only you"); every SSH tunnel it
gives binds its end on the reader's computer to 127.0.0.1.

    python3 -I -m unittest discover -s tests -p test_server_firewall.py -v      (from the AgentCake folder)

Step 1 once told the reader to open ports 22, 80 and 443 to the internet, while the Firewall section gave port 22 to
the site owner alone. A server whose SSH port is open to everyone is scanned and tried within minutes. Step 1 now opens
80 and 443 to the internet and says that SSH comes only from the owner's own address or through the cloud provider's
own SSH service (IAP on Google Cloud, as the path option's firewall rules use). The local page has no login, and
`ssh -L port:host:port` without an address binds as the SSH client's GatewayPorts setting says: with GatewayPorts yes,
anyone on the reader's network could open the dashboard through the tunnel. `-L 127.0.0.1:port:host:port` binds to this
computer alone, whatever that setting. test_server_docs.py checks the rest of SERVER.md; nothing here goes online.
"""
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from cake_server import SERVER_MD, read  # noqa: E402  (needs the path above)
from test_install_docs import section  # noqa: E402

LOCAL_FORWARD = re.compile(r"(?<![\w-])-L\s+([0-9A-Za-z.:\[\]<>-]+)")  # ssh's -L [bind_address:]port:host:hostport


def step_1(markdown):
    """SERVER.md's `### 1. Get a server`, up to the next heading, on one line."""
    match = re.search(r"^### 1\. Get a server\n(.*?)(?=^#{2,3} )", markdown, re.M | re.S)
    return " ".join(match.group(1).split())


class StepOne(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = read(SERVER_MD)
        cls.step = step_1(cls.server)

    def test_the_firewall_table_gives_ssh_to_the_site_owner_alone(self):
        row = re.search(r"^\| 22 \(SSH\) \| ([^|]+) \|", section(self.server, "Firewall"), re.M)
        self.assertEqual(row.group(1).strip(), "Only you")

    def test_step_1_opens_only_80_and_443_to_the_internet(self):
        opened = re.findall(r"\b[Oo]pen (ports? [\d, and]+?) to the internet", self.step)
        self.assertEqual(opened, ["ports 80 and 443"])

    def test_step_1_keeps_ssh_for_the_owners_own_address_or_the_providers_ssh_service(self):
        self.assertRegex(self.step, r"\bSSH on port 22 only from your own IP address\b")
        self.assertRegex(self.step, r"\bIAP on Google Cloud\b")


class Tunnels(unittest.TestCase):
    def test_every_tunnel_binds_to_127_0_0_1_on_the_readers_computer(self):
        forwards = LOCAL_FORWARD.findall(read(SERVER_MD))
        self.assertGreaterEqual(len(forwards), 5)  # step 8, the dashboard's two commands, another port, server logs
        for forward in forwards:
            self.assertRegex(forward, r"^127\.0\.0\.1:\d+:[^:]+:\d+$", forward)


if __name__ == "__main__":
    unittest.main()
