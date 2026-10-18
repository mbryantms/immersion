import type { ComponentProps } from "react";
import { ToggleGroup } from "radix-ui";
import { cn } from "@/lib/utils";

export function FilterGroup({ className, ...props }: ComponentProps<typeof ToggleGroup.Root>) {
  return <ToggleGroup.Root {...props} className={cn("inline-flex flex-wrap items-center gap-1 rounded-xl bg-muted/60 p-1", className)} />;
}

export function FilterOption({ className, ...props }: ComponentProps<typeof ToggleGroup.Item>) {
  return <ToggleGroup.Item {...props} className={cn("inline-flex min-h-9 items-center justify-center rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm", className)} />;
}
