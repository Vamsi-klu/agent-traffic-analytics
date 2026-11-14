<?php
/**
 * AgentCake site middleware for PHP, the server half (step S4.3). On each page response it sets one signed token, byte
 * for byte what the Node middleware (edge/node) makes for the same request:
 *
 *     Server-Timing: cake;desc="c1.<base64url JSON>.<base64url HMAC-SHA256>"
 *
 * cake.js reads it from the page's navigation entry and hands it to AgentCake with the visit, so cake learns what only
 * the site's server saw about the page request: the fetch metadata of the very first page, and the Web Bot Auth headers
 * as sent (AgentCake verifies the signature; this file does not). Mount it before the page's first output:
 *
 *     require __DIR__ . '/cake_edge.php';
 *     (new \AgentCake\Edge())->sendHeader();
 *
 * This file is the mounting: options, the secret, reading the request a SAPI hands over, the response head. The token's
 * format is in cake_edge_format.php beside it, the values in cake_edge.json; the AgentCake WordPress plugin
 * (edge/wordpress/agentcake) carries all three. PHP 7.4 or newer with only its always-on parts (hash, json, pcre,
 * random_bytes). It sets no cookie, stores nothing, makes no network request, and does nothing without a secret of at
 * least 32 bytes. Held to tests/vectors/edge_token.json by edge/php/tests. Splitting Server-Timing into entries follows
 * botscent (src/server/timing.ts, commit 7f948003, MIT) as edge/node/lib/timing.js does. Part of AgentCake, MIT licence.
 */

declare(strict_types=1);

namespace AgentCake;

require_once __DIR__ . '/cake_edge_format.php';

if (!\class_exists(Edge::class, false)) {
    /**
     * new Edge($options): secret (default: the CAKE_SERVER_TIMING_SECRET environment variable), clientIp(array $server)
     * (the visitor's address as the site knows it; without it the token has no network key), noStore, maxHeaderNames,
     * cut, skipExtensions, secretEnv (cake_edge.json, "options"), and now / randomId / warn for tests and logs.
     */
    final class Edge
    {
        /** The camelCase option a site passes, and its key under "options" in cake_edge.json. */
        private const OPTIONS = ['secretEnv' => 'secret_env', 'noStore' => 'no_store', 'maxHeaderNames' => 'max_header_names',
            'cut' => 'cut', 'skipExtensions' => 'skip_extensions'];
        private const WIRING = ['secret', 'clientIp', 'now', 'randomId', 'warn'];
        // The one message that cannot come from the settings, since it says they could not be read.
        private const NO_SETTINGS = '[agentcake] cake_edge.json could not be read beside cake_edge.php: no token is sent';
        private const SERVER_HEADER = 'HTTP_'; // protocol: CGI request header keys in $_SERVER
        private const MS_PER_S = 1000; // protocol

        private array $chosen = [];
        private ?string $key = null;
        private array $said = [];
        /** @var callable|null */
        private $clientIp = null;
        /** @var callable */
        private $now;
        /** @var callable */
        private $randomId;
        /** @var callable */
        private $warn;

        public function __construct(array $options = [])
        {
            $this->warn = self::hook($options, 'warn') ?? function (string $line): void {
                error_log($line);
            };
            try {
                $settings = EdgeFormat::settings();
            } catch (\Throwable $error) { // a mistake in the setup must cost the site its token, never its pages
                ($this->warn)(self::NO_SETTINGS);
                return;
            }
            $this->chosen = $this->choose($settings['options'], $options);
            $given = $options['secret'] ?? self::environment($this->chosen['secret_env']);
            $this->key = self::secretBytes($given);
            if (is_string($given) && $given !== '' && $this->key === null) {
                $this->say('short_secret', ['min' => $settings['fixed']['min_secret_bytes']]);
            }
            $this->clientIp = self::hook($options, 'clientIp');
            $this->now = self::hook($options, 'now') ?? function () {
                return self::nowMs();
            };
            $this->randomId = self::hook($options, 'randomId') ?? function () use ($settings): string {
                return EdgeFormat::b64url(random_bytes($settings['fixed']['token_id_bytes']));
            };
        }

        public function enabled(): bool
        {
            return $this->key !== null;
        }

        /**
         * Sets this request's token in Server-Timing if it is a page, keeping the Server-Timing entries already set, and
         * under noStore makes an HTML response private and unstored. Call it before any output. Returns the token or null.
         */
        public function sendHeader(?array $server = null): ?string
        {
            if ($this->key === null) {
                return null;
            }
            if (headers_sent()) {
                $this->say('headers_sent', []);
                return null;
            }
            $token = $this->tokenForRequest($server);
            if ($token === null) {
                return null;
            }
            try {
                $head = self::headersFor(headers_list(), $token, $this->chosen['no_store'], (string) ini_get('default_mimetype'));
                header_remove($head[0][0]);
                foreach ($head as [$name, $value]) {
                    header("$name: $value");
                }
            } catch (\Throwable $error) { // the server half must never break a page
                $this->say('head_failed', ['error' => get_class($error)]);
            }
            return $token;
        }

        /**
         * The token for the request in $server (default: this one, with getallheaders() where the SAPI has it, which keeps
         * the names as sent), or null: not a page, no secret, or a request that cannot be read. $headers: name => value.
         */
        public function tokenForRequest(?array $server = null, ?array $headers = null): ?string
        {
            if ($this->key === null) {
                return null;
            }
            if ($server === null) {
                $server = $_SERVER;
                $headers = $headers ?? (function_exists('getallheaders') ? (getallheaders() ?: null) : null);
            }
            try {
                $request = EdgeFormat::request(...self::requestOf($server, $headers));
                if (!EdgeFormat::isPage($request, $this->chosen)) {
                    return null;
                }
                return EdgeFormat::mint($this->key, $request, ($this->now)(), ($this->randomId)(), $this->address($server), null, null, $this->chosen);
            } catch (\Throwable $error) { // the server half must never break a page: a token that cannot be made is not sent
                $this->say('token_failed', ['error' => get_class($error)]);
                return null;
            }
        }

        /** The token for a request given as text, with everything that varies given, or null: what the vectors check. */
        public static function mintToken($secret, string $method, string $target, array $lines, $nowMs, string $id,
                                         ?string $ip = null, $verdict = null, $version = null, array $options = []): ?string
        {
            if (self::secretBytes($secret) === null) {
                return null;
            }
            $edge = new self(['secret' => $secret] + $options);
            $request = EdgeFormat::request($method, $target, $lines);
            return EdgeFormat::isPage($request, $edge->chosen) ? EdgeFormat::mint($edge->key, $request, $nowMs, $id, $ip, $verdict, $version, $edge->chosen) : null;
        }

        /**
         * The header lines to set, [[name, value], ...], given the ones set so far ("Name: value", as headers_list()
         * gives them): one Server-Timing with the site's own entries and this token's, and, under noStore, Cache-Control
         * for an HTML response ($defaultType: the type PHP sends when none was set).
         */
        public static function headersFor(array $lines, string $token, bool $noStore, string $defaultType): array
        {
            [$names, $fixed] = [EdgeFormat::settings()['headers'], EdgeFormat::settings()['fixed']];
            $timing = [];
            $type = $defaultType;
            foreach ($lines as $line) {
                $parts = array_map('trim', explode(':', (string) $line, 2));
                $name = EdgeFormat::lower($parts[0]);
                if (count($parts) === 2 && $name === $names['server_timing']) {
                    $timing[] = $parts[1];
                } elseif (count($parts) === 2 && $name === $names['content_type']) {
                    $type = $parts[1];
                }
            }
            $head = [[$names['server_timing'], self::withCakeEntry($timing, $token)]];
            $html = in_array(EdgeFormat::lower(trim(explode(';', $type)[0])), $fixed['html_types'], true);
            return $noStore && $html ? array_merge($head, [[$names['cache_control'], $fixed['no_store_value']]]) : $head;
        }

        /**
         * One Server-Timing value from the header's values so far: the site's own entries, any cake entry (a proxy's, a
         * second copy of the middleware's, a stored response's) dropped, and this token's entry last.
         */
        public static function withCakeEntry(array $values, string $token): string
        {
            $name = EdgeFormat::settings()['fixed']['entry_name'];
            $kept = [];
            foreach ($values as $value) {
                foreach (self::entries((string) $value) as $entry) {
                    if (EdgeFormat::lower(trim(explode(';', $entry, 2)[0])) !== $name) {
                        $kept[] = $entry;
                    }
                }
            }
            $kept[] = $name . ';desc="' . $token . '"';
            return implode(', ', $kept);
        }

        /** [method, target, lines] as the SAPI hands them over, the header bytes read one character per byte, as Node reads them. */
        private static function requestOf(array $server, ?array $headers): array
        {
            $lines = [];
            foreach ($headers ?? $server as $name => $value) {
                $name = (string) $name;
                if ($headers === null && strncmp($name, self::SERVER_HEADER, strlen(self::SERVER_HEADER)) !== 0) {
                    continue;
                }
                $name = $headers === null ? str_replace('_', '-', substr($name, strlen(self::SERVER_HEADER))) : $name;
                $lines[] = [self::latin1($name), self::latin1((string) $value)];
            }
            return [(string) ($server['REQUEST_METHOD'] ?? 'GET'), self::latin1((string) ($server['REQUEST_URI'] ?? '/')), $lines];
        }

        /** A Server-Timing value split into its entries at the commas outside quoted strings. */
        private static function entries(string $value): array
        {
            $entries = [];
            $start = 0;
            $quoted = false;
            for ($i = 0, $length = strlen($value); $i < $length; $i++) {
                if ($quoted && $value[$i] === '\\') {
                    $i++;
                } elseif ($value[$i] === '"') {
                    $quoted = !$quoted;
                } elseif ($value[$i] === ',' && !$quoted) {
                    $entries[] = substr($value, $start, $i - $start);
                    $start = $i + 1;
                }
            }
            $entries[] = (string) substr($value, $start);
            return array_values(array_filter(array_map('trim', $entries), 'strlen'));
        }

        /** The "options" values with the site's choices on top; an unknown option or a value of the wrong kind is named once and ignored. */
        private function choose(array $defaults, array $options): array
        {
            $chosen = $defaults;
            $unknown = [];
            $invalid = [];
            foreach ($options as $name => $value) {
                if (in_array($name, self::WIRING, true) || $value === null) {
                    continue;
                }
                $key = self::OPTIONS[$name] ?? null;
                if ($key === null) {
                    $unknown[] = $name;
                } elseif (!self::isRightKind($key, $value, $defaults['cut'])) {
                    $invalid[] = $name;
                } else {
                    $chosen[$key] = $key === 'cut' ? array_merge($chosen['cut'], $value) : $value;
                }
            }
            $chosen['skip_extensions'] = array_map(function (string $extension): string {
                return EdgeFormat::lower($extension);
            }, $chosen['skip_extensions']);
            foreach (['unknown_options' => $unknown, 'invalid_options' => $invalid] as $message => $names) {
                if ($names !== []) {
                    $this->say($message, ['names' => implode(', ', $names)]);
                }
            }
            return $chosen;
        }

        private static function isRightKind(string $key, $value, array $cut): bool
        {
            switch ($key) {
                case 'secret_env':
                    return is_string($value) && $value !== '';
                case 'no_store':
                    return is_bool($value);
                case 'max_header_names':
                    return is_int($value) && $value >= 0;
                case 'cut':
                    return is_array($value) && array_filter($value, function ($length, $field) use ($cut): bool {
                        return array_key_exists($field, $cut) && is_int($length) && $length > 0;
                    }, ARRAY_FILTER_USE_BOTH) === $value;
                default: // skip_extensions
                    return is_array($value) && array_filter($value, 'is_string') === $value;
            }
        }

        /** Says each distinct warning once per request, by its kind only: never with the secret in it. */
        private function say(string $key, array $values): void
        {
            $line = EdgeFormat::settings()['messages'][$key];
            foreach ($values as $name => $value) {
                $line = str_replace('{' . $name . '}', (string) $value, $line);
            }
            if (!isset($this->said[$line])) {
                $this->said[$line] = true;
                ($this->warn)($line);
            }
        }

        private function address(array $server): ?string
        {
            if ($this->clientIp === null) {
                return null;
            }
            try {
                $ip = ($this->clientIp)($server);
            } catch (\Throwable $error) { // the site's own code: whatever it throws costs the network key, never the page
                $this->say('client_ip_failed', ['error' => get_class($error)]);
                return null;
            }
            return is_string($ip) ? $ip : null;
        }

        private static function hook(array $options, string $name): ?callable
        {
            return isset($options[$name]) && is_callable($options[$name]) ? $options[$name] : null;
        }

        private static function environment(string $name): ?string
        {
            $value = getenv($name);
            if (is_string($value) && $value !== '') {
                return $value;
            }
            return isset($_SERVER[$name]) && is_string($_SERVER[$name]) ? $_SERVER[$name] : null;
        }

        private static function secretBytes($secret): ?string
        {
            return is_string($secret) && strlen($secret) >= EdgeFormat::settings()['fixed']['min_secret_bytes'] ? $secret : null;
        }

        /** Milliseconds since 1970: an integer, or on a 32-bit PHP a float, which holds them exactly. */
        private static function nowMs()
        {
            $ms = floor(microtime(true) * self::MS_PER_S);
            return PHP_INT_SIZE >= 8 ? (int) $ms : $ms;
        }

        private static function latin1(string $bytes): string
        {
            return (string) preg_replace_callback('/[\x80-\xff]/', function (array $byte): string {
                return chr(0xc0 | (ord($byte[0]) >> 6)) . chr(0x80 | (ord($byte[0]) & 0x3f)); // protocol: UTF-8 of U+0080..U+00FF
            }, $bytes);
        }
    }
}
