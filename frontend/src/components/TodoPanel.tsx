import type { TodoItem } from '../api';

// wizi's to-do list in the side panel, as Kanya's plan panel (spec 09).
const MARKS: Record<string, string> = { completed: '✓', in_progress: '◐', pending: '○' };
const STATUS_WORDS: Record<string, string> = { completed: 'done', in_progress: 'in progress', pending: 'to do' };

export default function TodoPanel({ todos }: { todos: TodoItem[] }) {
  const done = todos.filter((todo) => todo.status === 'completed').length;
  return (
    <section className="panel" aria-labelledby="todo-title">
      <header className="panel-header">
        <h2 id="todo-title">wizi's plan</h2>
        {todos.length > 0 && <span className="muted small">{done} of {todos.length} done</span>}
      </header>
      {todos.length === 0 ? (
        <p className="muted small">wizi writes its plan here once it starts working.</p>
      ) : (
        <ol className="todo-list">
          {todos.map((todo, index) => (
            <li key={`${index}-${todo.content}`} className={`todo todo-${todo.status}`}>
              <span className="todo-mark" aria-hidden="true">{MARKS[todo.status] ?? '○'}</span>
              <span className="todo-text">
                {todo.content}
                <span className="visually-hidden"> ({STATUS_WORDS[todo.status] ?? todo.status})</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
