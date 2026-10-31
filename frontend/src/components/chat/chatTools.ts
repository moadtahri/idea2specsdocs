/**
 * CH-1228: what every wizi chat gives its replies: copy, a rating kept for training, read aloud, try again
 * with guidance, the sources, and a long reply opened as a document in the reader on the right.
 *
 * A chat page provides `ChatToolsContext` (its project, how it asks wizi again, the reader); its reply rows
 * read it with `useChatTools`. The helpers here are pure.
 */
import { createContext, useContext } from "react";

export interface Source {
  url: string;
  label: string;
  host: string;
}

/** What the reader on the right shows. */
export type ReaderContent =
  { kind: "doc"; title: string; text: string } | { kind: "sources"; title: string; sources: Source[] };

export interface ChatTools {
  /** The project whose replies are rated. */
  projectId: string;
  /** Ask wizi to try its latest reply again, with the user's guidance when they gave some. */
  onRetry: (guidance: string) => void;
  openReader: (content: ReaderContent) => void;
}

export const ChatToolsContext = createContext<ChatTools | null>(null);

export function useChatTools(): ChatTools | null {
  return useContext(ChatToolsContext);
}

/** A reply this long is shown as a document: its opening in the chat, the whole in the reader. */
export const LONG_REPLY_CHARS = 1500;
/** Beyond this, any reply is a document. */
export const VERY_LONG_REPLY_CHARS = 6000;

/**
 * Kanya cuts every reply over 1,500 characters; wizi's question rounds often run longer, and their questions sit at
 * the end, so a cut would hide what the user must answer. A reply is a document when it is long and has a heading
 * (a written-out plan or summary), or when it is very long.
 */
export function isLong(text: string): boolean {
  const trimmed = text.trim();
  return (trimmed.length > LONG_REPLY_CHARS && /^#{1,3}\s/m.test(trimmed)) || trimmed.length > VERY_LONG_REPLY_CHARS;
}

/** The document's title: its first heading, or its first line, cut short. */
export function docTitle(text: string): string {
  const heading = /^#{1,3}\s+(.+)$/m.exec(text)?.[1];
  const first = heading ?? text.trim().split("\n")[0] ?? "wizi's reply";
  const plain = first
    .replace(/[*_`#>[\]]/g, "")
    .replace(/\(https?:[^)]*\)/g, "")
    .trim();
  return plain.length > 70 ? `${plain.slice(0, 68)}…` : plain || "wizi's reply";
}

/** The reply's opening for the chat: whole paragraphs up to about 500 characters. */
export function excerpt(text: string): string {
  const paragraphs = text.trim().split(/\n\s*\n/);
  let out = "";
  for (const paragraph of paragraphs) {
    if (out && out.length + paragraph.length > 500) break;
    out = out ? `${out}\n\n${paragraph}` : paragraph;
    if (out.length > 500) break;
  }
  return out.length > 700 ? `${out.slice(0, 680).trimEnd()}…` : out;
}

export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

/** The links in a reply, in order, each once: markdown links with their words, bare URLs with their host. */
export function sourcesOf(text: string): Source[] {
  const found = new Map<string, Source>();
  const add = (url: string, label: string) => {
    const clean = url.replace(/[.,;:!?)\]]+$/, "");
    if (found.has(clean)) return;
    let host = "";
    try {
      host = new URL(clean).hostname.replace(/^www\./, "");
    } catch {
      return;
    }
    found.set(clean, { url: clean, label: label.trim() || host, host });
  };
  for (const match of text.matchAll(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g)) add(match[2]!, match[1]!);
  const bare = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, " ");
  for (const match of bare.matchAll(/https?:\/\/[^\s<>()"']+/g)) add(match[0], "");
  return [...found.values()];
}

/** What "Try again" says to wizi. */
export function retryMessage(guidance: string): string {
  const words = guidance.trim();
  return words ? `Try your last reply again. This time: ${words}` : "Try your last reply again, differently.";
}

/** The reply's key, as the server computes it: the SHA-256 of its trimmed text, in hex. */
export async function replyHash(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text.trim());
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
