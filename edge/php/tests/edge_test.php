<?php
/**
 * What the PHP middleware does with a request and a response, as edge/node/test/express.test.js and
 * tests/test_edge_python.py check it for Node and Python: one token for each page and nothing for anything else, the
 * facts the browser sent, a secret that must be there and long enough, the site's options, and the response head
 * (Edge::headersFor, which sendHeader() applies with header()): the site's own Server-Timing kept, an inherited cake
 * entry replaced, noStore for HTML only.
 */

declare(strict_types=1);

namespace AgentCake\Tests;

use AgentCake\Edge;
use AgentCake\EdgeFormat;

function with_line(array $lines, string $name, ?string $value): array
{
    $out = [];
    foreach ($lines as [$lineName, $lineValue]) {
        if (strtolower($lineName) !== strtolower($name)) {
            $out[] = [$lineName, $lineValue];
        }
    }
    return $value === null ? $out : array_merge($out, [[$name, $value]]);
}

function collect_warnings(array &$lines): \Closure
{
    return function (string $line) use (&$lines): void {
        $lines[] = $line;
    };
}

function test_a_page_gets_a_token_with_the_facts_the_browser_sent(): void
{
    $token = edge()->tokenForRequest(server_vars('/products/cake?ref=home'));
    $payload = payload_of((string) $token);
    same(['s' => 'none', 'm' => 'navigate', 'd' => 'document', 'u' => '?1'], $payload['sf']);
    same('/products/cake', $payload['p'], 'the path without its query');
    same(array_map('strtolower', array_column(chrome_page(), 0)), $payload['hn'], 'the header names in the order sent');
    same(EdgeFormat::networkKey(SECRET, CLIENT_IP, now_ms()), $payload['ik']);
}

function test_getallheaders_keeps_the_names_as_sent_which_server_variables_cannot(): void
{
    $lines = [['Host', 'shop.example'], ['Sec-Fetch-Dest', 'document'], ['X_Under_Score', '1'], ['Accept', 'text/html']];
    $headers = [];
    foreach ($lines as [$name, $value]) {
        $headers[$name] = $value;
    }
    same(['host', 'sec-fetch-dest', 'accept'], payload_of((string) edge()->tokenForRequest(server_vars('/', []), $headers))['hn'],
        'a name with "_" is not a header name the token lists, as on Node');
    same(['host', 'sec-fetch-dest', 'x-under-score', 'accept'], payload_of((string) edge()->tokenForRequest(server_vars('/', $lines)))['hn'],
        'from $_SERVER, "_" and "-" read the same');
}

function test_raw_header_bytes_are_read_one_character_per_byte_as_node_and_python_read_them(): void
{
    $server = server_vars('/', with_line(chrome_page(), 'Accept-Language', 'caf' . "\u{e9}"));
    same("caf\xe9", $server['HTTP_ACCEPT_LANGUAGE'], 'the server hands over the byte');
    same("caf\u{e9}", payload_of((string) edge()->tokenForRequest($server))['al']);
    $utf8 = server_vars('/', chrome_page());
    $utf8['HTTP_ACCEPT_LANGUAGE'] = "caf\u{e9}"; // two bytes sent: two characters, as Node's HTTP parser reads them
    same("caf\u{c3}\u{a9}", payload_of((string) edge()->tokenForRequest($utf8))['al']);
}

function test_a_static_file_a_frame_a_post_a_head_a_dot_file_and_a_client_not_asking_for_html_get_nothing(): void
{
    $notHtml = with_line(with_line(chrome_page(), 'Sec-Fetch-Dest', null), 'Accept', 'application/json');
    $cases = [
        'a static file' => server_vars('/logo.png'), 'a POST' => server_vars('/', null, 'POST'),
        'a HEAD' => server_vars('/', null, 'HEAD'), 'a dot-file' => server_vars('/.well-known/security.txt'),
        'a frame' => server_vars('/', with_line(chrome_page(), 'Sec-Fetch-Dest', 'iframe')),
        'not asking for HTML' => server_vars('/', $notHtml),
    ];
    foreach ($cases as $why => $server) {
        same(null, edge()->tokenForRequest($server), $why);
    }
    $safari = with_line(chrome_page(), 'Sec-Fetch-Dest', null);
    check(edge()->tokenForRequest(server_vars('/', $safari)) !== null, 'no fetch metadata, accepts text/html: a page');
}

function test_no_secret_or_a_short_one_gets_nothing_and_a_short_one_is_named_once(): void
{
    $warnings = [];
    $off = edge(['secret' => null, 'secretEnv' => 'CAKE_TEST_UNSET_VARIABLE', 'warn' => collect_warnings($warnings)]);
    same([false, null, []], [$off->enabled(), $off->tokenForRequest(server_vars()), $warnings]);
    $short = str_repeat('x', EdgeFormat::settings()['fixed']['min_secret_bytes'] - 1);
    $edge = edge(['secret' => $short, 'warn' => collect_warnings($warnings)]);
    foreach ([1, 2, 3] as $visit) {
        same(null, $edge->tokenForRequest(server_vars()), "visit $visit");
    }
    same(1, count($warnings));
    check(strpos($warnings[0], $short) === false, 'the secret is never part of a message');
}

function test_the_secret_can_come_from_the_environment_variable_named_in_the_settings(): void
{
    $name = EdgeFormat::settings()['options']['secret_env'];
    $saved = getenv($name);
    putenv("$name=" . SECRET);
    try {
        $token = edge(['secret' => null])->tokenForRequest(server_vars());
    } finally {
        putenv($saved === false ? $name : "$name=$saved");
    }
    same(Edge::mintToken(SECRET, 'GET', '/', chrome_page(), now_ms(), 'id-1', CLIENT_IP), $token);
}

function test_a_site_can_change_the_options_and_a_mistake_is_named_once_and_ignored(): void
{
    $edge = edge(['cut' => ['user_agent' => 10], 'maxHeaderNames' => 2, 'skipExtensions' => ['.html']]);
    $payload = payload_of((string) $edge->tokenForRequest(server_vars('/about')));
    same([10, ['host', 'connection']], [strlen($payload['ua']), $payload['hn']]);
    same(null, $edge->tokenForRequest(server_vars('/about.HTML')));
    $warnings = [];
    $mistaken = edge(['nostore' => true, 'maxHeaderNames' => '40', 'cut' => ['user_agent' => -1], 'warn' => collect_warnings($warnings)]);
    same(2, count($warnings));
    check(strpos($warnings[0], 'nostore') !== false && strpos($warnings[1], 'maxHeaderNames, cut') !== false, implode(' | ', $warnings));
    same(count(chrome_page()), count(payload_of((string) $mistaken->tokenForRequest(server_vars()))['hn']), 'the default kept');
}

function test_a_client_ip_that_fails_costs_the_network_key_never_the_token(): void
{
    $warnings = [];
    $edge = edge(['clientIp' => function (): string {
        throw new \RuntimeException('no proxy header');
    }, 'warn' => collect_warnings($warnings)]);
    same(null, payload_of((string) $edge->tokenForRequest(server_vars()))['ik']);
    same(1, count($warnings));
}

function test_the_token_holds_no_ip_cookie_or_authorization(): void
{
    $lines = array_merge(chrome_page(), [['Cookie', 'session=s3cr3t'], ['Authorization', 'Bearer abc123']]);
    $text = json_encode(payload_of((string) edge()->tokenForRequest(server_vars('/', $lines))));
    foreach ([CLIENT_IP, '203.0.113', 's3cr3t', 'abc123', SECRET] as $kept) {
        check(strpos((string) $text, $kept) === false, "the token holds $kept");
    }
}

function test_server_timing_keeps_the_sites_entries_and_replaces_an_inherited_cake_entry(): void
{
    $head = Edge::headersFor(['Server-Timing: db;dur=53, cake;desc="c1.old.old"', 'server-timing: app;dur=2',
        'Content-Type: text/html; charset=UTF-8'], 'c1.new.new', false, 'text/html');
    same([['server-timing', 'db;dur=53, app;dur=2, cake;desc="c1.new.new"']], $head);
    same([['server-timing', 'cake;desc="t"']], Edge::headersFor([], 't', false, 'text/html'));
}

function test_no_store_makes_html_private_and_unstored_and_leaves_every_other_type_alone(): void
{
    $noStore = EdgeFormat::settings()['fixed']['no_store_value'];
    same(['cache-control', $noStore], Edge::headersFor(['Content-Type: text/html'], 't', true, 'text/plain')[1]);
    same(['cache-control', $noStore], Edge::headersFor([], 't', true, 'text/html')[1], "PHP's default type");
    same(1, count(Edge::headersFor(['Content-Type: application/json'], 't', true, 'text/html')));
    same(1, count(Edge::headersFor(['Content-Type: text/html'], 't', false, 'text/html')), 'left alone by default');
}
