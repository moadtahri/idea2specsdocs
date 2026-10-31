/** D50: the header's button for a chat's side panel (see `useSidePanel`). */
/** The header's button for the drawer: its name and, when there is one, a count ("2/4"). */
export function SideToggle({
  open,
  onToggle,
  label,
  count,
}: {
  open: boolean;
  onToggle: () => void;
  label: string;
  count?: string;
}) {
  return (
    <button
      type="button"
      className={`side-toggle${open ? " on" : ""}`}
      aria-expanded={open}
      aria-controls="chat-side"
      onClick={onToggle}
    >
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <path d="M14.5 4.5v15" stroke="currentColor" strokeWidth="1.7" />
      </svg>
      {label}
      {count && <span className="side-toggle-count">{count}</span>}
    </button>
  );
}
