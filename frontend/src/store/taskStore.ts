/**
 * 章节生成任务 store —— 解决「切页面丢任务」。
 *
 * 任务状态原本是 ProjectWorkspace 的组件 state：一离开页面组件就卸载，
 * 流式回调全打在一个死掉的组件上，界面上看起来任务凭空消失了；
 * 更糟的是用户回来看到旧正文、以为生成失败了，动手一编辑再保存，
 * 刚生成好的内容就被旧稿覆盖。
 *
 * 现在任务活在全局 store 里，按章节 id 存放：
 *   - 切页不中断：流继续跑，后端照常把结果写进数据库
 *   - 完成/失败走全局 toast，人在哪个页面都能收到通知
 *   - 回到该章自动接上：还在跑就接着看流，跑完了就刷新正文
 *   - 正在跑的那一章正文编辑区被流式面板占住，杜绝「旧稿覆盖新稿」
 */
import { create } from 'zustand';
import { chaptersApi } from '../api/client';
import { useAppStore } from './appStore';

export type TaskOp = 'generate' | 'continue' | 'rewrite';
export type TaskStatus = 'running' | 'done' | 'error' | 'stopped';

export interface ChapterTask {
  chapterId: number;
  op: TaskOp;
  instruction: string;
  status: TaskStatus;
  /** 已流出的正文（跨页面存活） */
  text: string;
  /** 上下文注入那行状态（「已注入 N 条设定…」） */
  statusLine: string;
  error?: string;
  controller: AbortController | null;
  startedAt: number;
}

interface TaskState {
  tasks: Record<number, ChapterTask>;
  startCommand: (chapterId: number, op: TaskOp, instruction: string) => void;
  stopCommand: (chapterId: number) => void;
  clearTask: (chapterId: number) => void;
}

const toast = (msg: string, type: 'success' | 'error' | 'info' = 'info') =>
  useAppStore.getState().addToast(msg, type);

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: {},

  startCommand: (chapterId, op, instruction) => {
    const existing = get().tasks[chapterId];
    if (existing?.status === 'running') {
      toast('这一章已经有任务在跑，等它结束再发起新的', 'info');
      return;
    }

    const label = op === 'continue' ? '续写' : op === 'rewrite' ? '重写' : '生成';
    const task: ChapterTask = {
      chapterId, op, instruction,
      status: 'running',
      text: '',
      statusLine: `正在${label}…`,
      controller: null,
      startedAt: Date.now(),
    };
    set((s) => ({ tasks: { ...s.tasks, [chapterId]: task } }));

    const patch = (p: Partial<ChapterTask>) =>
      set((s) => {
        const t = s.tasks[chapterId];
        if (!t) return s;
        return { tasks: { ...s.tasks, [chapterId]: { ...t, ...p } } };
      });

    const controller = chaptersApi.command(
      chapterId, op, instruction,
      (chunk) => patch({ text: (get().tasks[chapterId]?.text ?? '') + chunk }),
      (data) => {
        patch({ status: 'done', controller: null, statusLine: '' });
        const audit = data?.audit as { ok: boolean; issues: string[] } | undefined;
        if (audit && !audit.ok) {
          toast(`${label}完成，但叙述范围自检发现 ${audit.issues.length} 个问题`, 'error');
        } else {
          toast(`${label}完成，结果已写入正文`, 'success');
        }
      },
      (err) => {
        patch({ status: 'error', error: err, controller: null, statusLine: '' });
        toast(`失败: ${err}`, 'error');
      },
      (type, data) => {
        if (type === 'context') {
          const s = data.snapshot as Record<string, unknown>;
          const hidden = Number(s?.hidden_future_entities ?? 0);
          patch({
            statusLine:
              `已注入 ${s?.entity_count ?? 0} 条设定`
              + (hidden ? `（屏蔽 ${hidden} 条未来才出场的）` : '')
              + `，章节计划给到 CHA${s?.plan_upto}，检索命中 ${s?.rag_hits ?? 0} 条`,
          });
        }
      },
    );
    patch({ controller });
  },

  stopCommand: (chapterId) => {
    const t = get().tasks[chapterId];
    if (!t || t.status !== 'running') return;
    t.controller?.abort();
    set((s) => ({
      tasks: { ...s.tasks, [chapterId]: { ...t, status: 'stopped', controller: null } },
    }));
    toast('已停止', 'info');
  },

  clearTask: (chapterId) => {
    set((s) => {
      if (!s.tasks[chapterId]) return s;
      const next = { ...s.tasks };
      delete next[chapterId];
      return { tasks: next };
    });
  },
}));
