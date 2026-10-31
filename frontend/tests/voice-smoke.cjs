const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.addInitScript(() => {
      window.voiceTracksStopped = 0;
      window.voiceDenyPermission = false;
      window.voiceGains = [];
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
          window.voiceGains.push(gain);
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
      window.voiceSetVolume = (volume) => window.voiceGains.forEach((gain) => { gain.gain.value = volume; });
    });
    const json = (route, value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    await page.route('**/api/projects', (route) => json(route, [{ project_id: 'test', title: 'Voice test', updated_at: new Date().toISOString() }]));
    await page.route('**/api/projects/test/docs', (route) => json(route, { docs: [] }));
    let mode = 'normal';
    let tokenGate;
    let wsSessions = 0;
    let pcmChunks = 0;
    let terminations = 0;
    let fallbackCalls = 0;
    let chatCalls = 0;
    await page.route('**/api/transcribe/token', async (route) => {
      if (mode === 'token-fail') return json(route, { detail: 'Live transcription unavailable' }, 502);
      if (mode === 'hold-token') await new Promise((resolve) => { tokenGate = resolve; });
      try { await json(route, { token: 'temporary-test-token', websocket_url: 'wss://streaming.assemblyai.com/v3/ws', sample_rate: 16000 }); } catch {}
    });
    await page.route('**/api/transcribe', (route) => {
      fallbackCalls++;
      return json(route, { text: 'Whole recording after interruption.' });
    });
    await page.route('**/api/chat', (route) => { chatCalls++; return json(route, {}); });
    await page.routeWebSocket('wss://streaming.assemblyai.com/**', (socket) => {
      wsSessions++;
      const sessionMode = mode;
      let chunks = 0;
      const send = (value) => { try { socket.send(JSON.stringify(value)); } catch {} };
      send({ type: 'Begin', id: `voice-${wsSessions}` });
      socket.onMessage((message) => {
        if (typeof message === 'string') {
          const event = JSON.parse(message);
          if (event.type === 'Terminate') {
            terminations++;
            send({ type: 'Turn', turn_order: 0, end_of_turn: true, transcript: 'Create a todo list.' });
            send({ type: 'Turn', turn_order: 1, end_of_turn: true, transcript: 'Add reminders.' });
            send({ type: 'Termination', audio_duration_seconds: 5 });
          }
          return;
        }
        assert.ok(message.byteLength >= 1600 && message.byteLength <= 32000);
        pcmChunks++;
        chunks++;
        if (sessionMode === 'disconnect') { socket.close({ code: 1011, reason: 'Test disconnect' }); return; }
        if (chunks === 2) {
          send({ type: 'Turn', turn_order: 0, end_of_turn: false, transcript: 'Create' });
          send({ type: 'Turn', turn_order: 0, end_of_turn: false, transcript: 'Create a todo list' });
          send({ type: 'Turn', turn_order: 0, end_of_turn: true, transcript: 'Create a todo list.' });
        }
        if (chunks === 4) send({ type: 'Turn', turn_order: 1, end_of_turn: false, transcript: 'Add remind' });
      });
    });

    await page.goto('http://127.0.0.1:5178');
    await page.getByRole('combobox', { name: 'Current project' }).selectOption('test');
    const input = page.getByRole('textbox', { name: 'Message', exact: true });
    await input.fill('My notes');
    const start = () => page.getByRole('button', { name: 'Record voice message', exact: true }).click();
    await start();
    await page.getByRole('button', { name: 'Stop', exact: true }).waitFor();
    await page.waitForFunction(() => Number(document.querySelector('.audio-meter')?.dataset.level) > 0.05);
    await page.getByText('Create a todo list. Add remind', { exact: true }).waitFor();
    assert.equal(await input.inputValue(), 'My notes');
    await page.evaluate(() => window.voiceSetVolume(0));
    await page.waitForFunction(() => Number(document.querySelector('.audio-meter')?.dataset.level) === 0);
    await page.getByText('No audio detected — check your microphone', { exact: true }).waitFor();
    await page.evaluate(() => window.voiceSetVolume(0.2));
    await page.waitForFunction(() => Number(document.querySelector('.audio-meter')?.dataset.level) > 0.05);
    await page.getByText('Listening to your microphone', { exact: true }).waitFor();
    await page.screenshot({ path: 'tests/artifacts/live-voice.png', fullPage: true });
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value === 'My notes\nCreate a todo list. Add reminders.');
    assert.equal(fallbackCalls, 0);
    assert.ok(pcmChunks > 3);
    assert.equal(terminations, 1);
    assert.equal(await page.evaluate(() => window.voiceTracksStopped), 1);
    assert.equal(chatCalls, 0); // Transcript is reviewed before sending to wizi.
    await input.fill('Edited transcript');

    mode = 'disconnect';
    await start();
    await page.getByText('Live transcription unavailable — your voice note is still being recorded', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value === 'Edited transcript\nWhole recording after interruption.');
    assert.equal(fallbackCalls, 1);

    mode = 'token-fail';
    const sessionsBeforeFallback = wsSessions;
    await start();
    await page.getByText('Recording a voice note — transcription starts when you stop', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page.waitForFunction(() => (document.querySelector('textarea[aria-label="Message"]').value.match(/Whole recording after interruption\./g) || []).length === 2);
    assert.equal(fallbackCalls, 2);
    assert.equal(wsSessions, sessionsBeforeFallback);

    await page.evaluate(() => { window.voiceDenyPermission = true; });
    await start();
    await page.getByText('Microphone access was denied. Allow microphone access in your browser and try again.', { exact: true }).waitFor();
    await page.evaluate(() => { window.voiceDenyPermission = false; });
    mode = 'hold-token';
    const socketsBeforeCancel = wsSessions;
    await start();
    await page.getByText('Connecting live transcription…', { exact: true }).waitFor();
    const stoppedBeforeCancel = await page.evaluate(() => window.voiceTracksStopped);
    await page.getByRole('button', { name: 'Cancel recording' }).click();
    await page.waitForFunction((before) => window.voiceTracksStopped > before, stoppedBeforeCancel);
    if (tokenGate) tokenGate();
    assert.equal(wsSessions, socketsBeforeCancel);

    mode = 'normal';
    await start();
    await page.getByRole('button', { name: 'Stop', exact: true }).waitFor();
    const stoppedBeforeUnmount = await page.evaluate(() => window.voiceTracksStopped);
    await page.getByRole('combobox', { name: 'Current project' }).selectOption('');
    await page.waitForFunction((before) => window.voiceTracksStopped > before, stoppedBeforeUnmount);
    assert.equal(fallbackCalls, 2);
    assert.equal(chatCalls, 0);
    assert.deepEqual(errors, []);
    console.log('Live voice passed: real audio meter and silence detection, PCM streaming, partial revisions, final deduplication, editable text, disconnect fallback, denied permission, cancelled startup and unmount cleanup.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
