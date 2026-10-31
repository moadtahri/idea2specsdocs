/**
 * Voice in the chat (spec 09, ported from Kanya's): the microphone streamed to `/api/voice/listen` for live
 * transcription, and wizi's replies played from `/api/voice/speak`. Audio both ways is 16-bit 24 kHz mono PCM.
 *
 * - `listen(handlers)` opens the microphone and the socket. It calls `onPartial` while you speak, `onFinal` when a
 *   sentence ends and `onSpeechStarted` when you start talking (voice mode stops wizi's voice then). `stop()` ends it.
 * - `speak(text, signal)` plays a reply as it streams in; aborting the signal stops it at once.
 */
// itos has no sign-in: the backend relay holds the OpenAI key, so nothing secret passes through the page.
const API_BASE = "/api";

const RATE = 24000;

// The worklet hands 20 ms of float samples to the page, which turns them into 16-bit PCM.
const WORKLET = `
class Capture extends AudioWorkletProcessor {
  constructor() { super(); this.buffer = []; }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      this.buffer.push(new Float32Array(channel));
      if (this.buffer.length >= 4) { this.port.postMessage(this.buffer); this.buffer = []; }
    }
    return true;
  }
}
registerProcessor("itos-capture", Capture);
`;

function toPcm16(chunks: Float32Array[]): ArrayBuffer {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const out = new Int16Array(length);
  let at = 0;
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, chunk[i] ?? 0));
      out[at] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      at += 1;
    }
  }
  return out.buffer;
}

export interface ListenHandlers {
  onPartial: (text: string) => void;
  onFinal: (text: string) => void;
  onSpeechStarted?: () => void;
  onError: (message: string) => void;
}

export interface Listening {
  stop: () => void;
}

export async function listen(handlers: ListenHandlers): Promise<Listening> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser cannot use the microphone.");
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const context = new AudioContext({ sampleRate: RATE });
  const module = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
  await context.audioWorklet.addModule(module);
  URL.revokeObjectURL(module);
  const source = context.createMediaStreamSource(stream);
  const capture = new AudioWorkletNode(context, "itos-capture");
  source.connect(capture);

  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${scheme}//${location.host}${API_BASE}/voice/listen`);
  socket.binaryType = "arraybuffer";
  let ready = false;
  let closed = false;

  const shutdown = () => {
    if (closed) return;
    closed = true;
    capture.port.onmessage = null;
    source.disconnect();
    capture.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
  };

  socket.onmessage = (event) => {
    const message = JSON.parse(String(event.data)) as { type: string; text?: string };
    if (message.type === "ready") ready = true;
    else if (message.type === "partial") handlers.onPartial(message.text ?? "");
    else if (message.type === "final" && message.text) handlers.onFinal(message.text);
    else if (message.type === "speech_started") handlers.onSpeechStarted?.();
    else if (message.type === "error") handlers.onError(message.text ?? "Voice is not available right now.");
  };
  socket.onclose = () => shutdown();
  socket.onerror = () => handlers.onError("Voice could not connect.");
  capture.port.onmessage = (event: MessageEvent<Float32Array[]>) => {
    if (ready && socket.readyState === WebSocket.OPEN) socket.send(toPcm16(event.data));
  };

  return {
    stop: () => {
      shutdown();
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop" }));
        window.setTimeout(() => socket.close(), 2500); // the last sentence's words still come back
      }
    },
  };
}

/** Play wizi's reply as it streams in; resolves when it ends or is aborted. */
export async function speak(text: string, signal: AbortSignal): Promise<void> {
  const response = await fetch(`${API_BASE}/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error("wizi's voice is not available right now.");
  const context = new AudioContext({ sampleRate: RATE });
  const reader = response.body.getReader();
  let at = context.currentTime + 0.05;
  let carry = new Uint8Array(0);
  const stop = () => void context.close();
  signal.addEventListener("abort", stop, { once: true });
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done || signal.aborted) break;
      const bytes = new Uint8Array(carry.length + value.length);
      bytes.set(carry);
      bytes.set(value, carry.length);
      const even = bytes.length - (bytes.length % 2);
      carry = bytes.slice(even);
      const samples = new Int16Array(bytes.buffer.slice(0, even));
      if (!samples.length) continue;
      const buffer = context.createBuffer(1, samples.length, RATE);
      const channel = buffer.getChannelData(0);
      for (let i = 0; i < samples.length; i += 1) channel[i] = (samples[i] ?? 0) / 0x8000;
      const node = context.createBufferSource();
      node.buffer = buffer;
      node.connect(context.destination);
      at = Math.max(at, context.currentTime);
      node.start(at);
      at += buffer.duration;
    }
    if (!signal.aborted)
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(0, (at - context.currentTime) * 1000)));
  } finally {
    signal.removeEventListener("abort", stop);
    if (context.state !== "closed") void context.close();
  }
}
