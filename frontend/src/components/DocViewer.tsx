import { useEffect, useState } from 'react';
import { api, type DocMeta } from '../api';

export default function DocViewer({
  projectId,
  refreshKey,
}: {
  projectId: string;
  refreshKey: number;
}) {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState('');

  useEffect(() => {
    api
      .listDocs(projectId)
      .then((r) => {
        setDocs(r.docs);
        const ready = r.docs.find((d) => d.updated_at);
        if (ready && !active) {
          setActive(ready.slug);
        }
      })
      .catch(() => setDocs([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, refreshKey]);

  useEffect(() => {
    if (!active) return;
    api
      .readDoc(projectId, active)
      .then((d) => setMarkdown(d.markdown))
      .catch(() => setMarkdown('*Not generated yet.*'));
  }, [projectId, active, refreshKey]);

  return (
    <aside className="docs">
      <h3>Handover docs</h3>
      <ul>
        {docs.map((d) => (
          <li key={d.slug}>
            <button
              className={d.slug === active ? 'on' : ''}
              onClick={() => setActive(d.slug)}
              title={d.updated_at ?? 'not generated'}
            >
              {d.updated_at ? '●' : '○'} {d.title}
            </button>
          </li>
        ))}
      </ul>
      <pre className="md">{markdown}</pre>
      {active && (
        <a href={`/api/projects/${projectId}/docs/${active}/download`}>
          <button className="ghost">Download .md</button>
        </a>
      )}
    </aside>
  );
}
