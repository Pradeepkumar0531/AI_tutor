import * as React from "react";

/**
 * Returns true once `active` has stayed true for `delayMs`. Used for the
 * optional "still loading…" hint on legitimately slow requests. One timer per
 * call site, always cleaned up. Never fakes progress.
 */
export function useSlowHint(active: boolean, delayMs = 4000): boolean {
  const [slow, setSlow] = React.useState(false);
  React.useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    setSlow(false);
    const t = setTimeout(() => setSlow(true), delayMs);
    return () => clearTimeout(t);
  }, [active, delayMs]);
  return slow;
}
