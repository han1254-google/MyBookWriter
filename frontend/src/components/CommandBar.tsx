import { useState, useRef, useEffect, useCallback } from 'react';

export interface CommandAction {
  /** 传给后端的 op */
  op: string;
  label: string;
  /** 是否必须填写修改意见 */
  requiresInstruction?: boolean;
  /** 禁用原因，非空则该按钮不可点 */
  disabledReason?: string;
  variant?: 'primary' | 'normal' | 'danger';
}

interface CommandBarProps {
  actions: CommandAction[];
  onRun: (op: string, instruction: string) => void;
  isRunning: boolean;
  onStop?: () => void;
  placeholder?: string;
  /** 运行中显示的一行状态 */
  status?: string;
  /** 右侧附加内容，比如版本历史按钮 */
  extra?: React.ReactNode;
}

/**
 * 底部命令行 —— 取代原来挂在右侧的对话框。
 * 输入修改意见 + 点一个动作按钮（生成 / 续写 / 重写）。
 * Ctrl+Enter 执行第一个可用动作。
 */
export default function CommandBar({
  actions, onRun, isRunning, onStop,
  placeholder = '输入修改意见（可留空）…',
  status, extra,
}: CommandBarProps) {
  const [input, setInput] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  const run = useCallback((action: CommandAction) => {
    if (isRunning || action.disabledReason) return;
    const text = input.trim();
    if (action.requiresInstruction && !text) {
      ref.current?.focus();
      return;
    }
    onRun(action.op, text);
    setInput('');
  }, [input, isRunning, onRun]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        const first = actions.find((a) => !a.disabledReason);
        if (first) { e.preventDefault(); run(first); }
      }
    };
    const el = ref.current;
    el?.addEventListener('keydown', onKey);
    return () => el?.removeEventListener('keydown', onKey);
  }, [actions, run]);

  const styleOf = (a: CommandAction) => {
    if (a.disabledReason) {
      return 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] cursor-not-allowed opacity-60';
    }
    if (a.variant === 'primary') {
      return 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] cursor-pointer';
    }
    if (a.variant === 'danger') {
      return 'bg-[var(--bg-tertiary)] text-[var(--danger)] border border-[var(--border)] hover:border-[var(--danger)] cursor-pointer';
    }
    return 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] hover:border-[var(--accent)] cursor-pointer';
  };

  return (
    <div className="border-t border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-3">
      {(status || isRunning) && (
        <div className="flex items-center gap-2 mb-2 text-xs text-[var(--text-muted)]">
          {isRunning && <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />}
          <span>{status || '正在生成…'}</span>
          {isRunning && onStop && (
            <button
              onClick={onStop}
              className="ml-auto text-[var(--danger)] bg-none border-none cursor-pointer hover:underline"
            >
              停止
            </button>
          )}
        </div>
      )}

      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <textarea
            ref={ref}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder}
            rows={2}
            disabled={isRunning}
            className="w-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-[var(--accent)] disabled:opacity-50 font-mono"
          />
          <div className="text-[10px] text-[var(--text-muted)] mt-1">
            Ctrl+Enter 执行「{actions.find((a) => !a.disabledReason)?.label ?? '—'}」
          </div>
        </div>

        <div className="flex flex-col gap-1.5 pb-5">
          <div className="flex gap-1.5 flex-wrap justify-end">
            {actions.map((a) => (
              <button
                key={a.op}
                onClick={() => run(a)}
                disabled={isRunning || !!a.disabledReason}
                title={a.disabledReason || (a.requiresInstruction ? '需要先填写修改意见' : '')}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium border-none whitespace-nowrap transition-colors ${styleOf(a)}`}
              >
                {a.label}
              </button>
            ))}
          </div>
          {extra}
        </div>
      </div>
    </div>
  );
}
