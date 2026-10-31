import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { api, type ChatMsg, type InterruptEvent, type ProjectSummary, type TodoItem } from '../api';
import Approvals from './Approvals';
import Composer from './Composer';
import DocViewer from './DocViewer';
import QualityPanel from './QualityPanel';
import TodoPanel from './TodoPanel';
import { WiziFace, type FaceState } from './WiziFace';
import { ChatToolsContext, retryMessage, type ChatTools } from './chat/chatTools';
import { ReaderPane } from './chat/ReaderPane';
import { SideToggle } from './chat/SidePanel';
import { ThinkingLine } from './chat/ThinkingLine';
import { useReader } from './chat/useReader';
import { useSidePanel } from './chat/useSidePanel';
import { WiziReply } from './chat/WiziReply';

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

// The chat, laid out as Kanya's (spec 09): header, conversation with wizi's orb, the live line, the card inline, the
// boxed composer; the side panel (plan, brief and decisions, documents) and the reader on the right.
export default function Chat({ projectId, project, onRenamed, onDeleted }: {
  projectId: string;
  project: ProjectSummary | null;
  onRenamed: (updated: ProjectSummary) => void;
  onDeleted: (projectId: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [activity, setActivity] = useState<string[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [pending, setPending] = useState<InterruptEvent | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Ready for your message');
  // The server's own progress line ("Preparing 2 attached file(s)…"), shown in the live line until wizi acts.
  const [progress, setProgress] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [quietSeconds, setQuietSeconds] = useState(0);
  const [lastAttempt, setLastAttempt] = useState<ChatAttempt | null>(null);
  const startedAt = useRef(0);
  const lastUpdateAt = useRef(0);
  const [docsTick, setDocsTick] = useState(0);
  const side = useSidePanel();
  const reader = useReader();
  const [stopping, setStopping] = useState(false);
  const stopped = useRef(false);
  // Where the running turn's own messages start: they show as the live draft, not as finished replies.
  const [turnStart, setTurnStart] = useState(0);
  const [prefill, setPrefill] = useState<{ text: string; n: number }>({ text: '', n: 0 });
  const msgsRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const inFlight = useRef(false);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  // The conversation lives on the server (spec 08): show it whenever the project opens, in any browser.
  useEffect(() => {
    let cancelled = false;
    api.history(projectId)
      .then((saved) => {
        if (cancelled || inFlight.current) return;
        setMessages((current) => (current.length ? current : saved.messages));
        setTodos((current) => (current.length ? current : saved.todos));
        if (saved.pending) {
          setPending((current) => current ?? saved.pending);
          setStatus('Waiting for your approval');
        }
      })
      .catch(() => { /* an empty chat is still usable */ });
    return () => { cancelled = true; };
  }, [projectId]);

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
    setProgress('');
    setStreaming(true);
    setError('');
    stopped.current = false;
    // Everything after the messages already shown belongs to this turn: it shows as the live draft until it ends.
    setMessages((m) => { setTurnStart(m.length); return m; });
    try {
      let interrupted = false;
      let failed = false;
      let completed = false;
      for await (const ev of api.streamChat(projectId, message, resume, attachmentIds, controller.signal, attempt.userMessageId)) {
        lastUpdateAt.current = Date.now();
        setQuietSeconds(0);
        if (ev.type === 'status') { setStatus(ev.text); setProgress(ev.text.replace(/…$/, '')); }
        else if (ev.type === 'token' && ev.source === 'main') { setStatus('Writing a response…'); setProgress(''); pushToken(ev.source, ev.text); }
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
      if (!completed && !interrupted && !failed && !stopped.current) throw new Error('The connection ended before wizi finished. Please try again.');
      if (stopped.current) setStatus('Stopped. Everything you approved is saved.');
      if ((resume || attempt.answersCard) && completed && !interrupted && !failed) setPending(null);
    } catch (e) {
      if (controller.signal.aborted) return; // Project change/deletion intentionally closes this stream.
      if (stopped.current) { setStatus('Stopped. Everything you approved is saved.'); return; }
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

  const stop = async () => {
    stopped.current = true;
    setStopping(true);
    try {
      await api.stopTurn(projectId);
    } catch {
      stopped.current = false;
    } finally {
      setStopping(false);
    }
  };

  const tools = useMemo<ChatTools>(() => ({
    projectId,
    onRetry: (guidance: string) => send(retryMessage(guidance), []),
    openReader: reader.open,
  }), [projectId, reader.open]); // eslint-disable-line react-hooks/exhaustive-deps

  const lastMsg = messages[messages.length - 1];
  const showQuickReplies =
    !streaming && !pending && !error && lastMsg?.role === 'agent' && asksApproval(lastMsg.text);
  const shown = streaming ? messages.slice(0, turnStart) : messages;
  const draft = streaming ? messages.slice(turnStart).filter((m) => m.role === 'agent').map((m) => m.text).join('\n\n') : '';
  const latestReply = [...shown].reverse().find((m) => m.role === 'agent');
  const replyKey = latestReply ? `${shown.lastIndexOf(latestReply)}:${latestReply.text.length}` : '';
  const todosDone = todos.filter((todo) => todo.status === 'completed').length;
  const pill = streaming ? ['Working', 'working'] : pending ? ['Needs your review', 'waiting'] : error ? ['Needs attention', 'failed'] : ['Ready', 'ready'];

  return (
    <ChatToolsContext.Provider value={tools}>
      <div className="chat-page">
        <header className="chat-header">
          <ProjectTitle project={project} projectId={projectId} onRenamed={onRenamed} onDeleted={onDeleted} busy={streaming} />
          <span className={`status-pill status-${pill[1]}`} role="status" aria-live="polite" title={status}>{pill[0]}</span>
          <div className="chat-header-end">
            <SideToggle
              open={side.open}
              onToggle={side.toggle}
              label="Brief and documents"
              count={todos.length ? `${todosDone}/${todos.length}` : undefined}
            />
          </div>
        </header>

        <div
          className={`chat-layout${side.open ? ' side-open' : ''}${reader.content ? ' reader-open' : ''}`}
          style={{ '--reader-width': `${reader.width}px` } as CSSProperties}
        >
          <div className="chat-main">
            <div className="conversation-frame">
              <div
                className="conversation"
                ref={msgsRef}
                onScroll={onMsgsScroll}
                role="log"
                aria-label="Conversation with wizi"
                aria-live="polite"
                aria-relevant="additions"
              >
                {shown.length === 0 && !streaming && (
                  <p className="muted conversation-empty">
                    Describe your software idea: goal, users, scale, budget, timeline. Or attach your code and say
                    what to add or clean up.
                  </p>
                )}
                {shown.map((m, i) =>
                  m.role === 'user' ? (
                    <div key={m.id ?? i} className="msg msg-user">
                      <div className="msg-body">
                        <span className="visually-hidden">You:</span>
                        <p className="user-text">{m.text}</p>
                      </div>
                    </div>
                  ) : (
                    <WiziRow key={m.id ?? i} face={!streaming && !pending && m === latestReply ? 'standby' : 'still'}>
                      <WiziReply
                        text={m.text}
                        prompt={[...shown.slice(0, i)].reverse().find((before) => before.role === 'user')?.text ?? ''}
                        latest={!streaming && m === latestReply}
                      />
                    </WiziRow>
                  ),
                )}
                {streaming && (
                  <div aria-live="off">
                    <WiziRow face="thinking">
                      <ThinkingLine elapsed={elapsed} activity={draft ? '' : activity[activity.length - 1] ?? progress} draft={draft} />
                      {quietSeconds >= 15 && <p className="muted small">Waiting for an update…</p>}
                    </WiziRow>
                  </div>
                )}
                {pending && (
                  <WiziRow face="standby">
                    <Approvals
                      key={pending.interrupt_id}
                      interruptId={pending.interrupt_id}
                      disabled={streaming}
                      actions={pending.action_requests}
                      onResolve={resolveApproval}
                    />
                  </WiziRow>
                )}
                {showQuickReplies && (
                  <div className="quick-replies" role="group" aria-label="Approval actions">
                    <button type="button" className="button primary small" onClick={() => send('Approved — please go ahead.', [])}>✅ Approve</button>
                    <button
                      type="button"
                      className="button ghost small"
                      onClick={() => setPrefill((p) => ({ text: 'Please change: ', n: p.n + 1 }))}
                    >
                      ✏️ Request changes
                    </button>
                  </div>
                )}
                {error && (
                  <div className="chat-error" role="alert">
                    <p>{chatFailureMessage(new Error(error))}</p>
                    {lastAttempt && !streaming && (
                      <div className="button-row">
                        <button type="button" className="button primary small" onClick={resend}>Resend</button>
                        <button type="button" className="button ghost small" onClick={deleteFailed} title="Remove this failed message from the current chat">Delete</button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
            <Composer
              projectId={projectId}
              running={streaming}
              stopping={stopping}
              onSend={send}
              onStop={() => void stop()}
              reply={streaming || !latestReply ? null : { key: replyKey, text: latestReply.text }}
              prefill={prefill}
              placeholder={pending ? 'Type or say "approve", or what to change…' : undefined}
            />
          </div>
          <aside id="chat-side" className="chat-side" aria-label="Brief and documents" hidden={!side.open}>
            <div className="chat-side-head">
              <h2>Brief and documents</h2>
              <button type="button" className="icon-button" aria-label="Close the panel" onClick={side.toggle}>×</button>
            </div>
            <TodoPanel todos={todos} />
            <QualityPanel projectId={projectId} refreshKey={docsTick} disabled={streaming || !!pending} onDiscuss={(text) => send(text, [])} onChanged={() => setDocsTick((t) => t + 1)} />
            <DocViewer projectId={projectId} refreshKey={docsTick} onOpen={reader.open} />
          </aside>
          <ReaderPane reader={reader} />
        </div>
      </div>
    </ChatToolsContext.Provider>
  );
}

function WiziRow({ face = 'still', children }: { face?: FaceState; children: ReactNode }) {
  return (
    <div className="msg msg-kanya">
      <WiziFace className="avatar" size={36} state={face} />
      <div className="msg-body">
        <span className="visually-hidden">wizi:</span>
        {children}
      </div>
    </div>
  );
}

// The project's name in the header, renamed in place; Delete beside it asks once.
function ProjectTitle({ project, projectId, onRenamed, onDeleted, busy }: {
  project: ProjectSummary | null;
  projectId: string;
  onRenamed: (updated: ProjectSummary) => void;
  onDeleted: (projectId: string) => void;
  busy: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [name, setName] = useState('');
  const [working, setWorking] = useState(false);
  const [problem, setProblem] = useState('');
  const title = project?.title ?? 'Project';

  const save = async () => {
    if (!name.trim() || working) return;
    setWorking(true);
    setProblem('');
    try {
      onRenamed(await api.renameProject(projectId, name.trim()));
      setEditing(false);
    } catch (failure) {
      setProblem(failure instanceof Error ? failure.message : 'Could not rename the project.');
    } finally {
      setWorking(false);
    }
  };

  const remove = async () => {
    setWorking(true);
    setProblem('');
    try {
      await api.deleteProject(projectId);
      onDeleted(projectId);
    } catch (failure) {
      setProblem(failure instanceof Error ? failure.message : 'Could not delete the project.');
      setWorking(false);
    }
  };

  if (editing) {
    return (
      <form className="title-edit" aria-label="Rename project" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <label htmlFor="project-name" className="visually-hidden">Project name</label>
        <input id="project-name" autoFocus maxLength={200} value={name} disabled={working} onChange={(event) => setName(event.target.value)} />
        <button type="submit" className="button primary small" disabled={working || !name.trim()}>{working ? 'Saving…' : 'Save name'}</button>
        <button type="button" className="button ghost small" onClick={() => setEditing(false)}>Cancel</button>
        {problem && <span className="form-error small" role="alert">{problem}</span>}
      </form>
    );
  }
  return (
    <div className="title-wrap">
      <h1 title={title}>{title}</h1>
      <button type="button" className="button ghost small" onClick={() => { setName(title); setEditing(true); setConfirming(false); }}>Rename</button>
      {confirming ? (
        <>
          <button type="button" className="button danger small" disabled={working} onClick={() => void remove()}>{working ? 'Deleting…' : 'Delete for good'}</button>
          <button type="button" className="button ghost small" onClick={() => setConfirming(false)}>Keep</button>
        </>
      ) : (
        <button type="button" className="button ghost small" title={busy ? 'Deleting stops wizi first' : undefined} onClick={() => setConfirming(true)}>Delete</button>
      )}
      {problem && <span className="form-error small" role="alert">{problem}</span>}
    </div>
  );
}
