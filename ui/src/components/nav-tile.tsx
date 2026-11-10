import { cn } from "@/lib/utils";

/** The look of a filter or menu tile: the report list's kind selector, and the home page's menu. */
export function tileClassName(active: boolean): string {
  return cn(
    "flex items-baseline gap-2 border border-border bg-secondary px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground",
    active && "border-primary text-foreground shadow-[0_0_14px_rgb(240_138_36/0.35)]",
  );
}
