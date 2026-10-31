/**
 * CH-1228: the reader on the right of a chat: a long reply as a document (copy, download as Markdown) or a reply's
 * sources. Its left edge drags to resize it (`useReader`).
 */
import { useState } from "react";

import Markdown from "../Markdown";
import type { Reader } from "./useReader";
import "./reply-tools.css";

function download(name: string, text: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

export function ReaderPane({ reader }: { reader: Reader }) {
  const [copied, setCopied] = useState(false);
  const content = reader.content;
  if (!content) return null;

  const copy = async () => {
    if (content.kind !== "doc") return;
    try {
      await navigator.clipboard.writeText(content.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <aside className="reader-pane" aria-label={content.kind === "doc" ? "Document" : "Sources"}>
      <div
        className="reader-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Reader width"
        aria-valuemin={reader.min}
        aria-valuemax={reader.max}
        aria-valuenow={reader.width}
        tabIndex={0}
        title="Drag to resize; double-click for the default width"
        onPointerDown={reader.onPointerDown}
        onKeyDown={reader.onKeyDown}
        onDoubleClick={reader.reset}
      />
      <header className="reader-head">
        <h2 title={content.title}>{content.title}</h2>
        {content.kind === "doc" && (
          <>
            <button type="button" className="reader-button" onClick={() => void copy()}>
              {copied ? "Copied" : "Copy"}
            </button>
            <button type="button" className="reader-button" onClick={() => download("wizi-reply.md", content.text)}>
              Download
            </button>
          </>
        )}
        <button type="button" className="reader-close" aria-label="Close the reader" onClick={reader.close}>
          ×
        </button>
      </header>
      <div className="reader-body">
        {content.kind === "doc" ? (
          <Markdown text={content.text} />
        ) : (
          <ol className="reader-sources">
            {content.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  <span className="reader-source-label">{source.label}</span>
                  <span className="reader-source-host">{source.host}</span>
                </a>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
