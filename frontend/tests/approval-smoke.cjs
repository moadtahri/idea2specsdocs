// Regression: textual requests refer to a card that never arrived over SSE.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage();
  try {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      const fetchOriginal = window.fetch.bind(window);
      window.fetch = (...args) => {
        if (window.failNextChat && String(args[0]).endsWith('/api/chat')) {
          window.failNextChat = false;
          return Promise.reject(new DOMException('BodyStreamBuffer was aborted', 'AbortError'));
        }
        return fetchOriginal(...args);
      };
    });
    const json = (route, value) => route.fulfill({contentType: 'application/json', body: JSON.stringify(value)});
    await page.route('**/api/projects', route => json(route, [{project_id: 'approval-test', title: 'Approval regression', updated_at: new Date().toISOString()}]));
    await page.route('**/api/projects/approval-test/docs', route => json(route, {docs: []}));
    await page.route('**/api/projects/approval-test/quality?*', route => json(route, {brief: {status: 'approved', brief: {vertical: 'Software', service: 'Personal tasks'}, missing: []}}));
    const wording = 'Please use the **Approve & save / Request changes buttons** on the PRD card to approve — I’ll start Doc 2 (Technical Spike) once you do. &#x20;';
    let calls = 0;
    let failedApproval;
    await page.route('**/api/chat', route => {
      const body = route.request().postDataJSON();
      calls++;
      const emit = events => route.fulfill({contentType: 'text/event-stream', body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')});
      if (calls === 6) return emit([{type: 'interrupt', interrupt_id: 'real-document-approval', action_requests: [{name: 'write_file', args: {file_path: '/docs/prd.md', content: '# PRD\nFR-1: Create tasks.'}}], review_configs: []}, {type: 'done', thread_id: 'approval-test'}]);
      if (calls === 7) {
        assert.equal(body.resume[0].type, 'approve');
        failedApproval = body;
        return emit([{type: 'error', detail: 'BodyStreamBuffer was aborted'}, {type: 'done', thread_id: 'approval-test'}]);
      }
      if (calls === 8) {
        assert.deepEqual(body, failedApproval, 'Retry must preserve the approval decision and request ID');
        return emit([{type: 'token', source: 'main', text: 'PRD saved successfully.'}, {type: 'done', thread_id: 'approval-test'}]);
      }
      let text = wording;
      if (calls === 2 || calls === 3) {
        assert.match(body.message, /Approved/);
        assert.equal(body.resume, null, 'Text-only approval must send a normal message, not resume a nonexistent interrupt');
        text = calls === 2 ? wording.replace('PRD', 'Technical Spike').replace('Doc 2 (Technical Spike)', 'Doc 3 (Architecture)') : 'Saved your approval. Continuing with architecture.';
      }
      if (calls === 4) text = 'Example wording only:\n\n```text\n' + wording + '\n```';
      const chunks = [text.slice(0, 30), text.slice(30)].map(text => ({type: 'token', source: 'main', text}));
      return route.fulfill({contentType: 'text/event-stream', body: [...chunks, {type: 'done', thread_id: 'approval-test'}].map(event => `data: ${JSON.stringify(event)}\n\n`).join('')});
    });
    await page.goto(process.env.ITOS_TEST_URL || 'http://127.0.0.1:8080');
    await page.getByLabel('Current project').selectOption('approval-test');
    const input = page.getByRole('textbox', {name: 'Message', exact: true});
    await input.fill('Draft my PRD');
    await page.getByRole('button', {name: 'Send', exact: true}).click();
    const actions = page.getByRole('group', {name: 'Approval actions'});
    const approve = actions.getByRole('button', {name: /Approve/});
    await approve.waitFor();
    assert.equal(await page.locator('.approvals').count(), 0);
    await actions.getByRole('button', {name: /Request changes/}).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value === 'Please change: ');
    assert.equal(await input.inputValue(), 'Please change: ');
    await approve.click();
    await approve.waitFor();
    await approve.click();
    await page.getByText('Saved your approval. Continuing with architecture.', {exact: true}).waitFor();
    await actions.waitFor({state: 'detached'});
    assert.equal(calls, 3);
    await input.fill('Show an example');
    await page.getByRole('button', {name: 'Send', exact: true}).click();
    await page.locator('.msg.agent .codeblock').waitFor();
    await page.waitForFunction(() => document.querySelector('.agent-status span:last-child')?.textContent === 'Finished');
    assert.equal(await actions.count(), 0, 'Code examples must not trigger approval');
    await page.evaluate(() => { window.failNextChat = true; });
    await input.fill('Continue');
    await page.getByRole('button', {name: 'Send', exact: true}).click();
    await page.getByText('The chat connection was interrupted. Click Resend to try again, or Delete to remove this request.', {exact: true}).waitFor();
    assert.equal(await page.getByText('BodyStreamBuffer was aborted', {exact: true}).count(), 0);
    await page.getByRole('button', {name: 'Resend', exact: true}).click();
    await approve.waitFor();
    assert.equal(calls, 5);
    assert.equal(await page.locator('.msg.user').count(), 5, 'Retry must preserve the existing user message');
    await approve.click();
    const save = page.getByRole('button', {name: 'Approve & save', exact: true});
    await save.waitFor();
    await save.click();
    await page.getByText('The chat connection was interrupted. Click Resend to try again, or Delete to remove this request.', {exact: true}).waitFor();
    assert.equal(await page.getByText('BodyStreamBuffer was aborted', {exact: true}).count(), 0);
    assert.equal(await save.isVisible(), true, 'An approval must remain recoverable after a streamed error');
    await page.getByRole('button', {name: 'Resend', exact: true}).click();
    await page.getByText('PRD saved successfully.', {exact: true}).waitFor();
    await page.locator('.approvals').waitFor({state: 'detached'});
    assert.equal(calls, 8);
    assert.deepEqual(errors, []);
    console.log('PASS: repeated approvals, fetch abort, SSE abort under Approve & save, and approval-preserving resend');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
