'use client';

import { Send } from 'lucide-react';
import * as React from 'react';

import { AskStream } from '@/components/ask-stream';
import { SearchResults } from '@/components/search-results';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { search } from '@/lib/api';
import type { SearchResult } from '@/lib/types';

type Mode = 'ask' | 'search';

export interface ChatPanelProps {
  onOpenViewer: (url: string) => void;
}

export function ChatPanel({ onOpenViewer }: ChatPanelProps) {
  const [mode, setMode] = React.useState<Mode>('ask');
  const [input, setInput] = React.useState('');
  const [submitted, setSubmitted] = React.useState('');
  const [searchResults, setSearchResults] = React.useState<SearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = React.useState(false);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);

  function submit() {
    const text = input.trim();
    if (!text) return;
    if (mode === 'ask') {
      setSubmitted(text);
    } else {
      setSearchLoading(true);
      setSubmitted(text);
      void search(text)
        .then((res) => setSearchResults(res.results))
        .catch(() => setSearchResults([]))
        .finally(() => setSearchLoading(false));
    }
  }

  function rephrase() {
    setSubmitted('');
    inputRef.current?.focus();
  }

  return (
    <div className="flex h-full flex-col">
      <Tabs
        value={mode}
        onValueChange={(v) => {
          setMode(v as Mode);
          setSubmitted('');
          setSearchResults(null);
        }}
        className="border-b px-4 pt-3"
      >
        <TabsList>
          <TabsTrigger value="ask">Ask</TabsTrigger>
          <TabsTrigger value="search">Search</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex-1 overflow-y-auto p-4">
        {mode === 'ask' ? (
          <AskStream
            question={submitted}
            onOpenViewer={onOpenViewer}
            onRephrase={rephrase}
          />
        ) : (
          <SearchResults
            results={searchResults}
            loading={searchLoading}
            query={submitted}
            onOpenViewer={onOpenViewer}
          />
        )}
      </div>

      <form
        className="border-t bg-background p-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex items-end gap-2">
          <Textarea
            ref={inputRef}
            placeholder={mode === 'ask' ? 'Ask anything about your documents...' : 'Search documents...'}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            className="min-h-[60px] resize-none"
          />
          <Button type="submit" size="icon" disabled={!input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </div>
  );
}
