"use client";

import { useEffect, useState } from "react";

export type Theme = "light" | "dark" | "amoled";

export const themeValues: Theme[] = ["light", "dark", "amoled"];

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("regora-theme", theme);
  window.dispatchEvent(new CustomEvent("regora-theme", { detail: theme }));
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const read = () => {
      const current = document.documentElement.dataset.theme as Theme;
      setTheme(themeValues.includes(current) ? current : "dark");
    };
    read();
    window.addEventListener("regora-theme", read);
    return () => window.removeEventListener("regora-theme", read);
  }, []);

  return theme;
}
