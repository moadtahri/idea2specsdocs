import { useState } from 'react';
import type { ActionRequestItem } from '../api';
import Markdown from './Markdown';

type Decision = { type: 'approve' | 'reject'; message?: string };

const DOC_TITLES: Record<string, string> = {
  prd: 'PRD',
  'technical-spike': 'Technical Spike',
  'sad-architecture': 'SAD / Architecture',
  'api-specification': 'API Specification',
  'database-schema': 'Database Schema',
  'security-blueprint': 'Security Blueprint',
  'devops-iac-spec': 'DevOps IaC Spec',
  'qa-test-plan': 'QA Test Plan',
  runbook: 'Runbook / On-Call Docs',
};

function docTitle(path: unknown): string {
  const slug = String(path ?? '')
    .split(/[\\/]/)
    .pop()
    ?.replace(/\.md$/i, '');
  return (slug && DOC_TITLES[slug]) || slug || 'document';
}

function Preview({ action }: { action: ActionRequestItem }) {
  const a = action.args;
  if (action.name === 'edit_file') {
    return (
      <>
        <p className="muted">Replacing this part:</p>
        <Markdown text={String(a.old_string ?? '')} className="diff-old" />
        <p className="muted">With:</p>
        <Markdown text={String(a.new_string ?? '')} className="diff-new" />
      </>
    );
  }
  return <Markdown text={String(a.content ?? '')} className="doc-preview" />;
}

export default function Approvals({
  interruptId: _id,
  disabled,
  actions,
  onResolve,
}: {
  interruptId: string;
  disabled: boolean;
  actions: ActionRequestItem[];
  onResolve: (decisions: Decision[], summary: string) => void;
}) {
  const [changing, setChanging] = useState(false);
  const [feedback, setFeedback] = useState('');
  void _id;

  const titles = actions.map((a) => docTitle(a.args.file_path));
  const names = titles.join(', ');

  const approve = () => {
    onResolve(actions.map(() => ({ type: 'approve' })), `✅ Approved: ${names}`);
  };

  const requestChanges = () => {
    const message = feedback.trim();
    if (!message) return;
    onResolve(
      actions.map(() => ({ type: 'reject', message })),
      `✏️ Changes requested for ${names}: ${message}`,
    );
  };

  return (
    <div className="approvals">
      <h3>Review before saving</h3>
      <p className="muted">Use the buttons, or type or say "approve", or what to change, in the message box.</p>
      {actions.map((a, i) => (
        <div key={i} className="approval-card">
          <div className="approval-title">
            <strong>{titles[i]}</strong>
            <span className="badge">{a.name === 'edit_file' ? 'update' : 'new draft'}</span>
          </div>
          <details>
            <summary>Show the full {a.name === 'edit_file' ? 'change' : 'draft'}</summary>
            <Preview action={a} />
          </details>
        </div>
      ))}
      {changing && (
        <textarea
          className="feedback"
          rows={3}
          autoFocus
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="What should be different?"
        />
      )}
      <div className="row">
        {!changing ? (
          <>
            <button disabled={disabled} onClick={approve}>
              Approve &amp; save
            </button>
            <button disabled={disabled} onClick={() => setChanging(true)} className="ghost">
              Request changes
            </button>
          </>
        ) : (
          <>
            <button disabled={disabled || !feedback.trim()} onClick={requestChanges}>
              Send feedback
            </button>
            <button disabled={disabled} onClick={() => setChanging(false)} className="ghost">
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
