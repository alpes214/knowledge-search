import { apiBase } from '@/lib/api';
import type { AgentEvent } from '@/lib/types';

export async function* askStream(
  question: string,
  signal: AbortSignal,
): AsyncIterable<AgentEvent> {
  const res = await fetch(`${apiBase}/ask`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}`);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (value) buffer += value;
      let idx;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const event = parseSseBlock(block);
        if (event) yield event;
      }
      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseBlock(block: string): AgentEvent | null {
  let dataLine: string | null = null;
  for (const line of block.split('\n')) {
    if (line.startsWith('data: ')) dataLine = line.slice(6);
  }
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine) as AgentEvent;
  } catch {
    return null;
  }
}
