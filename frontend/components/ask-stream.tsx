'use client';

import { Loader2, Search } from 'lucide-react';
import * as React from 'react';

import { ErrorBanner } from '@/components/error-banner';
import { pdfUrl } from '@/lib/api';
import { askStream } from '@/lib/sse';
import type { AgentEvent, Citation } from '@/lib/types';

export interface AskStreamProps {
  question: string;
  onOpenViewer: (url: string) => void;
  onRephrase: () => void;
}

interface AskState {
  status: 'idle' | 'thinking' | 'tool' | 'streaming' | 'done' | 'error';
  text: string;
  citations: Citation[];
  toolName: string | null;
  error: { code: string; detail: string; retriable: boolean } | null;
}

const INITIAL_STATE: AskState = {
  status: 'idle',
  text: '',
  citations: [],
  toolName: null,
  error: null,
};

export function AskStream({ question, onOpenViewer, onRephrase }: AskStreamProps) {
  const [state, setState] = React.useState<AskState>(INITIAL_STATE);
  const [retryNonce, setRetryNonce] = React.useState(0);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    if (!question) {
      setState(INITIAL_STATE);
      return;
    }
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;

    let cancelled = false;
    setState({ ...INITIAL_STATE, status: 'thinking' });

    (async () => {
      try {
        for await (const event of askStream(question, controller.signal)) {
          if (cancelled) return;
          setState((prev) => applyEvent(prev, event));
        }
      } catch (e) {
        if (cancelled || controller.signal.aborted) return;
        setState((prev) => ({
          ...prev,
          status: 'error',
          error: {
            code: 'internal',
            detail: e instanceof Error ? e.message : String(e),
            retriable: false,
          },
        }));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [question, retryNonce]);

  if (state.status === 'idle') {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Ask anything about your documents.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted-foreground">{question}</div>

      {state.toolName && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Search className="h-3 w-3 animate-pulse" />
          Searching documents...
        </div>
      )}

      {state.status === 'thinking' && !state.text && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Thinking...
        </div>
      )}

      {state.text && (
        <AnswerWithCitations
          text={state.text}
          citations={state.citations}
          streaming={state.status !== 'done' && state.status !== 'error'}
          onOpenViewer={onOpenViewer}
        />
      )}

      {state.error && (
        <ErrorBanner
          code={state.error.code}
          detail={state.error.detail}
          retriable={state.error.retriable}
          onRetry={() => setRetryNonce((n) => n + 1)}
          onRephrase={onRephrase}
        />
      )}
    </div>
  );
}

function applyEvent(prev: AskState, event: AgentEvent): AskState {
  switch (event.type) {
    case 'tool_use':
      return { ...prev, status: 'tool', toolName: event.name };
    case 'tool_result':
      return { ...prev, toolName: null };
    case 'text':
      return {
        ...prev,
        status: 'streaming',
        text: prev.text + event.delta,
      };
    case 'done':
      return {
        ...prev,
        status: 'done',
        text: event.answer,
        citations: event.citations,
        toolName: null,
      };
    case 'error':
      return {
        ...prev,
        status: 'error',
        toolName: null,
        error: {
          code: event.code,
          detail: event.detail,
          retriable: event.retriable,
        },
      };
    default:
      return prev;
  }
}

function AnswerWithCitations({
  text,
  citations,
  streaming,
  onOpenViewer,
}: {
  text: string;
  citations: Citation[];
  streaming: boolean;
  onOpenViewer: (url: string) => void;
}) {
  const byNumber = React.useMemo(() => {
    const m = new Map<number, Citation>();
    for (const c of citations) m.set(c.n, c);
    return m;
  }, [citations]);

  const parts = React.useMemo(() => splitOnCitationMarkers(text), [text]);

  return (
    <div className="text-sm leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) =>
        part.type === 'text' ? (
          <span key={i}>{part.value}</span>
        ) : (
          <CitationLink
            key={i}
            n={part.n}
            citation={byNumber.get(part.n)}
            onOpenViewer={onOpenViewer}
          />
        ),
      )}
      {streaming && <span className="inline-block w-2 h-4 bg-foreground/60 ml-0.5 animate-pulse" />}
    </div>
  );
}

type Part = { type: 'text'; value: string } | { type: 'cite'; n: number };

function splitOnCitationMarkers(text: string): Part[] {
  const out: Part[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  for (const match of text.matchAll(re)) {
    const idx = match.index ?? 0;
    if (idx > last) out.push({ type: 'text', value: text.slice(last, idx) });
    out.push({ type: 'cite', n: parseInt(match[1], 10) });
    last = idx + match[0].length;
  }
  if (last < text.length) out.push({ type: 'text', value: text.slice(last) });
  return out;
}

function CitationLink({
  n,
  citation,
  onOpenViewer,
}: {
  n: number;
  citation: Citation | undefined;
  onOpenViewer: (url: string) => void;
}) {
  if (!citation || !citation.document_id) {
    return <span className="text-muted-foreground">[{n}]</span>;
  }
  return (
    <button
      type="button"
      onClick={() => onOpenViewer(pdfUrl(citation.document_id, citation.page))}
      className="inline-flex items-baseline rounded bg-primary/10 px-1 text-xs font-medium text-primary hover:bg-primary/20 align-baseline"
      title={`${citation.filename}${citation.page ? `, page ${citation.page}` : ''}`}
    >
      [{n}]
    </button>
  );
}
