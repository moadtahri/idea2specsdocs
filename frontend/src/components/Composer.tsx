/**
 * Where the user writes to wizi, as Kanya's composer (spec 09). One rounded box: the text on top, starting one line
 * high and growing with what is written (up to 40% of the window), and under it, inside the box, "+" on the left and
 * the voice buttons, Stop and Send on the right. Files are uploaded as soon as they are chosen, so the message carries
 * them by id. While wizi works, Stop ends its turn.
 */
import { useEffect, useId, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { api, type AttachmentMeta } from '../api';
import { VoiceButtons } from './chat/VoiceButtons';

const MAX_MESSAGE_CHARS = 8000;

export default function Composer({ projectId, running, stopping, onSend, onStop, reply, prefill, placeholder }: {
  projectId: string;
  running: boolean;
  stopping: boolean;
  onSend: (text: string, attachmentIds: string[], attachmentNames?: string[]) => void;
  onStop: () => void;
  /** wizi's latest reply, read aloud in voice mode. */
  reply?: { key: string; text: string } | null;
  prefill?: { text: string; n: number };
  placeholder?: string;
}) {
  const id = useId();
  const [text, setText] = useState('');
  const [files, setFiles] = useState<AttachmentMeta[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const box = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, window.innerHeight * 0.4)}px`;
  }, [text]);

  useEffect(() => {
    if (!prefill?.n) return;
    setText(prefill.text);
    box.current?.focus();
  }, [prefill]);

  const tooLong = text.length > MAX_MESSAGE_CHARS;
  const ready = (text.trim().length > 0 || files.length > 0) && !tooLong && !uploading && !running;

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!ready) return;
    onSend(text.trim(), files.map((file) => file.attachment_id), files.map((file) => file.filename));
    setText('');
    setFiles([]);
  };

  const upload = async (chosen: FileList | null) => {
    if (!chosen?.length) return;
    setUploading(true);
    setError('');
    try {
      for (const file of Array.from(chosen)) {
        const meta = await api.upload(projectId, file);
        setFiles((previous) => [...previous, meta]);
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The file could not be attached.');
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer boxed" onSubmit={submit}>
      <label htmlFor={`${id}-text`} className="visually-hidden">Message</label>
      {files.length > 0 && (
        <ul className="attachments" aria-label="Attached files">
          {files.map((file) => (
            <li key={file.attachment_id}>
              <span>{file.filename}</span>
              <button
                type="button"
                className="chip-remove"
                aria-label={`Remove ${file.filename}`}
                onClick={() => setFiles(files.filter((other) => other !== file))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="composer-box">
        <textarea
          ref={box}
          id={`${id}-text`}
          aria-label="Message"
          value={text}
          rows={1}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby={`${id}-hint`}
          aria-invalid={tooLong}
          placeholder={placeholder ?? (running ? 'wizi is working…' : 'Describe an idea or feature, attach files, or speak…')}
        />
        <div className="composer-row">
          <input
            ref={fileInput}
            id={`${id}-files`}
            type="file"
            multiple
            className="visually-hidden"
            onChange={(event) => void upload(event.target.files)}
          />
          <label htmlFor={`${id}-files`} className="add-button" title="Attach files" aria-label="Attach files">
            {uploading ? '…' : (
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            )}
          </label>
          <div className="composer-actions">
            <VoiceButtons
              reply={reply}
              onDictated={(words) => setText((current) => (current ? `${current.trimEnd()} ${words}` : words))}
              onUtterance={(words) => { if (!running) onSend(words, []); }}
            />
            {running && (
              <button type="button" className="button ghost" onClick={onStop} disabled={stopping}>
                <span className="stop-square" aria-hidden="true" />
                {stopping ? 'Stopping…' : 'Stop'}
              </button>
            )}
            <button type="submit" className="button primary composer-send" disabled={!ready}>
              Send
            </button>
          </div>
        </div>
      </div>
      <span id={`${id}-hint`} className={tooLong ? 'composer-over' : 'visually-hidden'}>
        {tooLong ? `${text.length} / ${MAX_MESSAGE_CHARS} characters: shorten it a little.` : 'Enter sends; Shift+Enter starts a new line.'}
      </span>
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>
  );
}
