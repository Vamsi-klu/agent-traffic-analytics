// How the pages write a count (src/lib/format.ts integer()): a whole number with a comma between thousands, as PostHog
// and the rest of the industry write it (1,900), whatever language the browser is set to, so one number reads the same
// on every card, chart, table and hover. Usage: node --test tests/
import assert from "node:assert/strict"
import { test } from "node:test"
import { integer } from "../src/lib/format.ts"

test("a count of a thousand or more has a comma between thousands", () => {
  assert.deepEqual([1000, 1323, 1900, 12345, 1234567].map(integer), ["1,000", "1,323", "1,900", "12,345", "1,234,567"])
})

test("a count under a thousand reads as it is", () => {
  assert.deepEqual([0, 7, 86, 999].map(integer), ["0", "7", "86", "999"])
})
