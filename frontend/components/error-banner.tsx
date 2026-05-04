'use client';

import { AlertTriangle, RotateCw } from 'lucide-react';

import { Button } from '@/components/ui/button';

export interface ErrorBannerProps {
  code: string;
  detail: string;
  retriable: boolean;
  onRetry?: () => void;
  onRephrase?: () => void;
}

const FRIENDLY_CODES: Record<string, string> = {
  tool_failed: 'A search tool failed. The embedding service may be down.',
  llm_unavailable: 'The language model is unavailable.',
  malformed_tool_call: 'The assistant produced an invalid response.',
  iteration_limit_exceeded:
    "The assistant couldn't find an answer in the allotted search rounds.",
  internal: 'Something went wrong on our end.',
};

export function ErrorBanner({
  code,
  detail,
  retriable,
  onRetry,
  onRephrase,
}: ErrorBannerProps) {
  const friendly = FRIENDLY_CODES[code] ?? 'An error occurred.';
  return (
    <div className="flex items-start gap-3 rounded-md border border-destructive bg-destructive/10 p-3 text-sm">
      <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
      <div className="flex-1 space-y-2">
        <div>
          <div className="font-medium text-destructive">{friendly}</div>
          <div className="text-xs text-muted-foreground mt-1 break-all">{detail}</div>
        </div>
        {retriable && onRetry && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            <RotateCw className="h-3 w-3" /> Retry
          </Button>
        )}
        {!retriable && onRephrase && (
          <Button size="sm" variant="outline" onClick={onRephrase}>
            Rephrase
          </Button>
        )}
      </div>
    </div>
  );
}
