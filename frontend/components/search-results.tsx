'use client';

import { ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { pdfUrl } from '@/lib/api';
import type { SearchResult } from '@/lib/types';

export interface SearchResultsProps {
  results: SearchResult[] | null; // null = not yet searched
  loading: boolean;
  query: string;
  onOpenViewer: (url: string) => void;
}

export function SearchResults({ results, loading, query, onOpenViewer }: SearchResultsProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-32 rounded-md bg-muted/50 animate-pulse" />
        ))}
      </div>
    );
  }

  if (results === null) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Type a query above and hit Enter.
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        No relevant matches found for {`"${query}"`}. Try different terms.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {results.map((r) => (
        <Card key={r.chunk_id}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium" title={r.filename}>
                  {r.filename}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  {r.page !== null && <span>page {r.page}</span>}
                  {r.heading && <span className="truncate">- {r.heading.replace(/\*/g, '')}</span>}
                  <Badge variant="outline">{r.score.toFixed(2)}</Badge>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onOpenViewer(pdfUrl(r.document_id, r.page))}
              >
                <ExternalLink className="h-3 w-3" /> View
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-sm prose prose-sm max-w-none prose-slate">
              <ReactMarkdown>{r.text}</ReactMarkdown>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
