/**
 * CH-1228: the reader on the right of a chat (a long reply as a document, or a reply's sources). Its left edge drags
 * to change its width, from 320px to 70% of the window (arrow keys on the edge too, double-click for the default);
 * the width is remembered on this device. Escape closes it.
 */
import { useCallback, useEffect, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent } from "react";

import type { ReaderContent } from "./chatTools";

const WIDTH_KEY = "itos.chat.reader.width";
const MIN_WIDTH = 320;
const DEFAULT_WIDTH = 480;

const maxWidth = () => Math.max(MIN_WIDTH, Math.round(window.innerWidth * 0.7));
const clamp = (value: number) => Math.round(Math.min(maxWidth(), Math.max(MIN_WIDTH, value)));

function storedWidth(): number {
  try {
    const saved = Number(window.localStorage.getItem(WIDTH_KEY));
    return saved ? clamp(saved) : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

export interface Reader {
  content: ReaderContent | null;
  open: (content: ReaderContent) => void;
  close: () => void;
  width: number;
  max: number;
  min: number;
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLDivElement>) => void;
  reset: () => void;
}

export function useReader(): Reader {
  const [content, setContent] = useState<ReaderContent | null>(null);
  const [width, setWidth] = useState(storedWidth);
  const keep = useCallback((value: number) => {
    const next = clamp(value);
    setWidth(next);
    try {
      window.localStorage.setItem(WIDTH_KEY, String(next));
    } catch {
      // a private window: the width holds until the page closes
    }
  }, []);
  const close = useCallback(() => setContent(null), []);

  useEffect(() => {
    if (!content) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setContent(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [content]);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("resizing-reader");
    // The reader sits at the window's right edge: its width is what is right of the pointer.
    const right = handle.parentElement?.getBoundingClientRect().right ?? window.innerWidth;
    const move = (moved: globalThis.PointerEvent) => setWidth(clamp(right - moved.clientX));
    const up = (released: globalThis.PointerEvent) => {
      keep(right - released.clientX);
      document.body.classList.remove("resizing-reader");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 64 : 24;
    if (event.key === "ArrowLeft") keep(width + step);
    else if (event.key === "ArrowRight") keep(width - step);
    else if (event.key === "Home") keep(maxWidth());
    else if (event.key === "End") keep(MIN_WIDTH);
    else return;
    event.preventDefault();
  };

  return {
    content,
    open: setContent,
    close,
    width,
    max: maxWidth(),
    min: MIN_WIDTH,
    onPointerDown,
    onKeyDown,
    reset: () => keep(DEFAULT_WIDTH),
  };
}
