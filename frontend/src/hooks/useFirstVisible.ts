import * as React from "react";

/**
 * First-visibility gate for below-fold sections. In browsers the flag flips
 * when the element nears the viewport (200px prefetch margin); where
 * IntersectionObserver does not exist (jsdom/tests, old browsers) it is true
 * immediately so data loading never depends on observer support.
 */
export function useFirstVisible<T extends HTMLElement>(): [
  React.MutableRefObject<T | null>,
  boolean,
] {
  const ref = React.useRef<T | null>(null);
  const [visible, setVisible] = React.useState(() => typeof IntersectionObserver === "undefined");

  React.useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, visible];
}
