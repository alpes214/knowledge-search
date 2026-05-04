import type {
  DocumentOut,
  SearchResponse,
  UploadResponse,
} from '@/lib/types';

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

async function expect<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${detail || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function listDocs(): Promise<DocumentOut[]> {
  return expect(await fetch(`${BASE}/docs`));
}

export async function getDoc(id: string): Promise<DocumentOut> {
  return expect(await fetch(`${BASE}/docs/${id}`));
}

export async function uploadDoc(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  return expect(await fetch(`${BASE}/docs`, { method: 'POST', body: form }));
}

export async function deleteDoc(id: string): Promise<void> {
  const res = await fetch(`${BASE}/docs/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function pdfUrl(id: string, page?: number | null): string {
  const fragment = page ? `#page=${page}` : '';
  return `${BASE}/docs/${id}/pdf${fragment}`;
}

export async function search(
  query: string,
  k = 10,
  docIds?: string[],
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, k: String(k) });
  for (const id of docIds ?? []) params.append('doc_id', id);
  return expect(await fetch(`${BASE}/search?${params.toString()}`));
}

export const apiBase = BASE;
