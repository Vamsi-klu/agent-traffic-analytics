"use strict"
/*
 * netkey.js — the network key: the first 16 hex characters of HMAC-SHA256(secret, "ip|<UTC day>|<prefix>"), where the
 * prefix is the /24 of an IPv4 address or the /48 of an IPv6 one (an IPv4-mapped IPv6 address counts as its IPv4).
 *
 * cake computes the same key from cake.js's own request and keeps only whether the two match, so no side stores the
 * address, and the day in the key makes it say nothing across days. Addresses are read by the rules of Python's
 * ipaddress module, which cake's side uses: four decimal octets without leading zeros; eight hex groups with at most one
 * "::", maybe an IPv4 tail and a zone after "%". Anything else has no prefix and so no key. The prefix is written the way
 * cake's own ip_prefix writes it (agentcake/netfacts.py: "203.0.113.0/24", "2001:db8:0::/48"). The MAC is the caller's,
 * as in token.js.
 * Step S4.1.
 */
const IPV4_OCTETS = 4 // protocol: an IPv4 address
const OCTET_BITS = 8 // protocol
const OCTET_MASK = 0xff // protocol
const OCTET_MAX = 255 // protocol
const HEXTETS = 8 // protocol: an IPv6 address
const HEXTET_BITS = 16 // protocol
const HEX = 16 // protocol: hexadecimal
const MIN_IPV6_PARTS = 3 // protocol: "::" alone splits into three parts
const MAPPED_AT = 5 // protocol: ::ffff:a.b.c.d is five zero groups, ffff, then the IPv4 address (RFC 4291 2.5.5.2)
const MAPPED_HEXTET = 0xffff // protocol
const DAY_CHARS = 10 // protocol: "YYYY-MM-DD", the start of an ISO 8601 time
const BYTE_HEX_DIGITS = 2 // protocol
const DECIMAL_OCTET = /^(?:0|[1-9][0-9]{0,2})$/
const HEXTET = /^[0-9A-Fa-f]{1,4}$/

function parseIPv4(text) {
  const octets = text.split(".")
  if (octets.length !== IPV4_OCTETS) return null
  const bytes = []
  for (const octet of octets) {
    if (!DECIMAL_OCTET.test(octet) || Number(octet) > OCTET_MAX) return null
    bytes.push(Number(octet))
  }
  return bytes
}

// The address without its zone ("fe80::1%eth0"), or null for a "%" with no zone or a second "%" (_split_scope_id).
function withoutZone(text) {
  const at = text.indexOf("%")
  if (at === -1) return text
  const zone = text.slice(at + 1)
  return zone && !zone.includes("%") ? text.slice(0, at) : null
}

// The eight groups of an IPv6 address, or null: the steps of Python's IPv6Address._ip_int_from_string.
function parseIPv6(text) {
  const address = text.includes("/") ? null : withoutZone(text)
  if (!address) return null
  const parts = address.split(":")
  if (parts.length < MIN_IPV6_PARTS) return null
  if (parts[parts.length - 1].includes(".")) {
    const ipv4 = parseIPv4(parts.pop())
    if (!ipv4) return null
    parts.push(((ipv4[0] << OCTET_BITS) | ipv4[1]).toString(HEX), ((ipv4[2] << OCTET_BITS) | ipv4[3]).toString(HEX))
  }
  if (parts.length > HEXTETS + 1) return null
  let skip = -1
  for (let i = 1; i < parts.length - 1; i++) {
    if (parts[i]) continue
    if (skip !== -1) return null
    skip = i
  }
  let high = parts.length
  let low = 0
  if (skip !== -1) {
    high = skip
    low = parts.length - skip - 1
    if (!parts[0] && --high) return null
    if (!parts[parts.length - 1] && --low) return null
    if (HEXTETS - high - low < 1) return null
  } else if (parts.length !== HEXTETS) {
    return null
  }
  const read = (part) => (HEXTET.test(part) ? parseInt(part, HEX) : NaN)
  const zeros = new Array(HEXTETS - high - low).fill(0)
  const groups = [...parts.slice(0, high).map(read), ...zeros, ...parts.slice(parts.length - low).map(read)]
  return groups.some(Number.isNaN) ? null : groups
}

function ipv4Prefix(octets, fixed) {
  const kept = fixed.ipv4_prefix_bits / OCTET_BITS
  return `${octets.map((octet, i) => (i < kept ? octet : 0)).join(".")}/${fixed.ipv4_prefix_bits}`
}

function ipv6Prefix(groups, fixed) {
  const kept = fixed.ipv6_prefix_bits / HEXTET_BITS
  return `${groups.slice(0, kept).map((group) => group.toString(HEX)).join(":")}::/${fixed.ipv6_prefix_bits}`
}

function isMapped(groups) {
  return groups.slice(0, MAPPED_AT).every((group) => group === 0) && groups[MAPPED_AT] === MAPPED_HEXTET
}

// "203.0.113.0/24", "2001:db8:abcd::/48", or null for anything that is not one address.
function ipPrefix(ip, fixed) {
  if (typeof ip !== "string") return null
  const text = ip.trim()
  const ipv4 = parseIPv4(text)
  if (ipv4) return ipv4Prefix(ipv4, fixed)
  const groups = parseIPv6(text)
  if (!groups) return null
  if (!isMapped(groups)) return ipv6Prefix(groups, fixed)
  const [high, low] = groups.slice(MAPPED_AT + 1)
  return ipv4Prefix([high >> OCTET_BITS, high & OCTET_MASK, low >> OCTET_BITS, low & OCTET_MASK], fixed)
}

// What the network key's MAC covers, or null when the address has no prefix.
function networkText(ip, nowMs, fixed) {
  const prefix = ipPrefix(ip, fixed)
  if (prefix === null || !Number.isFinite(nowMs)) return null
  const day = new Date(nowMs).toISOString().slice(0, DAY_CHARS)
  return `${fixed.network_key_label}|${day}|${prefix}`
}

function networkKeyOf(mac, fixed) {
  const hex = Array.from(mac, (byte) => byte.toString(HEX).padStart(BYTE_HEX_DIGITS, "0")).join("")
  return hex.slice(0, fixed.network_key_hex_chars)
}

module.exports = { ipPrefix, networkText, networkKeyOf }
