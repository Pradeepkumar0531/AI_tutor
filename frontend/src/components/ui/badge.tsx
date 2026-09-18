import { cn } from "@/lib/utils";

const tones: Record<string, string> = {
  // Blue/white-only system: positive states use the primary tint, caution
  // uses a neutral slate tint; only genuine errors use destructive red.
  default: "bg-secondary text-secondary-foreground",
  success: "bg-[hsl(var(--primary)/0.1)] text-primary",
  warning: "bg-muted text-foreground",
  danger: "bg-destructive/10 text-destructive",
  info: "bg-[hsl(var(--primary)/0.08)] text-primary",
};

export function Badge({
  tone = "default",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
