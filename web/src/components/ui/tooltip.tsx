"use client"

import * as React from "react"
import { cn } from "cn"
import { Tooltip as TooltipPrimitive } from "radix-ui"

/** Frosting: how long the pointer rests on an element before its tooltip opens, one value for every tooltip, PostHog's
 *  own (its Tooltip component, frontend/src/lib/lemon-ui/Tooltip/Tooltip.tsx: delayMs = 400, closeDelayMs = 0).
 *  Keyboard focus opens a tooltip at once, and it closes as soon as the pointer leaves. */
const TOOLTIP_DELAY_MS = 400

function TooltipProvider({
  delayDuration = TOOLTIP_DELAY_MS,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return (
    <TooltipPrimitive.Provider
      data-slot="tooltip-provider"
      delayDuration={delayDuration}
      {...props}
    />
  )
}

function Tooltip({
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />
}

/** Frosting: around an element of its own (asChild) the trigger leaves that element its data-slot (a badge stays a
 *  badge); there is not even an undefined key for it then, which would still clear the element's own. */
function TooltipTrigger({
  asChild,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger {...(asChild ? { asChild } : { "data-slot": "tooltip-trigger" })} {...props} />
}

/** Frosting (DESIGN.md §6): the look of every text shown on hover, this tooltip's and the charts' hover box's
 *  (ChartTooltipContent): the page's colours swapped (the text colour as its background, the page colour as its
 *  text), small text that starts at the left edge, as all other text does. TooltipContent stacks its lines, each from
 *  the left edge (shadcn's row centred its items, which centred every line once a tooltip stacked them). */
const tooltipSurface = "rounded-md bg-foreground px-3 py-1.5 text-left text-xs text-background"

function TooltipContent({
  className,
  sideOffset = 0,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 flex w-fit max-w-xs origin-(--radix-tooltip-content-transform-origin) flex-col items-start gap-1 has-data-[slot=kbd]:pr-1.5 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 **:data-[slot=kbd]:relative **:data-[slot=kbd]:isolate **:data-[slot=kbd]:z-50 **:data-[slot=kbd]:rounded-sm data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0 data-[state=delayed-open]:zoom-in-95 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          tooltipSurface,
          className
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="z-50 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45 rounded-[2px] bg-foreground fill-foreground" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  )
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger, tooltipSurface }
