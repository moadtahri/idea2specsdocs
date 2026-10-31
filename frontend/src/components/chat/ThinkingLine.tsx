/**
 * wizi's live line while a turn runs, as Kanya's (spec 09):
 * - it is typing: its draft, with a caret;
 * - a tool runs: what it is doing ("Reading your project files…");
 * - otherwise it thinks: a word that changes every 4 seconds, and animated dots.
 */
import Markdown from "../Markdown";

// Kanya's general words, and a few for wizi's work; her video ones (storyboarding, keyframing) are left out.
const THINKING_WORDS = [
  "Percolating", "Pondering", "Ideating", "Mapping", "Sketching", "Untangling", "Noodling", "Composing",
  "Specifying", "Brewing", "Riffing", "Weighing", "Forming", "Grilling",
] as const;

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function ThinkingLine({ elapsed, activity, draft }: { elapsed: number | null; activity: string; draft: string }) {
  const time = elapsed === null ? "" : clock(elapsed);
  if (draft.trim()) {
    return (
      <div className="live-draft" aria-live="off">
        <Markdown text={draft} />
        <span className="caret" aria-hidden="true" />
      </div>
    );
  }
  if (activity) {
    return (
      <div className="live-line">
        <span className="live-spinner" aria-hidden="true" />
        <span>
          <strong>{activity}…</strong> {time && <span className="muted">({time})</span>}
          <span className="live-note">I'll get back to you as soon as it's done.</span>
        </span>
      </div>
    );
  }
  const word = THINKING_WORDS[Math.floor((elapsed ?? 0) / 4) % THINKING_WORDS.length];
  return (
    <div className="live-line">
      <span className="canyassing">
        <span className="visually-hidden">wizi is thinking</span>
        {/* the word and the clock change every few seconds: shown, not read aloud */}
        <span className="canyassing-word" aria-hidden="true">
          {word}
          <span className="dots">
            <span>.</span>
            <span>.</span>
            <span>.</span>
          </span>
        </span>
        {time && (
          <small className="muted" aria-hidden="true">
            ({time})
          </small>
        )}
      </span>
    </div>
  );
}
