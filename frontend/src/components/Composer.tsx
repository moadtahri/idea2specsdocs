import { useEffect, useRef, useState } from 'react';
import { api, type AttachmentMeta } from '../api';
import { VoiceCapture, MAX_AUDIO_BYTES } from '../voice';

export default function Composer({ projectId, disabled, onSend, prefill, placeholder }: {
  projectId: string;
  disabled: boolean;
  onSend: (text: string, attachmentIds: string[], attachmentNames?: string[]) => void;
  prefill?: { text: string; n: number };
  placeholder?: string;
}) {
  const [input, setInput] = useState('');
  const [files, setFiles] = useState<AttachmentMeta[]>([]);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [starting, setStarting] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState('');
  const [retryAudio, setRetryAudio] = useState<Blob | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const voiceRef = useRef<VoiceCapture | null>(null);
  const stoppingRef = useRef(false);
  const lastSoundAt = useRef(Date.now());
  const [bars, setBars] = useState<number[]>(Array(9).fill(0));
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [silentSeconds, setSilentSeconds] = useState(0);
  const [meterAvailable, setMeterAvailable] = useState(false);
  const [liveText, setLiveText] = useState('');
  const [voiceStatus, setVoiceStatus] = useState('Opening microphone…');
  const mounted = useRef(true);
  const voiceBusy = useRef(false);
  const requestRef = useRef<AbortController | null>(null);
  const busy = disabled || uploading || starting || transcribing || recording;

  useEffect(() => {
    if (!prefill?.n) return;
    setInput(prefill.text);
    inputRef.current?.focus();
  }, [prefill]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestRef.current?.abort();
      voiceRef.current?.dispose();
    };
  }, []);

  const transcribe = async (blob: Blob) => {
    setTranscribing(true);
    setError('');
    voiceBusy.current = true;
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const mime = blob.type.split(';')[0];
      const extension = mime === 'audio/mp4' ? 'mp4' : mime === 'audio/ogg' ? 'ogg' : 'webm';
      const { text } = await api.transcribe(blob, `recording.${extension}`, controller.signal);
      if (!mounted.current) return;
      if (!text.trim()) throw new Error('No speech was detected. Please record again.');
      setInput((value) => value ? `${value}\n${text.trim()}` : text.trim());
      setRetryAudio(null);
      inputRef.current?.focus();
    } catch (err) {
      if (mounted.current) {
        setRetryAudio(blob);
        setError(err instanceof Error ? err.message : 'Voice transcription failed. Please retry.');
      }
    } finally {
      voiceBusy.current = false;
      if (mounted.current) setTranscribing(false);
    }
  };

  const startVoice = async () => {
    if (busy || voiceBusy.current) return;
    voiceBusy.current = true;
    setStarting(true);
    setError('');
    setRetryAudio(null);
    setRecordingSeconds(0);
    setSilentSeconds(0);
    setLiveText('');
    setVoiceStatus('Opening microphone…');
    setBars(Array(9).fill(0));
    const voice = new VoiceCapture({
      onMeter: (levels, hasSound) => {
        if (!mounted.current || voiceRef.current !== voice) return;
        setBars(levels);
        if (hasSound) lastSoundAt.current = Date.now();
      },
      onTime: (seconds) => {
        if (!mounted.current || voiceRef.current !== voice) return;
        setRecordingSeconds(seconds);
        setSilentSeconds(Math.floor((Date.now() - lastSoundAt.current) / 1000));
      },
      onStatus: (status) => { if (mounted.current && voiceRef.current === voice) setVoiceStatus(status); },
      onTranscript: (text) => { if (mounted.current && voiceRef.current === voice) setLiveText(text); },
      onStopRequested: () => { if (mounted.current && voiceRef.current === voice) void stopVoice(); },
    });
    voiceRef.current = voice;
    try {
      const result = await voice.start();
      if (!mounted.current || voiceRef.current !== voice) return;
      setMeterAvailable(result.meter);
      lastSoundAt.current = Date.now();
      setRecording(true);
    } catch (err) {
      voice.dispose();
      if (mounted.current && voiceRef.current === voice) {
        voiceRef.current = null;
        voiceBusy.current = false;
        setError(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Microphone access was denied. Allow microphone access in your browser and try again.'
          : err instanceof Error ? err.message : 'Microphone unavailable. Please try again.',
        );
        setStarting(false);
      }
    } finally {
      if (mounted.current && voiceRef.current === voice) setStarting(false);
    }
  };

  const stopVoice = async () => {
    const voice = voiceRef.current;
    if (!voice || stoppingRef.current || !mounted.current) return;
    stoppingRef.current = true;
    setRecording(false);
    setTranscribing(true);
    setVoiceStatus('Finishing your transcript…');
    try {
      const result = await voice.stop();
      if (!mounted.current) return;
      if (result.live && result.text.trim()) {
        setInput((value) => value ? `${value}\n${result.text.trim()}` : result.text.trim());
        inputRef.current?.focus();
      } else if (!result.blob.size || result.blob.size > MAX_AUDIO_BYTES) {
        setError(result.blob.size ? 'Recording is too large. Please record a shorter message (max 10 MB).' : 'The recording was empty. Please try again.');
      } else {
        setVoiceStatus('Transcribing your voice note…');
        await transcribe(result.blob);
      }
    } catch {
      if (mounted.current) setError('Recording could not finish. Please try again.');
    } finally {
      voice.dispose();
      if (voiceRef.current === voice) voiceRef.current = null;
      stoppingRef.current = false;
      voiceBusy.current = false;
      if (mounted.current) { setTranscribing(false); setLiveText(''); }
    }
  };

  const cancelStarting = () => {
    voiceRef.current?.dispose();
    voiceRef.current = null;
    voiceBusy.current = false;
    setStarting(false);
  };

  const pick = async (list: FileList | null) => {
    if (!list || busy) return;
    setUploading(true);
    setError('');
    try {
      for (const file of Array.from(list).slice(0, 10 - files.length)) {
        const meta = await api.upload(projectId, file);
        if (mounted.current) setFiles((previous) => [...previous, meta]);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : 'Upload failed. Please try again.');
    } finally {
      if (mounted.current) setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const send = () => {
    const text = input.trim();
    if ((!text && !files.length) || busy || voiceBusy.current) return;
    onSend(text, files.map((file) => file.attachment_id), files.map((file) => file.filename));
    setInput('');
    setFiles([]);
    setRetryAudio(null);
    setError('');
  };

  return (
    <div className="composer-wrap">
      {files.length > 0 && <div className="chips">
        {files.map((file) => <span key={file.attachment_id} className="chip">
          {file.filename}
          <button aria-label={`Remove ${file.filename}`} disabled={busy} onClick={() => setFiles((previous) => previous.filter((item) => item.attachment_id !== file.attachment_id))}>×</button>
        </span>)}
      </div>}
      {recording && <div className="voice-recording">
        <div className="rec">
          <div className="audio-meter" role="img" aria-label="Microphone input level" data-level={Math.max(...bars).toFixed(3)}>
            {bars.map((level, index) => <span key={index} style={{ height: `${4 + level * 30}px` }} />)}
          </div>
          <div className="rec-info"><strong>{voiceStatus}</strong><span>{!meterAvailable ? 'Audio meter unavailable' : silentSeconds >= 3 ? 'No audio detected — check your microphone' : 'Listening to your microphone'}</span></div>
          <time aria-label="Recording duration">{Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2, '0')}</time>
          <button className="ghost" onClick={() => void stopVoice()}>Stop</button>
        </div>
        {liveText && <div className="live-transcript" aria-live="polite"><small>Live transcript</small><p>{liveText}</p></div>}
      </div>}
      {(starting || transcribing) && <div className="rec" role="status"><span>{voiceStatus}</span>{starting && <button className="ghost" onClick={cancelStarting}>Cancel recording</button>}</div>}
      {error && <div className="error" role="alert">{error}</div>}
      {retryAudio && <div className="row">
        <button className="ghost" disabled={busy} onClick={() => { if (!voiceBusy.current) void transcribe(retryAudio); }}>Retry transcription</button>
        <button className="ghost" disabled={busy} onClick={() => { setRetryAudio(null); setError(''); }}>Discard recording</button>
      </div>}
      <div className="composer">
        <input ref={fileRef} type="file" multiple hidden
          accept=".txt,.md,.json,.csv,.pdf,.docx,.zip,.py,.js,.jsx,.ts,.tsx,.html,.css,.sql,.yaml,.yml,.toml,.go,.rs,.java,.cs,.cpp,.h,.sh"
          onChange={(event) => void pick(event.target.files)} />
        <button className="icon-btn" aria-label="Attach files" title="Attach source files or handover docs" disabled={busy} onClick={() => fileRef.current?.click()}>{uploading ? '…' : '+'}</button>
        <textarea ref={inputRef} rows={2} value={input} onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }}
          placeholder={placeholder ?? 'Describe an idea or feature, attach files, or record a message…'} disabled={disabled}
          aria-label="Message" />
        <button className="icon-btn" aria-label={recording ? 'Stop recording' : 'Record voice message'} title={recording ? 'Stop recording' : 'Record voice message'}
          disabled={disabled || starting || transcribing || uploading} onClick={() => recording ? void stopVoice() : void startVoice()}>🎤</button>
        <button onClick={send} disabled={busy || (!input.trim() && !files.length)}>Send</button>
      </div>
    </div>
  );
}
