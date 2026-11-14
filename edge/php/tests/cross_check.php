<?php
/**
 * PHP's half of a cross-language check, as edge/node/scripts/cross-check.js is Node's: reads a JSON list of
 * requests on stdin ({secret, request: {method, path, headers}, now_ms, id, client_ip, verdict, version}) and prints the
 * JSON list of the tokens PHP makes for them (null: no token). Whoever runs it compares them with another
 * implementation's, e.g. the 300 random requests of tests/test_edge_vectors.py against agentcake/edge_token.py's mint().
 *
 *     php edge/php/tests/cross_check.php < cases.json > tokens.json
 */

declare(strict_types=1);

require_once __DIR__ . '/../cake_edge.php';

$cases = json_decode((string) stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
$tokens = [];
foreach ($cases as $case) {
    $request = $case['request'];
    $lines = array_map(function (array $line): array {
        return [(string) $line[0], (string) $line[1]];
    }, $request['headers']);
    $tokens[] = \AgentCake\Edge::mintToken($case['secret'], $request['method'], $request['path'], $lines, $case['now_ms'],
        $case['id'], $case['client_ip'], $case['verdict'], $case['version']);
}
echo json_encode($tokens, JSON_UNESCAPED_SLASHES), "\n";
