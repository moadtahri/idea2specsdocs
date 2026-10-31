import { api } from './api';

const AUDIO_TYPES = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'];
export const MAX_AUDIO_BYTES = 10 * 1024 * 1024;
const MAX_SECONDS = 300;

interface VoiceCallbacks {
  onMeter: (bars: number[], hasSound: boolean) => void;
  onTime: (seconds: number) => void;
  onStatus: (status: string) => void;
  onTranscript: (text: string) => void;
  onStopRequested: () => void;
}

export interface VoiceResult { blob: Blob; text: string; live: boolean }

/** One microphone session owns all audio nodes, sockets, timers and recording data. */
export class VoiceCapture {
  private readonly abort = new AbortController();
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private socket: WebSocket | null = null;
  private turns = new Map<number, string>();
  private chunks: Blob[] = [];
  private bytes = 0;
  private animation = 0;
  private clock: ReturnType<typeof setInterval> | undefined;
  private disposed = false;
  private stopping = false;
  private liveFailed = false;
  private terminated = false;
  private live = false;
  private flushComplete: (() => void) | undefined;
  private terminationComplete: ((success: boolean) => void) | undefined;
  private recordingStopped: ((blob: Blob) => void) | undefined;
  private recordingResult: Promise<Blob> | undefined;
  private result: Promise<VoiceResult> | undefined;

  constructor(private readonly callbacks: VoiceCallbacks) {}

  async start(): Promise<{ live: boolean; meter: boolean }> {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error('Recording is unavailable. Use a browser with microphone support on HTTPS or localhost.');
    }
    const mimeType = AUDIO_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    if (!mimeType) throw new Error('This browser cannot record a supported audio format. Please try another browser.');
    // Resume in the original click gesture, before waiting for permissions or AWS.
    try {
      this.context = new AudioContext();
      void this.context.resume().catch(() => undefined);
    } catch { this.context = null; }
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    if (this.disposed) { this.stream.getTracks().forEach((track) => track.stop()); throw new DOMException('Cancelled', 'AbortError'); }
    try {
      if (this.context) {
        this.source = this.context.createMediaStreamSource(this.stream);
        this.startMeter();
      }
    } catch { this.closeAudio(); }

    if (this.context?.audioWorklet && this.source) {
      this.callbacks.onStatus('Connecting live transcription…');
      try {
        await this.context.audioWorklet.addModule('/audio-capture.js');
        const token = await api.streamingToken(this.abort.signal);
        if (this.disposed) throw new DOMException('Cancelled', 'AbortError');
        await this.connect(token.websocket_url, token.token);
        if (this.disposed) throw new DOMException('Cancelled', 'AbortError');
        this.worklet = new AudioWorkletNode(this.context, 'pcm-capture');
        this.worklet.port.onmessage = ({ data }) => {
          if (data.type === 'flushed') this.flushComplete?.();
          if (data.type === 'audio' && !this.liveFailed && this.socket?.readyState === WebSocket.OPEN) {
            if (this.socket.bufferedAmount > 256000) this.failLive();
            else this.socket.send(data.buffer);
          }
        };
        this.source.connect(this.worklet);
        this.worklet.connect(this.context.destination); // Processor emits silent output.
        this.live = !this.liveFailed;
      } catch (error) {
        if (this.disposed) throw error;
        this.failLive();
      }
    }
    if (this.disposed) throw new DOMException('Cancelled', 'AbortError');
    this.recorder = new MediaRecorder(this.stream, { mimeType });
    this.recordingResult = new Promise((resolve) => { this.recordingStopped = resolve; });
    this.recorder.ondataavailable = ({ data }) => {
      if (data.size) this.chunks.push(data);
      this.bytes += data.size;
      if (this.bytes > MAX_AUDIO_BYTES && !this.stopping) this.callbacks.onStopRequested();
    };
    this.recorder.onstop = () => {
      this.recordingStopped?.(new Blob(this.chunks, { type: this.recorder?.mimeType || mimeType }));
      if (!this.stopping && !this.disposed) this.callbacks.onStopRequested();
    };
    this.recorder.onerror = () => {
      if (!this.disposed) {
        this.failLive();
        this.callbacks.onStopRequested();
      }
    };
    this.recorder.start(1000);
    const started = Date.now();
    this.clock = setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      this.callbacks.onTime(seconds);
      if (seconds >= MAX_SECONDS) this.callbacks.onStopRequested();
    }, 1000);
    this.callbacks.onStatus(this.live ? 'Live transcription' : 'Recording a voice note — transcription starts when you stop');
    return { live: this.live, meter: !!this.source };
  }

  private startMeter() {
    if (!this.context || !this.source) return;
    const analyser = this.context.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.65;
    this.source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const frequencies = new Uint8Array(analyser.frequencyBinCount);
    const rate = this.context.sampleRate;
    let previous = 0;
    const draw = (now: number) => {
      if (this.disposed || this.stopping) return;
      if (now - previous > 80) {
        analyser.getFloatTimeDomainData(samples);
        analyser.getByteFrequencyData(frequencies);
        const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
        const level = Math.min(1, rms * 8);
        const bars = Array.from({ length: 9 }, (_, band) => {
          const from = Math.max(1, Math.floor((80 * Math.pow(1.6, band)) * analyser.fftSize / rate));
          const to = Math.min(frequencies.length, Math.max(from + 1, Math.ceil(from * 1.6)));
          let total = 0;
          for (let index = from; index < to; index++) total += frequencies[index];
          return Math.min(1, total / Math.max(1, to - from) / 180) * level;
        });
        this.callbacks.onMeter(bars, rms > 0.008);
        previous = now;
      }
      this.animation = requestAnimationFrame(draw);
    };
    this.animation = requestAnimationFrame(draw);
  }

  private connect(endpoint: string, token: string): Promise<void> {
    const url = new URL(endpoint);
    if (url.protocol !== 'wss:' || !['streaming.assemblyai.com', 'streaming.us.assemblyai.com', 'streaming.eu.assemblyai.com'].includes(url.hostname)) {
      return Promise.reject(new Error('Unsupported streaming endpoint'));
    }
    url.searchParams.set('token', token);
    url.searchParams.set('sample_rate', '16000');
    url.searchParams.set('encoding', 'pcm_s16le');
    return new Promise((resolve, reject) => {
      let began = false;
      const socket = new WebSocket(url);
      this.socket = socket;
      const timer = setTimeout(() => { reject(new Error('Live connection timed out')); this.failLive(); }, 10000);
      const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
      this.abort.signal.addEventListener('abort', abort, { once: true });
      socket.onmessage = ({ data }) => {
        let event;
        try { event = JSON.parse(String(data)); } catch { return; }
        if (event.type === 'Begin') {
          began = true;
          clearTimeout(timer);
          this.abort.signal.removeEventListener('abort', abort);
          resolve();
        } else if (event.type === 'Turn' && typeof event.transcript === 'string' && Number.isInteger(event.turn_order)) {
          this.turns.set(event.turn_order, event.transcript);
          if (!this.disposed) this.callbacks.onTranscript(this.text());
        } else if (event.type === 'Termination') {
          this.terminated = true;
          this.terminationComplete?.(true);
          if (!this.stopping && !this.disposed) this.callbacks.onStopRequested();
        } else if (event.type === 'Error' || event.error) {
          if (!began) { clearTimeout(timer); reject(new Error('Live transcription unavailable')); }
          this.failLive();
        }
      };
      socket.onerror = socket.onclose = () => {
        clearTimeout(timer);
        this.abort.signal.removeEventListener('abort', abort);
        if (!began) reject(new Error('Live transcription unavailable'));
        if (!this.terminated && !this.disposed) this.failLive();
        this.terminationComplete?.(this.terminated);
      };
    });
  }

  private text() { return [...this.turns].sort(([a], [b]) => a - b).map(([, text]) => text.trim()).filter(Boolean).join(' '); }

  private failLive() {
    this.liveFailed = true;
    this.closeSocket();
    if (!this.disposed && !this.stopping) this.callbacks.onStatus('Live transcription unavailable — your voice note is still being recorded');
    this.terminationComplete?.(false);
  }

  stop(): Promise<VoiceResult> {
    this.result ??= this.finish();
    return this.result;
  }

  private async finish(): Promise<VoiceResult> {
    this.stopping = true;
    clearInterval(this.clock);
    cancelAnimationFrame(this.animation);
    if (this.recorder?.state !== 'inactive') this.recorder?.stop();
    if (this.worklet && !this.liveFailed) {
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 300);
        this.flushComplete = () => { clearTimeout(timer); resolve(); };
        this.worklet?.port.postMessage('flush');
      });
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.closeAudio();
    const blob = await this.recordingResult ?? new Blob();
    let complete = this.terminated;
    if (this.live && !this.liveFailed && !complete && this.socket?.readyState === WebSocket.OPEN) {
      complete = await new Promise<boolean>((resolve) => {
        const timer = setTimeout(() => resolve(false), 8000);
        this.terminationComplete = (ok) => { clearTimeout(timer); resolve(ok); };
        this.socket?.send(JSON.stringify({ type: 'Terminate' }));
      });
    }
    this.closeSocket();
    return { blob, text: this.text(), live: this.live && !this.liveFailed && complete };
  }

  private closeSocket() {
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState < WebSocket.CLOSING) {
      if (socket.readyState === WebSocket.OPEN && !this.terminated) socket.send(JSON.stringify({ type: 'Terminate' }));
      socket.close();
    }
  }

  private closeAudio() {
    cancelAnimationFrame(this.animation);
    this.source?.disconnect();
    this.worklet?.disconnect();
    this.worklet?.port.close();
    this.source = null;
    this.worklet = null;
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => undefined);
    this.context = null;
  }

  dispose() {
    this.disposed = true;
    this.stopping = true;
    this.abort.abort();
    clearInterval(this.clock);
    cancelAnimationFrame(this.animation);
    if (this.recorder?.state !== 'inactive') this.recorder?.stop();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.closeAudio();
    this.closeSocket();
    this.terminationComplete?.(false);
  }
}
