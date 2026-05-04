'use client';

import { FileText, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

export interface PdfPreviewProps {
  url: string | null;
  onClose: () => void;
}

export function PdfPreview({ url, onClose }: PdfPreviewProps) {
  if (!url) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <div className="flex flex-col items-center gap-2">
          <FileText className="h-8 w-8" />
          <div className="text-sm">Click a citation to preview its source.</div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-1.5">
        <span className="truncate text-xs text-muted-foreground" title={url}>
          {extractFilename(url)}
        </span>
        <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close preview">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <iframe src={url} title="Document preview" className="flex-1 w-full border-0" />
    </div>
  );
}

function extractFilename(url: string): string {
  try {
    const u = new URL(url);
    const parts = u.pathname.split('/').filter(Boolean);
    // /docs/<id>/pdf -> we don't have the filename in the URL; use the path
    return parts[parts.length - 2] ?? url;
  } catch {
    return url;
  }
}
