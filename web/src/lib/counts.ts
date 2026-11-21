// A count of sessions in words: the number as every count is written (integer(), src/lib/format.ts), the noun from
// src/lib/words.ts in the right number. A file of its own because words.ts and format.ts import nothing at run time,
// so the tests can read them as they are.
import { integer } from "@/lib/format"
import { WORDS } from "@/lib/words"

/** "1 session", "1,280 sessions". */
export const sessionCount = (n: number) => `${integer(n)} ${n === 1 ? WORDS.session : WORDS.sessions}`
