<?php
/**
 * The shared vectors (tests/vectors/edge_token.json), which the Node middleware, the Python middleware and AgentCake
 * check too: every mint vector's token byte for byte, from the vector's request as text (Edge::mintToken) and from the
 * same request as a SAPI hands it to PHP ($_SERVER's raw bytes, or getallheaders()); every network key vector.
 */

declare(strict_types=1);

namespace AgentCake\Tests;

use AgentCake\Edge;
use AgentCake\EdgeFormat;

function vector_secret(array $vector): string
{
    return vectors()['secrets'][$vector['secret']];
}

/** A vector whose request names a header twice: a SAPI merges the two lines into one $_SERVER key. */
function repeats_a_header(array $vector): bool
{
    $names = array_map('strtolower', array_column($vector['request']['headers'], 0));
    return count(array_unique($names)) < count($names);
}

function vector_edge(array $vector): Edge
{
    return new Edge([
        'secret' => vector_secret($vector),
        'now' => function () use ($vector) {
            return $vector['now_ms'];
        },
        'randomId' => function () use ($vector): string {
            return $vector['id'];
        },
        'clientIp' => function () use ($vector): ?string {
            return $vector['client_ip'];
        },
        'warn' => function (string $line): void {
            throw new Failure("unexpected warning: $line");
        },
    ]);
}

function test_every_mint_vector_makes_its_token_byte_for_byte(): void
{
    foreach (vectors()['mint'] as $v) {
        $r = $v['request'];
        $token = Edge::mintToken(vector_secret($v), $r['method'], $r['path'], $r['headers'], $v['now_ms'], $v['id'],
            $v['client_ip'], $v['verdict'], $v['version']);
        same($v['token'], $token, $v['name']);
        if ($token !== null) {
            same($v['payload'], payload_of($token), $v['name']);
        }
    }
}

function test_a_time_held_as_a_float_by_a_32_bit_php_makes_the_same_token(): void
{
    $v = vectors()['mint'][0];
    $r = $v['request'];
    same($v['token'], Edge::mintToken(vector_secret($v), $r['method'], $r['path'], $r['headers'], (float) $v['now_ms'],
        $v['id'], $v['client_ip']));
}

function test_every_network_key_vector_gives_its_prefix_and_key(): void
{
    foreach (vectors()['network_keys'] as $v) {
        same($v['prefix'], EdgeFormat::ipPrefix($v['ip']), $v['name']);
        same($v['key'], EdgeFormat::networkKey(vector_secret($v), $v['ip'], $v['now_ms']), $v['name']);
    }
}

function test_every_vector_as_server_variables_gets_its_token(): void
{
    foreach (vectors()['mint'] as $v) {
        if ($v['verdict'] !== null || repeats_a_header($v)) {
            continue; // botscent is a JavaScript library: no verdict from PHP. A repeated line: the next test.
        }
        $r = $v['request'];
        same($v['token'], vector_edge($v)->tokenForRequest(server_vars($r['path'], $r['headers'], $r['method'])), $v['name']);
    }
}

function test_every_vector_as_getallheaders_lines_gets_its_token(): void
{
    foreach (vectors()['mint'] as $v) {
        if ($v['verdict'] !== null || repeats_a_header($v)) {
            continue;
        }
        $r = $v['request'];
        $headers = [];
        foreach ($r['headers'] as [$name, $value]) {
            $headers[$name] = latin1($value);
        }
        same($v['token'], vector_edge($v)->tokenForRequest(server_vars($r['path'], [], $r['method']), $headers), $v['name']);
    }
}

function test_a_repeated_line_merged_by_the_server_is_named_once_and_otherwise_the_same(): void
{
    foreach (vectors()['mint'] as $v) {
        if (!repeats_a_header($v)) {
            continue;
        }
        $r = $v['request'];
        $expected = $v['payload'];
        $expected['hn'] = array_values(array_unique($expected['hn']));
        check(count($expected['hn']) < count($v['payload']['hn']), 'the vector repeats a name');
        same($expected, payload_of((string) vector_edge($v)->tokenForRequest(server_vars($r['path'], $r['headers']))), $v['name']);
    }
}
