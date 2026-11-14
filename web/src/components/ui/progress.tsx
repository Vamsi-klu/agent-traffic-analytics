import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Progress as ProgressPrimitive } from "radix-ui"

// Frosting: tone "ok" for healthy storage, "warn" past 80% (DESIGN.md §6.1)
const indicatorVariants = cva("size-full flex-1 rounded-full transition-all", {
  variants: { tone: { default: "bg-primary", ok: "bg-ok", warn: "bg-warn" } },
  defaultVariants: { tone: "default" },
})

function Progress({
  className,
  value,
  tone = "default",
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root> & VariantProps<typeof indicatorVariants>) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      className={cn(
        "relative flex h-4 w-full items-center overflow-x-hidden rounded-full border-2 border-line bg-muted",
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className={indicatorVariants({ tone })}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
