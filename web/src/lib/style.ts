/** The pages' two styles (DESIGN.md §17). Cake is the default: the Frosting look, with Crumb. Minimal is a plain look
 *  for reports and screenshots. <html data-style="minimal"> turns Minimal on (src/styles/tokens.css and the minimal:
 *  variant in src/index.css); Cake leaves no attribute, so nothing of Minimal applies to it. Both are light only.
 *
 *  The choice belongs to this browser: the top bar's Style menu (components/cake/style-menu.tsx) keeps it in
 *  localStorage, so the next visit opens in the style picked last. Where the browser keeps no site data (a private
 *  window, site data turned off), the pages open in Cake and a choice lasts as long as the page stays open. */
import { useSyncExternalStore } from "react"

export type StyleName = "cake" | "minimal"
/** In the order the menu lists them: the default first. */
export const STYLE_NAMES: StyleName[] = ["cake", "minimal"]

const DEFAULT_STYLE: StyleName = "cake"
/** The localStorage key of the choice; scripts/shots.mjs sets it to shoot the pages in Minimal. */
const STORAGE_KEY = "agentcake-style"
const listeners = new Set<() => void>()

const isStyle = (value: string | null): value is StyleName => STYLE_NAMES.includes(value as StyleName)

/** The style this browser picked last, or Cake when it picked none, keeps something else or keeps no site data. */
function kept(): StyleName {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return isStyle(value) ? value : DEFAULT_STYLE
  } catch {
    return DEFAULT_STYLE
  }
}

function keep(style: StyleName) {
  try {
    localStorage.setItem(STORAGE_KEY, style)
  } catch {
    // no site data in this browser: the choice lasts as long as the page stays open
  }
}

let current: StyleName = kept()

/** Marks the root element with the style in use; Cake leaves no attribute. */
export function showStyle() {
  if (current === DEFAULT_STYLE) delete document.documentElement.dataset.style
  else document.documentElement.dataset.style = current
}

/** Picks a style: the pages change at once and the next visit opens in it. */
export function setStyle(style: StyleName) {
  current = style
  keep(style)
  showStyle()
  for (const listener of listeners) listener()
}

function onStyleChange(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

/** The style in use, for a component that shows it or measures its own text in the page's font (the charts). */
export function useStyle(): StyleName {
  return useSyncExternalStore(onStyleChange, () => current)
}
