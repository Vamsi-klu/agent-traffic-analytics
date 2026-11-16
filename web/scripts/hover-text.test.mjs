// Tests for check:ui's hover text rule (scripts/hover-text.mjs): every text shown on hover goes through the theme
// tooltip, never the browser's own title box, and a tooltip's look is its component's. Usage: node --test scripts/
import assert from "node:assert/strict"
import { test } from "node:test"
import { hoverTextProblems } from "./hover-text.mjs"

/** The messages for one source file (a cake component unless `ui`). */
const problems = (source, { ui = false } = {}) => hoverTextProblems(ui ? "src/components/ui/x.tsx" : "src/components/cake/x.tsx", source).map((p) => p.message)

test("a title attribute on an element or a component is the browser's own hover box", () => {
  assert.equal(problems(`export const A = () => <span title="Warning threshold" />`).length, 1)
  const [message] = problems(`export const B = ({ about }) => <Badge variant="tag" title={about}>Likely</Badge>`)
  assert.match(message, /title= on <Badge>/)
  assert.match(message, /Hint/)
})

test("a component whose title is a visible heading may take one", () => {
  for (const tag of ["PageHeader", "SettingRow", "OnboardingStep", "OnboardingLayout", "StatsTable", "WebStatsTable", "PageError"]) {
    assert.deepEqual(problems(`export const A = () => <${tag} title="Settings" />`), [], tag)
  }
})

test("an SVG <title> is the browser's own hover box too", () => {
  const [message] = problems(`export const A = () => <svg role="img"><title>An AI agent acted for a human</title></svg>`)
  assert.match(message, /<title>/)
})

test("a tooltip's look is its component's: TooltipContent and ChartTooltipContent take no className outside the ui folder", () => {
  assert.equal(problems(`export const A = () => <TooltipContent className="flex flex-col gap-1">x</TooltipContent>`).length, 1)
  assert.equal(problems(`export const A = () => <ChartTooltipContent labelClassName="font-bold" />`).length, 1)
  assert.deepEqual(problems(`export const A = () => <TooltipContent>Pause</TooltipContent>`), [])
  assert.deepEqual(problems(`export const A = () => <TooltipContent className="z-50">x</TooltipContent>`, { ui: true }), [])
})

test("only JSX counts: a title in an object, a type or a sentence is no hover box", () => {
  assert.deepEqual(problems(`type Row = { title: string }\nexport const rows: Row[] = [{ title: "Sessions" }]\nexport const A = () => <p>Use title= never</p>`), [])
})

test("a problem points at its place in the file", () => {
  const source = `export const A = () => (\n  <div>\n    <span title="x" />\n  </div>\n)`
  const [{ index }] = hoverTextProblems("src/pages/x.tsx", source)
  assert.equal(source.slice(0, index).split("\n").length, 3)
})
