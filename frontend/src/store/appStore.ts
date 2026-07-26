/**
 * Zustand 全局状态
 */
import { create } from 'zustand';

interface Idea {
  id: number;
  title: string;
  content: string;
  chat_history: string;
  created_at: string;
  updated_at: string;
}

interface Outline {
  id: number;
  idea_id: number | null;
  title: string;
  content: string;
  chapter_count: number;
  created_at: string;
  updated_at: string;
}

interface Chapter {
  id: number;
  outline_id: number;
  chapter_number: number;
  title: string;
  content: string;
  status: string;
  precha_name: string;
  precha_link: string;
  precha_content: string;
}

interface AppState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // RAG
  ragAvailable: boolean;
  ragCategories: string[];
  setRagInfo: (available: boolean, categories: string[]) => void;

  // Ideas
  ideas: Idea[];
  setIdeas: (ideas: Idea[]) => void;

  // Outlines
  outlines: Outline[];
  setOutlines: (outlines: Outline[]) => void;

  // Library
  libraries: Record<string, Record<string, string[]>>;
  setLibraries: (libs: Record<string, Record<string, string[]>>) => void;

  // Toast
  toasts: Array<{ id: number; message: string; type: 'success' | 'error' | 'info' }>;
  addToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  removeToast: (id: number) => void;
}

let toastId = 0;

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  ragAvailable: false,
  ragCategories: [],
  setRagInfo: (available, categories) => set({ ragAvailable: available, ragCategories: categories }),

  ideas: [],
  setIdeas: (ideas) => set({ ideas }),

  outlines: [],
  setOutlines: (outlines) => set({ outlines }),

  libraries: {},
  setLibraries: (libraries) => set({ libraries }),

  toasts: [],
  addToast: (message, type = 'info') => {
    const id = ++toastId;
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
