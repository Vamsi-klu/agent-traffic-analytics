// The top bar's Style menu (DESIGN.md §17): Cake, the default look with Crumb, and Minimal, the plain look. A palette
// icon and the word, as other products' appearance menus are; the menu lists both styles with a small preview of each
// and a check at the one in use. Picking a style changes the pages at once, without loading them again, and this
// browser opens the next visit in it (lib/style.ts).
import { ChevronDown, Palette } from "lucide-react"
import cakePreview from "@/assets/styles/cake.png"
import minimalPreview from "@/assets/styles/minimal.png"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { STYLE_NAMES, setStyle, useStyle, type StyleName } from "@/lib/style"
import { WORDS } from "@/lib/words"

/** Each style's preview in the menu: the dashboard's first screen in it, 1280 × 800 shrunk to 480 × 300 (made by
 *  scripts/style-previews.mjs). */
const PREVIEWS: Record<StyleName, string> = { cake: cakePreview, minimal: minimalPreview }

const pick = (value: string) => { if (STYLE_NAMES.includes(value as StyleName)) setStyle(value as StyleName) }

/** The top bar's "Style" menu: both styles, a small preview beside each name, a check at the one in use. On a phone the
 *  button is only the palette, as the top bar's pages are only their icons there. */
export function StyleMenu() {
  const style = useStyle()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" aria-label={`${WORDS.style}: ${WORDS.styles[style]}`}>
          <Palette aria-hidden /><span className="max-sm:sr-only">{WORDS.style}</span><ChevronDown aria-hidden className="max-sm:hidden" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>{WORDS.style}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={style} onValueChange={pick}>
          {STYLE_NAMES.map((name) => (
            <DropdownMenuRadioItem key={name} value={name} className="gap-3 py-1.5">
              <img src={PREVIEWS[name]} alt="" className="h-9 w-14 rounded-sm border border-line object-cover object-left-top minimal:border-input" />
              <span className="font-bold minimal:font-medium">{WORDS.styles[name]}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
