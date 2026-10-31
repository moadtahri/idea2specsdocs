import { useEffect, useState } from 'react';
import { api, type ProjectSummary } from './api';
import Chat from './components/Chat';

export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [error, setError] = useState('');
  const [action, setAction] = useState<'rename' | null>(null);
  const [projectName, setProjectName] = useState('');
  const [managing, setManaging] = useState(false);
  const [actionError, setActionError] = useState('');

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

  const create = async () => {
    const t = title.trim();
    if (!t) return;
    try {
      const p = await api.createProject(t);
      setTitle('');
      await refresh();
      setCurrent(p.project_id);
      setAction(null);
      setActionError('');
    } catch {
      setError('Could not create project.');
    }
  };

  const manageProject = async () => {
    if (!current || !action || managing) return;
    setManaging(true);
    setActionError('');
    try {
      const updated = await api.renameProject(current, projectName.trim());
      setProjects((all) => all.map((project) => project.project_id === current ? updated : project));
      setAction(null);
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : 'Could not update the project. Please try again.');
    } finally {
      setManaging(false);
    }
  };

  const deleteSelectedProject = async () => {
    if (!current || managing) return;
    const projectId = current;
    setManaging(true);
    setAction(null);
    setActionError('');
    try {
      await api.deleteProject(projectId);
      setProjects((all) => all.filter((project) => project.project_id !== projectId));
      setCurrent(null);
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : 'Could not delete the project. Please try again.');
    } finally {
      setManaging(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>itos</h1>
        <p>Brainstorm with wizi and turn ideas into implementation-ready handover docs.</p>
      </header>
      {error && <div className="error">{error}</div>}
      <div className="projects">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void create()}
          placeholder="New project title…"
        />
        <button disabled={managing} onClick={() => void create()}>New project</button>
        <select aria-label="Current project" disabled={managing} value={current ?? ''} onChange={(e) => { setCurrent(e.target.value || null); setAction(null); setActionError(''); }}>
          <option value="">— pick a project to resume —</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.title}
            </option>
          ))}
        </select>
        <button className="ghost" disabled={!current || managing} onClick={() => {
          setProjectName(projects.find((project) => project.project_id === current)?.title ?? '');
          setAction('rename'); setActionError('');
        }}>Rename</button>
        <button className="ghost" disabled={!current || managing} onClick={() => void deleteSelectedProject()}>{managing && !action ? 'Deleting…' : 'Delete'}</button>
      </div>
      {actionError && !action && <div className="error" role="alert">{actionError}</div>}
      {action && <section className="project-action" aria-label="Rename project">
          <label htmlFor="project-name">Project name</label>
          <input id="project-name" autoFocus maxLength={200} value={projectName} disabled={managing} onChange={(event) => setProjectName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && projectName.trim()) void manageProject(); }} />
        {actionError && <div className="error" role="alert">{actionError}</div>}
        <div className="row">
          <button disabled={managing || !projectName.trim()} onClick={() => void manageProject()}>{managing ? 'Working…' : 'Save name'}</button>
          <button className="ghost" disabled={managing} onClick={() => { setAction(null); setActionError(''); }}>Cancel</button>
        </div>
      </section>}
      {current ? (
        <Chat key={current} projectId={current} />
      ) : (
        <p className="empty">Create or pick a project to start brainstorming.</p>
      )}
    </div>
  );
}
