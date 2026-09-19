/**
 * Zustand 全局状态
 *
 * 实体类型统一从 api/client 引入，避免两处定义漂移。
 */
import { create } from 'zustand';
import type { Idea, Outline, Project } from '../api/client';

type ToastType = 'success' | 'error' | 'info';

interface AppState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // RAG
  ragAvailable: boolean;
  ragCategories: string[];
  setRagInfo: (available: boolean, categories: string[]) => void;

  // 缓存的列表
  ideas: Idea[];
  setIdeas: (ideas: Idea[]) => void;

  outlines: Outline[];
  setOutlines: (outlines: Outline[]) => void;

  projects: Project[];
  setProjects: (projects: Project[]) => void;

  libraries: Record<string, Record<string, string[]>>;
  setLibraries: (libs: Record<string, Record<string, string[]>>) => void;

  // Toast
  toasts: Array<{ id: number; message: string; type: ToastType }>;
  addToast: (message: string, type?: ToastType) => void;
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

  projects: [],
  setProjects: (projects) => set({ projects }),

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
