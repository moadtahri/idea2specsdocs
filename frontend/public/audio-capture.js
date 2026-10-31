// Convert native microphone samples to mono PCM16 at 16 kHz in 200 ms chunks.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.remaining = this.ratio;
    this.sum = 0;
    this.buffer = new ArrayBuffer(6400);
    this.view = new DataView(this.buffer);
    this.index = 0;
    this.active = true;
    this.port.onmessage = (event) => {
      if (event.data === 'flush') {
        this.active = false;
        if (this.index) this.emit(Math.max(800, this.index));
        this.port.postMessage({ type: 'flushed' });
      }
    };
  }

  emit(samples = 3200) {
    const buffer = this.buffer.slice(0, samples * 2);
    this.port.postMessage({ type: 'audio', buffer }, [buffer]);
    this.buffer = new ArrayBuffer(6400);
    this.view = new DataView(this.buffer);
    this.index = 0;
  }

  process(inputs) {
    if (!this.active) return true;
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    for (const sample of channel) {
      let weight = 1;
      while (weight > 1e-9) {
        const take = Math.min(weight, this.remaining);
        this.sum += sample * take;
        weight -= take;
        this.remaining -= take;
        if (this.remaining < 1e-9) {
          const value = Math.max(-1, Math.min(1, this.sum / this.ratio));
          this.view.setInt16(this.index++ * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
          this.remaining = this.ratio;
          this.sum = 0;
          if (this.index === 3200) this.emit();
        }
      }
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCapture);
