<?php
/**
 * A two-page site for trying the PHP middleware in a real browser, the same pages as
 * edge/node/scripts/test-site.js: a home page and a second page that link to each other, each showing the token its own
 * navigation entry carries in Server-Timing (what cake.js reads): its id and the four Sec-Fetch values inside it. Pages
 * go out with Cache-Control: no-cache and an ETag, so opening one again is a 304, unless CAKE_NO_STORE=1 turns on the
 * middleware's noStore. A router script for PHP's built-in server:
 *
 *     CAKE_SERVER_TIMING_SECRET=<secret> php -S 127.0.0.1:8123 edge/php/example.php
 */

declare(strict_types=1);

require __DIR__ . '/cake_edge.php';

const PAGES = [
    '/' => ['title' => 'Test shop', 'link' => '/next', 'label' => 'Next page'],
    '/next' => ['title' => 'Second page', 'link' => '/', 'label' => 'Home'],
];

// The page reads its own navigation entry, as cake.js does, and shows the token's id and Sec-Fetch values.
const READER = <<<'JS'
const entry = performance.getEntriesByType("navigation")[0]
const cake = (entry.serverTiming || []).find((each) => each.name === "cake")
const out = document.getElementById("cake")
if (!cake) out.textContent = "No cake entry in this page's Server-Timing."
else {
  const body = atob(cake.description.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
  const payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(body, (char) => char.charCodeAt(0))))
  out.textContent = "token " + payload.id + " · Sec-Fetch site " + payload.sf.s + ", mode " + payload.sf.m + ", dest " + payload.sf.d + ", user " + payload.sf.u
}
JS;

$path = (string) strtok($_SERVER['REQUEST_URI'] ?? '/', '?');
$page = PAGES[$path] ?? null;
if ($page === null) {
    http_response_code(404);
    header('Content-Type: text/plain');
    echo "not found\n";
    return;
}

$body = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>' . $page['title'] . '</title></head>'
    . "\n<body><h1>" . $page['title'] . '</h1><p><a id="link" href="' . $page['link'] . '">' . $page['label'] . '</a></p>'
    . '<p id="cake"></p><script>' . READER . "</script></body></html>\n";
$etag = '"' . rtrim(strtr(base64_encode(hash('sha256', $body, true)), '+/', '-_'), '=') . '"';
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-cache');
header('ETag: ' . $etag);

// After the page's own headers, so noStore has the last word on Cache-Control; before any output.
(new \AgentCake\Edge([
    'noStore' => getenv('CAKE_NO_STORE') === '1',
    'clientIp' => function (array $server): ?string {
        return $server['REMOTE_ADDR'] ?? null;
    },
]))->sendHeader();

if (($_SERVER['HTTP_IF_NONE_MATCH'] ?? '') === $etag) {
    http_response_code(304);
    return;
}
echo $body;
