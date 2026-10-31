/**
 * The voice buttons every wizi composer carries (D46), beside Send:
 * - **Dictate** (microphone): your words appear in the box as you speak; press it again to stop. Nothing is sent.
 * - **Start voice** (sound wave): a spoken conversation. Each sentence you finish goes to wizi as a message; its
 *   reply is read aloud. Talking over wizi stops its voice. Cards and previews still appear on screen.
 * A short caption shows what is being heard. Escape stops either mode.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { listen, speak, type Listening } from "./voice";
import "./voice.css";

interface Props {
  /** Dictation: a finished sentence to add to the box. */
  onDictated: (text: string) => void;
  /** Voice mode: a finished sentence to send to wizi. */
  onUtterance: (text: string) => void;
  /** wizi's latest reply; read aloud in voice mode when its key changes. */
  reply?: { key: string; text: string } | null;
  disabled?: boolean;
}

type Mode = "off" | "dictate" | "voice";

export function VoiceButtons({ onDictated, onUtterance, reply, disabled }: Props) {
  const [mode, setMode] = useState<Mode>("off");
  const [caption, setCaption] = useState("");
  const [problem, setProblem] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const session = useRef<Listening | null>(null);
  const voice = useRef<AbortController | null>(null);
  const spokenKey = useRef<string | null>(reply?.key ?? null);
  const modeRef = useRef<Mode>("off");

  const quiet = useCallback(() => {
    voice.current?.abort();
    voice.current = null;
    setSpeaking(false);
  }, []);

  const stop = useCallback(() => {
    session.current?.stop();
    session.current = null;
    quiet();
    modeRef.current = "off";
    setMode("off");
    setCaption("");
  }, [quiet]);

  const start = async (next: Mode) => {
    if (mode !== "off") {
      const same = mode === next;
      stop();
      if (same) return;
    }
    setProblem("");
    spokenKey.current = reply?.key ?? null; // speak only replies that arrive from now on
    try {
      session.current = await listen({
        onPartial: (text) => setCaption(text),
        onFinal: (text) => {
          setCaption("");
          if (modeRef.current === "voice") onUtterance(text);
          else onDictated(text);
        },
        onSpeechStarted: () => {
          if (modeRef.current === "voice") quiet();
        },
        onError: (message) => {
          setProblem(message);
          stop();
        },
      });
      modeRef.current = next;
      setMode(next);
    } catch (error) {
      setProblem(
        error instanceof Error && error.name === "NotAllowedError"
          ? "Allow the microphone to use voice."
          : "The microphone is not available.",
      );
    }
  };

  useEffect(() => {
    if (mode !== "voice" || !reply || reply.key === spokenKey.current || !reply.text.trim()) return;
    spokenKey.current = reply.key;
    quiet();
    const controller = new AbortController();
    voice.current = controller;
    setSpeaking(true);
    speak(reply.text, controller.signal)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setProblem("wizi's voice is not available right now.");
      })
      .finally(() => {
        if (voice.current === controller) {
          voice.current = null;
          setSpeaking(false);
        }
      });
  }, [mode, reply, quiet]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && modeRef.current !== "off") stop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return (
    <div className="voice-buttons">
      {(caption || problem || mode !== "off") && (
        <span className={`voice-caption${problem ? " is-problem" : ""}`} role="status" aria-live="polite">
          {problem ||
            caption ||
            (speaking
              ? "wizi is speaking… talk to interrupt"
              : mode === "voice"
                ? "Listening… speak to wizi"
                : "Listening…")}
        </span>
      )}
      <button
        type="button"
        className={`voice-button${mode === "dictate" ? " is-on" : ""}`}
        aria-pressed={mode === "dictate"}
        aria-label={mode === "dictate" ? "Stop dictating" : "Dictate"}
        title={mode === "dictate" ? "Stop dictating" : "Dictate"}
        disabled={disabled}
        onClick={() => void start("dictate")}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>
      <button
        type="button"
        className={`voice-button voice-start${mode === "voice" ? " is-on" : ""}${speaking ? " is-speaking" : ""}`}
        aria-pressed={mode === "voice"}
        aria-label={mode === "voice" ? "End voice" : "Start voice"}
        title={mode === "voice" ? "End voice" : "Start voice"}
        disabled={disabled}
        onClick={() => void start("voice")}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M5 10v4M9 7v10M13 4v16M17 8v8M21 11v2"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  );
}
