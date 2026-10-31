// Real Compose API and UI; only the post-approval model reply is stubbed.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const base = process.env.ITOS_TEST_URL || 'http://127.0.0.1:8080';
  let project;
  try {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    project = (await (await page.request.post(`${base}/api/projects`, {data: {title: 'Disposable discovery verification'}})).json()).project_id;
    const brief = {
      vertical: 'Appointment booking for independent salons', service: 'Book and cancel hair appointments',
      purpose: 'Reduce calls and appointment conflicts', users: 'Customers and salon owner',
      workflows: 'Choose provider and time, book, cancel at least 24 hours before appointment',
      scope: 'Booking and cancellation only; no payments or marketplace', permissions: 'Customers manage their bookings; owner manages schedule',
      data_lifecycle: 'Name and email; delete expired bookings after 90 days; owner search by date',
      constraints: 'Single salon, local time zone, no payments, budget and timeline flexible',
      success_criteria: 'Prevent double booking and enforce the cancellation window', assumptions: [], sources: ['Owner supplied brief'], open_questions: [],
    };
    let saved = await page.request.put(`${base}/api/projects/${project}/brief`, {data: brief});
    assert.equal(saved.status(), 200);
    await page.route('**/api/chat', route => {
      assert.match(route.request().postDataJSON().message, /approved the project brief/i);
      return route.fulfill({contentType: 'text/event-stream', body: 'data: {"type":"token","source":"main","text":"I will plan the salon booking bundle using your cancellation and scheduling decisions."}\n\ndata: {"type":"done","thread_id":"test"}\n\n'});
    });
    await page.goto(base);
    await page.getByLabel('Current project').selectOption(project);
    await page.getByRole('button', {name: 'Review project brief', exact: true}).click();
    assert.equal(await page.getByLabel('Industry / app vertical', {exact: true}).inputValue(), brief.vertical);
    assert.equal(await page.getByLabel('Service provided', {exact: true}).inputValue(), brief.service);
    await page.getByRole('button', {name: 'Approve brief & plan bundle', exact: true}).click();
    await page.getByText('Brief approved', {exact: false}).waitFor();
    let state = await (await page.request.get(`${base}/api/projects/${project}/quality`)).json();
    assert.equal(state.brief.status, 'approved');
    assert.equal(state.ready_for_implementation, false);
    await page.getByRole('button', {name: 'Review project brief', exact: true}).click();
    await page.getByText('Bundle review · not reviewed', {exact: true}).click();
    await page.getByRole('button', {name: 'Run independent review', exact: true}).click();
    await page.getByText('Write some draft documents before requesting a bundle review.', {exact: true}).waitFor();
    state = await (await page.request.get(`${base}/api/projects/${project}/quality`)).json();
    assert.equal(state.review_status, 'incomplete');
    assert.equal(state.ready_for_production, false);
    await page.getByText('Project brief · approved · 10/10 areas described', {exact: true}).click();
    await page.getByLabel('Service provided', {exact: true}).fill('Book appointments and manage a waitlist');
    await page.getByRole('button', {name: 'Save brief changes', exact: true}).click();
    await page.getByText('Project brief · proposed · 10/10 areas described', {exact: true}).waitFor();
    state = await (await page.request.get(`${base}/api/projects/${project}/quality`)).json();
    assert.equal(state.brief.status, 'proposed');
    assert.equal(state.review_status, 'outdated');
    assert.deepEqual(errors, []);
    await page.screenshot({path: 'tests/artifacts/itos-discovery-quality.png', fullPage: true});
    console.log('PASS: vertical/service brief, approval, review feedback and revision invalidation in Compose UI');
  } catch (error) {
    await page.screenshot({path: 'tests/artifacts/itos-quality-failure.png', fullPage: true});
    console.error(await page.locator('.quality-panel').innerText());
    throw error;
  } finally {
    if (project) await page.request.delete(`${base}/api/projects/${project}`);
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
