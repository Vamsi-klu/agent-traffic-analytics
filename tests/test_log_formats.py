"""Reading web server access logs: agentcake/log_formats.py.

    python3 -I -m unittest discover -s tests -p test_log_formats.py -v      (from the Agent Cake folder)

Five samples of 100 lines each, written from made-up requests the way each web server writes them (log_samples.py):
nginx combined, nginx with the recommended log_format, Apache combined, Apache with the recommended LogFormat, and
Caddy's JSON. Every field of every line reads back as it was written: time, address, method, target, protocol,
status, Host, scheme and each logged header, with the servers' escaping undone. A site's own nginx log_format or
Apache LogFormat is compiled the same way; a format without what matching needs (time, address, request, status,
User-Agent) is refused. The recommended formats are the ones docs/*.example show.
"""
import functools
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import log_formats  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from log_samples import (FORMAT_OF_SAMPLE, FORMATS, LINE_WRITERS, ROOT, nginx_escape, parsed_view,  # noqa: E402
                         requests)

SAMPLE_LINES = 100
START_MS = 1794500000123
SPEC = load("data/logs.json")
DOCS = {"nginx": "docs/nginx.conf.example", "apache": "docs/apache.conf.example", "caddy": "docs/Caddyfile.example"}
FIELDS = ("t_ms", "ip", "method", "target", "protocol", "status", "host", "scheme", "headers")


@functools.lru_cache(maxsize=None)
def sample(name):
    """(line, truth) of the 100 lines of one sample format; the same lines for every test."""
    truths = requests(SAMPLE_LINES, seed=FORMATS.index(name) + 1, start_ms=START_MS)
    return tuple((LINE_WRITERS[name](truth), truth) for truth in truths)


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


class FiveFormats(unittest.TestCase):
    def test_every_field_of_every_line_reads_back(self):
        for name in FORMATS:
            log_format = log_formats.named(FORMAT_OF_SAMPLE.get(name, name))
            for number, (line, truth) in enumerate(sample(name)):
                record = log_format.parse(line)
                expected = parsed_view(name, truth)
                with self.subTest(format=name, line=number):
                    self.assertIsNotNone(record, line)
                    for field in FIELDS:
                        self.assertEqual(getattr(record, field), getattr(expected, field), field)

    def test_each_sample_has_what_the_tests_need(self):
        """The samples hold the cases the reading has to get right, so the test above is not easy by accident."""
        for name in FORMATS:
            lines = [line for line, _ in sample(name)]
            truths = [truth for _, truth in sample(name)]
            self.assertTrue(any(":" in t.ip for t in truths), f"{name}: an IPv6 address")
            self.assertTrue(any("signature" in t.headers for t in truths), f"{name}: a signed request")
            self.assertTrue(any('"' in t.headers["user-agent"] for t in truths), f"{name}: a quote to escape")
            self.assertTrue(any(t.method == "POST" for t in truths) and any(t.status == 301 for t in truths), name)
            self.assertEqual(len(lines), SAMPLE_LINES)

    def test_detection_names_each_samples_format(self):
        for name in FORMATS:
            lines = [line for line, _ in sample(name)]
            self.assertEqual(log_formats.detect(lines).name, FORMAT_OF_SAMPLE.get(name, name), name)

    def test_nothing_is_detected_in_lines_of_no_known_format(self):
        self.assertIsNone(log_formats.detect(["hello world", "", "\x16\x03\x01\x02"]))

    def test_both_servers_combined_format_strings_read_both_servers_lines(self):
        combined = SPEC["formats"]["combined"]
        readers = (log_formats.from_nginx(combined["template"]), log_formats.from_apache(combined["apache_template"]))
        for name in ("nginx-combined", "apache-combined"):
            for line, truth in sample(name):
                first, second = (reader.parse(line) for reader in readers)
                self.assertEqual(first, second, line)
                self.assertEqual(first.ip, truth.ip)

    def test_a_line_that_is_cut_garbage_or_of_another_format_is_not_read(self):
        line, _ = sample("nginx-agentcake")[0]
        nginx = log_formats.named("nginx-agentcake")
        for bad in ("", "-", line[: len(line) // 2], "\x16\x03\x01\x00\xa5\x01", sample("apache-agentcake")[0][0],
                    sample("caddy-json")[0][0], line + " extra"):
            self.assertIsNone(nginx.parse(bad), bad)
        self.assertIsNone(log_formats.named("caddy-json").parse('{"level":"info","msg":"serving initial config"}'))

    def test_a_line_longer_than_the_cap_is_not_read(self):
        line, _ = sample("nginx-combined")[0]
        long_line = line[:-1] + "x" * SPEC["max_line_chars"] + '"'
        self.assertIsNone(log_formats.named("combined").parse(long_line))

    def test_a_dash_or_an_empty_value_is_a_missing_header(self):
        nginx = log_formats.from_nginx('$remote_addr [$msec] "$request" $status "$http_user_agent" '
                                       '"$http_accept_language"')
        dash = nginx.parse('192.0.2.1 [1794500000.123] "GET / HTTP/1.1" 200 "Mozilla/5.0" "-"')
        empty = nginx.parse('192.0.2.1 [1794500000.123] "GET / HTTP/1.1" 200 "Mozilla/5.0" ""')
        self.assertEqual(dash.headers, {"user-agent": "Mozilla/5.0"})
        self.assertEqual(empty.headers, {"user-agent": "Mozilla/5.0"})

    def test_escapes_of_both_servers_and_of_json_mode_are_undone(self):
        nginx = log_formats.from_nginx('$remote_addr [$msec] "$request" $status "$http_user_agent"')
        apache = log_formats.from_apache('%a [%{msec}t] "%r" %>s "%{User-Agent}i"')
        ua = 'Bot "quoted" café\\x \t'
        self.assertEqual(nginx.parse(f'192.0.2.1 [1794500000.123] "GET / HTTP/1.1" 200 "{nginx_escape(ua)}"')
                         .headers["user-agent"], ua)
        self.assertEqual(apache.parse('192.0.2.1 [1794500000123] "GET / HTTP/1.1" 200 '
                                      '"Bot \\"quoted\\" caf\\xc3\\xa9\\\\x \\t"').headers["user-agent"], ua)
        self.assertEqual(nginx.parse('192.0.2.1 [1794500000.123] "GET / HTTP/1.1" 200 '
                                     '"Bot \\"quoted\\" café\\\\x \\u0009"').headers["user-agent"], ua)


    def test_a_json_time_that_is_no_finite_number_is_not_read(self):
        caddy = log_formats.named("caddy-json")
        line, _ = sample("caddy-json")[0]
        for bad in ("NaN", "Infinity", "-Infinity", '"soon"', "true"):
            self.assertIsNone(caddy.parse(re.sub(r'"ts":[^,]+', f'"ts":{bad}', line, count=1)), bad)

    def test_a_field_logged_twice_takes_the_first_value_there_is(self):
        nginx = log_formats.from_nginx('$remote_addr [$msec] "$request" $status "$host" "$http_host" '
                                       '"$http_user_agent"')
        record = nginx.parse('192.0.2.1 [1794500000.123] "GET / HTTP/1.1" 200 "-" "shop.example:8443" "Mozilla/5.0"')
        self.assertEqual(record.host, "shop.example:8443")


class SitesOwnFormats(unittest.TestCase):
    """A site that keeps its own format passes its format string: nginx's log_format, Apache's LogFormat."""

    def test_an_nginx_log_format_directive_pasted_whole(self):
        nginx = log_formats.from_nginx("log_format main '$remote_addr - $remote_user [$time_local] \"$request\" '\n"
                                       "                '$status $body_bytes_sent \"$http_referer\" '\n"
                                       "                '\"$http_user_agent\" \"$http_x_forwarded_for\"';")
        record = nginx.parse('203.0.113.9 - - [12/Nov/2026:19:59:32 -0800] "GET /cart HTTP/2.0" 200 612 "-" '
                             '"Mozilla/5.0 (X11)" "-"')
        self.assertEqual((record.ip, record.t_ms, record.target, record.status),
                         ("203.0.113.9", 1794542372000, "/cart", 200))
        self.assertEqual(record.headers, {"user-agent": "Mozilla/5.0 (X11)"})

    def test_an_apache_logformat_with_status_conditions_and_its_quotes(self):
        apache = log_formats.from_apache(r'LogFormat "%h %l %u %t \"%r\" %>s %b \"%!200,304{Referer}i\" '
                                         r'\"%{User-agent}i\" %D" combinedio')
        record = apache.parse('198.51.100.4 - - [12/Nov/2026:19:59:32 +0100] "GET /?a=1 HTTP/1.1" 304 - "-" '
                              '"Mozilla/5.0" 1534')
        self.assertEqual((record.ip, record.t_ms, record.target, record.status, record.headers),
                         ("198.51.100.4", 1794509972000, "/?a=1", 304, {"user-agent": "Mozilla/5.0"}))

    def test_apache_path_and_query_make_the_target_and_nginx_reads_iso_time(self):
        apache = log_formats.from_apache('%a %{sec}t %m %U%q %H %>s "%{User-Agent}i" "%{Host}i"')
        record = apache.parse('192.0.2.7 1794500000 GET /search?q=x HTTP/1.1 200 "Mozilla/5.0" "shop.example:8443"')
        self.assertEqual((record.method, record.target, record.protocol, record.host, record.t_ms),
                         ("GET", "/search?q=x", "HTTP/1.1", "shop.example:8443", 1794500000000))
        nginx = log_formats.from_nginx('$remote_addr $time_iso8601 "$request" $status "$http_user_agent"')
        record = nginx.parse('192.0.2.7 2026-11-12T19:59:32-08:00 "GET / HTTP/1.1" 200 "Mozilla/5.0"')
        self.assertEqual(record.t_ms, 1794542372000)

    def test_a_format_without_what_matching_needs_is_refused_with_what_it_lacks(self):
        for compile_format, text, lacking in (
                (log_formats.from_nginx, '$remote_addr "$request" $status "$http_user_agent"', "time"),
                (log_formats.from_nginx, '[$msec] "$request" $status "$http_user_agent"', "ip"),
                (log_formats.from_nginx, '$remote_addr [$msec] "$request" $status', "user-agent"),
                (log_formats.from_apache, '%a %t %>s "%{User-Agent}i"', "request"),
                (log_formats.from_apache, '%a %t "%r" "%{User-Agent}i"', "status")):
            with self.subTest(text=text), self.assertRaises(log_formats.FormatError) as caught:
                compile_format(text)
            self.assertIn(lacking, str(caught.exception))


class RecommendedFormats(unittest.TestCase):
    def test_docs_show_the_recommended_config_lines(self):
        for name, spec in SPEC["formats"].items():
            for line in spec.get("config", ()):
                self.assertIn(line, read(DOCS[spec["server"]]), f"{name}: {line}")

    def test_the_config_lines_compile_to_the_recommended_formats(self):
        for name, compile_format in (("nginx-agentcake", log_formats.from_nginx),
                                     ("apache-agentcake", log_formats.from_apache)):
            config = "\n".join(SPEC["formats"][name]["config"][:-1])  # without access_log / CustomLog
            ours = compile_format(config)
            for line, truth in sample(name):
                self.assertEqual(ours.parse(line), log_formats.named(name).parse(line), line)

    def test_what_each_format_lacks_of_the_recommended_fields(self):
        recommended = list(SPEC["recommended"]["fields"])
        self.assertEqual(log_formats.named("combined").missing(), [f for f in recommended if f != "user-agent"])
        for name in ("nginx-agentcake", "apache-agentcake", "caddy-json"):
            self.assertEqual(log_formats.named(name).missing(), [], name)


if __name__ == "__main__":
    unittest.main()
