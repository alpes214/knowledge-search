'use client';

import * as React from 'react';

import { ChatPanel } from '@/components/chat-panel';
import { DocsSidebar } from '@/components/docs-sidebar';
import { PdfPreview } from '@/components/pdf-preview';
import type { DocumentOut } from '@/lib/types';

export default function HomePage() {
  const [docs, setDocs] = React.useState<DocumentOut[]>([]);
  const [pdfUrl, setPdfUrl] = React.useState<string | null>(null);

  return (
    <main
      className="grid h-screen w-screen overflow-hidden"
      style={{ gridTemplateColumns: pdfUrl ? '280px 1fr 1fr' : '280px 1fr' }}
    >
      <DocsSidebar docs={docs} onDocsChange={setDocs} />
      <div className="flex h-full flex-col border-r">
        <header className="flex items-center justify-between border-b px-4 py-3">
          <h1 className="text-base font-semibold">Knowledge Search</h1>
        </header>
        <div className="flex-1 overflow-hidden">
          <ChatPanel onOpenViewer={setPdfUrl} />
        </div>
      </div>
      {pdfUrl && (
        <div className="h-full">
          <PdfPreview url={pdfUrl} onClose={() => setPdfUrl(null)} />
        </div>
      )}
    </main>
  );
}
