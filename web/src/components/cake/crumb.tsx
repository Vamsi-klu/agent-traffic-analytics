// Crumb, the mascot: a slice of cake with a magnifying glass. A plain white body (no layers, no sprinkles), frosting
// with drips in the palette colour, a red cherry, ink outline and face. Drawn for the product (no third-party art). DESIGN.md §7.
// Lines use --cake-line (light in dark mode); the face (.face) stays ink on the white body.
// Standing poses idle like the agent avatars (sway, bob, squash) and the open eyes blink (§15); still with reduced motion.
import { PRODUCT_NAME } from "@/lib/product"
import { cn } from "@/lib/utils"

export type CrumbPose = "wave" | "look" | "sleep" | "oops"

const BODY = "M52 86 Q50 76 60 74 L140 70 Q152 70 152 82 L156 152 Q156 164 144 164 L60 166 Q48 166 48 154 Z"
const CAP = "M45 88 Q44 64 66 63 L136 59 Q157 59 157 80 L157 88 Q151 97 144 88 Q137 103 129 90 Q122 95 116 88 Q108 107 99 90 Q92 96 86 90 Q78 101 70 90 Q62 96 56 90 Q50 95 45 88 Z"

export function Crumb({ pose = "look", className, title }: { pose?: CrumbPose; className?: string; title?: string }) {
  const label = title ?? `Crumb, ${PRODUCT_NAME}'s mascot`
  const look = pose === "look" ? 3 : 0
  return (
    <svg viewBox="0 0 200 200" role="img" aria-label={label} className={cn("crumb", className)}>
      <ellipse className="shadow" cx="100" cy="193" rx="42" ry="5" />
      <g className={pose === "wave" ? "hop" : "idle"}>
        {pose === "sleep" ? (
          <>
            <path className="o" strokeWidth="6" d="M78 164 q-4 10 -16 12" /><path className="o" strokeWidth="6" d="M120 164 q6 10 18 12" />
            <ellipse className="f-outline" cx="58" cy="177" rx="9" ry="5" /><ellipse className="f-outline" cx="142" cy="177" rx="9" ry="5" />
          </>
        ) : (
          <>
            <path className="o" strokeWidth="6" d="M84 164 C82 174 76 181 68 184" /><path className="o" strokeWidth="6" d="M116 164 C120 172 128 177 138 177" />
            <ellipse className="f-outline" cx="63" cy="186" rx="10" ry="5.5" /><ellipse className="f-outline" cx="143" cy="178" rx="10" ry="5.5" />
          </>
        )}
        {pose === "wave" || pose === "look" ? (
          <>
            <path className="o" strokeWidth="6" d="M153 124 C160 130 162 136 164 140" />
            <path className="o" strokeWidth="6" d="M165 139 L173 128" />
            <circle className="o f-cream" strokeWidth="3" cx="164" cy="141" r="6.5" />
            <circle className="o f-glass" strokeWidth="5" cx="180" cy="117" r="14" />
            <path className="o" strokeWidth="3" d="M172 112 q3 -5 9 -5" />
          </>
        ) : pose === "oops" ? (
          <><path className="o" strokeWidth="6" d="M153 118 C168 112 172 100 170 90" /><circle className="o f-cream" strokeWidth="3" cx="170" cy="86" r="7" /></>
        ) : (
          <path className="o" strokeWidth="6" d="M153 128 C162 134 162 146 156 150" />
        )}
        <path className="f-body" d={BODY} />
        <path className="o" strokeWidth="4" d={BODY} />
        <path className="o f-frosting" strokeWidth="4" d={CAP} />
        <path className="o" strokeWidth="4" d="M106 40 Q110 27 122 25" />
        <circle className="o f-cherry" strokeWidth="4" cx="103" cy="50" r="11" />
        <ellipse className="f-shine" cx="99" cy="46" rx="3" ry="2.2" />
        {pose === "sleep" ? (
          <>
            <path className="o face" strokeWidth="3.5" d="M80 102 q6 5 12 0" /><path className="o face" strokeWidth="3.5" d="M108 101 q6 5 12 0" />
            <ellipse className="f-outline face" cx="100" cy="112" rx="4" ry="3" />
            <text x="160" y="70" fontSize="22">z</text><text x="172" y="52" fontSize="18">z</text>
          </>
        ) : pose === "oops" ? (
          <>
            <circle className="f-outline face" cx="86" cy="101" r="6" /><circle className="f-outline face" cx="114" cy="100" r="6" />
            <circle className="f-shine" cx="88" cy="99" r="2" /><circle className="f-shine" cx="116" cy="98" r="2" />
            <ellipse className="f-outline face" cx="100" cy="114" rx="5" ry="6" />
          </>
        ) : (
          <>
            <g className="blink">
              <ellipse className="f-outline face" cx={86 + look} cy="101" rx="5.5" ry="7" /><ellipse className="f-outline face" cx={114 + look} cy="100" rx="5.5" ry="7" />
              <circle className="f-shine" cx={88 + look} cy="98" r="2" /><circle className="f-shine" cx={116 + look} cy="97" r="2" />
            </g>
            <path className="o f-outline face" strokeWidth="2.5" d="M92 108 Q100 119 108 108 Z" />
            <path className="f-jam" d="M96 113 Q100 117 104 113" />
          </>
        )}
        <ellipse className="f-cheek" cx="74" cy="110" rx="6" ry="3.5" /><ellipse className="f-cheek" cx="126" cy="109" rx="6" ry="3.5" />
        {pose === "wave" ? (
          <>
            <g className="wave"><path className="o" strokeWidth="6" d="M50 120 C36 114 30 100 31 88" /><circle className="o f-cream" strokeWidth="3" cx="31" cy="83" r="7" /></g>
            <path className="o faint" strokeWidth="3" d="M18 74 l-8 -4 M16 88 l-9 0 M20 101 l-8 4" />
          </>
        ) : pose === "oops" ? (
          <><path className="o" strokeWidth="6" d="M50 118 C38 112 32 102 32 92" /><circle className="o f-cream" strokeWidth="3" cx="32" cy="88" r="7" /></>
        ) : (
          <path className="o" strokeWidth="6" d="M50 126 C40 132 38 144 44 150" />
        )}
      </g>
    </svg>
  )
}

/** Crumb's head only: the logo, and the marker on human + agent rows. */
export function CrumbHead({ className, title }: { className?: string; title?: string }) {
  return (
    <svg viewBox="40 20 124 100" className={cn("crumb", className)} role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      <path className="o f-body" strokeWidth="5" d="M50 112 L52 86 Q50 76 60 74 L140 70 Q152 70 152 82 L154 112 Z" />
      <path className="o f-frosting" strokeWidth="5" d={CAP} />
      <path className="o" strokeWidth="5" d="M106 40 Q110 27 122 25" />
      <circle className="o f-cherry" strokeWidth="5" cx="103" cy="50" r="11" />
      <ellipse className="f-outline face" cx="86" cy="101" rx="5.5" ry="7" /><ellipse className="f-outline face" cx="114" cy="100" rx="5.5" ry="7" />
    </svg>
  )
}
