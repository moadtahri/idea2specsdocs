import { useEffect, useState } from 'react';
import { api, type ProjectSummary } from './api';
import Chat from './components/Chat';
import { AppLayout } from './components/layout/AppLayout';
import { Sidebar } from './components/layout/Sidebar';

// The app as Kanya's (spec 09): the projects in the sidebar, the chat beside it; no project open shows the start page.
export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [error, setError] = useState('');

  const refresh = () =>
    api
      .listProjects()
      .then((p) => {
        setProjects(p);
        setError('');
      })
      .catch(() => setError('itos cannot reach the server. Please check that the app is running and try again.'));

  useEffect(() => {
    void refresh();
    const t = setInterval(() => {
      void refresh();
    }, 10000);
    return () => clearInterval(t);
  }, []);

  const created = async (projectId: string) => {
    await refresh();
    setCurrent(projectId);
  };

  const renamed = (updated: ProjectSummary) =>
    setProjects((all) => all.map((project) => (project.project_id === updated.project_id ? updated : project)));

  const deleted = (projectId: string) => {
    setProjects((all) => all.filter((project) => project.project_id !== projectId));
    setCurrent(null);
  };

  const project = projects.find((p) => p.project_id === current) ?? null;

  return (
    <AppLayout
      inChat={current !== null}
      page={current ?? 'home'}
      sidebar={(slot) => (
        <Sidebar projects={projects} current={current} onOpen={setCurrent} onNew={() => setCurrent(null)} {...slot} />
      )}
    >
      {error && <p className="form-error banner" role="alert">{error}</p>}
      {current ? (
        <Chat key={current} projectId={current} project={project} onRenamed={renamed} onDeleted={deleted} />
      ) : (
        <StartPage onCreated={created} />
      )}
    </AppLayout>
  );
}

function StartPage({ onCreated }: { onCreated: (projectId: string) => Promise<void> }) {
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');

  const create = async () => {
    const name = title.trim();
    if (!name || busy) return;
    setBusy(true);
    setProblem('');
    try {
      const p = await api.createProject(name);
      setTitle('');
      await onCreated(p.project_id);
    } catch {
      setProblem('Could not create the project. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>Start a project</h1>
        <p className="lede">
          Tell wizi your idea, or bring your code and a change you want. It asks what only you can answer, writes the
          documents and specs, and never saves anything without your approval.
        </p>
      </header>
      <form className="panel start-form" onSubmit={(event) => { event.preventDefault(); void create(); }}>
        <div className="field">
          <label htmlFor="new-project-title">Project name</label>
          <input
            id="new-project-title"
            value={title}
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="New project title…"
          />
        </div>
        <div className="button-row">
          <button type="submit" className="button primary" disabled={busy || !title.trim()}>
            {busy ? 'Creating…' : 'New project'}
          </button>
        </div>
        {problem && <p className="form-error" role="alert">{problem}</p>}
      </form>
    </div>
  );
}
