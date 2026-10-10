import { useEffect, useState } from "react";

/** Follows the `dark` class on <html> (set by useTheme), so charts can redraw in the right colours. */
export function useIsDark(): boolean {
  const read = () => document.documentElement.classList.contains("dark");
  const [dark, setDark] = useState(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}
