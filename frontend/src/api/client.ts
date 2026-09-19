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

type Json = Record<string, unknown>;
type ChunkFn = (text: string) => void;
type DoneFn = (data?: Json) => void;
type ErrorFn = (err: string) => void;
/** 非 text/done/error 的事件（plan / status / context） */
type EventFn = (type: string, data: Json) => void;

export function streamRequest(
  url: string, body: unknown,
  onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn,
  onEvent?: EventFn,
): AbortController {
  const controller = new AbortController();
  fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  }).then(async (resp) => {
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
      onError(err.error || `HTTP ${resp.status}`);
      return;
    }
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
          else onEvent?.(data.type, data);
        } catch { /* 忽略不完整的行 */ }
      }
    }
  }).catch(err => {
    if (err.name !== 'AbortError') onError(err.message);
  });
  return controller;
}

// ============================================================
// 类型
// ============================================================
export interface StoryEntity {
  id: number;
  idea_id: number | null;
  project_id: number | null;
  kind: string;
  kind_label: string;
  name: string;
  summary: string;
  detail: string;
  attributes: Record<string, string>;
  first_appear_chapter: number | null;
  sort_order: number;
}

export interface Idea {
  id: number;
  title: string;
  content: string;
  one_liner: string;
  core_concept: string;
  worldview: string;
  themes: string;
  opening: string;
  sources: Array<Json>;
  structured_ok: boolean;
  entities?: StoryEntity[];
  created_at: string;
  updated_at: string;
}

export interface Outline {
  id: number;
  idea_id: number | null;
  project_id: number | null;
  title: string;
  content: string;
  synopsis: string;
  themes: string;
  structure_note: string;
  parsed_ok: boolean;
  chapter_count: number;
  chapters?: ChapterSummary[];
  created_at: string;
  updated_at: string;
}

export interface ChapterSummary {
  id: number;
  project_id: number;
  outline_id: number | null;
  chapter_number: number;
  sort_key: number;
  label: string;
  title: string;
  status: string;
  word_count: number;
  has_plan: boolean;
  has_precha: boolean;
  has_content: boolean;
  updated_at: string;
}

export interface Chapter extends ChapterSummary {
  plan_scene: string;
  plan_events: string;
  plan_emotion: string;
  plan_settings: string;
  plan_notes: string;
  precha_name: string;
  precha_link: string;
  precha_time: string;
  precha_place: string;
  precha_chars: string;
  precha_cause: string;
  precha_process: string;
  precha_result: string;
  precha_media: string;
  precha_auto: boolean;
  content: string;
  context_snapshot: Json;
  knowledge_context: Json;
  entities?: StoryEntity[];
  onstage_entity_ids?: number[];
  audit?: { ok: boolean; issues: string[]; note?: string };
  revision_count?: number;
}

export interface Project {
  id: number;
  title: string;
  synopsis: string;
  source_type: string;
  idea_id: number | null;
  outline_id: number | null;
  status: string;
  style_notes: string;
  chapter_count: number;
  word_count: number;
  completed_count: number;
  chapters?: ChapterSummary[];
  entities?: StoryEntity[];
  outline?: Outline | null;
  idea?: Idea | null;
  created_at: string;
  updated_at: string;
}

export interface Revision {
  id: number;
  target_type: string;
  target_id: number;
  version_no: number;
  op: string;
  op_label: string;
  instruction: string;
  char_count: number;
  content?: string;
  created_at: string;
}

export interface LibraryCategory {
  id: number;
  library_type: string;
  name: string;
  description: string;
  aliases: string[];
  is_active: boolean;
  sort_order: number;
  file_count?: number;
}

// ============================================================
// Ideas
// ============================================================
export const ideasApi = {
  generate: (
    prompt: string, files: string[] | null,
    onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn, onEvent?: EventFn,
  ) => streamRequest('/ideas/generate', { prompt, files }, onChunk, onDone, onError, onEvent),

  /** 底部命令行：按意见重写创意 */
  command: (
    ideaId: number, instruction: string, section: string | null,
    onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn,
  ) => streamRequest(`/ideas/${ideaId}/command`, { instruction, section, op: 'rewrite' },
    onChunk, onDone, onError),

  save: (data: { title?: string; content: string; structure?: Json; knowledge_context?: unknown }) =>
    request<{ success: boolean; id: number; idea: Idea }>('/ideas/save',
      { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Idea> & { skip_restructure?: boolean }) =>
    request<{ success: boolean; idea: Idea }>(`/ideas/${id}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  restructure: (id: number) =>
    request<{ success: boolean; entity_count: number; idea: Idea }>(
      `/ideas/${id}/restructure`, { method: 'POST' }),
  list: () => request<Idea[]>('/ideas'),
  get: (id: number) => request<Idea>(`/ideas/${id}`),
  delete: (id: number) => request<{ success: boolean }>(`/ideas/${id}`, { method: 'DELETE' }),

  listEntities: (id: number, kind?: string) =>
    request<StoryEntity[]>(`/ideas/${id}/entities${kind ? `?kind=${kind}` : ''}`),
  createEntity: (id: number, data: Partial<StoryEntity>) =>
    request<{ success: boolean; entity: StoryEntity }>(`/ideas/${id}/entities`,
      { method: 'POST', body: JSON.stringify(data) }),

  revisions: (id: number) => request<Revision[]>(`/ideas/${id}/revisions`),
  revert: (id: number, versionNo: number) =>
    request<{ success: boolean; idea: Idea }>(`/ideas/${id}/revert/${versionNo}`,
      { method: 'POST' }),
};

// ============================================================
// Entities（跨创意/作品共用）
// ============================================================
export const entitiesApi = {
  update: (id: number, data: Partial<StoryEntity>) =>
    request<{ success: boolean; entity: StoryEntity }>(`/entities/${id}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) =>
    request<{ success: boolean }>(`/entities/${id}`, { method: 'DELETE' }),
};

// ============================================================
// Outlines
// ============================================================
export const outlinesApi = {
  generate: (
    data: { idea_id?: number; prompt?: string; chapter_count?: number | null; structure_hint?: string },
    onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn,
  ) => streamRequest('/outlines/generate', data, onChunk, onDone, onError),

  /** 底部命令行：按意见重写大纲 */
  command: (
    outlineId: number, instruction: string,
    onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn,
  ) => streamRequest(`/outlines/${outlineId}/command`, { instruction },
    onChunk, onDone, onError),

  save: (data: { idea_id?: number; title?: string; content: string; parsed?: Json }) =>
    request<{ success: boolean; id: number; project_id: number; outline: Outline; chapters: ChapterSummary[] }>(
      '/outlines/save', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Outline>) =>
    request<{ success: boolean; outline: Outline }>(`/outlines/${id}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  list: () => request<Outline[]>('/outlines'),
  get: (id: number) => request<Outline>(`/outlines/${id}`),
  delete: (id: number) => request<{ success: boolean }>(`/outlines/${id}`, { method: 'DELETE' }),
  reparse: (id: number) =>
    request<{ success: boolean; chapter_count: number; project_id: number; chapters: ChapterSummary[] }>(
      `/outlines/${id}/reparse`, { method: 'POST' }),
  revisions: (id: number) => request<Revision[]>(`/outlines/${id}/revisions`),
};

// ============================================================
// Projects（作品 / 创作界面）
// ============================================================
export const projectsApi = {
  list: () => request<Project[]>('/projects'),
  get: (id: number) => request<Project>(`/projects/${id}`),
  create: (data: { source_type: 'outline' | 'idea' | 'blank'; outline_id?: number; idea_id?: number; title?: string }) =>
    request<{ success: boolean; project: Project }>('/projects',
      { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Project>) =>
    request<{ success: boolean; project: Project }>(`/projects/${id}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) => request<{ success: boolean }>(`/projects/${id}`, { method: 'DELETE' }),

  listChapters: (id: number) => request<ChapterSummary[]>(`/projects/${id}/chapters`),
  createChapter: (id: number, data: { title?: string; chapter_number?: number; auto_precha?: boolean }) =>
    request<{ success: boolean; chapter: Chapter; precha_from: number | null }>(
      `/projects/${id}/chapters`, { method: 'POST', body: JSON.stringify(data) }),
  reorder: (id: number, order: number[]) =>
    request<{ success: boolean; chapters: ChapterSummary[] }>(`/projects/${id}/reorder`,
      { method: 'PUT', body: JSON.stringify({ order }) }),

  listEntities: (id: number, kind?: string) =>
    request<StoryEntity[]>(`/projects/${id}/entities${kind ? `?kind=${kind}` : ''}`),
  createEntity: (id: number, data: Partial<StoryEntity>) =>
    request<{ success: boolean; entity: StoryEntity }>(`/projects/${id}/entities`,
      { method: 'POST', body: JSON.stringify(data) }),
};

// ============================================================
// Chapters
// ============================================================
export const chaptersApi = {
  get: (id: number) => request<Chapter>(`/chapters/${id}`),
  update: (id: number, data: Partial<Chapter>) =>
    request<{ success: boolean; chapter: Chapter }>(`/chapters/${id}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) => request<{ success: boolean }>(`/chapters/${id}`, { method: 'DELETE' }),

  /** 底部命令行：生成 / 续写 / 重写 */
  command: (
    id: number, op: 'generate' | 'continue' | 'rewrite', instruction: string,
    onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn, onEvent?: EventFn,
  ) => streamRequest(`/chapters/${id}/command`, { op, instruction },
    onChunk, onDone, onError, onEvent),

  regeneratePrecha: (id: number) =>
    request<{ success: boolean; chapter: Chapter; precha_from: number }>(
      `/chapters/${id}/precha/regenerate`, { method: 'POST' }),
  previewContext: (id: number) =>
    request<{ snapshot: Json; system_prompt: string; citations: Json[] }>(
      `/chapters/${id}/context`),
  setEntities: (id: number, links: Array<{ entity_id: number; role: string }>) =>
    request<{ success: boolean }>(`/chapters/${id}/entities`,
      { method: 'PUT', body: JSON.stringify({ links }) }),

  revisions: (id: number) => request<Revision[]>(`/chapters/${id}/revisions`),
  revision: (id: number, versionNo: number) =>
    request<Revision>(`/chapters/${id}/revisions/${versionNo}`),
  revert: (id: number, versionNo: number) =>
    request<{ success: boolean; chapter: Chapter }>(`/chapters/${id}/revert/${versionNo}`,
      { method: 'POST' }),
};

// ============================================================
// Rewrite
// ============================================================
export const rewriteApi = {
  analyze: (text: string) =>
    request<{ success: boolean; analysis: Json }>('/rewrite/analyze',
      { method: 'POST', body: JSON.stringify({ text }) }),
  rewrite: (text: string, instructions: string | null,
            onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/rewrite/rewrite', { text, instructions }, onChunk, onDone, onError),
};

// ============================================================
// Export
// ============================================================
export const exportApi = {
  markdown: (projectId: number, onlyCompleted = true) =>
    request<{ full_text: string; title: string; chapter_count: number; word_count: number; only_completed: boolean }>(
      `/writing/export/${projectId}`,
      { method: 'POST', body: JSON.stringify({ only_completed: onlyCompleted }) }),
  file: async (projectId: number, fmt: 'epub' | 'pdf') => {
    const resp = await fetch(`${BASE}/writing/export/${projectId}/${fmt}`, { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: `导出失败 (HTTP ${resp.status})` }));
      throw new Error(err.error);
    }
    return resp.blob();
  },
};

// ============================================================
// Upload / Libraries
// ============================================================
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
    return resp.json() as Promise<{
      success: boolean; id: number; library_type: string; folder_name: string;
      filename: string; is_new_category: boolean; classify_reason: string;
    }>;
  },
  getLibraries: () => request<{ structure: Record<string, Record<string, string[]>>; files: Json[] }>('/libraries'),
  deleteFile: (id: number) => request<{ success: boolean }>(`/libraries/${id}`, { method: 'DELETE' }),
  summarize: (id: number, force = false) =>
    request<{ success: boolean; summary: string; cached: boolean }>(
      `/libraries/${id}/summarize`, { method: 'POST', body: JSON.stringify({ force }) }),
  getCategories: () => request<Record<string, LibraryCategory[]>>('/categories'),
  createCategory: (data: { library_type: string; name: string; description?: string }) =>
    request<{ success: boolean; category: LibraryCategory }>('/categories',
      { method: 'POST', body: JSON.stringify(data) }),
  updateCategory: (id: number, data: Partial<LibraryCategory>) =>
    request<{ success: boolean; category: LibraryCategory }>(`/categories/${id}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  ragFiles: () => request<Array<{ source: string; filename: string; library_type: string; category: string; chunks: number }>>('/rag/files'),
};

// ============================================================
// Storyboard
// ============================================================
export const storyboardApi = {
  presets: () => request<Json>('/storyboard/presets'),
  generate: (data: Json, onChunk: ChunkFn, onDone: DoneFn, onError: ErrorFn) =>
    streamRequest('/storyboard/generate', data, onChunk, onDone, onError),
};
