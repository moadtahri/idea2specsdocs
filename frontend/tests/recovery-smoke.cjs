// Verify partial SSE delivery, attachment retries, deletion and collapsible docs.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');
const http = require('node:http');

(async () => {
  const attempts = [];
  let finish;
  const server = http.createServer(async (request, response) => {
    let body = '';
    for await (const chunk of request) body += chunk;
    attempts.push(JSON.parse(body));
    response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache' });
    const emit = (event) => response.write(`data: ${JSON.stringify(event)}\r\n\r\n`);
    response.write(': connected\r\n\r\n');
    emit({ type: 'status', text: 'Reading your attached notes…' });
    const pulse = setInterval(() => emit({ type: 'heartbeat' }), 200);
    finish = (failed) => {
      clearInterval(pulse);
      if (failed) emit({ type: 'error', detail: 'The model service is temporarily unavailable. Please resend.' });
      else {
        emit({ type: 'token', source: 'main', text: 'Your notes describe a simple personal task list.' });
        emit({ type: 'done', thread_id: 'test' });
      }
      response.end();
    };
    response.on('close', () => clearInterval(pulse));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const json = (route, value) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) });
    await page.route('**/api/projects', (route) => json(route, [{ project_id: 'test', title: 'Todo app', updated_at: new Date().toISOString() }]));
    await page.route('**/api/projects/test/docs', (route) => json(route, { docs: [] }));
    let uploads = 0;
    await page.route('**/api/projects/test/uploads', (route) => {
      uploads++;
      const filename = route.request().postDataBuffer().toString().match(/filename="([^"]+)"/)[1];
      return json(route, { attachment_id: `file-${uploads}`, filename, size: 30, content_type: 'text/plain', text_preview: 'Todo app notes' });
    });
    await page.route('**/api/chat', (route) => route.continue({ url: `http://127.0.0.1:${server.address().port}/api/chat` }));
    await page.goto('http://127.0.0.1:5178');
    await page.locator('select').selectOption('test');
    const chat = page.locator('.chat');
    const expanded = await chat.boundingBox();
    await page.getByRole('button', { name: 'Hide handover docs' }).click();
    await page.locator('.docs').waitFor({ state: 'hidden' });
    const collapsed = await chat.boundingBox();
    assert.ok(collapsed.width > expanded.width + 250);
    await page.getByRole('button', { name: 'Show handover docs' }).click();
    await page.locator('.docs').waitFor({ state: 'visible' });

    await page.locator('input[type="file"]').setInputFiles([
      { name: 'requirements.txt', mimeType: 'text/plain', buffer: Buffer.from('Users create and complete tasks.') },
      { name: 'constraints.md', mimeType: 'text/markdown', buffer: Buffer.from('No sign-in for the MVP.') },
    ]);
    await page.getByRole('button', { name: 'Remove constraints.md' }).waitFor();
    const input = page.getByRole('textbox', { name: 'Message', exact: true });
    await input.fill('Discuss my todo list app');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByText('Reading your attached notes…', { exact: true }).waitFor();
    assert.equal(attempts.length, 1);
    assert.equal(await page.getByRole('button', { name: 'Send', exact: true }).isDisabled(), true);
    await page.waitForFunction(() => document.querySelector('.agent-status small')?.textContent.includes('1s elapsed'));
    // The server has not finished: this asserts progress is visible DURING streaming.
    assert.equal(await page.locator('.agent-status.working').count(), 1);
    finish(true);
    await page.getByRole('button', { name: 'Resend', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Resend', exact: true }).click();
    await page.getByText('Reading your attached notes…', { exact: true }).waitFor();
    assert.equal(attempts.length, 2);
    assert.equal(attempts[1].message, attempts[0].message);
    assert.deepEqual(attempts[1].attachment_ids, ['file-1', 'file-2']);
    assert.equal(attempts[1].message_id, attempts[0].message_id);
    assert.equal(await page.locator('.msg.user').count(), 1);
    finish(false);
    await page.getByText('Your notes describe a simple personal task list.').waitFor();
    await page.locator('.agent-status.working').waitFor({ state: 'detached' });
    assert.equal(uploads, 2);
    await input.fill('A message to delete');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByText('Reading your attached notes…', { exact: true }).waitFor();
    finish(true);
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    assert.equal(await page.getByText('A message to delete', { exact: true }).count(), 0);
    assert.equal(await page.locator('.error').count(), 0);
    assert.equal(await page.getByText('Your notes describe a simple personal task list.').count(), 1);
    await page.getByRole('button', { name: 'Hide handover docs' }).click();
    await page.screenshot({ path: 'tests/artifacts/chat-collapsed.png', fullPage: true });
    console.log('Recovery smoke passed: progress before completion, heartbeats, elapsed time, text + attachments preserved on resend, failed message deletion, docs collapse and full-width chat.');
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
