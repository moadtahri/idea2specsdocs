/**
 * The sidebar, as in Kanya's app (spec 09): the itos name, New project, the projects (the open one marked), and the
 * theme. Folded to a rail in a chat, each project shows as its first letter and its name on hover.
 */
import type { ProjectSummary } from "../../api";
import { useTheme, type ThemeChoice } from "../../theme";
import { WiziFace } from "../WiziFace";

const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: "system", label: "Auto" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function Sidebar({
  projects,
  current,
  onOpen,
  onNew,
  rail = false,
  onToggleRail,
  onNavigate,
}: {
  projects: ProjectSummary[];
  current: string | null;
  onOpen: (projectId: string) => void;
  onNew: () => void;
  rail?: boolean;
  onToggleRail?: () => void;
  onNavigate?: () => void;
}) {
  const [theme, setTheme] = useTheme();
  const open = projects.find((project) => project.project_id === current);

  return (
    <div className="sidebar-inner">
      <div className="brand">
        <WiziFace className="brand-mark" size={26} state="still" />
        <span className="brand-name">itos</span>
        {onToggleRail && (
          <button
            type="button"
            className="rail-toggle"
            aria-label={rail ? "Open the sidebar" : "Fold the sidebar"}
            aria-expanded={!rail}
            title={rail ? "Open the sidebar" : "Fold the sidebar"}
            onClick={onToggleRail}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
              <path d="M9.5 4.5v15" stroke="currentColor" strokeWidth="1.7" />
            </svg>
          </button>
        )}
      </div>

      {rail && open && (
        <button
          type="button"
          className="rail-site"
          title={`${open.title}: open the sidebar to see every project`}
          aria-label={`Project ${open.title}. Open the sidebar to see every project.`}
          onClick={onToggleRail}
        >
          {open.title.trim().charAt(0).toUpperCase() || "?"}
        </button>
      )}

      <nav aria-label="Projects" className="nav">
        <ul>
          <li>
            <a
              href="#new"
              className={`nav-link${current === null ? " active" : ""}`}
              title={rail ? "New project" : undefined}
              onClick={(event) => {
                event.preventDefault();
                onNew();
                onNavigate?.();
              }}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                <path {...stroke} d="M12 5v14M5 12h14" />
              </svg>
              <span className="nav-label">New project</span>
            </a>
          </li>
          {projects.map((project) => (
            <li key={project.project_id}>
              <a
                href={`#${project.project_id}`}
                className={`nav-link${project.project_id === current ? " active" : ""}`}
                aria-current={project.project_id === current ? "page" : undefined}
                title={rail ? project.title : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  onOpen(project.project_id);
                  onNavigate?.();
                }}
              >
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
                  <path {...stroke} d="M5 5.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4.5 3.5V16.5H5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z" />
                </svg>
                <span className="nav-label">{project.title}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-foot">
        <div className="theme-switch" role="radiogroup" aria-label="Theme">
          {THEMES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={theme === option.value}
              className={theme === option.value ? "on" : undefined}
              onClick={() => setTheme(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
