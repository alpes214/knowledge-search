'use client';

import { Upload } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { getDoc, uploadDoc } from '@/lib/api';
import type { DocumentOut } from '@/lib/types';

export interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: (doc: DocumentOut) => void;
  onDocUpdate: (doc: DocumentOut) => void;
}

export function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
  onDocUpdate,
}: UploadDialogProps) {
  const [dragOver, setDragOver] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  if (!open) return null;

  async function handleFile(file: File) {
    setError(null);
    setBusy(true);
    try {
      const result = await uploadDoc(file);
      const initial: DocumentOut = {
        id: result.doc_id,
        filename: file.name,
        status: result.status,
        page_count: null,
        chunk_count: null,
        error_message: null,
        uploaded_at: new Date().toISOString(),
      };
      onUploaded(initial);
      onOpenChange(false);
      pollUntilTerminal(result.doc_id, onDocUpdate);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="w-[420px] rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-base font-semibold">Upload PDF</h3>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed transition-colors ${
            dragOver ? 'border-primary bg-primary/5' : 'border-input'
          }`}
        >
          <Upload className="h-6 w-6 text-muted-foreground" />
          <div className="text-sm text-muted-foreground">
            {busy ? 'Uploading...' : 'Drop a PDF or click to choose'}
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
        {error && <div className="mt-3 text-sm text-destructive">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

function pollUntilTerminal(id: string, onUpdate: (doc: DocumentOut) => void) {
  const poll = async () => {
    try {
      const doc = await getDoc(id);
      onUpdate(doc);
      if (doc.status === 'ready' || doc.status === 'failed') return;
    } catch {
      // ignore transient errors; keep polling
    }
    setTimeout(poll, 5000);
  };
  setTimeout(poll, 2000);
}
