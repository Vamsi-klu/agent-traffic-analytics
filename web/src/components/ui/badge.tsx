import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const badgeVariants = cva(
  "group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border-2 border-transparent px-2 py-0.5 text-xs font-extrabold whitespace-nowrap minimal:border minimal:font-semibold transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        secondary:
          "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive:
          "bg-destructive/10 text-destructive focus-visible:ring-destructive/20 [a]:hover:bg-destructive/20",
        outline:
          "border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground",
        ghost:
          "hover:bg-muted hover:text-muted-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        // Frosting category variants (DESIGN.md §3.1): one shape, each its own colours (bot and unknown share the one
        // grey). Use them through <VerdictBadge> and <TurnsBadge>, never by hand.
        human: "border-line bg-human-soft text-human-foreground minimal:border-transparent",
        agent: "border-line bg-agent-soft text-agent-foreground minimal:border-transparent",
        unknown: "border-line bg-unsure-soft text-unsure-foreground minimal:border-transparent",
        bot: "border-line bg-unsure-soft text-unsure-foreground minimal:border-transparent",
        // a Human session cake couldn't tell: beside its Human badge, through <ThinEvidenceTag>
        thin: "rounded-md border-dashed border-line bg-unsure-soft text-unsure-foreground font-bold minimal:border-unsure",
        // neutral tag: agent names, sources, "off by default"
        tag: "rounded-md border-border bg-card text-muted-foreground font-bold minimal:rounded-full minimal:text-foreground minimal:font-medium",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
