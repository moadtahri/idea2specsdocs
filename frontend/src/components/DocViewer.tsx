import { useEffect, useState } from 'react';
import { api, type DocMeta, type PackageChecks } from '../api';
import Markdown from './Markdown';

export default function DocViewer({
  projectId,
  refreshKey,
  collapsed,
  onCollapse,
}: {
  projectId: string;
  refreshKey: number;
  collapsed: boolean;
  onCollapse: () => void;
}) {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState('');
  const [loadedSlug, setLoadedSlug] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copying' | 'copied' | 'failed'>('idle');
  const [checks, setChecks] = useState<PackageChecks | null>(null);
  const [questionsNote, setQuestionsNote] = useState('');
  const hasPackage = docs.some((d) => d.updated_at && !d.slug.startsWith('bundle'));

  useEffect(() => {
    if (!hasPackage) { setChecks(null); return; }
    let cancelled = false;
    api.packageChecks(projectId)
      .then((c) => { if (!cancelled) setChecks(c); })
      .catch(() => { if (!cancelled) setChecks(null); });
    return () => { cancelled = true; };
  }, [projectId, refreshKey, hasPackage]);

  const bringBackQuestions = async (file: File | undefined) => {
    if (!file) return;
    setQuestionsNote('Reading questions…');
    try {
      const result = await api.returnQuestions(projectId, await file.text());
      const added = result.created.length;
      const known = result.existing.length;
      setQuestionsNote(
        added === 0 && known === 0
          ? 'No open questions in that file.'
          : `${added} new question${added === 1 ? '' : 's'} added to the decisions${known ? `, ${known} already there` : ''}. Ask wizi to go through them.`,
      );
    } catch (e) {
      setQuestionsNote(e instanceof Error ? e.message : 'Could not read that file.');
    }
  };

  useEffect(() => setCopyStatus('idle'), [markdown]);

  useEffect(() => {
    if (copyStatus !== 'copied') return;
    const timer = setTimeout(() => setCopyStatus('idle'), 2500);
    return () => clearTimeout(timer);
  }, [copyStatus]);

  const copyContent = async () => {
    if (!markdown || loading || loadedSlug !== active) return;
    setCopyStatus('copying');
    try {
      await navigator.clipboard.writeText(markdown);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
    }
  };

  useEffect(() => {
    let cancelled = false;
    api
      .listDocs(projectId)
      .then((r) => {
        if (cancelled) return;
        setDocs(r.docs);
        const bundle = r.docs.find((d) => d.slug === 'bundle' && d.updated_at);
        const ready = bundle ?? r.docs.find((d) => d.updated_at);
        if (ready) setActive((selected) => selected ?? ready.slug);
      })
      .catch(() => { if (!cancelled) setDocs([]); });
    return () => { cancelled = true; };
  }, [projectId, refreshKey]);

  useEffect(() => {
    if (!active || collapsed) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    setMarkdown('');
    setLoadedSlug(null);
    api
      .readDoc(projectId, active)
      .then((d) => { if (!cancelled) { setMarkdown(d.markdown); setLoadedSlug(active); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the document.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, active, refreshKey, retry, collapsed]);

  return (
    <aside className="docs" hidden={collapsed}>
      <div className="docs-head"><h3>Handover docs</h3><button className="ghost" onClick={onCollapse} aria-label="Hide handover docs" aria-expanded={true}>Collapse</button></div>
      <p className="muted">The agent package is what a coding agent builds from: a skill, the specs and these documents, to unzip at the root of the repository. The readable bundle explains the contracts in plain language.</p>
      {hasPackage && (
        <div className="package-tools">
          <a href={`/api/projects/${projectId}/package`} download>
            <button className="ghost">Download agent package (.zip)</button>
          </a>
          {checks && (checks.findings.length === 0
            ? <p className="muted">Package checks: every task can be verified and every link resolves.</p>
            : <details className="package-checks">
                <summary>
                  Package checks: {checks.blockers > 0 && <strong>{checks.blockers} to fix</strong>}
                  {checks.blockers > 0 && checks.warnings > 0 && ', '}
                  {checks.warnings > 0 && `${checks.warnings} to look at`}
                </summary>
                <ul>
                  {checks.findings.map((f, i) => (
                    <li key={i} className={f.severity}><code>{f.file}</code>: {f.message}</li>
                  ))}
                </ul>
              </details>)}
          <label className="file-pick">
            Bring back questions.md
            <input type="file" accept=".md,text/markdown,text/plain" hidden
              onChange={(e) => { void bringBackQuestions(e.target.files?.[0]); e.target.value = ''; }} />
          </label>
          {questionsNote && <p role="status" className="muted">{questionsNote}</p>}
        </div>
      )}
      <ul>
        {docs.map((d) => (
          <li key={d.slug}>
            <button
              className={d.slug === active ? 'on' : ''}
              onClick={() => setActive(d.slug)}
              title={d.updated_at ?? 'not generated'}
            >
              {d.updated_at ? '●' : '○'} {d.title}{d.status && <small> · {d.status.replace('_', ' ')}</small>}
            </button>
          </li>
        ))}
      </ul>
      {loading && <p role="status">Preparing your document…</p>}
      {error && <div className="error">{error} <button className="ghost" onClick={() => setRetry((n) => n + 1)}>Retry</button></div>}
      {markdown && loadedSlug === active && <>
        <div className="doc-actions">
          <button className="ghost" disabled={loading || copyStatus === 'copying'} onClick={() => void copyContent()}>
            {copyStatus === 'copied' ? 'Copied!' : copyStatus === 'copying' ? 'Copying…' : 'Copy content'}
          </button>
          <span role="status" className="muted">{copyStatus === 'copied' ? 'Document copied to clipboard.' : copyStatus === 'failed' ? 'Could not copy. Allow clipboard access in your browser and try again.' : ''}</span>
        </div>
        <Markdown text={markdown} className="md" />
      </>}
      {active && markdown && loadedSlug === active && !loading && (
        <a href={`/api/projects/${projectId}/docs/${active}/download`}>
          <button className="ghost">Download .md</button>
        </a>
      )}
    </aside>
  );
}
