import { useEffect, useState } from 'react';
import { api, type DocMeta, type PackageChecks } from '../api';
import type { ReaderContent } from './chat/chatTools';

// The documents in the side panel (spec 09): each opens in the reader, as Kanya's long replies do; the agent package,
// its checks and the questions coming back stay here.
export default function DocViewer({
  projectId,
  refreshKey,
  onOpen,
}: {
  projectId: string;
  refreshKey: number;
  onOpen: (content: ReaderContent) => void;
}) {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [checks, setChecks] = useState<PackageChecks | null>(null);
  const [questionsNote, setQuestionsNote] = useState('');
  const hasPackage = docs.some((d) => d.updated_at && !d.slug.startsWith('bundle'));

  useEffect(() => {
    let cancelled = false;
    api
      .listDocs(projectId)
      .then((r) => { if (!cancelled) setDocs(r.docs); })
      .catch(() => { if (!cancelled) setDocs([]); });
    return () => { cancelled = true; };
  }, [projectId, refreshKey]);

  useEffect(() => {
    if (!hasPackage) { setChecks(null); return; }
    let cancelled = false;
    api.packageChecks(projectId)
      .then((c) => { if (!cancelled) setChecks(c); })
      .catch(() => { if (!cancelled) setChecks(null); });
    return () => { cancelled = true; };
  }, [projectId, refreshKey, hasPackage]);

  const open = async (doc: DocMeta) => {
    if (!doc.updated_at || opening) return;
    setOpening(doc.slug);
    setError('');
    try {
      const content = await api.readDoc(projectId, doc.slug);
      onOpen({ kind: 'doc', title: doc.title, text: content.markdown });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not open the document.');
    } finally {
      setOpening(null);
    }
  };

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

  return (
    <section className="panel docs-panel" aria-labelledby="docs-title">
      <header className="panel-header">
        <h2 id="docs-title">Handover docs</h2>
      </header>
      <p className="muted small">
        The agent package is what a coding agent builds from: a skill, the specs and these documents, to unzip at the
        root of the repository. The readable bundle explains the contracts in plain language.
      </p>
      {hasPackage && (
        <div className="package-tools">
          <a className="button primary small" href={`/api/projects/${projectId}/package`} download>
            Download agent package (.zip)
          </a>
          {checks && (checks.findings.length === 0
            ? <p className="muted small">Package checks: every task can be verified and every link resolves.</p>
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
          <label className="button ghost small file-pick">
            Bring back questions.md
            <input type="file" accept=".md,text/markdown,text/plain" hidden
              onChange={(e) => { void bringBackQuestions(e.target.files?.[0]); e.target.value = ''; }} />
          </label>
          {questionsNote && <p role="status" className="muted small">{questionsNote}</p>}
        </div>
      )}
      <ul className="doc-list">
        {docs.map((d) => (
          <li key={d.slug}>
            <button
              type="button"
              className="doc-row"
              disabled={!d.updated_at || opening !== null}
              onClick={() => void open(d)}
              title={d.updated_at ? `Open ${d.title}` : 'Not written yet'}
            >
              <span className={`doc-dot${d.updated_at ? ' ready' : ''}`} aria-hidden="true" />
              <span className="doc-name">{d.title}</span>
              <span className="muted small">{opening === d.slug ? 'Opening…' : d.updated_at ? (d.status ?? '').replace('_', ' ') : 'missing'}</span>
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="form-error small" role="alert">{error}</p>}
    </section>
  );
}
