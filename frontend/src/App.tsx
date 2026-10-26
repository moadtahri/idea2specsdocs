import { useEffect, useState } from 'react';
import { api, type ProjectSummary } from './api';
import Chat from './components/Chat';

export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');

  const refresh = () =>
    api
      .listProjects()
      .then(setProjects)
      .catch(() => setError('Backend unreachable — start it with: cd backend && uv run uvicorn app.main:app --reload'));

  useEffect(() => {
    void refresh();
  }, []);

  const create = async () => {
    const t = title.trim();
    if (!t) return;
    try {
      const p = await api.createProject(t);
      setTitle('');
      await refresh();
      setCurrent(p.project_id);
    } catch {
      setError('Could not create project.');
    }
  };

  return (
    <div className="app">
      <header>
        <h1>idea2specsdocs</h1>
        <p>brainstorm with an agent → 9 handover docs, remembered in SQLite</p>
      </header>
      {error && <div className="error">{error}</div>}
      <div className="projects">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void create()}
          placeholder="New project title…"
        />
        <button onClick={() => void create()}>New project</button>
        <select value={current ?? ''} onChange={(e) => setCurrent(e.target.value || null)}>
          <option value="">— pick a project to resume —</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.title}
            </option>
          ))}
        </select>
      </div>
      {current ? (
        <Chat key={current} projectId={current} />
      ) : (
        <p className="empty">Create or pick a project to start brainstorming.</p>
      )}
    </div>
  );
}
