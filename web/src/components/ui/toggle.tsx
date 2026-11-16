import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Toggle as TogglePrimitive } from "radix-ui"

const toggleVariants = cva(
  "group/toggle inline-flex items-center justify-center gap-1 rounded-full text-sm font-bold whitespace-nowrap text-muted-foreground transition-all outline-none hover:bg-muted hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 aria-pressed:bg-foreground aria-pressed:text-background data-[state=on]:bg-foreground data-[state=on]:text-background dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-transparent",
        outline: "border-2 border-line bg-card hover:bg-muted",
        // Frosting: the session list's verdict filter, each verdict in its badge's colours by one rule (DESIGN.md §6.1):
        // its soft colour and its text colour, and once picked its text colour as the background. All is outline.
        agent: "border-2 border-line bg-agent-soft text-agent-foreground hover:bg-agent-soft data-[state=on]:bg-agent-foreground data-[state=on]:text-card aria-pressed:bg-agent-foreground aria-pressed:text-card",
        human: "border-2 border-line bg-human-soft text-human-foreground hover:bg-human-soft data-[state=on]:bg-human-foreground data-[state=on]:text-card aria-pressed:bg-human-foreground aria-pressed:text-card",
        bot: "border-2 border-line bg-unsure-soft text-unsure-foreground hover:bg-unsure-soft data-[state=on]:bg-unsure-foreground data-[state=on]:text-card aria-pressed:bg-unsure-foreground aria-pressed:text-card",
      },
      // Frosting: every size keeps the base's pill, as every dropdown is one (DESIGN.md §6)
      size: {
        default:
          "h-8 min-w-8 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        sm: "h-7 min-w-7 px-2.5 text-[0.8rem] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 min-w-9 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Toggle({
  className,
  variant = "default",
  size = "default",
  ...props
}: React.ComponentProps<typeof TogglePrimitive.Root> &
  VariantProps<typeof toggleVariants>) {
  return (
    <TogglePrimitive.Root
      data-slot="toggle"
      className={cn(toggleVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Toggle, toggleVariants }
