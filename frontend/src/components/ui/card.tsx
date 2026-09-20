import * as React from "react";

import { cn } from "@/lib/utils";

export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & {
    accent?: boolean;
    variant?: "default" | "dark" | "light";
  }
>(({ className, accent = false, variant = "default", ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-[10px] border bg-card text-card-foreground",
      "shadow-[0_1px_2px_hsl(var(--primary)/0.05),0_6px_20px_-8px_hsl(var(--primary)/0.12)]",
      accent && "card-accent",
      // Intentional surfaces only: dark navy for hero/summary surfaces, the
      // subtle white→light-blue gradient for dense readable content. `light`
      // reuses the shared `card-hero` surface — one definition, no copies.
      variant === "dark" && "card-dark border-white/15 text-primary-foreground",
      variant === "light" && "card-hero",
      className,
    )}
    {...props}
  />
));
Card.displayName = "Card";

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5 p-6", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-lg font-semibold leading-none", className)} {...props} />;
}

export function CardDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}
