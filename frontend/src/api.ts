// Typed API client — mirrors backend/app/schemas.py (contract).

export interface ProjectSummary {
  project_id: string;
  title: string;
  updated_at: string;
}

export interface ProjectCreated {
  project_id: string;
  thread_id: string;
  title: string;
}

export interface DocMeta {
  slug: string;
  title: string;
  updated_at: string | null;
}

export interface DocContent {
  slug: string;
  title: string;
  markdown: string;
}

export type ChatMsg = { role: 'user' | 'agent'; text: string; source?: string };

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
  | { type: 'token'; source: string; text: string }
  | { type: 'tool_call'; source: string; name: string; args_preview: string }
  | { type: 'subagent'; status: string; name: string }
  | { type: 'interrupt'; interrupt_id: string; action_requests: ActionRequestItem[]; review_configs: unknown[] }
  | { type: 'doc_updated'; slug: string; title: string }
  | { type: 'custom'; source: string; data: unknown }
  | { type: 'done'; thread_id: string }
  | { type: 'error'; detail: string };

const json = async (res: Response) => {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export const api = {
  health: () => fetch('/api/health').then(json),
  createProject: (title: string): Promise<ProjectCreated> =>
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).then(json),
  listProjects: (): Promise<ProjectSummary[]> => fetch('/api/projects').then(json),
  listDocs: (projectId: string): Promise<{ docs: DocMeta[] }> =>
    fetch(`/api/projects/${projectId}/docs`).then(json),
  readDoc: (projectId: string, slug: string): Promise<DocContent> =>
    fetch(`/api/projects/${projectId}/docs/${slug}`).then(json),

  /** POST /api/chat and yield parsed SSE events. */
  async *streamChat(
    projectId: string,
    message: string,
    resume?: { type: string; message?: string; edited_action?: unknown }[],
    signal?: AbortSignal,
  ): AsyncGenerator<StreamEvent> {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, message, resume: resume ?? null }),
      signal,
    });
    if (!res.ok || !res.body) throw new Error(`Chat failed: HTTP ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop() ?? '';
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data:')) continue;
        try {
          yield JSON.parse(line.slice(5).trim()) as StreamEvent;
        } catch {
          /* ignore partial */
        }
      }
    }
  },
};
