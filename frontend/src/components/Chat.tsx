import { useEffect, useRef, useState } from 'react';
import { api, type ChatMsg, type InterruptEvent, type TodoItem } from '../api';
import Approvals from './Approvals';
import Composer from './Composer';
import DocViewer from './DocViewer';
import TodoPanel from './TodoPanel';

interface Thought {
  source: string;
  text: string;
}

export default function Chat({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string[]>([]);
  const [thoughts, setThoughts] = useState<Thought[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [steps, setSteps] = useState<Map<string, number>>(new Map());
  const [pending, setPending] = useState<InterruptEvent | null>(null);
  const [error, setError] = useState('');
  const [docsTick, setDocsTick] = useState(0);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activity, thoughts]);

  const pushToken = (source: string, text: string) =>
    setMessages((m) => {
      const last = m[m.length - 1];
      if (last && last.role === 'agent' && last.source === source) {
        return [...m.slice(0, -1), { ...last, text: last.text + text }];
      }
      return [...m, { role: 'agent', text, source }];
    });

  const run = async (
    message: string,
    resume?: { type: string; message?: string }[],
    attachmentIds: string[] = [],
  ) => {
    setStreaming(true);
    setError('');
    try {
      for await (const ev of api.streamChat(projectId, message, resume, attachmentIds)) {
        if (ev.type === 'token') pushToken(ev.source, ev.text);
        else if (ev.type === 'thought')
          setThoughts((t) => {
            const last = t[t.length - 1];
            if (last && last.source === ev.source) {
              return [...t.slice(0, -1), { ...last, text: last.text + ev.text }];
            }
            return [...t.slice(-9), { source: ev.source, text: ev.text }];
          });
        else if (ev.type === 'step')
          setSteps((s) => new Map(s).set(`${ev.source}:${ev.node}`, (s.get(`${ev.source}:${ev.node}`) ?? 0) + 1));
        else if (ev.type === 'todos') setTodos(ev.todos);
        else if (ev.type === 'tool_call')
          setActivity((a) => [...a.slice(-19), `⚙ ${ev.source}: ${ev.name}`]);
        else if (ev.type === 'subagent')
          setActivity((a) => [...a.slice(-19), `👷 ${ev.name} — ${ev.status}`]);
        else if (ev.type === 'interrupt')
          setPending({
            interrupt_id: ev.interrupt_id,
            action_requests: ev.action_requests,
            review_configs: ev.review_configs,
          });
        else if (ev.type === 'doc_updated') setDocsTick((t) => t + 1);
        else if (ev.type === 'error') setError(ev.detail);
        else if (ev.type === 'done') setActivity([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Chat failed — is the backend running?');
    } finally {
      setStreaming(false);
      setDocsTick((t) => t + 1);
    }
  };

  const send = (text: string, attachmentIds: string[]) => {
    if ((!text.trim() && attachmentIds.length === 0) || streaming) return;
    setMessages((m) => [
      ...m,
      {
        role: 'user',
        text:
          text.trim() +
          (attachmentIds.length > 0 ? ` [${attachmentIds.length} attachment(s)]` : ''),
      },
    ]);
    void run(text, undefined, attachmentIds);
  };

  const resolveApproval = (decisions: { type: 'approve' | 'reject' }[]) => {
    setPending(null);
    setMessages((m) => [
      ...m,
      { role: 'user', text: `(reviewed writes: ${decisions.map((d) => d.type).join(', ')})` },
    ]);
    void run('', decisions, []);
  };

  return (
    <div className="layout">
      <section className="chat">
        <TodoPanel todos={todos} streaming={streaming} />
        <div className="msgs">
          {messages.length === 0 && (
            <p className="empty">
              Describe your software idea — goal, users, scale, budget, timeline.
              The agent brainstorms with you, then drafts the 9 handover docs.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.source && m.source !== 'main' && <small>{m.source}</small>}
              <p>{m.text}</p>
            </div>
          ))}
          {thoughts.length > 0 && (
            <details className="thoughts" open={streaming}>
              <summary>
                💭 agent thinking ({thoughts.length} block{thoughts.length > 1 ? 's' : ''})
              </summary>
              {thoughts.slice(-5).map((t, i) => (
                <div key={i} className="thought">
                  <small>{t.source}</small>
                  <p>{t.text.slice(0, 800)}</p>
                </div>
              ))}
            </details>
          )}
          {steps.size > 0 && (
            <div className="steps">
              {[...steps.entries()].map(([k, n]) => (
                <span key={k} className="step-chip">
                  ▸ {k} ×{n}
                </span>
              ))}
            </div>
          )}
          {activity.length > 0 && (
            <div className="activity">
              {activity.map((a, i) => (
                <div key={i}>{a}</div>
              ))}
            </div>
          )}
          {pending && (
            <Approvals
              interruptId={pending.interrupt_id}
              actions={pending.action_requests}
              onResolve={resolveApproval}
            />
          )}
          {error && <div className="error">{error}</div>}
          {streaming && <div className="typing">agent is working…</div>}
          <div ref={bottom} />
        </div>
        <Composer projectId={projectId} disabled={streaming || !!pending} onSend={send} />
      </section>
      <DocViewer projectId={projectId} refreshKey={docsTick} />
    </div>
  );
}
