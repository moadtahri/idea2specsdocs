// Typed API client — mirrors backend/app/schemas.py (contract).

export interface ProjectSummary {
  project_id: string;
  title: string;
  updated_at: string;
}

export interface ProjectBrief {
  vertical: string; service: string; purpose: string; users: string; workflows: string;
  scope: string; permissions: string; data_lifecycle: string; constraints: string; success_criteria: string;
  assumptions: string[]; sources: string[]; open_questions: string[];
  /** What the user brought; older saved briefs may lack it (treated as 'idea'). */
  intake?: Intake;
}
export type Intake = 'idea' | 'feature' | 'cleanup';
export interface BriefState {
  status: string; revision: string; missing: string[]; brief: ProjectBrief;
}
export interface WorkItem {
  id: string; kind: string; title: string; detail: string; impact: string; owner: string;
  affected_docs: string[]; proposal: string; status: string; resolution: string;
  /** Who settles it; items saved before the decision map lack it (treated as 'stakeholder'). */
  owner_type?: 'stakeholder' | 'default' | 'repo';
  /** IDs of the items that must be resolved first. */
  blocked_by?: string[];
  basis?: string;
  /** The user's own words that settled it in chat. */
  answered_with?: string;
}
export interface QualityState {
  brief: BriefState; review_status: string; spec_revision: string;
  ready_for_implementation: boolean; implementation_verified: boolean; ready_for_production: boolean;
  verification_note: string; items: WorkItem[];
  /** IDs of open items whose blockers are all resolved: decidable now. */
  frontier?: string[];
  findings: {id: string; title: string; detail: string; severity: string; impact: string; recommendation: string; citations: {slug: string; line: number; quote: string}[]}[];
  last_review: {summary: string; errors: string[]} | null;
  evidence: {id: string; scope: string; outcome: string; source_revision: string; environment: string; artifact_valid: boolean; spec_revision: string}[];
  required_test_ids: string[]; required_launch_ids: string[];
  security_coverage: {control_id: string; test_ids: string[]; mapped: boolean}[];
}

export interface ProjectCreated {
  project_id: string;
  thread_id: string;
  title: string;
}

export interface DocMeta {
  slug: string;
  status?: string;
  title: string;
  updated_at: string | null;
}

export interface DocContent {
  slug: string;
  title: string;
  markdown: string;
}

export type ChatMsg = { id?: string; role: 'user' | 'agent'; text: string; source?: string };

export interface AttachmentMeta {
  attachment_id: string;
  filename: string;
  content_type: string;
  size: number;
  text_preview: string;
  created_at: string;
}

export interface StreamingToken {
  token: string;
  websocket_url: string;
  sample_rate: number;
}

export interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export interface ActionRequestItem {
  name: string;
  args: Record<string, unknown>;
}

export interface InterruptEvent {
  interrupt_id: string;
  action_requests: ActionRequestItem[];
  review_configs: unknown[];
}

export type StreamEvent =
  | { type: 'status'; text: string; request_id?: string }
  | { type: 'heartbeat' }
  | { type: 'token'; source: string; text: string }
  | { type: 'thought'; source: string; text: string }
  | { type: 'step'; source: string; node: string }
  | { type: 'tool_call'; source: string; name: string; args_preview: string }
  | { type: 'subagent'; status: string; name: string }
  | { type: 'todos'; todos: TodoItem[] }
  | { type: 'interrupt'; interrupt_id: string; action_requests: ActionRequestItem[]; review_configs: unknown[] }
  | { type: 'doc_updated'; slug: string; title: string }
  | { type: 'custom'; source: string; data: unknown }
  | { type: 'done'; thread_id: string }
  | { type: 'error'; detail: string; request_id?: string };

export interface PackageFinding { severity: 'blocker' | 'warning'; file: string; message: string }
export interface PackageChecks { blockers: number; warnings: number; findings: PackageFinding[] }
export interface ReturnedQuestions { created: WorkItem[]; existing: WorkItem[] }

const json = async (res: Response) => {
  if (!res.ok) {
    // FastAPI errors carry a human-readable `detail`; surface it when present.
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`);
  }
  return res.json();
};

export const api = {
  quality: (id: string, environment = 'production'): Promise<QualityState> => fetch(`/api/projects/${id}/quality?environment=${encodeURIComponent(environment)}`).then(json),
  saveBrief: (id: string, brief: ProjectBrief): Promise<BriefState> => fetch(`/api/projects/${id}/brief`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(brief)}).then(json),
  approveBrief: (id: string, revision: string): Promise<BriefState> => fetch(`/api/projects/${id}/brief/approve`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({revision})}).then(json),
  resolveItem: (id: string, item: string, status: string, resolution: string) => fetch(`/api/projects/${id}/work-items/${item}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({status, resolution})}).then(json),
  review: (id: string, environment: string) => fetch(`/api/projects/${id}/reviews`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({environment})}).then(json),
  recordEvidence: (id: string, evidence: Record<string, unknown>) => fetch(`/api/projects/${id}/evidence`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(evidence)}).then(json),
  health: () => fetch('/api/health').then(json),
  createProject: (title: string): Promise<ProjectCreated> =>
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).then(json),
  listProjects: (): Promise<ProjectSummary[]> => fetch('/api/projects').then(json),
  renameProject: (projectId: string, title: string): Promise<ProjectSummary> =>
    fetch(`/api/projects/${projectId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }),
    }).then(json),
  deleteProject: async (projectId: string): Promise<void> => {
    const response = await fetch(`/api/projects/${projectId}`, { method: 'DELETE' });
    if (!response.ok) await json(response);
  },
  packageChecks: (projectId: string): Promise<PackageChecks> =>
    fetch(`/api/projects/${projectId}/package/checks`).then(json),
  returnQuestions: (projectId: string, markdown: string): Promise<ReturnedQuestions> =>
    fetch(`/api/projects/${projectId}/questions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ markdown }),
    }).then(json),
  questionnaireAnswers: (projectId: string, markdown: string): Promise<{ answered_by: string; settled: WorkItem[]; refused: { item: string; reason: string }[] }> =>
    fetch(`/api/projects/${projectId}/questionnaire/answers`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ markdown }),
    }).then(json),
  listDocs: (projectId: string): Promise<{ docs: DocMeta[] }> =>
    fetch(`/api/projects/${projectId}/docs`).then(json),
  readDoc: (projectId: string, slug: string): Promise<DocContent> =>
    fetch(`/api/projects/${projectId}/docs/${slug}`).then(json),
  upload: async (projectId: string, file: File): Promise<AttachmentMeta> => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`/api/projects/${projectId}/uploads`, {
      method: 'POST',
      body: fd,
    });
    return json(res);
  },
  transcribe: async (blob: Blob, filename = 'audio.webm', signal?: AbortSignal): Promise<{ text: string }> => {
    const fd = new FormData();
    fd.append('file', blob, filename);
    const res = await fetch('/api/transcribe', { method: 'POST', body: fd, signal });
    return json(res);
  },
  streamingToken: async (signal?: AbortSignal): Promise<StreamingToken> =>
    fetch('/api/transcribe/token', { method: 'POST', signal, cache: 'no-store' }).then(json),

  /** POST /api/chat and yield parsed SSE events. */
  async *streamChat(
    projectId: string,
    message: string,
    resume?: { type: string; message?: string; edited_action?: unknown }[],
    attachmentIds?: string[],
    signal?: AbortSignal,
    messageId?: string,
  ): AsyncGenerator<StreamEvent> {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        message_id: messageId,
        message,
        resume: resume ?? null,
        attachment_ids: attachmentIds ?? [],
      }),
      signal,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(typeof body?.detail === 'string' ? body.detail : `Chat failed: HTTP ${res.status}`);
    }
    if (!res.body) throw new Error('The chat connection did not open. Please resend your message.');
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    try { for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r/g, '');
      const parts = buf.split('\n\n');
      buf = parts.pop() ?? '';
      for (const part of parts) {
        const line = part.split('\n').filter((value) => value.startsWith('data:')).map((value) => value.slice(5).trimStart()).join('\n');
        if (!line) continue;
        try {
          yield JSON.parse(line) as StreamEvent;
        } catch {
          /* ignore partial */
        }
      }
    } } finally { reader.releaseLock(); }
  },
};
