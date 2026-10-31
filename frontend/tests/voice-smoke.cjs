// Run against Vite at :5178. wizi's voice (spec 09): dictation and voice mode over a routed /api/voice/listen socket, read aloud over /api/voice/speak.
// The AssemblyAI voice-note flow (meter, silence warning, token fallback, Cancel recording) is gone; these are its equivalents.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.addInitScript(() => {
      window.voiceTracksStopped = 0;
      window.voiceDenyPermission = false;
      Object.defineProperty(navigator, 'mediaDevices', { value: {
        getUserMedia: async () => {
          if (window.voiceDenyPermission) throw new DOMException('Denied', 'NotAllowedError');
          const context = new AudioContext();
          const oscillator = context.createOscillator();
          oscillator.frequency.value = 440;
          const gain = context.createGain();
          gain.gain.value = 0.18;
          const destination = context.createMediaStreamDestination();
          oscillator.connect(gain).connect(destination);
          oscillator.start();
          await context.resume();
          for (const track of destination.stream.getTracks()) {
            const stop = track.stop.bind(track);
            let stopped = false;
            track.stop = () => {
              if (stopped) return;
              stopped = true;
              window.voiceTracksStopped++;
              stop(); oscillator.stop(); void context.close();
            };
          }
          return destination.stream;
        },
      } });
    });
    const json = (route, value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    await page.route('**/api/projects', (route) => json(route, [{ project_id: 'test', title: 'Voice test', updated_at: new Date().toISOString() }]));
    await page.route('**/api/projects/test/docs', (route) => json(route, { docs: [] }));
    await page.route('**/api/projects/test/history', (route) => json(route, { messages: [], pending: null, todos: [] }));
    await page.route('**/api/projects/test/feedback', (route) => json(route, { ratings: [] }));
    await page.route('**/api/projects/test/quality?*', (route) => json(route, {
      brief: { status: 'approved', revision: 'r1', brief: { vertical: 'Software', service: 'Personal tasks' }, missing: [] },
      review_status: 'not_reviewed', spec_revision: 's1', ready_for_implementation: false, implementation_verified: false,
      ready_for_production: false, verification_note: '', items: [], frontier: [], findings: [], last_review: null,
      evidence: [], required_test_ids: [], required_launch_ids: [], security_coverage: [],
    }));
    let mode = 'dictate';
    let wsSessions = 0;
    let pcmChunks = 0;
    let stops = 0;
    const chats = [];
    const speeches = [];
    const emit = (events) => events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
    await page.route('**/api/chat', (route) => {
      chats.push(route.request().postDataJSON());
      return route.fulfill({ contentType: 'text/event-stream', body: emit([{ type: 'token', source: 'main', text: 'Here is a plan for your todo app.' }, { type: 'done', thread_id: 'test' }]) });
    });
    // Two seconds of 24 kHz 16-bit silence: long enough to see wizi speaking and to talk over it.
    await page.route('**/api/voice/speak', (route) => {
      speeches.push(route.request().postDataJSON());
      return route.fulfill({ contentType: 'audio/pcm', body: Buffer.alloc(24000 * 2 * 2) });
    });
    let socketNow;
    await page.routeWebSocket('**/api/voice/listen', (socket) => {
      wsSessions++;
      socketNow = socket;
      const sessionMode = mode;
      let chunks = 0;
      const send = (value) => { try { socket.send(JSON.stringify(value)); } catch {} };
      if (sessionMode === 'error') { send({ type: 'error', text: 'Live transcription unavailable' }); return; }
      send({ type: 'ready' });
      socket.onMessage((message) => {
        if (typeof message === 'string') {
          if (JSON.parse(message).type === 'stop') {
            stops++;
            send({ type: 'final', text: 'Add reminders.' }); // the last sentence still comes back after stop
          }
          return;
        }
        // 16-bit PCM, in whole 128-sample render quanta.
        assert.ok(message.byteLength > 0 && message.byteLength % 256 === 0);
        pcmChunks++;
        chunks++;
        if (sessionMode === 'dictate') {
          if (chunks === 2) {
            send({ type: 'speech_started' });
            send({ type: 'partial', text: 'Create' });
            send({ type: 'partial', text: 'Create a todo list' });
            send({ type: 'final', text: 'Create a todo list.' });
          }
          if (chunks === 4) send({ type: 'partial', text: 'Add remind' });
        }
        if (sessionMode === 'voice' && chunks === 2) send({ type: 'final', text: 'Plan a todo app.' });
      });
    });

    await page.goto('http://127.0.0.1:5178');
    await page.locator('a[href="#test"]').click();
    const input = page.getByRole('textbox', { name: 'Message', exact: true });
    const caption = page.locator('.voice-caption');
    await input.fill('My notes');

    // Dictation: partial words show in the caption, finished sentences join the box, nothing is sent.
    await page.getByRole('button', { name: 'Dictate', exact: true }).click();
    await page.getByRole('button', { name: 'Stop dictating', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value === 'My notes Create a todo list.');
    await caption.filter({ hasText: 'Add remind' }).waitFor();
    await page.screenshot({ path: 'tests/artifacts/live-voice.png', fullPage: true });
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Dictate', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value === 'My notes Create a todo list. Add reminders.');
    assert.ok(pcmChunks > 3);
    assert.equal(stops, 1);
    assert.equal(await page.evaluate(() => window.voiceTracksStopped), 1);
    assert.equal(chats.length, 0); // Dictated text is reviewed before sending to wizi.
    await input.fill('Edited transcript');

    // The relay reports a problem: it shows, and the microphone is released.
    mode = 'error';
    await page.getByRole('button', { name: 'Dictate', exact: true }).click();
    await page.locator('.voice-caption.is-problem', { hasText: 'Live transcription unavailable' }).waitFor();
    await page.waitForFunction(() => window.voiceTracksStopped === 2);
    assert.equal(await input.inputValue(), 'Edited transcript');

    await page.evaluate(() => { window.voiceDenyPermission = true; });
    const sessionsBeforeDenied = wsSessions;
    await page.getByRole('button', { name: 'Dictate', exact: true }).click();
    await page.locator('.voice-caption.is-problem', { hasText: 'Allow the microphone to use voice.' }).waitFor();
    assert.equal(wsSessions, sessionsBeforeDenied);
    await page.evaluate(() => { window.voiceDenyPermission = false; });

    // Voice mode: a finished sentence goes to wizi as a message and its reply is read aloud; talking over it stops it.
    mode = 'voice';
    await input.fill('');
    await page.getByRole('button', { name: 'Start voice', exact: true }).click();
    await page.getByRole('button', { name: 'End voice', exact: true }).waitFor();
    await page.locator('.msg.msg-kanya .bubble', { hasText: 'Here is a plan for your todo app.' }).waitFor();
    assert.equal(chats.length, 1);
    assert.equal(chats[0].message, 'Plan a todo app.');
    await caption.filter({ hasText: 'wizi is speaking' }).waitFor();
    assert.deepEqual(speeches, [{ text: 'Here is a plan for your todo app.' }]);
    socketNow.send(JSON.stringify({ type: 'speech_started' }));
    await caption.filter({ hasText: 'Listening… speak to wizi' }).waitFor();
    const stoppedBeforeEnd = await page.evaluate(() => window.voiceTracksStopped);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Start voice', exact: true }).waitFor();
    await page.waitForFunction((before) => window.voiceTracksStopped > before, stoppedBeforeEnd);

    // Read aloud on a reply streams it from /api/voice/speak.
    const actions = page.locator('.reply-actions');
    await actions.getByRole('button', { name: 'Read aloud', exact: true }).click();
    await actions.getByRole('button', { name: 'Stop reading', exact: true }).waitFor();
    assert.equal(speeches.length, 2);
    assert.deepEqual(speeches[1], { text: 'Here is a plan for your todo app.' });
    await actions.getByRole('button', { name: 'Read aloud', exact: true }).waitFor();

    // Leaving the chat while dictating releases the microphone.
    mode = 'dictate';
    await page.getByRole('button', { name: 'Dictate', exact: true }).click();
    await page.getByRole('button', { name: 'Stop dictating', exact: true }).waitFor();
    const stoppedBeforeUnmount = await page.evaluate(() => window.voiceTracksStopped);
    await page.locator('a[href="#new"]').click();
    await page.getByRole('heading', { name: 'Start a project', exact: true }).waitFor();
    await page.waitForFunction((before) => window.voiceTracksStopped > before, stoppedBeforeUnmount);
    assert.equal(chats.length, 1);
    assert.deepEqual(errors, []);
    console.log('Live voice passed: real audio stream, PCM streaming, partial captions, dictation into the box, last words after stop, relay error, denied permission, voice mode send and spoken reply, talk-over, read aloud and unmount cleanup.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
