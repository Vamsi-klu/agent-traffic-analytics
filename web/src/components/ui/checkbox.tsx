"use client"

import * as React from "react"
import { CheckIcon } from "lucide-react"
import { cn } from "cn"
import { Checkbox as CheckboxPrimitive } from "radix-ui"

// shadcn/ui's Checkbox (MIT). Frosting: the 2px ink frame every control has; ticked, the box is inverted (an ink box
// with a cream tick), as a picked ToggleGroup item is. A small square radius, unlike the theme's round controls, so it
// never reads as a pick-one circle; the hit area reaches past the box, so it is 36px across.
function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer relative flex size-5 shrink-0 items-center justify-center rounded-[5px] border-2 border-line bg-card text-background transition-colors outline-none after:absolute after:-inset-2 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-checked:bg-foreground data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none"
      >
        <CheckIcon className="size-3.5" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
