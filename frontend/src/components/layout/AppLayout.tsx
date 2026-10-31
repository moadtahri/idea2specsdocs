/**
 * The frame of every page, as in Kanya's app (spec 09): the sidebar (a drawer on narrow screens) and the page beside
 * it. In a project's chat the sidebar folds to a rail of icons so the chat has the room; the panel button
 * opens or folds it, and the choice is remembered on this device, for chats and for other pages apart. Open, its edge
 * drags to change its width (200-420px; arrow keys on the edge too, double-click for the default), also remembered.
 */
import {
  useCallback,
  useEffect,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";

function stored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

const WIDTH_KEY = "itos.sidebar.width";
const MIN_WIDTH = 200;
const MAX_WIDTH = 420;
const DEFAULT_WIDTH = 264;

const clampWidth = (value: number) => Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, value)));

/** The open sidebar's width, dragged from its edge and remembered on this device. */
function useSidebarWidth() {
  const [width, setWidth] = useState(() => {
    const saved = Number(stored(WIDTH_KEY));
    return saved ? clampWidth(saved) : DEFAULT_WIDTH;
  });
  const keep = useCallback((value: number) => {
    const next = clampWidth(value);
    setWidth(next);
    try {
      window.localStorage.setItem(WIDTH_KEY, String(next));
    } catch {
      // a private window: the width holds until the page closes
    }
  }, []);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("resizing-sidebar");
    const move = (moved: globalThis.PointerEvent) => setWidth(clampWidth(moved.clientX));
    const up = (released: globalThis.PointerEvent) => {
      keep(released.clientX);
      document.body.classList.remove("resizing-sidebar");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 40 : 16;
    if (event.key === "ArrowLeft") keep(width - step);
    else if (event.key === "ArrowRight") keep(width + step);
    else if (event.key === "Home") keep(MIN_WIDTH);
    else if (event.key === "End") keep(MAX_WIDTH);
    else return;
    event.preventDefault();
  };
  return { width, onPointerDown, onKeyDown, reset: () => keep(DEFAULT_WIDTH) };
}

/** Whether the sidebar is a rail on this page: in a chat by default, elsewhere only when the user folded it. */
function useRail(inChat: boolean): [boolean, () => void] {
  const kind = inChat ? "chat" : "page";
  const key = `itos.sidebar.${kind}`;
  const [choices, setChoices] = useState<Record<string, string | null>>(() => ({
    chat: stored("itos.sidebar.chat"),
    page: stored("itos.sidebar.page"),
  }));
  const choice = choices[kind];
  const rail = choice ? choice === "rail" : kind === "chat";
  const toggle = useCallback(() => {
    const next = rail ? "full" : "rail";
    try {
      window.localStorage.setItem(key, next);
    } catch {
      // not remembered in a private window; the sidebar still folds
    }
    setChoices((previous) => ({ ...previous, [kind]: next }));
  }, [rail, key, kind]);
  return [rail, toggle];
}

export interface SidebarSlot {
  rail: boolean;
  onToggleRail: () => void;
  onNavigate: () => void;
}

/** `page` changes when the user moves to another page (a project or home): the drawer closes then. */
export function AppLayout({
  inChat,
  page,
  sidebar: renderSidebar,
  children,
}: {
  inChat: boolean;
  page: string;
  sidebar: (slot: SidebarSlot) => ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [rail, toggleRail] = useRail(inChat);
  const sidebar = useSidebarWidth();
  useEffect(() => setOpen(false), [page]);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div
      className={`app${open ? " drawer-open" : ""}${rail ? " rail" : ""}`}
      style={{ "--sidebar-width": `${sidebar.width}px` } as CSSProperties}
    >
      <a className="skip-link" href="#main">
        Skip to the page
      </a>
      <header className="topbar">
        <button
          type="button"
          className="menu-button"
          aria-expanded={open}
          aria-controls="sidebar"
          onClick={() => setOpen(!open)}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path
              d="M4 7h16M4 12h16M4 17h16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
          <span className="visually-hidden">Menu</span>
        </button>
        <span className="brand-name">itos</span>
      </header>
      <aside id="sidebar" className="sidebar">
        {renderSidebar({ rail, onToggleRail: toggleRail, onNavigate: () => setOpen(false) })}
      </aside>
      {!rail && (
        <div
          className="sidebar-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Sidebar width"
          aria-controls="sidebar"
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={MAX_WIDTH}
          aria-valuenow={sidebar.width}
          tabIndex={0}
          title="Drag to resize; double-click for the default width"
          onPointerDown={sidebar.onPointerDown}
          onKeyDown={sidebar.onKeyDown}
          onDoubleClick={sidebar.reset}
        />
      )}
      {open && <div className="scrim" aria-hidden="true" onClick={() => setOpen(false)} />}
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
