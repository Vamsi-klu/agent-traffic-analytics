"""`agentcake doctor` on a server: agentcake/doctor_public.py, the subdomain route's checks and the same-site path's.

    python3 -I -m unittest discover -s tests -p test_doctor_public.py -v      (from the AgentCake folder)

A real `agentcake serve` (cake_server.CakeServer: trust_lb on, path_prefix /cake; here also site_domain example.com)
stands behind HTTPS stand-ins on 127.0.0.1 (doctor_public_fixtures.py), and doctor's network is FakeNet: a made-up
resolver that leads each name to one of them, and Python's default certificate check trusting only a test authority
made for the run. No request leaves this computer.

The subdomain route (public_url https://cake.example.com). Set up right (a Caddy as deploy/Caddyfile sets it up:
Host kept, the visitor's address in X-Cake-Client-IP, a visitor's X-Cake-JA4 removed) every line passes. Each wrong
setup fails its own line and says what to change: no DNS record; a record that leads to another server; a self-signed
certificate; an AgentCake without CORS (0.5); Cloudflare's proxy in front of the subdomain (its address in DNS and the
address AgentCake sees); a Caddyfile that lets a visitor's X-Cake-JA4 through.
The same-site path (public_url empty): the self-check goes through https://example.com/cake/collect, and
what sits in front is named by the headers it adds: CloudFront removing Accept-Language (change: AllViewer), CloudFront
refusing the upload with 403 (change: Allowed HTTP methods; another front's 403 keeps the path rule change), nginx
replacing Host (change: proxy_set_header Host $host), a Google load balancer passing everything on (all pass).
Every self-check is registered on the local listener first, so it never counts as a visit.
The lines that need no server (the certificate line, the answer after an arrival, the recent visitors) are in
test_doctor_public_lines.py.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agentcake import config, doctor, doctor_lines, doctor_public, wording  # noqa: E402
from cake_server import PREFIX, CakeServer, free_port  # noqa: E402
from doctor_public_fixtures import (CORS_NONE, CORS_PASS, Certificates, Elsewhere, FakeNet, Former,  # noqa: E402
                                    Front, Platform, cdn_addresses)

SITE_DOMAIN, PUBLIC_HOST = "example.com", "cake.example.com"
PUBLIC_URL = "https://" + PUBLIC_HOST
ORIGIN = "https://" + SITE_DOMAIN
# Documentation addresses (RFC 5737): where the DNS records lead, and this server's own address as Caddy sees it.
CAKE_ADDRESS, SITE_ADDRESS, ELSEWHERE_ADDRESS, SERVER_ADDRESS = "203.0.113.10", "198.51.100.30", "192.0.2.40", "203.0.113.11"
REAL_JA4 = "t13d1516h2_8daaf6152771_02713d6af862"  # a JA4 a load balancer writes (FoxIO's example)
# AgentCake answers CORS on its public listener itself, so these tests read its own answers.
AGENTCAKE_CORS = CORS_PASS
KEYS = ("doctor_public_dns", "doctor_public_cert", "doctor_public_this", "doctor_public_cors", "doctor_public_upload",
        "doctor_public_address", "doctor_public_visitors")
PATH_KEYS = ("doctor_public_upload", "doctor_public_address", "doctor_public_visitors")
NO_CDN = {"sessions": 0, "cdn": 0, "misconfigured": False}  # the protection net's state in /api/health
BETWEEN_TWO_SENTENCES = r"[.!?];|;\s+[A-Z]"  # a semicolon between two sentences (not a command's own: "$host;")
CERTIFICATES = None


def setUpModule():
    global CERTIFICATES
    CERTIFICATES = Certificates()


def tearDownModule():
    CERTIFICATES.remove()


def caddy(**changes):
    """A Caddy as deploy/Caddyfile sets it up, with changes."""
    settings = dict(client_ip=SERVER_ADDRESS, answer={"Server": "Caddy"}, cors=AGENTCAKE_CORS)
    return Platform(**dict(settings, **changes))


def text(key, **values):
    return wording.text(key, **values)


class ServerMode(unittest.TestCase):
    """One `agentcake serve` for the class, its settings in a scratch CAKE_HOME that this process reads too."""
    public_url = PUBLIC_URL

    @classmethod
    def setUpClass(cls):
        if not CERTIFICATES.available:
            raise unittest.SkipTest("no openssl command to make the test certificates with")
        cls.cake = CakeServer(trust_lb=True)
        cls.environment = mock.patch.dict(os.environ, {"CAKE_HOME": cls.cake.home})
        cls.environment.start()
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_domain=SITE_DOMAIN, public_url=cls.public_url)

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()
        cls.cake.remove()

    def front(self, platform, certificate=None):
        server = Front(certificate or CERTIFICATES.site, self.cake.public_port, platform)
        self.addCleanup(server.close)
        return server.port

    def doctor(self, names, servers, **health):
        """{copy key: (verdict, info)} of doctor's server-mode lines; health: fields added to /api/health's answer."""
        c = config.load_cfg()
        answer = dict(doctor.reach(c).health or {}, **health)
        lines = doctor_public.public_checks(c, answer, FakeNet(CERTIFICATES.ca, names, servers))
        by_name = {name: (verdict, info) for name, verdict, info in lines}
        self.assertEqual(len(by_name), len(lines), lines)
        return {key: by_name[text(key)] for key in KEYS if text(key) in by_name}

    def assert_passes(self, lines, keys):
        self.assertEqual(sorted(lines), sorted(keys))
        for key in keys:
            self.assertIs(lines[key][0], True, f"{key}: {lines[key][1]}")

    def visits(self):
        health = doctor.reach(config.load_cfg()).health
        return health["real_sessions"], health["selfcheck_visits"]


class SubdomainRoute(ServerMode):
    def through_caddy(self, platform=None, certificate=None, address=CAKE_ADDRESS, **health):
        port = self.front(platform or caddy(), certificate)
        return self.doctor({PUBLIC_HOST: [address]}, {address: port}, **health)

    def test_set_up_right_every_line_passes(self):
        lines = self.through_caddy(address_check=NO_CDN)
        self.assert_passes(lines, KEYS)
        self.assertEqual(lines["doctor_public_dns"][1], text("doctor_public_dns_info", host=PUBLIC_HOST,
                                                             addresses=CAKE_ADDRESS))
        self.assertIn(text("doctor_public_through", platforms="Caddy"), lines["doctor_public_upload"][1])

    def test_the_self_check_is_never_counted_as_a_visit(self):
        real, selfchecks = self.visits()
        self.through_caddy()
        self.assertEqual(self.visits(), (real, selfchecks + 1))

    def test_an_agentcake_that_does_not_answer_here_leaves_the_lines_that_need_it_out(self):
        port = self.front(caddy())
        c = config.load_cfg()
        lines = doctor_public.public_checks(c, None, FakeNet(CERTIFICATES.ca, {PUBLIC_HOST: [CAKE_ADDRESS]},
                                                             {CAKE_ADDRESS: port}))
        why = text("doctor_public_not_checked", why=text("doctor_public_why_down"))
        self.assertIs(lines[1][1], True)  # the certificate is Caddy's
        self.assertEqual([(verdict, info) for _, verdict, info in lines[2:]], [(doctor_lines.SKIP, why)] * 5)

    def test_a_caddy_sending_to_another_port_than_public_listen_says_so(self):
        nowhere = Front(CERTIFICATES.site, free_port(), caddy())  # nothing listens on that port
        self.addCleanup(nowhere.close)
        lines = self.doctor({PUBLIC_HOST: [CAKE_ADDRESS]}, {CAKE_ADDRESS: nowhere.port})
        self.assertEqual(lines["doctor_public_this"], (False, text(
            "doctor_public_this_upstream", url=f"{PUBLIC_URL}{PREFIX}/cake.js", status=502, host=PUBLIC_HOST,
            prefix=PREFIX, listen=config.load_cfg()["public_listen"])))

    def test_no_dns_record_fails_and_says_to_add_one(self):
        lines = self.doctor({}, {})
        verdict, info = lines["doctor_public_dns"]
        self.assertIs(verdict, False)
        self.assertIn(f"No DNS record exists for {PUBLIC_HOST} yet", info)
        self.assertIn("Add an A record", info)
        for key in ("doctor_public_cert", "doctor_public_this", "doctor_public_upload"):
            self.assertEqual(lines[key], (doctor_lines.SKIP, text("doctor_public_not_checked",
                                                                  why=text("doctor_public_why_dns"))))

    def test_a_record_leading_to_another_server_fails_this_agentcake_and_says_where_to_point_it(self):
        elsewhere = Elsewhere(CERTIFICATES.site)
        self.addCleanup(elsewhere.close)
        lines = self.doctor({PUBLIC_HOST: [ELSEWHERE_ADDRESS]}, {ELSEWHERE_ADDRESS: elsewhere.port})
        self.assertIs(lines["doctor_public_dns"][0], True)
        self.assertEqual(lines["doctor_public_this"], (False, text(
            "doctor_public_this_other", url=f"{PUBLIC_URL}{PREFIX}/cake.js", status=404, host=PUBLIC_HOST,
            prefix=PREFIX)))
        self.assertEqual(lines["doctor_public_upload"][0], doctor_lines.SKIP)

    def test_a_self_signed_certificate_fails_and_says_why(self):
        lines = self.through_caddy(certificate=CERTIFICATES.self_signed)
        verdict, info = lines["doctor_public_cert"]
        self.assertIs(verdict, False)
        self.assertRegex(info, "self[- ]signed certificate")
        self.assertIn(text("doctor_public_cert_hint", host=PUBLIC_HOST), info)
        self.assertEqual(lines["doctor_public_this"][0], doctor_lines.SKIP)

    def test_an_agentcake_without_cors_fails_the_cors_line(self):
        lines = self.through_caddy(caddy(cors=CORS_NONE))
        verdict, info = lines["doctor_public_cors"]
        self.assertIs(verdict, False)
        self.assertIn(text("doctor_public_cors_options", status=404, allow=text("doctor_public_cors_none")), info)
        self.assertIn(text("doctor_public_cors_upload", allow=text("doctor_public_cors_none")), info)
        self.assertNotRegex(info, BETWEEN_TWO_SENTENCES)
        self.assertIn("sends CORS headers from version 0.6.0", info)
        self.assertIs(lines["doctor_public_upload"][0], True)

    def cloudflare(self, seen):
        """Cloudflare's proxy in front of a Caddy that writes seen as the visitor's address."""
        return caddy(client_ip=seen, add={"CF-Ray": "8c0ffee0-SJC", "CF-Connecting-IP": SERVER_ADDRESS},
                     answer={"Server": "cloudflare", "CF-Ray": "8c0ffee0-SJC"})

    def test_cloudflare_in_front_of_a_caddy_that_takes_its_address_fails_the_address_line(self):
        listed, edge = cdn_addresses(2)
        lines = self.through_caddy(self.cloudflare(seen=edge), address=listed)
        grey_cloud = text("doctor_public_fix_cloudflare_dns", host=PUBLIC_HOST, prefix=PREFIX)
        self.assertEqual(lines["doctor_public_dns"], (doctor_lines.WARN, text(
            "doctor_public_dns_cdn", host=PUBLIC_HOST, address=listed, cdn="Cloudflare", fix=grey_cloud)))
        self.assertEqual(lines["doctor_public_address"], (False, text(
            "doctor_public_address_cdn", cdn="Cloudflare", fix=grey_cloud)))
        self.assertIn(text("doctor_public_through", platforms="Cloudflare"), lines["doctor_public_upload"][1])

    def test_cloudflare_in_front_of_the_shipped_caddyfile_passes_with_a_warning(self):
        listed = cdn_addresses(1)[0]  # deploy/Caddyfile reads CF-Connecting-IP: the visitor's own address
        lines = self.through_caddy(self.cloudflare(seen=SERVER_ADDRESS), address=listed, address_check=NO_CDN)
        self.assertEqual(lines["doctor_public_dns"][0], doctor_lines.WARN)
        self.assertTrue(doctor_lines.passed([(key, verdict, info) for key, (verdict, info) in lines.items()]), lines)

    def test_a_caddyfile_letting_a_visitors_ja4_through_fails_the_upload_line(self):
        lines = self.through_caddy(caddy(clear_ja4=False))
        verdict, info = lines["doctor_public_upload"]
        self.assertIs(verdict, False)
        self.assertIn(text("doctor_public_made_up", header="X-Cake-JA4",
                           fix=text("doctor_public_made_up_fix", header="X-Cake-JA4")), info)

    def test_no_visitor_address_from_caddy_is_a_warning(self):
        lines = self.through_caddy(caddy(client_ip=None))
        self.assertEqual(lines["doctor_public_address"], (doctor_lines.WARN, text(
            "doctor_public_address_none", fix=text("doctor_public_address_none_fix"))))

    def test_a_caddy_without_the_collect_path_fails_the_upload_line(self):
        lines = self.through_caddy(caddy(blocked=("/collect",)))
        self.assertEqual(lines["doctor_public_upload"], (False, text(
            "doctor_public_upload_status", url=f"{PUBLIC_URL}{PREFIX}/collect", status=404,
            through=text("doctor_public_through", platforms="Caddy"),
            fix=text("doctor_public_fix_forward", host=PUBLIC_HOST, prefix=PREFIX))))
        self.assertEqual(lines["doctor_public_address"][0], doctor_lines.SKIP)

    def test_a_server_the_site_moved_from_takes_the_upload_and_keeps_it_from_here(self):
        former = Former(CERTIFICATES.site, config.load_cfg()["site_key"])
        self.addCleanup(former.close)
        lines = self.doctor({PUBLIC_HOST: [ELSEWHERE_ADDRESS]}, {ELSEWHERE_ADDRESS: former.port})
        self.assertIs(lines["doctor_public_this"][0], True)  # the same site key: only the upload tells
        self.assertEqual(lines["doctor_public_upload"], (False, text(
            "doctor_public_upload_lost", url=f"{PUBLIC_URL}{PREFIX}/collect", status=204, through="",
            host=PUBLIC_HOST, prefix=PREFIX)))

    def test_trust_lb_off_on_the_subdomain_route_is_a_warning(self):
        self.addCleanup(config.save_user, trust_lb=True)
        config.save_user(trust_lb=False)
        lines = self.through_caddy(caddy(clear_ja4=False))
        self.assertEqual(lines["doctor_public_address"], (doctor_lines.WARN, text(
            "doctor_public_address_off", launcher=doctor_public.paths.launcher())))
        self.assertIs(lines["doctor_public_upload"][0], True)  # a made-up X-Cake-JA4 is not read at all

    def test_without_site_domain_there_is_no_origin_to_check_from(self):
        self.addCleanup(config.save_user, site_domain=SITE_DOMAIN)
        config.save_user(site_domain="")
        lines = self.through_caddy()
        self.assertIs(lines["doctor_public_this"][0], True)
        for key in ("doctor_public_cors", "doctor_public_upload", "doctor_public_address"):
            self.assertEqual(lines[key], (doctor_lines.SKIP, text("doctor_public_no_site_domain",
                                                                  launcher=doctor_public.paths.launcher())))


class SameSitePath(ServerMode):
    public_url = ""

    def through(self, platform):
        port = self.front(platform)
        lines = self.doctor({SITE_DOMAIN: [SITE_ADDRESS]}, {SITE_ADDRESS: port}, address_check=NO_CDN)
        self.assertEqual(sorted(lines), sorted(PATH_KEYS))
        return lines

    def test_cloudfront_removing_accept_language_is_named_with_allviewer(self):
        cloudfront = Platform(drop=("Accept-Language",), client_ip=SERVER_ADDRESS,
                              add={"Via": "1.1 0123abcd.cloudfront.net (CloudFront)", "X-Amz-Cf-Id": "doctor-test"},
                              answer={"Via": "1.1 0123abcd.cloudfront.net (CloudFront)", "X-Amz-Cf-Id": "doctor-test"})
        verdict, info = self.through(cloudfront)["doctor_public_upload"]
        self.assertIs(verdict, False)
        self.assertEqual(info, text("doctor_public_upload_changed",
                                    changes=text("doctor_public_removed", header="Accept-Language"),
                                    through=text("doctor_public_through", platforms="CloudFront"),
                                    fix=text("doctor_public_fix_cloudfront", prefix=PREFIX, host=SITE_DOMAIN)))

    def test_cloudfront_defaults_name_each_changed_header(self):
        cloudfront = Platform(drop=("Accept-Language",), replace={"User-Agent": "Amazon CloudFront"}, keep_host=False,
                              client_ip=SERVER_ADDRESS, answer={"X-Amz-Cf-Id": "doctor-test"})
        info = self.through(cloudfront)["doctor_public_upload"][1]
        self.assertIn(text("doctor_public_removed", header="Accept-Language"), info)
        self.assertIn(text("doctor_public_replaced", header="User-Agent", value="Amazon CloudFront"), info)
        self.assertIn(text("doctor_public_replaced", header="Host", value=f"127.0.0.1:{self.cake.public_port}"), info)

    def test_cloudfront_refusing_the_upload_names_its_allowed_http_methods(self):
        """A /cake/* behavior that leaves POST out of its Allowed HTTP methods: CloudFront answers the upload 403 itself
        (AWS: "Invalid method"), so what to change is that setting, not the path rule."""
        cloudfront = Platform(refused=("POST",), client_ip=SERVER_ADDRESS,
                              answer={"Via": "1.1 0123abcd.cloudfront.net (CloudFront)", "X-Amz-Cf-Id": "doctor-test"})
        lines = self.through(cloudfront)
        self.assertEqual(lines["doctor_public_upload"], (False, text(
            "doctor_public_upload_status", url=f"{ORIGIN}{PREFIX}/collect", status=403,
            through=text("doctor_public_through", platforms="CloudFront"),
            fix=text("doctor_public_fix_cloudfront_methods", prefix=PREFIX, host=SITE_DOMAIN))))
        self.assertEqual(lines["doctor_public_address"][0], doctor_lines.SKIP)

    def test_another_front_refusing_the_upload_keeps_the_path_rule_change(self):
        nginx = Platform(refused=("POST",), client_ip=SERVER_ADDRESS, answer={"Server": "nginx/1.27.3"})
        self.assertEqual(self.through(nginx)["doctor_public_upload"], (False, text(
            "doctor_public_upload_status", url=f"{ORIGIN}{PREFIX}/collect", status=403,
            through=text("doctor_public_through", platforms="nginx"),
            fix=text("doctor_public_fix_forward", prefix=PREFIX, host=SITE_DOMAIN))))

    def test_nginx_replacing_host_is_named_with_its_line(self):
        nginx = Platform(keep_host=False, client_ip=SERVER_ADDRESS, answer={"Server": "nginx/1.27.3"})
        verdict, info = self.through(nginx)["doctor_public_upload"]
        self.assertIs(verdict, False)
        self.assertEqual(info, text("doctor_public_upload_changed",
                                    changes=text("doctor_public_replaced", header="Host",
                                                 value=f"127.0.0.1:{self.cake.public_port}"),
                                    through=text("doctor_public_through", platforms="nginx"),
                                    fix=text("doctor_public_fix_nginx", prefix=PREFIX, host=SITE_DOMAIN)))

    def test_a_load_balancer_passing_everything_on_passes_and_is_named(self):
        google = Platform(client_ip=SERVER_ADDRESS, ja4=REAL_JA4, add={"Via": "1.1 google"},
                          answer={"Via": "1.1 google"})
        lines = self.through(google)
        self.assert_passes(lines, PATH_KEYS)
        self.assertIn(text("doctor_public_through", platforms="Google Cloud load balancer"),
                      lines["doctor_public_upload"][1])

    def test_a_load_balancer_passing_a_visitors_ja4_on_is_named(self):
        lines = self.through(Platform(client_ip=SERVER_ADDRESS, clear_ja4=False))
        self.assertIn(text("doctor_public_made_up", header="X-Cake-JA4",
                           fix=text("doctor_public_made_up_fix_path", header="X-Cake-JA4")),
                      lines["doctor_public_upload"][1])


if __name__ == "__main__":
    unittest.main()
