<?php
/**
 * The PHP site middleware's tests, with a runner of their own: a site's PHP and WordPress Playground have no
 * PHPUnit, and the middleware has no dependencies, so neither do its tests.
 *
 *     php edge/php/tests/run.php          (PHP 7.4 or newer, from the AgentCake folder or anywhere else)
 *
 * Loads every *_test.php file in this folder and runs each function in it whose name starts with test_, in file order.
 * Any PHP warning or notice fails the test it happens in. Prints one line per test and the totals; the exit status is
 * 1 when a test fails. The helpers the test files share are below.
 */

declare(strict_types=1);

namespace AgentCake\Tests;

use AgentCake\Edge;

const REPO = __DIR__ . '/../../..';
const SECRET = 'test-only secret for the PHP middleware, never used elsewhere';
const CLIENT_IP = '203.0.113.77'; // RFC 5737 documentation range: nobody's address

final class Failure extends \Exception
{
}

function check(bool $condition, string $message): void
{
    if (!$condition) {
        throw new Failure($message);
    }
}

function same($expected, $actual, string $message = ''): void
{
    if ($expected !== $actual) {
        $what = 'expected ' . var_export($expected, true) . ', got ' . var_export($actual, true);
        throw new Failure($message === '' ? $what : "$message: $what");
    }
}

function read_json(string $path): array
{
    return json_decode((string) file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
}

function vectors(): array
{
    static $vectors = null;
    return $vectors ?? ($vectors = read_json(REPO . '/tests/vectors/edge_token.json'));
}

/** The vectors' first request: a page typed into Chrome, header lines in Chrome's order. */
function chrome_page(): array
{
    return vectors()['mint'][0]['request']['headers'];
}

function now_ms(): int
{
    return vectors()['mint'][0]['now_ms'];
}

/** Text (UTF-8) as the bytes a server hands PHP for a header line: one byte per character, as Latin-1. */
function latin1(string $text): string
{
    return (string) preg_replace_callback('/[\xC2\xC3][\x80-\xBF]/', function (array $pair): string {
        return chr(((ord($pair[0][0]) & 0x1F) << 6) | (ord($pair[0][1]) & 0x3F));
    }, $text);
}

/** $_SERVER as a SAPI fills it for a request: HTTP_ keys in the order sent, raw bytes, a repeated line joined. */
function server_vars(string $path = '/', ?array $lines = null, string $method = 'GET'): array
{
    $server = ['REQUEST_METHOD' => $method, 'REQUEST_URI' => $path, 'REMOTE_ADDR' => CLIENT_IP, 'SERVER_PROTOCOL' => 'HTTP/1.1'];
    foreach ($lines ?? chrome_page() as [$name, $value]) {
        $key = 'HTTP_' . strtoupper(str_replace('-', '_', $name));
        $value = latin1(trim($value, " \t\r\n"));
        $server[$key] = isset($server[$key]) ? $server[$key] . ', ' . $value : $value;
    }
    return $server;
}

function edge(array $options = []): Edge
{
    return new Edge($options + [
        'secret' => SECRET,
        'now' => function () {
            return now_ms();
        },
        'randomId' => function (): string {
            return 'id-1';
        },
        'clientIp' => function (array $server): ?string {
            return $server['REMOTE_ADDR'] ?? null;
        },
        'warn' => function (string $line): void {
            throw new Failure("unexpected warning: $line");
        },
    ]);
}

/** The payload as anyone reading the response can read it: no secret needed. */
function payload_of(string $token): array
{
    $body = explode('.', $token)[1];
    return json_decode((string) base64_decode(strtr($body, '-_', '+/')), true, 512, JSON_THROW_ON_ERROR);
}

function token_in(string $serverTiming): ?string
{
    return preg_match('/(?:^|,)\s*cake;desc="([^"]*)"/', $serverTiming, $match) === 1 ? $match[1] : null;
}

// ---------------------------------------------------------------- the runner
set_error_handler(function (int $level, string $message, string $file, int $line): bool {
    throw new \ErrorException($message, 0, $level, $file, $line);
});
require_once __DIR__ . '/../cake_edge.php';

$before = get_defined_functions()['user'];
$files = glob(__DIR__ . '/*_test.php') ?: [];
foreach ($files as $file) {
    require_once $file;
}
$tests = array_values(array_filter(array_diff(get_defined_functions()['user'], $before), function (string $name): bool {
    return strpos(substr($name, (int) strrpos($name, '\\') + 1), 'test_') === 0;
}));

echo 'PHP ', PHP_VERSION, ' (', PHP_INT_SIZE * 8, '-bit integers), ', count($tests), " tests\n";
$failed = 0;
foreach ($tests as $number => $test) {
    $label = substr($test, (int) strrpos($test, '\\') + 1);
    try {
        $test();
        echo 'ok ', $number + 1, ' ', $label, "\n";
    } catch (\Throwable $error) {
        $failed++;
        $where = $error instanceof Failure ? '' : ' (' . get_class($error) . ' at ' . basename($error->getFile()) . ':' . $error->getLine() . ')';
        echo 'not ok ', $number + 1, ' ', $label, "\n    # ", $error->getMessage(), $where, "\n";
    }
}
echo count($tests) - $failed, ' passed, ', $failed, " failed\n";
exit($failed === 0 && $tests !== [] ? 0 : 1);
