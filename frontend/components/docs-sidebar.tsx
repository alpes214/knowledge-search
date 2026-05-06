'use client';

import { FileText, Upload } from 'lucide-react';
import * as React from 'react';

import { UploadDialog } from '@/components/upload-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { listDocs } from '@/lib/api';
import type { DocStatus, DocumentOut } from '@/lib/types';

export interface DocsSidebarProps {
  docs: DocumentOut[];
  onDocsChange: (docs: DocumentOut[]) => void;
}

const STATUS_VARIANT: Record<
  DocStatus,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  pending: 'outline',
  processing: 'secondary',
  ready: 'default',
  failed: 'destructive',
};

export function DocsSidebar({ docs, onDocsChange }: DocsSidebarProps) {
  const [loading, setLoading] = React.useState(true);
  const [uploadOpen, setUploadOpen] = React.useState(false);

  React.useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const list = await listDocs();
      onDocsChange(list);
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="flex h-full flex-col border-r bg-muted/30">
      <div className="border-b p-3">
        <h2 className="text-base font-semibold">Documents</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <SkeletonRows />
        ) : docs.length === 0 ? (
          <EmptyState onUpload={() => setUploadOpen(true)} />
        ) : (
          <ul className="space-y-1">
            {docs.map((doc) => (
              <li
                key={doc.id}
                className="group flex items-start gap-2 rounded-md p-2 hover:bg-muted"
              >
                <FileText className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <div className="truncate text-xs font-medium" title={doc.filename}>
                    {doc.filename}
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <Badge variant={STATUS_VARIANT[doc.status]} className="text-[10px]">
                      {doc.status}
                    </Badge>
                    {doc.chunk_count !== null && (
                      <span className="text-[10px] text-muted-foreground">
                        {doc.chunk_count} chunks
                      </span>
                    )}
                  </div>
                  {doc.error_message && (
                    <div
                      className="mt-1 text-[10px] text-destructive truncate"
                      title={doc.error_message}
                    >
                      {doc.error_message}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t p-3">
        <Button
          size="sm"
          className="w-full min-h-[60px]"
          onClick={() => setUploadOpen(true)}
        >
          <Upload className="h-3 w-3" /> Upload
        </Button>
      </div>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={(newDoc) => {
          onDocsChange([newDoc, ...docs]);
        }}
        onDocUpdate={(updated) => {
          onDocsChange(docs.map((d) => (d.id === updated.id ? updated : d)));
        }}
      />
    </aside>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-2 p-2">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-12 rounded-md bg-muted/50 animate-pulse" />
      ))}
    </div>
  );
}

function EmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 p-6 text-center">
      <FileText className="h-8 w-8 text-muted-foreground" />
      <div className="text-xs text-muted-foreground">
        No documents yet. Upload one to get started.
      </div>
      <Button size="sm" onClick={onUpload}>
        <Upload className="h-3 w-3" /> Upload
      </Button>
    </div>
  );
}
