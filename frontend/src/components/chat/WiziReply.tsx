/**
 * CH-1228: one of wizi's replies in a chat: the bubble (a long reply shows its opening and a document card that
 * opens it in the reader) and, under it, the actions: copy, good or bad (kept for training; a bad one asks why),
 * read aloud, try again with guidance (its latest reply only), and the sources when it has links.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import Markdown from "../Markdown";
import { docTitle, excerpt, isLong, replyHash, sourcesOf, useChatTools, wordCount, type ChatTools } from "./chatTools";
import { errorMessage, REASONS, useRate, useRatings, useWithdraw, type Rating } from "./feedback";
import { speak } from "./voice";
import "./reply-tools.css";

interface Props {
  text: string;
  /** The user's message this reply answered, kept with a rating. */
  prompt?: string;
  /** Its latest finished reply: only it offers "Try again". */
  latest?: boolean;
}

export function WiziReply({ text, prompt = "", latest = false }: Props) {
  const tools = useChatTools();
  const long = isLong(text);
  const title = useMemo(() => docTitle(text), [text]);
  return (
    <>
      <div className="bubble">
        {long ? (
          <>
            <div className="reply-excerpt">
              <Markdown text={excerpt(text)} />
            </div>
            <button
              type="button"
              className="doc-card"
              onClick={() => tools?.openReader({ kind: "doc", title, text })}
              disabled={!tools}
            >
              <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <path
                  d="M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10A.5.5 0 0 1 7 20zM14 3.5V8h4M9.5 12h5M9.5 15h5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="doc-card-words">
                <strong>{title}</strong>
                <span className="muted small">Document · {wordCount(text).toLocaleString()} words · Open</span>
              </span>
            </button>
          </>
        ) : (
          <Markdown text={text} />
        )}
      </div>
      {tools && <ReplyActions tools={tools} text={text} prompt={prompt} latest={latest} />}
    </>
  );
}

// The actions ------------------------------------------------------------------------------------------------------
let speaking: AbortController | null = null; // one reply read aloud at a time, across the page

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const ICONS = {
  copy: "M9 9.5h9.5V20a.5.5 0 0 1-.5.5H9.5A.5.5 0 0 1 9 20zM6 15H5.5a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5H15a.5.5 0 0 1 .5.5v.5",
  check: "M5 12.5l4.5 4.5L19 7.5",
  up: "M7.5 10.5v9h-3v-9zM7.5 10.5l4-7c1.4 0 2.3 1 2 2.4l-.6 3.1h5.3c1 0 1.8 1 1.5 2l-1.7 6.8c-.2.8-.9 1.2-1.6 1.2H7.5",
  down: "M16.5 13.5v-9h3v9zM16.5 13.5l-4 7c-1.4 0-2.3-1-2-2.4l.6-3.1H5.8c-1 0-1.8-1-1.5-2l1.7-6.8c.2-.8.9-1.2 1.6-1.2h8.9",
  speak: "M4 9.5h3.5L12 5.5v13l-4.5-4H4zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11",
  stop: "M7 7h10v10H7z",
  retry: "M19 12a7 7 0 1 1-2.1-5M19 4.5V7h-2.5",
  sources: "M4.5 5.5c2.5-.8 5-.6 7.5 1 2.5-1.6 5-1.8 7.5-1v13c-2.5-.8-5-.6-7.5 1-2.5-1.6-5-1.8-7.5-1zM12 6.5v13",
};

function ReplyActions({
  tools,
  text,
  prompt,
  latest,
}: {
  tools: ChatTools;
  text: string;
  prompt: string;
  latest: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [reading, setReading] = useState(false);
  const [panel, setPanel] = useState<"none" | "bad" | "retry">("none");
  const [hash, setHash] = useState("");
  const ratings = useRatings(tools.projectId);
  const rate = useRate(tools.projectId);
  const withdraw = useWithdraw(tools.projectId);
  const mine = useRef<AbortController | null>(null);
  const sources = useMemo(() => sourcesOf(text), [text]);

  useEffect(() => {
    let live = true;
    replyHash(text)
      .then((value) => live && setHash(value))
      .catch(() => undefined); // no crypto.subtle (an insecure origin): ratings still save, just not shown again
    return () => {
      live = false;
    };
  }, [text]);
  useEffect(() => () => mine.current?.abort(), []);

  const rating: Rating | null = ratings.data?.find((row) => row.reply_hash === hash)?.rating ?? null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const read = () => {
    if (reading) {
      mine.current?.abort();
      return;
    }
    speaking?.abort();
    const controller = new AbortController();
    speaking = controller;
    mine.current = controller;
    setReading(true);
    speak(text, controller.signal)
      .catch(() => undefined)
      .finally(() => {
        if (speaking === controller) speaking = null;
        setReading(false);
      });
  };

  const good = () => {
    setPanel("none");
    if (rating === "good" && hash) withdraw.mutate(hash);
    else rate.mutate({ rating: "good", reply: text, prompt });
  };
  const bad = () => {
    if (rating === "bad" && hash) {
      withdraw.mutate(hash);
      setPanel("none");
    } else setPanel(panel === "bad" ? "none" : "bad");
  };

  const problem = rate.error ?? withdraw.error;
  return (
    <div className="reply-actions-wrap">
      <div className="reply-actions" role="toolbar" aria-label="wizi's reply">
        <button type="button" className="reply-action" onClick={() => void copy()} title={copied ? "Copied" : "Copy"}>
          <Icon d={copied ? ICONS.check : ICONS.copy} />
          <span className="visually-hidden">{copied ? "Copied" : "Copy"}</span>
        </button>
        <button
          type="button"
          className={`reply-action${rating === "good" ? " is-on" : ""}`}
          aria-pressed={rating === "good"}
          onClick={good}
          title="Good reply"
        >
          <Icon d={ICONS.up} />
          <span className="visually-hidden">Good reply</span>
        </button>
        <button
          type="button"
          className={`reply-action${rating === "bad" ? " is-on" : ""}`}
          aria-pressed={rating === "bad"}
          aria-expanded={panel === "bad"}
          onClick={bad}
          title="Bad reply"
        >
          <Icon d={ICONS.down} />
          <span className="visually-hidden">Bad reply</span>
        </button>
        <button
          type="button"
          className={`reply-action${reading ? " is-on" : ""}`}
          aria-pressed={reading}
          onClick={read}
          title={reading ? "Stop reading" : "Read aloud"}
        >
          <Icon d={reading ? ICONS.stop : ICONS.speak} />
          <span className="visually-hidden">{reading ? "Stop reading" : "Read aloud"}</span>
        </button>
        {latest && (
          <button
            type="button"
            className={`reply-action${panel === "retry" ? " is-on" : ""}`}
            aria-expanded={panel === "retry"}
            onClick={() => setPanel(panel === "retry" ? "none" : "retry")}
            title="Try again…"
          >
            <Icon d={ICONS.retry} />
            <span className="visually-hidden">Try again…</span>
          </button>
        )}
        {sources.length > 0 && (
          <button
            type="button"
            className="reply-action reply-sources"
            onClick={() => tools.openReader({ kind: "sources", title: "Sources", sources })}
            title="Sources"
          >
            <Icon d={ICONS.sources} />
            <span>Sources · {sources.length}</span>
          </button>
        )}
        {(rate.isSuccess || withdraw.isSuccess) && panel === "none" && !problem && (
          <span className="reply-thanks muted small" role="status">
            {rating ? "Thanks: this helps wizi learn." : ""}
          </span>
        )}
      </div>
      {panel === "bad" && (
        <BadForm
          busy={rate.isPending}
          onCancel={() => setPanel("none")}
          onSubmit={(reasons, note) =>
            rate.mutate(
              { rating: "bad", reply: text, prompt, reasons, note },
              { onSuccess: () => setPanel("none") },
            )
          }
        />
      )}
      {panel === "retry" && (
        <RetryForm
          onCancel={() => setPanel("none")}
          onSubmit={(guidance) => {
            setPanel("none");
            tools.onRetry(guidance);
          }}
        />
      )}
      {problem ? (
        <p className="form-error small" role="alert">
          {errorMessage(problem)}
        </p>
      ) : null}
    </div>
  );
}

function BadForm({
  busy,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (reasons: string[], note: string) => void;
}) {
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const toggle = (id: string) =>
    setReasons((current) => (current.includes(id) ? current.filter((each) => each !== id) : [...current, id]));
  return (
    <form
      className="reply-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(reasons, note);
      }}
    >
      <p className="reply-form-title">What was wrong? It helps wizi learn.</p>
      <div className="reply-reasons" role="group" aria-label="Reasons">
        {REASONS.map((reason) => (
          <button
            key={reason.id}
            type="button"
            className={`reason-chip${reasons.includes(reason.id) ? " is-on" : ""}`}
            aria-pressed={reasons.includes(reason.id)}
            onClick={() => toggle(reason.id)}
          >
            {reason.label}
          </button>
        ))}
      </div>
      <textarea
        rows={2}
        maxLength={1000}
        value={note}
        placeholder="Anything else? (optional)"
        aria-label="What else was wrong"
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="reply-form-buttons">
        <button type="button" className="button ghost small" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="button primary small" disabled={busy}>
          {busy ? "Saving…" : "Send feedback"}
        </button>
      </div>
    </form>
  );
}

function RetryForm({ onCancel, onSubmit }: { onCancel: () => void; onSubmit: (guidance: string) => void }) {
  const [guidance, setGuidance] = useState("");
  return (
    <form
      className="reply-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(guidance);
      }}
    >
      <label className="reply-form-title" htmlFor="retry-guidance">
        Try again. What should wizi do differently? (optional)
      </label>
      <textarea
        id="retry-guidance"
        rows={2}
        maxLength={1500}
        value={guidance}
        placeholder="Shorter; use the 2024 figures; more about tile roofs…"
        onChange={(event) => setGuidance(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            onSubmit(guidance);
          }
        }}
      />
      <div className="reply-form-buttons">
        <button type="button" className="button ghost small" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="button primary small">
          Try again
        </button>
      </div>
    </form>
  );
}
