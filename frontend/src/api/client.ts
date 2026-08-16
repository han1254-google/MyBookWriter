/**
 * API 客户端 — 封装所有后端请求
 */
const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || `HTTP ${resp.status}`);
  }
  return resp.json();
}

type ChunkFn = (text: string) => void;
type DoneFn = (data?: Record<string, unknown>) => void;
type ErrorFn = (err: string) => void;

export function streamRequest(
  url: string, body: unknown,
  onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn,
): AbortController {
  const controller = new AbortController();
  fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(async (resp) => {
    const reader = resp.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === 'text') onChunk(data.content);
          else if (data.type === 'done') onDone(data);
          else if (data.type === 'error') onError(data.content);
        } catch { /* skip */ }
      }
    }
  }).catch(err => {
    if (err.name !== 'AbortError') onError(err.message);
  });
  return controller;
}

// ---- Ideas ----
export const ideasApi = {
  generate: (prompt: string, category: string | null, files: string[] | null, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/ideas/generate', { prompt, category, files }, onChunk, onDone, onError),
  chat: (ideaId: number, message: string, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest(`/ideas/chat/${ideaId}`, { message }, onChunk, onDone, onError),
  save: (data: { title: string; content: string; knowledge_context?: string; chat_history?: string }) =>
    request<{ success: boolean; id: number }>('/ideas/save', { method: 'POST', body: JSON.stringify(data) }),
  list: () => request<Array<Record<string, unknown>>>('/ideas'),
  get: (id: number) => request<Record<string, unknown>>(`/ideas/${id}`),
  delete: (id: number) => request<{ success: boolean }>(`/ideas/${id}`, { method: 'DELETE' }),
};

// ---- Outlines ----
export const outlinesApi = {
  generate: (data: { idea_id?: number; prompt?: string }, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/outlines/generate', data, onChunk, onDone, onError),
  chat: (outlineId: number, message: string, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest(`/outlines/chat/${outlineId}`, { message }, onChunk, onDone, onError),
  save: (data: { idea_id?: number; title: string; content: string }) =>
    request<{ success: boolean; id: number }>('/outlines/save', { method: 'POST', body: JSON.stringify(data) }),
  list: () => request<Array<Record<string, unknown>>>('/outlines'),
  get: (id: number) => request<Record<string, unknown>>(`/outlines/${id}`),
  delete: (id: number) => request<{ success: boolean }>(`/outlines/${id}`, { method: 'DELETE' }),
};

// ---- Writing ----
export const writingApi = {
  startWriting: (outlineId: number, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/writing/start', { outline_id: outlineId }, onChunk, onDone, onError),
  generateChapter: (outlineId: number, chapterNumber: number, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/writing/chapter', { outline_id: outlineId, chapter_number: chapterNumber }, onChunk, onDone, onError),
  chatChapter: (chapterId: number, message: string, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest(`/writing/chat/${chapterId}`, { message }, onChunk, onDone, onError),
  saveChapter: (data: { outline_id: number; chapter_number: number; title: string; content: string; status: string }) =>
    request<{ success: boolean }>('/writing/save', { method: 'POST', body: JSON.stringify(data) }),
  getChapters: (outlineId: number) => request<Array<Record<string, unknown>>>(`/writing/chapters/${outlineId}`),
  deleteChapter: (chapterId: number) => request<{ success: boolean }>(`/writing/chapter/${chapterId}`, { method: 'DELETE' }),
  exportBook: (outlineId: number) => request<{ full_text: string; title: string }>(`/writing/export/${outlineId}`, { method: 'POST' }),
};

// ---- Rewrite ----
export const rewriteApi = {
  analyze: (text: string) =>
    request<{ success: boolean; analysis: Record<string, unknown> }>('/rewrite/analyze', { method: 'POST', body: JSON.stringify({ text }) }),
  rewrite: (text: string, instructions: string | null, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/rewrite/rewrite', { text, instructions }, onChunk, onDone, onError),
};

// ---- Upload ----
export const uploadApi = {
  upload: async (file: File, libraryType?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (libraryType) formData.append('library_type', libraryType);
    const resp = await fetch(`${BASE}/upload`, { method: 'POST', body: formData });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(err.error);
    }
    return resp.json() as Promise<{ success: boolean; id: number; library_type: string; folder_name: string; filename: string }>;
  },
  getLibraries: () => request<{ structure: Record<string, Record<string, string[]>>; files: Array<Record<string, unknown>> }>('/libraries'),
  deleteFile: (id: number) => request<{ success: boolean }>(`/libraries/${id}`, { method: 'DELETE' }),
};
