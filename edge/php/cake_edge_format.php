<?php
/**
 * The token's format for the PHP site middleware: which requests get a token, the facts it holds, the JSON
 * the MAC covers, the network key. What tests/vectors/edge_token.json pins, byte for byte the Node middleware's
 * (edge/node/lib/facts.js, mint.js, token.js, netkey.js). cake_edge.php loads this file and does the mounting.
 *
 *     c1.<base64url of the payload's JSON>.<base64url HMAC-SHA256(secret, "c1." + the middle part)>
 *
 * Request text here is UTF-8: cake_edge.php reads a SAPI's header bytes one character per byte, as Node does. Case
 * changes are ASCII only, so they never depend on the locale. Part of AgentCake, MIT licence.
 */

declare(strict_types=1);

namespace AgentCake;

if (!\class_exists(EdgeFormat::class, false)) {
    final class EdgeFormat
    {
        private const JSON_FLAGS = JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_LINE_TERMINATORS; // protocol: JSON.stringify's spelling
        private const CONTROL = '/[\x00-\x1f\x7f]/';
        private const HEADER_NAME = '/\A[a-z0-9-]+\z/';
        private const IDENTIFIER = '/\A[a-z0-9][a-z0-9._-]*\z/i';
        private const VERSION = '/\A[0-9A-Za-z.+-]+\z/';
        private const ABSOLUTE_FORM = '~\A[a-z][a-z0-9+.-]*://[^/?#]*~i'; // "https://shop.example" before a full URL's path
        private const DECIMAL_OCTET = '/\A(?:0|[1-9][0-9]{0,2})\z/';
        private const HEXTET = '/\A[0-9A-Fa-f]{1,4}\z/';
        private const EDGE_WHITESPACE = " \t\r\n"; // protocol: what Fetch's Headers trims from a header value
        private const OWS = " \t"; // protocol: HTTP's optional whitespace
        private const ASCII_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'; // protocol
        private const ASCII_LOWER = 'abcdefghijklmnopqrstuvwxyz'; // protocol
        private const MS_PER_S = 1000; // protocol
        private const IPV4_OCTETS = 4; // protocol: an IPv4 address
        private const OCTET_MAX = 255; // protocol
        private const OCTET_BITS = 8; // protocol
        private const OCTET_MASK = 0xff; // protocol
        private const HEXTETS = 8; // protocol: an IPv6 address
        private const HEXTET_BITS = 16; // protocol
        private const MIN_IPV6_PARTS = 3; // protocol: "::" alone splits into three parts
        private const MAPPED_AT = 5; // protocol: ::ffff:a.b.c.d is five zero groups, ffff, then the IPv4 address (RFC 4291 2.5.5.2)
        private const MAPPED_HEXTET = 0xffff; // protocol

        /** @var array|null cake_edge.json, read once */
        private static $loaded = null;

        public static function settings(): array
        {
            return self::$loaded ?? (self::$loaded = json_decode((string) file_get_contents(__DIR__ . '/cake_edge.json'), true, 512, JSON_THROW_ON_ERROR));
        }

        /** [method, path, values by lower-case name, names in order]: repeated lines joined with ", ", values trimmed, as Fetch reads them. */
        public static function request(string $method, string $target, array $lines): array
        {
            $values = [];
            $names = [];
            foreach ($lines as [$name, $value]) {
                $name = self::lower((string) $name);
                $value = trim((string) $value, self::EDGE_WHITESPACE);
                $values[$name] = isset($values[$name]) ? $values[$name] . ', ' . $value : $value;
                $names[] = $name;
            }
            // The path as sent, without the query: no URL parsing, since a browser sends its paths resolved already.
            $path = preg_split('/[?#]/', (string) preg_replace(self::ABSOLUTE_FORM, '', $target, 1), 2)[0];
            return [strtr($method, self::ASCII_LOWER, self::ASCII_UPPER), $path === '' ? '/' : $path, $values, $names];
        }

        /**
         * A GET of a top-level document: Sec-Fetch-Dest document, or, from a client that sends no fetch metadata, a GET
         * accepting text/html. Never a static file (by extension) or a dot-file. A prefetch or prerender counts: the
         * browser shows that very response if the visitor goes to the page, and its Sec-Purpose says so.
         */
        public static function isPage(array $request, array $chosen): bool
        {
            [$method, $path, $values] = $request;
            [$fixed, $headers] = [self::settings()['fixed'], self::settings()['headers']];
            if ($method !== $fixed['page_method']) {
                return false;
            }
            $dest = $values[$headers['sec_fetch_dest']] ?? null;
            $lower = self::lower($path);
            foreach (explode('/', $lower) as $segment) {
                if ($segment !== '' && $segment[0] === '.') {
                    return false;
                }
            }
            foreach ($chosen['skip_extensions'] as $extension) {
                if ($extension === '' || substr($lower, -strlen($extension)) === $extension) {
                    return false;
                }
            }
            return $dest !== null ? self::lower($dest) === $fixed['page_dest'] : self::accepts($values, $fixed['page_type']);
        }

        /** The token: the facts of a request that isPage() took, its id and time, the network key, botscent's verdict. */
        public static function mint(string $key, array $request, $nowMs, string $id, ?string $ip, $verdict, $version, array $chosen): string
        {
            $fixed = self::settings()['fixed'];
            $payload = ['v' => $fixed['payload_version'], 'id' => $id, 't' => $nowMs] + self::facts($request, $chosen)
                + ['ik' => self::networkKey($key, $ip, $nowMs), 'bs' => self::verdictFields($verdict),
                    'bsv' => self::short($version, $fixed['version_max'], self::VERSION)];
            $signed = $fixed['token_prefix'] . '.' . self::b64url(self::json($payload));
            return $signed . '.' . self::b64url(hash_hmac('sha256', $signed, $key, true));
        }

        /** "203.0.113.0/24" or "2001:db8:0::/48" by the rules of Python's ipaddress (an IPv4-mapped address as its IPv4), else null. */
        public static function ipPrefix($ip): ?string
        {
            if (!is_string($ip)) {
                return null;
            }
            $fixed = self::settings()['fixed'];
            $octets = self::ipv4(trim($ip));
            $groups = $octets === null ? self::ipv6(trim($ip)) : null;
            if ($groups !== null && array_slice($groups, 0, self::MAPPED_AT) === array_fill(0, self::MAPPED_AT, 0) && $groups[self::MAPPED_AT] === self::MAPPED_HEXTET) {
                [$high, $low] = array_slice($groups, self::MAPPED_AT + 1);
                $octets = [$high >> self::OCTET_BITS, $high & self::OCTET_MASK, $low >> self::OCTET_BITS, $low & self::OCTET_MASK];
            }
            if ($octets !== null) {
                $kept = intdiv($fixed['ipv4_prefix_bits'], self::OCTET_BITS);
                return implode('.', array_merge(array_slice($octets, 0, $kept), array_fill(0, self::IPV4_OCTETS - $kept, 0))) . '/' . $fixed['ipv4_prefix_bits'];
            }
            if ($groups === null) {
                return null;
            }
            $kept = array_slice($groups, 0, intdiv($fixed['ipv6_prefix_bits'], self::HEXTET_BITS));
            return implode(':', array_map('dechex', $kept)) . '::/' . $fixed['ipv6_prefix_bits'];
        }

        /**
         * The first 16 hex characters of HMAC-SHA256(secret, "ip|<UTC day>|<prefix>"), or null for no address. AgentCake
         * computes the same from cake.js's own request and keeps only whether the two match: no side keeps the address.
         */
        public static function networkKey($secret, ?string $ip, $nowMs): ?string
        {
            $prefix = $ip === null || $ip === '' ? null : self::ipPrefix($ip);
            if ($prefix === null) {
                return null;
            }
            $fixed = self::settings()['fixed'];
            $day = (new \DateTime('@' . sprintf('%.0f', floor($nowMs / self::MS_PER_S))))->format('Y-m-d');
            return substr(hash_hmac('sha256', "{$fixed['network_key_label']}|$day|$prefix", (string) $secret), 0, $fixed['network_key_hex_chars']);
        }

        public static function lower(string $text): string
        {
            return strtr($text, self::ASCII_UPPER, self::ASCII_LOWER);
        }

        public static function b64url(string $bytes): string
        {
            return rtrim(strtr(base64_encode($bytes), '+/', '-_'), '=');
        }

        /** The payload's fields that describe the request, in the format's order: p, sf, sp, md, al, ch, ua, hn, sg. */
        private static function facts(array $request, array $chosen): array
        {
            [, $path, $values, $names] = $request;
            [$fixed, $headers, $cut] = [self::settings()['fixed'], self::settings()['headers'], $chosen['cut']];
            $header = function (string $role, string $length) use ($values, $headers, $cut): ?string {
                return self::cut($values[$headers[$role]] ?? null, $cut[$length]);
            };
            $kept = array_values(array_filter($names, function (string $name) use ($cut): bool {
                return strlen($name) <= $cut['header_name'] && preg_match(self::HEADER_NAME, $name) === 1;
            }));
            return ['p' => self::cut($path, $cut['path']),
                'sf' => ['s' => $header('sec_fetch_site', 'sec_fetch'), 'm' => $header('sec_fetch_mode', 'sec_fetch'),
                    'd' => $header('sec_fetch_dest', 'sec_fetch'), 'u' => $header('sec_fetch_user', 'sec_fetch_user')],
                'sp' => $header('sec_purpose', 'sec_purpose'),
                'md' => self::accepts($values, $fixed['markdown_type']),
                'al' => $header('accept_language', 'accept_language'),
                'ch' => ['ua' => $header('sec_ch_ua', 'sec_ch_ua'), 'pf' => $header('sec_ch_ua_platform', 'sec_ch_ua_platform'),
                    'mb' => $header('sec_ch_ua_mobile', 'sec_ch_ua_mobile')],
                'ua' => $header('user_agent', 'user_agent'),
                'hn' => array_slice($kept, 0, $chosen['max_header_names']),
                'sg' => ['a' => $header('signature_agent', 'signature_agent'), 's' => isset($values[$headers['signature']]),
                    'i' => isset($values[$headers['signature_input']])]];
        }

        /** Whether the request's Accept lists this media type (parameters and case aside). */
        private static function accepts(array $values, string $type): bool
        {
            foreach (explode(',', $values[self::settings()['headers']['accept']] ?? '') as $range) {
                if (self::lower(trim(explode(';', $range)[0], self::OWS)) === $type) {
                    return true;
                }
            }
            return false;
        }

        /** botscent's verdict ({type, agent_name, reasons}) as {t, a, r}, short identifiers only; null when there is none. */
        private static function verdictFields($verdict): ?array
        {
            $fixed = self::settings()['fixed'];
            if (!is_array($verdict) || !in_array($verdict['type'] ?? null, $fixed['verdict_types'], true)) {
                return null;
            }
            $reasons = isset($verdict['reasons']) && is_array($verdict['reasons']) && array_values($verdict['reasons']) === $verdict['reasons'] ? $verdict['reasons'] : [];
            $kept = array_values(array_filter($reasons, function ($reason) use ($fixed): bool {
                return self::short($reason, $fixed['verdict_id_max'], self::IDENTIFIER) !== null;
            }));
            return ['t' => $verdict['type'], 'a' => self::short($verdict['agent_name'] ?? null, $fixed['verdict_id_max'], self::IDENTIFIER),
                'r' => array_slice($kept, 0, $fixed['verdict_reasons_max'])];
        }

        private static function short($value, int $longest, string $pattern): ?string
        {
            return is_string($value) && strlen($value) <= $longest && preg_match($pattern, $value) === 1 ? $value : null;
        }

        /** The value without control characters, at most $length characters (code points) long; null stays null. */
        private static function cut(?string $value, int $length): ?string
        {
            if ($value === null) {
                return null;
            }
            $clean = (string) preg_replace(self::CONTROL, '', $value);
            if (strlen($clean) <= $length) {
                return $clean;
            }
            if (preg_match('/\A.{0,' . $length . '}/su', $clean, $match) !== 1) {
                throw new \UnexpectedValueException('a header value that is not UTF-8');
            }
            return $match[0];
        }

        /** JSON as JavaScript's JSON.stringify writes it, which the MAC covers byte for byte. */
        private static function json($value): string
        {
            if (is_array($value)) {
                $list = $value === [] || array_keys($value) === range(0, count($value) - 1);
                $items = [];
                foreach ($value as $key => $item) {
                    $items[] = ($list ? '' : self::json((string) $key) . ':') . self::json($item);
                }
                return $list ? '[' . implode(',', $items) . ']' : '{' . implode(',', $items) . '}';
            }
            if (is_float($value)) {
                return sprintf('%.0f', $value); // the time, held as a float by a 32-bit PHP: whole milliseconds
            }
            $json = json_encode($value, self::JSON_FLAGS);
            if ($json === false) {
                throw new \UnexpectedValueException(json_last_error_msg());
            }
            return $json;
        }

        private static function ipv4(string $text): ?array
        {
            $octets = explode('.', $text);
            if (count($octets) !== self::IPV4_OCTETS) {
                return null;
            }
            foreach ($octets as $octet) {
                if (preg_match(self::DECIMAL_OCTET, $octet) !== 1 || (int) $octet > self::OCTET_MAX) {
                    return null;
                }
            }
            return array_map('intval', $octets);
        }

        /** The eight groups of an IPv6 address, or null: the steps of Python's IPv6Address._ip_int_from_string. */
        private static function ipv6(string $text): ?array
        {
            [$address, $zone] = array_pad(explode('%', $text, 2), 2, null);
            if (strpos($text, '/') !== false || ($zone !== null && ($zone === '' || strpos($zone, '%') !== false))) {
                return null;
            }
            $parts = explode(':', $address);
            if (count($parts) < self::MIN_IPV6_PARTS) {
                return null;
            }
            if (strpos((string) end($parts), '.') !== false) {
                $octets = self::ipv4((string) array_pop($parts));
                if ($octets === null) {
                    return null;
                }
                array_push($parts, dechex(($octets[0] << self::OCTET_BITS) | $octets[1]), dechex(($octets[2] << self::OCTET_BITS) | $octets[3]));
            }
            $count = count($parts);
            $skip = -1;
            for ($i = 1; $i < $count - 1; $i++) {
                if ($parts[$i] === '' && $skip !== -1) {
                    return null;
                }
                $skip = $parts[$i] === '' ? $i : $skip;
            }
            [$high, $low] = $skip === -1 ? [$count, 0] : [$skip, $count - $skip - 1];
            if ($count > self::HEXTETS + 1 || ($skip === -1 && $count !== self::HEXTETS)
                || ($skip !== -1 && (($parts[0] === '' && --$high) || ($parts[$count - 1] === '' && --$low) || self::HEXTETS - $high - $low < 1))) {
                return null;
            }
            $groups = array_merge(array_slice($parts, 0, $high), array_fill(0, self::HEXTETS - $high - $low, '0'), array_slice($parts, $count - $low, $low));
            foreach ($groups as $part) {
                if (preg_match(self::HEXTET, $part) !== 1) {
                    return null;
                }
            }
            return array_map('hexdec', $groups);
        }
    }
}
