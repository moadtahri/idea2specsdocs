import { useEffect, useRef, useState } from 'react';
import { api, type AttachmentMeta } from '../api';

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

export default function Composer({
  projectId,
  disabled,
  onSend,
}: {
  projectId: string;
  disabled: boolean;
  onSend: (text: string, attachmentIds: string[]) => void;
}) {
  const [input, setInput] = useState('');
  const [files, setFiles] = useState<AttachmentMeta[]>([]);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recError, setRecError] = useState('');
  const [liveText, setLiveText] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRef = useRef<{ stream: MediaStream; recorder: MediaRecorder } | null>(null);
  const [audioBlob, setAudioBlob] = useState<{ blob: Blob } | null>(null);

  useEffect(() => () => {
    recRef.current?.stop();
    mediaRef.current?.stream.getTracks().forEach((t) => t.stop());
  }, []);

  const pick = async (list: FileList | null) => {
    if (!list) return;
    setUploading(true);
    try {
      for (const f of Array.from(list).slice(0, 10 - files.length)) {
        const meta = await api.upload(projectId, f);
        setFiles((p) => [...p, meta]);
      }
    } catch {
      setRecError('Upload failed (max 10 MB; txt/md/json/csv/pdf/docx/audio).');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const startVoice = async () => {
    setRecError('');
    setLiveText('');
    const SR = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (SR) {
      // On-device live transcription (Chrome/Edge) — free, instant.
      const rec = new SR();
      recRef.current = rec;
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.onresult = (e) => {
        let finalChunk = '';
        let interim = '';
        const results = Array.from(
          e.results as unknown as ArrayLike<
            ArrayLike<{ transcript: string; isFinal?: boolean }>
          >,
        );
        for (const r of results) {
          const alt = r[0];
          if (!alt) continue;
          if (alt.isFinal) finalChunk += alt.transcript;
          else interim = alt.transcript;
        }
        setLiveText(interim);
        if (finalChunk) setInput((v) => (v ? `${v} ${finalChunk}` : finalChunk));
      };
      rec.onerror = (e) => setRecError(`Mic error: ${e.error}`);
      rec.onend = () => {
        setRecording(false);
        setLiveText('');
      };
      rec.start();
      setRecording(true);
      return;
    }
    // Fallback: record audio blob for server transcription.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        setAudioBlob({ blob });
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        try {
          const { text } = await api.transcribe(blob);
          setInput((v) => (v ? `${v} ${text}` : text));
        } catch {
          setRecError('Server transcription unavailable — needs OPENAI_API_KEY on backend.');
        }
      };
      mediaRef.current = { stream, recorder };
      recorder.start();
      setRecording(true);
    } catch {
      setRecError('Microphone unavailable in this browser.');
    }
  };

  const stopVoice = () => {
    recRef.current?.stop();
    recRef.current = null;
    mediaRef.current?.recorder.stop();
    setRecording(false);
    setLiveText('');
  };

  const send = () => {
    const text = input.trim();
    if ((!text && files.length === 0) || disabled || uploading) return;
    onSend(text, files.map((f) => f.attachment_id));
    setInput('');
    setFiles([]);
    setAudioBlob(null);
  };

  return (
    <div className="composer-wrap">
      {(files.length > 0 || audioBlob) && (
        <div className="chips">
          {files.map((f) => (
            <span key={f.attachment_id} className="chip">
              📎 {f.filename}
              <button onClick={() => setFiles((p) => p.filter((x) => x.attachment_id !== f.attachment_id))}>×</button>
            </span>
          ))}
          {audioBlob && <span className="chip">🎤 voice note attached</span>}
        </div>
      )}
      {recording && (
        <div className="rec">
          <span className="dot" /> recording… {liveText && <em>{liveText}</em>}
          <button className="ghost" onClick={stopVoice}>Stop</button>
        </div>
      )}
      {recError && <div className="error">{recError}</div>}
      <div className="composer">
        <input
          ref={fileRef as never}
          type="file"
          multiple
          hidden
          accept=".txt,.md,.json,.csv,.pdf,.docx,audio/*"
          onChange={(e) => void pick(e.target.files)}
        />
        <button
          className="icon-btn"
          title="Attach files"
          onClick={() => (fileRef.current as unknown as HTMLInputElement)?.click()}
          disabled={disabled || uploading}
        >
          {uploading ? '…' : '+'}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Type your idea, attach files (+), or dictate (🎤)…"
          disabled={disabled}
        />
        <button
          className="icon-btn"
          title="Dictate"
          onClick={() => (recording ? stopVoice() : void startVoice())}
          disabled={disabled}
        >
          🎤
        </button>
        <button onClick={send} disabled={disabled || uploading || (!input.trim() && files.length === 0)}>
          Send
        </button>
      </div>
    </div>
  );
}
