"use client";

import { Circle, Moon, Sun } from "lucide-react";
import { applyTheme, useTheme, type Theme } from "@/lib/theme";

const themes: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "amoled", label: "AMOLED", icon: Circle },
];

export default function ThemeToggle() {
  const theme = useTheme();

  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      {themes.map(({ value, label, icon: Icon }) => (
        <button
          type="button"
          key={value}
          className={theme === value ? "active" : ""}
          aria-pressed={theme === value}
          title={`${label} theme`}
          onClick={() => applyTheme(value)}
        >
          <Icon size={13} fill={value === "amoled" ? "currentColor" : "none"} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
