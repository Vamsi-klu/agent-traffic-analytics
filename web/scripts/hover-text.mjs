// check:ui's hover text rule (DESIGN.md §6, §11, §12): every text shown on hover goes through the theme tooltip (cake's
// Hint and InfoTip), which opens on keyboard focus too and has one look, never the browser's own grey title box:
//  - no title= attribute, except on the components whose title prop is a heading they show on the page;
//  - no SVG <title> (a name for screen readers is aria-label);
//  - outside src/components/ui, TooltipContent and ChartTooltipContent take no className or labelClassName: their look
//    is the component's (a tooltip styled by hand is how the centred lines and the chart's other box came about).
// The files are parsed as TSX, so only JSX counts: a title in an object, a type or a sentence is nothing to this rule.
import path from "node:path"
import ts from "typescript"

/** Components whose title prop is a heading on the page, not hover text. */
export const HEADING_TITLES = new Set(["PageHeader", "SettingRow", "OnboardingStep", "OnboardingLayout", "StatsTable", "WebStatsTable", "PageError"])
const TOOLTIP_BOXES = new Set(["TooltipContent", "ChartTooltipContent"])
const STYLE_PROPS = new Set(["className", "labelClassName"])
const HOVER = "hover text goes through Hint (the theme tooltip, one look, opens on focus too); a name for screen readers is aria-label (DESIGN.md §6, §11)"

/** The problems in one TSX file, each with where it starts (index into source) and what to do instead. */
export function hoverTextProblems(file, source) {
  const inUi = file.split(path.sep).join("/").includes("components/ui/")
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const problems = []
  const visit = (node) => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = node.tagName.getText(tree)
      if (tag === "title") problems.push({ index: node.getStart(tree), message: `<title> in an SVG: the browser shows it in its own box on hover; ${HOVER}` })
      for (const attribute of node.attributes.properties) {
        if (!ts.isJsxAttribute(attribute)) continue
        const name = attribute.name.getText(tree)
        if (name === "title" && !HEADING_TITLES.has(tag)) {
          problems.push({ index: attribute.getStart(tree), message: `title= on <${tag}>: the browser's own hover box; ${HOVER}` })
        }
        if (!inUi && TOOLTIP_BOXES.has(tag) && STYLE_PROPS.has(name)) {
          problems.push({ index: attribute.getStart(tree), message: `${name}= on <${tag}>: a tooltip's look is its component's (src/components/ui), never restyled in place` })
        }
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(tree)
  return problems
}
