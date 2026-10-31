/**
 * D50: a chat's side panel (a video's plan and settings, a campaign's tasks and budget) is a drawer, closed by default,
 * so the chat has the room. On a wide screen (1500px and more) an open panel sits beside the chat; narrower, it slides
 * over it and Escape closes it. The choice is remembered on this device.
 */
import { useCallback, useEffect, useState } from "react";

const KEY = "itos.chat.side";

export function useSidePanel() {
  const [open, setOpen] = useState(() => {
    try {
      return window.localStorage.getItem(KEY) === "open";
    } catch {
      return false;
    }
  });
  const toggle = useCallback(() => {
    setOpen((was) => {
      try {
        window.localStorage.setItem(KEY, was ? "closed" : "open");
      } catch {
        // a private window: the drawer still opens, it is just not remembered
      }
      return !was;
    });
  }, []);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && window.matchMedia("(max-width: 1499px)").matches) toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, toggle]);
  return { open, toggle };
}
