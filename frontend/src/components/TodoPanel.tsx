import type { TodoItem } from '../api';

export default function TodoPanel({
  todos,
  streaming,
}: {
  todos: TodoItem[];
  streaming: boolean;
}) {
  if (todos.length === 0) {
    if (!streaming) return null;
    return (
      <div className="todos">
        <span className="spin">⟳</span> wizi is preparing your request…
      </div>
    );
  }
  const done = todos.filter((t) => t.status === 'completed').length;
  const pct = Math.round((done / todos.length) * 100);
  const icon = (s: string) =>
    s === 'completed' ? '✓' : s === 'in_progress' ? '◉' : '○';
  return (
    <div className="todos">
      <div className="todos-head">
        <strong>wizi’s plan</strong>
        <span>
          {done}/{todos.length} · {pct}%
        </span>
      </div>
      <div className="bar">
        <div className="fill" style={{ width: `${pct}%` }} />
      </div>
      <ul>
        {todos.map((t, i) => (
          <li key={i} className={t.status}>
            <span className="ico">{icon(t.status)}</span>
            <span>{t.content}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
