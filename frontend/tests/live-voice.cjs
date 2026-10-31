// Live AssemblyAI check: public sample audio replaces microphone input only.
const { chromium } = require(process.argv[2] || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const base = process.env.ITOS_TEST_URL || 'http://127.0.0.1:8080';
  let projectId;
  try {
    const response = await page.request.get('https://assembly.ai/wildfires.mp3');
    assert.equal(response.status(), 200);
    const audio = await response.body();
    assert.ok(audio.length < 10 * 1024 * 1024);
    await page.addInitScript(({ audio }) => {
      window.liveVoiceStats = { chunks: 0, turns: 0, terminated: 0, started: 0, error: '' };
      let fixture;
      Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: async () => {
        const context = new AudioContext();
        const bytes = Uint8Array.from(atob(audio), (character) => character.charCodeAt(0));
        const source = context.createBufferSource();
        source.buffer = await context.decodeAudioData(bytes.buffer);
        const destination = context.createMediaStreamDestination();
        source.connect(destination);
        await context.resume();
        fixture = () => { source.start(0, 0, 8); window.liveVoiceStats.started = performance.now(); };
        for (const track of destination.stream.getTracks()) {
          const stop = track.stop.bind(track);
          let stopped = false;
          track.stop = () => {
            if (stopped) return;
            stopped = true; stop();
            try { source.stop(); } catch {}
            void context.close();
          };
        }
        return destination.stream;
      } } });
      const NativeRecorder = window.MediaRecorder;
      window.MediaRecorder = class extends NativeRecorder {
        start(...args) { super.start(...args); fixture?.(); }
      };
      const NativeSocket = window.WebSocket;
      window.WebSocket = class extends NativeSocket {
        constructor(...args) {
          super(...args);
          this.addEventListener('message', ({ data }) => {
            try {
              const event = JSON.parse(data);
              if (event.type === 'Turn') window.liveVoiceStats.turns++;
              if (event.type === 'Termination') window.liveVoiceStats.terminated++;
              if (event.type === 'Error' || event.error) window.liveVoiceStats.error = String(event.error || event.message || 'Streaming error').replace(/token=[^&\s]+/g, 'token=[hidden]');
            } catch {}
          });
        }
        send(data) { if (typeof data !== 'string') window.liveVoiceStats.chunks++; super.send(data); }
      };
    }, { audio: audio.toString('base64') });
    let fallbackCalls = 0;
    page.on('request', (request) => { if (request.url().endsWith('/api/transcribe')) fallbackCalls++; });
    await page.goto(base);
    const created = await page.request.post(`${base}/api/projects`, { data: { title: 'Disposable live voice verification' } });
    assert.equal(created.status(), 201);
    projectId = (await created.json()).project_id;
    await page.reload();
    await page.getByRole('combobox', { name: 'Current project' }).selectOption(projectId);
    await page.getByRole('button', { name: 'Record voice message', exact: true }).click();
    await page.getByText('Live transcription', { exact: true }).waitFor({ timeout: 45000 });
    console.log('Live AssemblyAI session connected; sending public sample microphone audio.');
    await page.waitForFunction(() => window.liveVoiceStats.turns > 0, { timeout: 30000 });
    await page.waitForFunction(() => window.liveVoiceStats.started && performance.now() - window.liveVoiceStats.started >= 8500);
    await page.locator('.live-transcript p').waitFor();
    await page.screenshot({ path: 'tests/artifacts/live-voice-real.png', fullPage: true });
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message"]').value.trim().length > 10, { timeout: 30000 });
    const text = await page.getByRole('textbox', { name: 'Message', exact: true }).inputValue();
    const stats = await page.evaluate(() => window.liveVoiceStats);
    assert.ok(stats.chunks > 5);
    assert.ok(stats.turns > 0);
    assert.equal(stats.terminated, 1);
    assert.equal(fallbackCalls, 0);
    assert.match(text, /wildfires|smoke|Canada/i);
    console.log(`Live voice verified: ${stats.chunks} audio chunks, ${stats.turns} transcript events, clean termination, no fallback. Transcript: ${text.slice(0, 140)}`);
  } catch (error) {
    console.error('Live status:', await page.locator('.rec').allTextContents().catch(() => []));
    console.error('Streaming diagnostics:', await page.evaluate(() => window.liveVoiceStats).catch(() => null));
    throw error;
  } finally {
    if (projectId) {
      await page.goto(base).catch(() => {});
      await page.request.delete(`${base}/api/projects/${projectId}`).catch(() => {});
    }
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
