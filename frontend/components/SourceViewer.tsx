"use client";
import { useEffect, useRef, useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneLight,
  vscDarkPlus,
} from "react-syntax-highlighter/dist/esm/styles/prism";
import { X, FileCode2, LoaderCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Citation, Node } from "@/lib/types";
import { useTheme } from "@/lib/theme";
export default function SourceViewer({
  repository,
  citation,
  onClose,
}: {
  repository: string;
  citation: Citation;
  onClose: () => void;
}) {
  const [source, setSource] = useState<Node | null>(null);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const theme = useTheme();
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    setSource(null);
    setError("");
    const controller = new AbortController();
    api<Node>(
      `/repositories/${repository}/source?path=${encodeURIComponent(citation.file)}`,
      { signal: controller.signal },
    )
      .then(setSource)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [repository, citation.file]);
  useEffect(() => {
    if (source) {
      const element = dialog.current?.querySelector(
        `[data-line="${citation.start_line}"]`,
      );
      element?.scrollIntoView({ block: "center" });
    }
  }, [source, citation]);
  return (
    <dialog ref={dialog} className="source-modal" onCancel={onClose}>
      <header>
        <FileCode2 size={18} />
        <strong>{citation.file}</strong>
        <span>
          L{citation.start_line}–{citation.end_line}
        </span>
        <button
          onClick={onClose}
          className="icon-button"
          aria-label="Close source"
        >
          <X size={20} />
        </button>
      </header>
      <div className="source-body">
        {error ? (
          <div className="error">{error}</div>
        ) : source ? (
          <SyntaxHighlighter
            language={
              source.language === "Python"
                ? "python"
                : source.language === "TypeScript"
                  ? "typescript"
                  : "javascript"
            }
            style={theme === "light" ? oneLight : vscDarkPlus}
            showLineNumbers
            wrapLines
            lineProps={(line) => ({
              "data-line": line,
              style: {
                display: "block",
                backgroundColor:
                  line >= citation.start_line && line <= citation.end_line
                    ? "color-mix(in srgb, var(--accent) 12%, transparent)"
                    : undefined,
                borderLeft:
                  line >= citation.start_line && line <= citation.end_line
                    ? "2px solid var(--accent)"
                    : "2px solid transparent",
              },
            })}
            customStyle={{
              margin: 0,
              background: "var(--surface-low)",
              fontSize: 13,
              lineHeight: 1.8,
              minHeight: "100%",
            }}
          >
            {source.source || ""}
          </SyntaxHighlighter>
        ) : (
          <div className="empty">
            <LoaderCircle className="spin" />
            Loading indexed source…
          </div>
        )}
      </div>
      <footer>
        Read-only indexed source · Citations point to the analyzed repository
        version.
      </footer>
    </dialog>
  );
}
