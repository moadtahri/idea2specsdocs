import { useState } from 'react';
import type { ActionRequestItem } from '../api';

export default function Approvals({
  interruptId: _id,
  actions,
  onResolve,
}: {
  interruptId: string;
  actions: ActionRequestItem[];
  onResolve: (decisions: { type: 'approve' | 'reject'; message?: string }[]) => void;
}) {
  const [busy, setBusy] = useState(false);
  void _id;

  const decide = (type: 'approve' | 'reject') => {
    setBusy(true);
    onResolve(actions.map(() => ({ type })));
  };

  return (
    <div className="approvals">
      <h3>Approval needed — agent wants to write docs</h3>
      {actions.map((a, i) => (
        <details key={i} open>
          <summary>
            <code>{a.name}</code>
          </summary>
          <pre>{JSON.stringify(a.args, null, 2)}</pre>
        </details>
      ))}
      <div className="row">
        <button disabled={busy} onClick={() => decide('approve')}>
          Approve write
        </button>
        <button disabled={busy} onClick={() => decide('reject')} className="ghost">
          Reject
        </button>
      </div>
    </div>
  );
}
