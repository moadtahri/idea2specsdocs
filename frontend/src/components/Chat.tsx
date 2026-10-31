import { useEffect, useRef, useState } from 'react';
import { api, type ChatMsg, type InterruptEvent, type TodoItem } from '../api';
import Approvals from './Approvals';
import Composer from './Composer';
import DocViewer from './DocViewer';
import QualityPanel from './QualityPanel';
import Markdown from './Markdown';
import TodoPanel from './TodoPanel';

interface ChatAttempt {
  userMessageId: string;
  message: string;
  attachmentIds: string[];
  resume?: { type: string; message?: string }[];
  // Typed while a card waited: the server turns it into the card's decision.
  answersCard?: boolean;
}

// Some replies request approval without emitting a document-tool interrupt.
// Keep a clickable fallback for both typed-approval and card/button wording.
const ASKS_APPROVAL =
  /\b(reply|type|say|respond|answer|send|write)\b[^.\r\n]{0,40}\bapprov|\b(use|click|press|tap|select|choose)\b[^.\r\n]{0,120}\bapprov(?:e|al)\b|\bplease\s+approve\b|\bwaiting for your approval\b|\bonce you approve\b|\bapprove\b[^.\r\n]{0,80}\b(tell|let) me\b[^.\r\n]{0,30}\bchange|\b(shall|should|can|may) i (proceed|continue|go ahead|start|draft)\b/i;

function asksApproval(text: string): boolean {
  const prose = text.replace(/(```|~~~)[\s\S]*?\1/g, '')
    .replace(/&(?:nbsp|#160|#x[a-f0-9]+|#32);/gi, ' ')
    .replace(/[*_`]/g, '').replace(/\s+/g, ' ');
  return ASKS_APPROVAL.test(prose);
}

function chatFailureMessage(failure: unknown): string {
  const message = failure instanceof Error ? failure.message : '';
  if ((failure instanceof Error && failure.name === 'AbortError') || /BodyStreamBuffer|aborted|failed to fetch|networkerror|network.*(?:lost|error)|terminated|load failed/i.test(message)) {
    return 'The chat connection was interrupted. Click Resend to try again, or Delete to remove this request.';
  }
  return message || 'Chat failed. Please resend your message.';
}

// User-facing wording for agent tools; anything unlisted is internal and not shown.
const ACTIVITY_LABELS: Record<string, string> = {
  get_project_context: 'Reading your project brief and decisions',
  propose_project_brief: 'Preparing your project brief for review',
  propose_work_item: 'Recording a decision to clarify',
  load_review_skill: 'Checking the requirements checklist',
  review_bundle: 'Reviewing the bundle for gaps and contradictions',
  check_bundle_contracts: 'Checking security controls against the QA plan',
  task: '🧑‍💼 A specialist is working on part of your plan',
  write_todos: '🗒 Updating the plan',
  ls: '📂 Reviewing your project files',
  glob: '📂 Reviewing your project files',
  grep: '🔎 Searching your project files',
  read_file: '📖 Reading your project files',
  list_docs: '📑 Checking which documents are ready',
  estimate_cost: '💰 Estimating running costs',
  write_file: '📝 Drafting a document for your review',
  edit_file: '📝 Drafting changes for your review',
};

export default function Chat({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [pending, setPending] = useState<InterruptEvent | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Ready for your message');
  const [elapsed, setElapsed] = useState(0);
  const [quietSeconds, setQuietSeconds] = useState(0);
  const [lastAttempt, setLastAttempt] = useState<ChatAttempt | null>(null);
  const startedAt = useRef(0);
  const lastUpdateAt = useRef(0);
  const [docsTick, setDocsTick] = useState(0);
  const [docsCollapsed, setDocsCollapsed] = useState(false);
  const [prefill, setPrefill] = useState<{ text: string; n: number }>({ text: '', n: 0 });
  const msgsRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const inFlight = useRef(false);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (!streaming) return;
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 1000));
      setQuietSeconds(Math.floor((Date.now() - lastUpdateAt.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [streaming]);

  // scroll the message pane itself (not the page) to the latest content,
  // unless the user scrolled up to read earlier messages
  useEffect(() => {
    const el = msgsRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages, activity, pending, error, streaming]);

  const onMsgsScroll = () => {
    const el = msgsRef.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  };

  const pushActivity = (line: string) =>
    setActivity((a) => (a[a.length - 1] === line ? a : [...a.slice(-5), line]));

  const pushToken = (source: string, text: string) =>
    setMessages((m) => {
      const last = m[m.length - 1];
      if (last && last.role === 'agent' && last.source === source) {
        return [...m.slice(0, -1), { ...last, text: last.text + text }];
      }
      return [...m, { role: 'agent', text, source }];
    });

  const run = async (attempt: ChatAttempt) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const controller = new AbortController();
    request.current = controller;
    const { message, resume, attachmentIds } = attempt;
    setLastAttempt(attempt);
    startedAt.current = Date.now();
    lastUpdateAt.current = Date.now();
    setElapsed(0);
    setQuietSeconds(0);
    setStatus('Sending your request…');
    setActivity([]);
    setStreaming(true);
    setError('');
    try {
      let interrupted = false;
      let failed = false;
      let completed = false;
      for await (const ev of api.streamChat(projectId, message, resume, attachmentIds, controller.signal, attempt.userMessageId)) {
        lastUpdateAt.current = Date.now();
        setQuietSeconds(0);
        if (ev.type === 'status') setStatus(ev.text);
        else if (ev.type === 'token' && ev.source === 'main') { setStatus('Writing a response…'); pushToken(ev.source, ev.text); }
        else if (ev.type === 'step' && ev.node === 'model') setStatus('Reviewing the next step…');
        else if (ev.type === 'todos') setTodos(ev.todos);
        else if (ev.type === 'tool_call') {
          const label = ACTIVITY_LABELS[ev.name];
          if (label) { pushActivity(label); setStatus(label); }
        } else if (ev.type === 'interrupt') {
          interrupted = true;
          setStatus('Waiting for your approval');
          setPending({
            interrupt_id: ev.interrupt_id,
            action_requests: ev.action_requests,
            review_configs: ev.review_configs,
          });
        } else if (ev.type === 'doc_updated') setDocsTick((t) => t + 1);
        else if (ev.type === 'error') { failed = true; setError(chatFailureMessage(new Error(ev.detail))); setStatus('Request needs attention'); }
        else if (ev.type === 'done') {
          completed = true;
          setActivity([]);
          if (!failed) setStatus(interrupted ? 'Waiting for your approval' : 'Finished');
        }
      }
      if (!completed && !interrupted && !failed) throw new Error('The connection ended before wizi finished. Please try again.');
      if ((resume || attempt.answersCard) && completed && !interrupted && !failed) setPending(null);
    } catch (e) {
      if (controller.signal.aborted) return; // Project change/deletion intentionally closes this stream.
      setError(chatFailureMessage(e));
      setStatus('Request needs attention');
    } finally {
      inFlight.current = false;
      setStreaming(false);
      setDocsTick((t) => t + 1);
    }
  };

  const send = (text: string, attachmentIds: string[], attachmentNames: string[] = []) => {
    if ((!text.trim() && attachmentIds.length === 0) || inFlight.current) return;
    stickToBottom.current = true;
    const userMessageId = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      {
        role: 'user',
        id: userMessageId,
        text:
          text.trim() +
          (attachmentIds.length > 0 ? `\n\nAttached: ${attachmentNames.length ? attachmentNames.join(', ') : `${attachmentIds.length} file(s)`}` : ''),
      },
    ]);
    // With a card waiting, typed or spoken words answer it: the server approves or requests changes (spec 03 T5).
    void run({ userMessageId, message: text, attachmentIds, answersCard: !!pending });
  };

  const resolveApproval = (
    decisions: { type: 'approve' | 'reject'; message?: string }[],
    summary: string,
  ) => {
    if (inFlight.current) return;
    stickToBottom.current = true;
    const userMessageId = crypto.randomUUID();
    setMessages((m) => [...m, { id: userMessageId, role: 'user', text: summary }]);
    void run({ userMessageId, message: '', attachmentIds: [], resume: decisions });
  };

  const resend = () => {
    if (!lastAttempt || inFlight.current) return;
    setMessages((all) => {
      const index = all.findIndex((message) => message.id === lastAttempt.userMessageId);
      return index < 0 ? all : all.slice(0, index + 1);
    });
    stickToBottom.current = true;
    void run(lastAttempt);
  };

  const deleteFailed = () => {
    if (!lastAttempt || inFlight.current) return;
    setMessages((all) => {
      const index = all.findIndex((message) => message.id === lastAttempt.userMessageId);
      return index < 0 ? all : all.slice(0, index);
    });
    setError('');
    setActivity([]);
    setLastAttempt(null);
    setStatus(pending ? 'Waiting for your approval' : 'Ready for your message');
  };

  const lastMsg = messages[messages.length - 1];
  const showQuickReplies =
    !streaming && !pending && !error && lastMsg?.role === 'agent' && asksApproval(lastMsg.text);

  return (
    <div className={`layout${docsCollapsed ? ' docs-collapsed' : ''}`}>
      <section className="chat">
        <div className={`agent-status ${streaming ? 'working' : error ? 'failed' : ''}`} role="status" aria-live="polite">
          <span className={streaming ? 'status-dot pulse' : 'status-dot'} />
          <div><strong>{streaming ? 'wizi is working' : error ? 'wizi stopped' : pending ? 'wizi needs your review' : 'wizi'}</strong><span>{status}</span></div>
          {streaming && <small>{elapsed}s elapsed{quietSeconds >= 15 ? ' · Waiting for an update…' : ''}</small>}
          {docsCollapsed && <button className="ghost" onClick={() => setDocsCollapsed(false)} aria-expanded={false}>Show handover docs</button>}
        </div>
        <TodoPanel todos={todos} streaming={streaming} />
        <div className="msgs" ref={msgsRef} onScroll={onMsgsScroll}>
          {messages.length === 0 && (
            <p className="empty">
              Describe your software idea — goal, users, scale, budget, timeline.
              Or attach existing source files and handover docs to plan a feature.
              Get implementation contracts for coding agents and a readable overview.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.source && m.source !== 'main' && <small>{m.source}</small>}
              <Markdown text={m.text} className="msg-body" />
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
              key={pending.interrupt_id}
              interruptId={pending.interrupt_id}
              disabled={streaming}
              actions={pending.action_requests}
              onResolve={resolveApproval}
            />
          )}
          {showQuickReplies && (
            <div className="quick-replies" role="group" aria-label="Approval actions">
              <button onClick={() => send('Approved — please go ahead.', [])}>✅ Approve</button>
              <button
                className="ghost"
                onClick={() => setPrefill((p) => ({ text: 'Please change: ', n: p.n + 1 }))}
              >
                ✏️ Request changes
              </button>
            </div>
          )}
          {error && <div className="error" role="alert">
            <p>{chatFailureMessage(new Error(error))}</p>
            {lastAttempt && !streaming && <div className="row">
              <button onClick={resend}>Resend</button>
              <button className="ghost" onClick={deleteFailed} title="Remove this failed message from the current chat">Delete</button>
            </div>}
          </div>}
          {streaming && <div className="typing">wizi is working…</div>}
        </div>
        <QualityPanel projectId={projectId} refreshKey={docsTick} disabled={streaming || !!pending} onDiscuss={text => send(text, [])} onChanged={() => setDocsTick(t => t + 1)} />
        <Composer projectId={projectId} disabled={streaming} onSend={send} prefill={prefill}
          placeholder={pending ? 'Type or say "approve", or what to change…' : undefined} />
      </section>
      <DocViewer projectId={projectId} refreshKey={docsTick} collapsed={docsCollapsed} onCollapse={() => setDocsCollapsed(true)} />
    </div>
  );
}
