const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function processor(rate) {
  let Processor;
  class AudioWorkletProcessor {
    constructor() { this.port = { messages: [], postMessage(data) { this.messages.push(data); } }; }
  }
  vm.runInNewContext(fs.readFileSync('public/audio-capture.js', 'utf8'), {
    AudioWorkletProcessor, sampleRate: rate,
    registerProcessor(name, implementation) { assert.equal(name, 'pcm-capture'); Processor = implementation; },
  });
  return new Processor();
}

for (const rate of [16000, 44100, 48000]) {
  const capture = processor(rate);
  for (let offset = 0; offset < rate; offset += 128) {
    capture.process([[new Float32Array(Math.min(128, rate - offset)).fill(0.25)]]);
  }
  const frames = capture.port.messages.filter((message) => message.type === 'audio');
  assert.equal(frames.length, 5);
  assert.equal(frames.reduce((total, frame) => total + frame.buffer.byteLength, 0), 32000);
  for (const frame of frames) {
    assert.equal(frame.buffer.byteLength, 6400);
    assert.equal(new DataView(frame.buffer).getInt16(0, true), 8192);
  }
}
for (const [level, expected] of [[-2, -32768], [2, 32767]]) {
  const capture = processor(48000);
  capture.process([[new Float32Array(1000).fill(level)]]);
  capture.port.onmessage({ data: 'flush' });
  const frame = capture.port.messages.find((message) => message.type === 'audio');
  assert.equal(frame.buffer.byteLength, 1600); // A short final frame is padded to 50 ms.
  assert.equal(new DataView(frame.buffer).getInt16(0, true), expected);
  assert.equal(capture.port.messages.at(-1).type, 'flushed');
  const count = capture.port.messages.length;
  capture.process([[new Float32Array(48000).fill(level)]]);
  assert.equal(capture.port.messages.length, count);
}
console.log('Audio capture passed: 16/44.1/48 kHz resampling, PCM16 little endian, 200 ms frames, clipping and stop flush.');
