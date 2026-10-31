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
      Object.defineProperty(navigator, 'mediaDevices', { value: {
        getUserMedia: async () => ({ getTracks: () => [{ stop: () => { window.stoppedTracks++; } }] }),
      } });
      window.MediaRecorder = class {
        static isTypeSupported(type) { return type === 'audio/mp4'; }
        constructor(_stream, options) { this.mimeType = options.mimeType; this.state = 'inactive'; }
        start() { this.state = 'recording'; }
        stop() {
          this.state = 'inactive';
          this.ondataavailable?.({ data: new Blob(['test recording'], { type: this.mimeType }) });
          this.onstop?.();
        }
      };
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
    let recordings = 0;
    await page.route('**/api/transcribe', (route) => {
      recordings++;
      assert.match(route.request().postData(), /filename="recording.mp4"/);
      assert.match(route.request().postData(), /Content-Type: audio\/mp4/);
      return recordings === 1
        ? json(route, { detail: 'Voice transcription cannot access its AWS secret.' }, 503)
        : json(route, { text: 'Add saved searches to the project.' });
    });

    await page.goto('http://127.0.0.1:5178');
    await page.locator('select').selectOption('test');
    const input = page.getByRole('textbox', { name: 'Message', exact: true });
    await input.fill('Plan this feature.\n\n```python\nprint("hello")\n```');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByRole('button', { name: '✅ Approve', exact: true }).waitFor();
    assert.equal(await page.locator('.msg.user .codeblock').count(), 1);
    assert.equal(await page.locator('.msg.agent .codeblock').count(), 1);
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

    await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page.getByText('Voice transcription cannot access its AWS secret.').waitFor();
    await page.getByRole('button', { name: 'Retry transcription' }).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value.includes('Add saved searches'));
    assert.equal(recordings, 2);
    assert.ok(await page.evaluate(() => window.stoppedTracks > 0));
    assert.equal(await page.getByText('voice note attached').count(), 0);
    assert.equal(await page.locator('.docs .codeblock').count(), 1);
    assert.equal(await page.locator('.docs .markdown strong').innerText(), 'save searches');
    await page.screenshot({ path: 'tests/artifacts/chat.png', fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Browser smoke passed: code callouts, CRLF streaming, approval/retry/changes, bundle rendering, microphone MP4 and transcription retry.');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
