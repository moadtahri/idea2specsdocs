import { useEffect, useState } from 'react';
import { api, type Intake, type ProjectBrief, type QualityState, type WorkItem } from '../api';
import DecisionMap, { ownerLabels } from './DecisionMap';

const intakes: [Intake, string][] = [
  ['idea', 'A new idea (nothing built yet)'], ['feature', 'A codebase plus a feature'], ['cleanup', 'A codebase to redo or clean up'],
];

const fields: [keyof ProjectBrief, string][] = [
  ['vertical', 'Industry / app vertical'], ['service', 'Service provided'], ['purpose', 'Problem and purpose'],
  ['users', 'Users and roles'], ['workflows', 'Core workflows and exceptions'], ['scope', 'MVP scope and non-goals'],
  ['permissions', 'Ownership, permissions and deletion'], ['data_lifecycle', 'Data, retention and search'],
  ['constraints', 'Integrations, budget, scale and constraints'], ['success_criteria', 'Measurable success and acceptance'],
];

function Decision({ item, titles, open, disabled, resolve }: {item: WorkItem; titles: Map<string, string>; open?: boolean; disabled: boolean; resolve: (item: WorkItem, status: string, text: string) => void}) {
  const [text, setText] = useState(item.resolution || item.proposal);
  const waiting = (item.blocked_by ?? []).map(id => titles.get(id) ?? 'an earlier decision');
  return <details className="quality-card" open={open}><summary>{item.title} · {item.status} · {item.impact}</summary>
    <p>{item.detail}</p><p>{ownerLabels[item.owner_type ?? 'stakeholder']} · Owner: {item.owner} · Affects: {item.affected_docs.join(', ')}</p>
    {!!waiting.length && <p>Settle first: {waiting.join(', ')}</p>}
    {item.answered_with && <p>You answered in chat: “{item.answered_with}”</p>}
    {item.proposal && <p>Proposed answer: {item.proposal}</p>}
    <label>Decision or reason for deferral<textarea value={text} onChange={event => setText(event.target.value)} /></label>
    <div className="row"><button disabled={disabled || !text.trim()} onClick={() => resolve(item, 'resolved', text)}>Confirm decision</button>
      <button className="ghost" disabled={disabled || !text.trim()} onClick={() => resolve(item, 'deferred', text)}>Defer with reason</button>
      <button className="ghost" disabled={disabled} onClick={() => resolve(item, 'open', '')}>Reopen</button></div>
  </details>;
}

export default function QualityPanel({ projectId, refreshKey, disabled, onDiscuss, onChanged }: {
  projectId: string; refreshKey: number; disabled: boolean; onDiscuss: (message: string) => void; onChanged: () => void;
}) {
  const [state, setState] = useState<QualityState | null>(null);
  const [draft, setDraft] = useState<ProjectBrief | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [environment, setEnvironment] = useState('production');
  const [scope, setScope] = useState('implementation');
  const [revision, setRevision] = useState('');
  const [command, setCommand] = useState('');
  const [summary, setSummary] = useState('');
  const [coverage, setCoverage] = useState('');
  const [outcome, setOutcome] = useState('passed');
  const [file, setFile] = useState<File | null>(null);
  const [attested, setAttested] = useState(false);
  const [selected, setSelected] = useState('');
  const [answersNote, setAnswersNote] = useState('');
  const bringBackAnswers = async (filled: File | undefined) => {
    if (!filled) return;
    setAnswersNote('Reading answers…');
    try {
      const result = await api.questionnaireAnswers(projectId, await filled.text());
      const n = result.settled.length;
      setAnswersNote(`${n} decision${n === 1 ? '' : 's'} settled${result.answered_by ? ` by ${result.answered_by}` : ''}.`
        + (result.refused.length ? ` ${result.refused.length} not applied: ${result.refused.map(r => r.reason).join('; ')}` : ''));
      await refresh(); onChanged();
    } catch (e) {
      setAnswersNote(e instanceof Error ? e.message : 'Could not read that file.');
    }
  };
  const refresh = async () => {
    const current = await api.quality(projectId, environment);
    setState(current); setDraft(current.brief.brief);
    return current;
  };
  useEffect(() => {
    let active = true;
    api.quality(projectId, environment).then(current => { if (active) { setState(current); setDraft(current.brief.brief); setError(''); } }).catch(() => { if (active) setError('Project brief could not be loaded. Retry to review it.'); });
    return () => { active = false; };
  }, [projectId, refreshKey, environment]);
  const act = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label); setError('');
    try { await action(); await refresh(); onChanged(); } catch (failure) { setError(failure instanceof Error ? failure.message : 'Please retry.'); }
    finally { setBusy(''); }
  };
  const locked = disabled || !!busy;
  const titles = new Map((state?.items ?? []).map(item => [item.id, item.title]));
  const selectedItem = state?.items.find(item => item.id === selected);
  const decidable = state?.frontier?.length ?? 0;
  const resolveDecision = (value: WorkItem, status: string, text: string) =>
    void act('Recording decision…', () => api.resolveItem(projectId, value.id, status, text));
  return <section className="quality-panel" aria-label="Project brief and quality">
    <div className="quality-heading"><span>{state?.brief.status === 'approved' ? 'Brief approved' : 'Clarify → approve brief → research & plan'}
      {state?.brief.brief.vertical && ` · ${state.brief.brief.vertical}`}</span>
      <button className="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Collapse brief & quality' : 'Review project brief'}</button></div>
    {open && <div className="quality-body">
      <p>Questions follow your app’s industry and service. Wizi reads your description and files first, then clarifies missing decisions before planning the bundle.</p>
      {!state && <button disabled={!!busy} onClick={() => void act('Loading brief…', refresh)}>Retry loading brief</button>}
      {draft && state && <>
        <details open={state.brief.status !== 'approved'}><summary>Project brief · {state.brief.status} · {10 - state.brief.missing.length}/10 areas described</summary>
          <fieldset disabled={locked} className="brief-fields">
            <label>What you brought<select aria-label="What you brought" value={draft.intake ?? 'idea'} onChange={event => setDraft({...draft, intake: event.target.value as Intake})}>
              {intakes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            {fields.map(([key, label]) => <label key={key}>{label}<textarea aria-label={label} value={String(draft[key])} onChange={event => setDraft({...draft, [key]: event.target.value})} /></label>)}
            {(['assumptions', 'sources', 'open_questions'] as const).map(key => <label key={key}>{key.replace('_', ' ')} (one per line)<textarea value={draft[key].join('\n')} onChange={event => setDraft({...draft, [key]: event.target.value.split('\n').filter(line => line.trim())})} /></label>)}
          </fieldset>
          {state.brief.missing.length > 0 && <p>Still to clarify: {state.brief.missing.map(key => key.replace('_', ' ')).join(', ')}.</p>}
          <div className="row"><button disabled={locked} onClick={() => void act('Saving brief…', () => api.saveBrief(projectId, draft))}>Save brief changes</button>
            <button disabled={locked || fields.some(([key]) => !String(draft[key]).trim()) || !!draft.open_questions.length || state.brief.status === 'approved'} onClick={() => void act('Approving brief…', async () => {
              const saved = await api.saveBrief(projectId, draft);
              await api.approveBrief(projectId, saved.revision);
              setOpen(false);
              onDiscuss('I approved the project brief. Use its vertical and service to research the remaining risks and plan the handover bundle.');
            })}>Approve brief & plan bundle</button>
            <button className="ghost" disabled={locked} onClick={() => onDiscuss('Please clarify the missing project brief details using my supplied context. Establish the app vertical and service first, then ask up to three relevant questions at a time.')}>Discuss with wizi</button></div>
        </details>
        <details open={decidable > 0 && state.brief.status !== 'approved'}><summary>Decisions and requirements · {state.items.length}{decidable > 0 && ` · ${decidable} decidable now`}</summary>
          <p>Proposals need your confirmation. Deferring records a scope decision; it does not establish that a control was implemented.</p>
          {decidable > 0 && <div className="questionnaire">
            <a href={`/api/projects/${projectId}/questionnaire`} download><button className="ghost" disabled={locked}>Questions for someone else (.md)</button></a>
            <label className="file-pick">Bring back their answers
              <input type="file" accept=".md,text/markdown,text/plain" hidden disabled={locked}
                onChange={(e) => { void bringBackAnswers(e.target.files?.[0]); e.target.value = ''; }} />
            </label>
            {answersNote && <p role="status" className="muted">{answersNote}</p>}
          </div>}
          {!!state.items.length && <DecisionMap items={state.items} frontier={state.frontier ?? []} selected={selected} onSelect={id => setSelected(selected === id ? '' : id)} />}
          {selectedItem && <Decision key={`selected-${selectedItem.id}-${selectedItem.status}`} item={selectedItem} titles={titles} open disabled={locked} resolve={resolveDecision} />}
          {state.items.filter(item => item.id !== selected).map(item => <Decision key={item.id + item.status} item={item} titles={titles} disabled={locked} resolve={resolveDecision} />)}
          {!state.items.length && <p>No structured decisions recorded yet.</p>}
        </details>
        <details><summary>Bundle review · {state.review_status.replace('_', ' ')}</summary>
          <p>Implementation specification: {state.ready_for_implementation ? 'ready' : 'readiness not established'} · Implementation evidence: {state.implementation_verified ? 'covered' : 'not established'} · Production: {state.ready_for_production ? 'ready from supplied evidence' : 'not established'}</p>
          <label>Target environment<input value={environment} onChange={event => setEnvironment(event.target.value)} disabled={locked} /></label>
          <button disabled={locked || !environment.trim()} onClick={() => void act('Reviewing contracts and citations…', () => api.review(projectId, environment))}>Run independent review</button>
          {!!state.security_coverage?.length && <>
            <h4>Security-to-QA coverage</h4>
            <p>These links describe planned verification. They do not establish that tests passed.</p>
            <table><thead><tr><th>Control</th><th>QA test cases</th></tr></thead><tbody>
              {state.security_coverage.map(row => <tr key={row.control_id}><td>{row.control_id}</td><td>{row.mapped ? row.test_ids.join(', ') : 'Unmapped — implementation blocker'}</td></tr>)}
            </tbody></table>
            {state.security_coverage.some(row => !row.mapped) && <button disabled={locked} onClick={() => onDiscuss(`Please repair security-to-QA traceability for these controls: ${state.security_coverage.filter(row => !row.mapped).map(row => row.control_id).join(', ')}. Read the saved security blueprint and QA plan, preserve existing IDs, reuse cases only if their assertions cover the control, and propose missing test procedures with setup, steps, expected results and automation or a repeatable manual procedure. Run the contract preflight after approved changes. Do not claim tests passed or promote document status without evidence.`)}>Complete missing security coverage with wizi</button>}
          </>}
          {state.last_review && <><p>{state.last_review.summary}</p>{state.last_review.errors.map((value, index) => <p className="error" key={index}>{value}</p>)}</>}
          {state.findings.map(finding => <details className="quality-card" key={finding.id}><summary>{finding.title} · {finding.severity} · {finding.impact}</summary>
            <p>{finding.detail}</p><p>{finding.recommendation}</p>
            {finding.citations.map((citation, index) => <blockquote key={index}><small>{citation.slug}, line {citation.line}</small><p>{citation.quote}</p></blockquote>)}
            <button disabled={locked} onClick={() => onDiscuss(`Please address this review finding in the affected contracts, preserving approved decisions: ${finding.title}. ${finding.detail} ${finding.recommendation}`)}>Discuss finding with wizi</button>
          </details>)}
        </details>
        <details><summary>Verification evidence · {state.evidence.length}</summary>
          <p>{state.verification_note}</p>
          {state.evidence.map(record => <p key={record.id}>{record.scope}: {record.outcome} · {record.source_revision} · {record.environment} · {!record.artifact_valid ? 'attachment unavailable or changed' : record.spec_revision === state.spec_revision ? 'current specification' : 'outdated specification'}</p>)}
          <p>QA coverage: {state.required_test_ids.join(', ') || 'No test IDs yet'}. Launch coverage: {state.required_launch_ids.join(', ') || 'No launch control IDs yet'}.</p>
          <fieldset disabled={locked} className="brief-fields">
            <label>Check type<select value={scope} onChange={event => setScope(event.target.value)}><option value="implementation">Implementation tests</option><option value="production">Production controls</option></select></label>
            <label>Code revision<input value={revision} onChange={event => setRevision(event.target.value)} /></label>
            <label>Command / verification procedure<input value={command} onChange={event => setCommand(event.target.value)} /></label>
            <label>Result summary<textarea value={summary} onChange={event => setSummary(event.target.value)} /></label>
            <label>Covered requirement / test IDs (comma separated)<input value={coverage} onChange={event => setCoverage(event.target.value)} /></label>
            <label>Result<select value={outcome} onChange={event => setOutcome(event.target.value)}><option value="passed">Passed</option><option value="failed">Failed</option></select></label>
            <label>Result file<input type="file" accept=".txt,.md,.json,.csv,.pdf" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
            <label><input type="checkbox" checked={attested} onChange={event => setAttested(event.target.checked)} /> I confirm these results were obtained for this code revision and environment.</label>
          </fieldset>
          <button disabled={locked || !file || !attested || !revision.trim() || !command.trim() || summary.trim().length < 3 || !coverage.trim()} onClick={() => void act('Saving verification evidence…', async () => {
            const uploaded = await api.upload(projectId, file!);
            await api.recordEvidence(projectId, {scope, environment, source_revision: revision, command, summary, outcome, covered_ids: coverage.split(',').map(value => value.trim()).filter(Boolean), attachment_id: uploaded.attachment_id, attested});
            setAttested(false);
          })}>Record verification result</button>
        </details>
      </>}
    </div>}
    {busy && <p role="status" className="quality-progress"><span className="status-dot pulse" /> {busy}</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
