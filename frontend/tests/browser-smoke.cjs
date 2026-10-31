// Run against Vite at :5178. Pass a Playwright installation path if it is external.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.addInitScript(() => {
      window.stoppedTracks = 0;
      // A real (oscillator) stream: dictation feeds it through an AudioWorklet.
      Object.defineProperty(navigator, 'mediaDevices', { value: {
        getUserMedia: async () => {
          const context = new AudioContext();
          const oscillator = context.createOscillator();
          const destination = context.createMediaStreamDestination();
          oscillator.connect(destination);
          oscillator.start();
          for (const track of destination.stream.getTracks()) {
            const stop = track.stop.bind(track);
            track.stop = () => { window.stoppedTracks++; stop(); oscillator.stop(); void context.close(); };
          }
          return destination.stream;
        },
      } });
    });
    const json = (route, value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    const emit = (route, events) => route.fulfill({ contentType: 'text/event-stream', body: events.map((event) => `data: ${JSON.stringify(event)}\r\n\r\n`).join('') });
    const token = (text) => ({ type: 'token', source: 'main', text });
    const done = { type: 'done', thread_id: 'test' };
    const review = (id) => ({ type: 'interrupt', interrupt_id: id, action_requests: [{ name: 'write_file', args: { file_path: '/docs/security-blueprint.md', content: '# Security\n\nSEC-1: Protect saved searches.\n\n```sql\nSELECT id FROM searches;\n```' } }], review_configs: [] });
    await page.route('**/api/projects', (route) => json(route, [{ project_id: 'test', title: 'Saved search feature', updated_at: new Date().toISOString() }]));
    await page.route('**/api/projects/test/docs', (route) => json(route, { docs: [
      { slug: 'bundle', title: 'Handover Bundle (readable)', updated_at: new Date().toISOString() },
      { slug: 'bundle-agent', title: 'Handover Bundle (for agents)', updated_at: new Date().toISOString() },
    ] }));
    await page.route('**/api/projects/test/history', (route) => json(route, { messages: [], pending: null, todos: [] }));
    await page.route('**/api/projects/test/feedback', (route) => json(route, { ratings: [] }));
    await page.route('**/api/projects/test/quality?*', (route) => json(route, {
      brief: { status: 'approved', revision: 'r1', brief: { vertical: 'Software', service: 'Saved searches' }, missing: [] },
      review_status: 'not_reviewed', spec_revision: 's1', ready_for_implementation: false, implementation_verified: false,
      ready_for_production: false, verification_note: '', items: [], frontier: [], findings: [], last_review: null,
      evidence: [], required_test_ids: [], required_launch_ids: [], security_coverage: [],
    }));
    await page.route('**/api/projects/test/docs/bundle', (route) => json(route, { slug: 'bundle', title: 'Overview', markdown: '# Feature overview\n\nUsers can **save searches**.\n\n- Review security\n- Verify acceptance tests\n\n```json\n{"saved": true}\n```' }));
    let chatCalls = 0;
    await page.route('**/api/chat', (route) => {
      const body = route.request().postDataJSON();
      chatCalls++;
      if (chatCalls === 1) return emit(route, [
        { type: 'thought', source: 'main', text: 'Hidden reasoning' },
        { type: 'token', source: 'tools:abc', text: 'Hidden specialist notes' },
        token('I will protect your saved searches.\n\n```ts\nconst enabled = true;\n```\n\nReply **approve** and I\'ll draft Doc 6 (security), or tell me what to change.'), done,
      ]);
      if (chatCalls === 2) {
        assert.match(body.message, /Approved/);
        return emit(route, [token('Review the security draft below.'), review('review-1'), done]);
      }
      if (chatCalls === 3) {
        assert.equal(body.resume[0].type, 'approve');
        return json(route, { detail: 'Temporary connection issue' }, 503);
      }
      if (chatCalls === 4) {
        assert.equal(body.resume[0].type, 'approve');
        return emit(route, [token('Your document has been saved.'), done]);
      }
      if (chatCalls === 5) return emit(route, [token('Review this update.'), review('review-2'), done]);
      if (chatCalls === 6) {
        assert.equal(body.resume[0].type, 'reject');
        assert.equal(body.resume[0].message, 'Keep saved searches private');
        return emit(route, [token('I revised the privacy requirement.'), review('review-3'), done]);
      }
      return emit(route, [token('Saved the revised document.'), done]);
    });
    // Dictation streams to /api/voice/listen (the AssemblyAI recording and its retry are gone): the first session fails, the second transcribes.
    let sessions = 0;
    let pcmChunks = 0;
    await page.routeWebSocket('**/api/voice/listen', (socket) => {
      sessions++;
      const session = sessions;
      const send = (value) => { try { socket.send(JSON.stringify(value)); } catch {} };
      send(session === 1 ? { type: 'error', text: 'Voice transcription cannot access its AWS secret.' } : { type: 'ready' });
      socket.onMessage((message) => {
        if (typeof message === 'string') return;
        pcmChunks++;
        if (pcmChunks === 2) {
          send({ type: 'partial', text: 'Add saved' });
          send({ type: 'final', text: 'Add saved searches to the project.' });
        }
      });
    });

    await page.goto('http://127.0.0.1:5178');
    await page.locator('a[href="#test"]').click();
    const input = page.getByRole('textbox', { name: 'Message', exact: true });
    await input.fill('Plan this feature.\n\n```python\nprint("hello")\n```');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByRole('button', { name: '✅ Approve', exact: true }).waitFor();
    // The user's message now shows as plain text (no code callout): its fence must survive verbatim.
    assert.match(await page.locator('.msg.msg-user .user-text').innerText(), /```python\nprint\("hello"\)\n```/);
    assert.equal(await page.locator('.msg.msg-kanya .codeblock').count(), 1);
    assert.equal(await page.getByText('Hidden reasoning').count(), 0);
    assert.equal(await page.getByText('Hidden specialist notes').count(), 0);
    await page.getByRole('button', { name: '✅ Approve', exact: true }).click();
    await page.getByText('Show the full draft').click();
    assert.equal(await page.locator('.approval-card .codeblock').count(), 1);
    await page.getByRole('button', { name: 'Approve & save' }).click();
    await page.getByText('Temporary connection issue').waitFor();
    await page.getByRole('button', { name: 'Approve & save' }).click();
    await page.getByText('Your document has been saved.').waitFor();
    await page.locator('.approvals').waitFor({ state: 'detached' });
    await input.fill('Update privacy');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByRole('button', { name: 'Request changes', exact: true }).click();
    await page.getByPlaceholder('What should be different?').fill('Keep saved searches private');
    await page.getByRole('button', { name: 'Send feedback', exact: true }).click();
    await page.getByRole('button', { name: 'Approve & save' }).click();
    await page.getByText('Saved the revised document.').waitFor();
    await page.locator('.approvals').waitFor({ state: 'detached' });

    await page.getByRole('button', { name: 'Dictate', exact: true }).click();
    await page.locator('.voice-caption.is-problem', { hasText: 'Voice transcription cannot access its AWS secret.' }).waitFor();
    await page.getByRole('button', { name: 'Dictate', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value.includes('Add saved searches'));
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Dictate', exact: true }).waitFor();
    assert.equal(sessions, 2);
    await page.waitForFunction(() => window.stoppedTracks >= 2);
    assert.equal(chatCalls, 7); // dictated words wait in the box; nothing is sent
    await page.getByRole('button', { name: 'Brief and documents' }).click();
    await page.locator('#chat-side .doc-row', { hasText: 'Handover Bundle (readable)' }).click();
    await page.locator('.reader-pane .reader-body .markdown').waitFor();
    assert.equal(await page.locator('.reader-body .codeblock').count(), 1);
    assert.equal(await page.locator('.reader-body .markdown strong').innerText(), 'save searches');
    await page.screenshot({ path: 'tests/artifacts/chat.png', fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Browser smoke passed: code callouts, CRLF streaming, approval/retry/changes, bundle in the reader, dictation with a failed then working voice session.');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
