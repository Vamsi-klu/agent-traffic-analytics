"use strict"
/*
 * netkey.test.js — the network key: a keyed hash of the visitor's /24 (IPv4) or /48 (IPv6) and the UTC day, so cake can
 * tell whether the page and cake.js's own request came from the same network without anyone keeping the address.
 * Addresses are parsed by the rules of Python's ipaddress module, which cake's side uses.
 *
 * Run: node --test edge/node/test/
 */
const test = require("node:test")
const assert = require("node:assert/strict")
const { ipPrefix, networkKey } = require("..")
const { SECRET, OTHER_SECRET, NOW } = require("./helpers")

const DAY_MS = 24 * 60 * 60 * 1000

test("IP prefixes: the /24 of IPv4, the /48 of IPv6, the IPv4 inside a mapped IPv6 address", () => {
  for (const [address, prefix] of [
    ["203.0.113.77", "203.0.113.0/24"],
    [" 203.0.113.77 ", "203.0.113.0/24"],
    ["::ffff:198.51.100.9", "198.51.100.0/24"],
    ["::ffff:c633:6409", "198.51.100.0/24"],
    ["2001:db8:abcd:12::1", "2001:db8:abcd::/48"],
    ["2001:db8::1", "2001:db8:0::/48"],
    ["2001:0DB8:00ab:ffff::", "2001:db8:ab::/48"],
    ["fe80::1%eth0", "fe80:0:0::/48"],
    ["::1", "0:0:0::/48"],
    ["::", "0:0:0::/48"],
    ["::1.2.3.4", "0:0:0::/48"],
    ["::ffff:0:1.2.3.4", "0:0:0::/48"],
    ["1:2:3:4:5:6:1.2.3.4", "1:2:3::/48"],
    ["1:2:3:4:5:6:7::", "1:2:3::/48"],
  ]) {
    assert.equal(ipPrefix(address), prefix, address)
  }
})

test("anything that is not one address has no prefix", () => {
  for (const address of [
    "256.1.1.1", "01.2.3.4", "1.2.3", "1.2.3.4.5", "1.2.3.4:80", "[2001:db8::1]", "2001:db8::1::2", "12345::",
    "1:2:3:4:5:6:7:8:9", "1:2:3:4:5:6:7", ":1:2:3:4:5:6:7", "1::2:3:4:5:6:7:8", "::ffff:1.2.3.04", "fe80::1%", "",
    "not-an-ip", null, undefined, 2130706433,
  ]) {
    assert.equal(ipPrefix(address), null, String(address))
  }
})

test("the network key is the same for the same /24 on the same UTC day under the same secret, and only then", async () => {
  const key = await networkKey(SECRET, "203.0.113.77", NOW)
  assert.match(key, /^[0-9a-f]{16}$/)
  assert.equal(await networkKey(SECRET, "203.0.113.5", NOW), key, "the same /24")
  assert.equal(await networkKey(SECRET, "::ffff:203.0.113.200", NOW + 1000), key, "the same /24, mapped, later that day")
  assert.notEqual(await networkKey(SECRET, "203.0.114.77", NOW), key, "another /24")
  assert.notEqual(await networkKey(SECRET, "203.0.113.77", NOW + DAY_MS), key, "another day")
  assert.notEqual(await networkKey(OTHER_SECRET, "203.0.113.77", NOW), key, "another secret")
})

test("no address, or one that cannot be read: no network key", async () => {
  assert.equal(await networkKey(SECRET, null, NOW), null)
  assert.equal(await networkKey(SECRET, "unknown", NOW), null)
})
