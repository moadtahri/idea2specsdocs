// Run against the real Compose stack. Deletes only the project this test creates.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true });
  let projectId;
  const base = process.env.ITOS_TEST_URL || 'http://127.0.0.1:8080';
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  try {
    const errors = [];
    const dialogs = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('dialog', async (dialog) => { dialogs.push(dialog.message()); await dialog.dismiss(); });
    await page.goto(base);
    await page.locator('.sidebar .brand-name', { hasText: 'itos' }).waitFor();
    assert.match(await page.title(), /itos.*wizi/);
    await page.getByLabel('Project name', { exact: true }).fill('Disposable UI verification');
    const created = page.waitForResponse((response) => response.url().endsWith('/api/projects') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'New project', exact: true }).click();
    projectId = (await (await created).json()).project_id;
    await page.getByRole('button', { name: 'Rename', exact: true }).click();
    await page.getByLabel('Project name', { exact: true }).fill('Renamed UI verification');
    await page.getByRole('button', { name: 'Save name', exact: true }).click();
    await page.locator('.chat-header h1', { hasText: 'Renamed UI verification' }).waitFor();
    await page.waitForFunction((id) => document.querySelector(`a[href="#${id}"]`)?.textContent.includes('Renamed UI verification'), projectId);
    const toggle = page.getByRole('button', { name: 'Brief and documents' });
    await toggle.click();
    await page.locator('#chat-side .docs-panel').waitFor({ state: 'visible' });
    await toggle.click();
    await page.locator('#chat-side').waitFor({ state: 'hidden' });
    await page.locator('input[type="file"]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('A simple personal task list with complete and delete actions.') });
    await page.getByRole('button', { name: 'Remove notes.txt' }).waitFor();
    await page.getByRole('textbox', { name: 'Message', exact: true }).fill('Discuss my todo app with me.');
    const connected = page.waitForResponse((response) => response.url().endsWith('/api/chat') && response.status() === 200);
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await connected;
    assert.equal(await page.locator('.status-pill.status-working').textContent(), 'Working');
    const deleted = page.waitForResponse((response) => response.request().method() === 'DELETE' && response.url().endsWith(`/api/projects/${projectId}`));
    await page.locator('.chat-header').getByRole('button', { name: 'Delete', exact: true }).click();
    await page.getByRole('button', { name: 'Delete for good', exact: true }).click();
    assert.equal((await deleted).status(), 204);
    await page.getByRole('heading', { name: 'Start a project', exact: true }).waitFor();
    assert.equal(await page.locator(`a[href="#${projectId}"]`).count(), 0);
    assert.equal((await page.request.get(`${base}/api/projects/${projectId}/docs`)).status(), 404);
    assert.deepEqual(dialogs, []);
    assert.deepEqual(errors, []);
    await page.screenshot({ path: 'tests/artifacts/itos-compose.png', fullPage: true });
    console.log('Compose browser passed: itos/wizi branding, rename in the chat header, brief-and-documents drawer, upload, live progress, delete (asked once) during active work.');
    projectId = null;
  } finally {
    if (projectId) await page.request.delete(`${base}/api/projects/${projectId}`).catch(() => {});
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
