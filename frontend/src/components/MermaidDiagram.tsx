import { useEffect, useState } from 'react';

// Draws a ```mermaid block (spec 05 T6). mermaid loads only when a diagram is on screen, so the main bundle stays
// small. It runs with securityLevel "strict": labels are sanitised and click handlers and scripts are disabled, which
// is what makes inserting its SVG safe. If a diagram cannot be drawn, its source shows instead.

let counter = 0;

export default function MermaidDiagram({ code, fallback }: { code: string; fallback: JSX.Element }) {
  const [svg, setSvg] = useState('');
  const [failed, setFailed] = useState(false);
  const [showSource, setShowSource] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    import('mermaid')
      .then(async ({ default: mermaid }) => {
        // The app is dark whatever the system setting, so the diagram is too.
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'dark' });
        const { svg: drawn } = await mermaid.render(`itos-diagram-${++counter}`, code);
        if (!cancelled) setSvg(drawn);
      })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [code]);

  if (failed) return fallback;
  return (
    <figure className="diagram">
      {svg ? <div className="diagram-svg" dangerouslySetInnerHTML={{ __html: svg }} /> : <p className="muted">Drawing the diagram…</p>}
      <button className="ghost" onClick={() => setShowSource((s) => !s)}>{showSource ? 'Hide source' : 'Show source'}</button>
      {showSource && fallback}
    </figure>
  );
}
