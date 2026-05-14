import { useEffect } from "react";

export function useTheme() {
  useEffect(() => {
    // Always light theme — remove any stale dark-mode class/attr
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
  }, []);
}
