"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, Paperclip, X } from "lucide-react";

import { getToken } from "@/lib/auth-token";
import type { AttachmentMeta } from "@/lib/types";

function fmtSize(bytes?: number) {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Wrap any composer in a drag-and-drop target. Dropping files calls `onFiles`;
 * a dashed overlay appears while dragging. Purely presentational — the parent
 * owns the upload.
 */
export function AttachmentDropArea({
  onFiles,
  children,
  className,
  disabled,
}: {
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      className={`relative ${className ?? ""}`}
      onDragOver={(e) => {
        if (disabled) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        if (disabled) return;
        e.preventDefault();
        setOver(false);
        const files = Array.from(e.dataTransfer.files || []);
        if (files.length) onFiles(files);
      }}
    >
      {children}
      {over && !disabled && (
        <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center rounded-lg border-2 border-dashed border-signal-red/60 bg-red-50/80 text-xs font-semibold text-signal-red">
          Drop files to attach
        </div>
      )}
    </div>
  );
}

/** Paperclip button + hidden file input (multi-select). */
export function AttachButton({
  onFiles,
  disabled,
  className,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  return (
    <>
      <button
        type="button"
        title="Attach files"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className={className ?? "rounded-md p-2 text-brand-muted hover:bg-subtle hover:text-brand-dark disabled:opacity-50"}
      >
        <Paperclip size={16} />
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
    </>
  );
}

/** Chips for files staged on the composer (uploaded, not yet sent). */
export function PendingAttachments({
  items,
  uploading,
  onRemove,
}: {
  items: AttachmentMeta[];
  uploading?: number;
  onRemove: (id: number) => void;
}) {
  if (!items.length && !uploading) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-2">
      {items.map((a) => (
        <span
          key={a.id}
          className="inline-flex max-w-[240px] items-center gap-1.5 rounded-full border border-brand-border bg-subtle px-2.5 py-1 text-[11px] text-brand-dark"
        >
          <FileText size={12} className="shrink-0 text-brand-muted" />
          <span className="truncate" title={a.filename}>{a.filename}</span>
          {fmtSize(a.size_bytes) && <span className="shrink-0 text-brand-muted">{fmtSize(a.size_bytes)}</span>}
          <button
            type="button"
            title="Remove"
            onClick={() => onRemove(a.id)}
            className="shrink-0 rounded-full p-0.5 text-brand-muted hover:bg-red-50 hover:text-signal-red"
          >
            <X size={11} />
          </button>
        </span>
      ))}
      {uploading ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-border bg-subtle px-2.5 py-1 text-[11px] text-brand-muted">
          <Loader2 size={12} className="animate-spin" /> Uploading {uploading} file{uploading === 1 ? "" : "s"}…
        </span>
      ) : null}
    </div>
  );
}

/**
 * Downloadable chips on a message bubble. `endpointFor` builds the scoped
 * download URL for the current user type (staff / employee / supplier); the
 * fetch carries the auth token, so a plain <a href> would not work.
 */
export function AttachmentChips({
  items,
  endpointFor,
}: {
  items?: AttachmentMeta[];
  endpointFor: (id: number) => string;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  if (!items || !items.length) return null;

  async function download(a: AttachmentMeta) {
    setBusy(a.id);
    try {
      const token = getToken();
      const res = await fetch(endpointFor(a.id), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      window.alert("Attachment download failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.map((a) => (
        <button
          key={a.id}
          type="button"
          disabled={busy === a.id}
          onClick={(e) => {
            e.stopPropagation();
            void download(a);
          }}
          title={`Download ${a.filename}`}
          className="inline-flex max-w-[260px] items-center gap-1.5 rounded-full border border-brand-border bg-card px-2.5 py-1 text-[11px] font-medium text-brand-dark shadow-sm hover:bg-subtle disabled:opacity-60"
        >
          {busy === a.id ? (
            <Loader2 size={12} className="animate-spin shrink-0" />
          ) : (
            <FileText size={12} className="shrink-0 text-signal-red" />
          )}
          <span className="truncate">{a.filename}</span>
          {fmtSize(a.size_bytes) && <span className="shrink-0 text-brand-muted">{fmtSize(a.size_bytes)}</span>}
        </button>
      ))}
    </div>
  );
}
