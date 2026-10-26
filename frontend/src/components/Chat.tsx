import { useEffect, useRef, useState } from 'react';
import { api, type ChatMsg, type InterruptEvent } from '../api';
import Approvals from './Approvals';
import DocViewer from './DocViewer';

export default function Chat({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string[]>([]);
  const [pending, setPending] = useState<InterruptEvent | null>(null);
  const [error, setError] = useState('');
  const [docsTick, setDocsTick] = useState(0);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activity]);

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
  ) => {
    setStreaming(true);
    setError('');
    try {
      for await (const ev of api.streamChat(projectId, message, resume)) {
        if (ev.type === 'token') pushToken(ev.source, ev.text);
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

  const send = () => {
    const text = input.trim();
    if (!text || streaming) return;
    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    void run(text);
  };

  const resolveApproval = (decisions: { type: 'approve' | 'reject' }[]) => {
    setPending(null);
    setMessages((m) => [
      ...m,
      { role: 'user', text: `(reviewed writes: ${decisions.map((d) => d.type).join(', ')})` },
    ]);
    void run('', decisions);
  };

  return (
    <div className="layout">
      <section className="chat">
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
        <div className="composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Type your idea or follow-up…"
            disabled={streaming || !!pending}
          />
          <button onClick={send} disabled={streaming || !!pending || !input.trim()}>
            Send
          </button>
        </div>
      </section>
      <DocViewer projectId={projectId} refreshKey={docsTick} />
    </div>
  );
}
