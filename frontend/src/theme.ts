/** Light, dark, or the system's choice: set as data-theme on <html> (tokens.css reads it), remembered here. */
import { useCallback, useEffect, useState } from "react";

import { readStored, writeStored } from "./lib/storage";

export type ThemeChoice = "system" | "light" | "dark";

function stored(): ThemeChoice {
  const value = readStored("theme");
  return value === "light" || value === "dark" ? value : "system";
}

function apply(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

/** Apply the remembered theme before React renders, so the page never flashes the wrong one. */
export function applyStoredTheme(): void {
  apply(stored());
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(stored);
  useEffect(() => apply(choice), [choice]);
  const choose = useCallback((next: ThemeChoice) => {
    setChoice(next);
    writeStored("theme", next === "system" ? null : next);
  }, []);
  return [choice, choose];
}
