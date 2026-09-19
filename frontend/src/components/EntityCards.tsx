import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { StoryEntity } from '../api/client';

const ATTR_LABELS: Record<string, string> = {
  role: '身份',
  age: '年龄',
  relation: '关系',
  speech_habit: '说话习惯',
  physical_mark: '外貌标志',
  time: '时间',
  place: '地点',
  society: '社会',
  tech_level: '技术水平',
};

const KIND_ICONS: Record<string, string> = {
  character: '👤',
  worldview: '🌍',
  setting: '⚙️',
  location: '📍',
  item: '📦',
  term: '📖',
  theme: '💭',
};

/** 展示顺序：世界观 → 设定 → 人物 → 其他 */
const KIND_ORDER = ['worldview', 'setting', 'character', 'location', 'item', 'term', 'theme'];

interface EntityCardProps {
  entity: StoryEntity;
  onSave?: (id: number, data: Partial<StoryEntity>) => Promise<void> | void;
  onDelete?: (id: number) => Promise<void> | void;
  /** 显示「首次出场章」输入框（作品内才有意义） */
  showFirstAppear?: boolean;
  onstage?: boolean;
}

export function EntityCard({
  entity, onSave, onDelete, showFirstAppear, onstage,
}: EntityCardProps) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entity);
  const [saving, setSaving] = useState(false);

  const startEdit = () => { setDraft(entity); setEditing(true); setOpen(true); };

  const save = async () => {
    if (!onSave) return;
    setSaving(true);
    try {
      await onSave(entity.id, {
        name: draft.name,
        summary: draft.summary,
        detail: draft.detail,
        attributes: draft.attributes,
        first_appear_chapter: draft.first_appear_chapter,
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const attrs = Object.entries(entity.attributes || {}).filter(([, v]) => v);

  return (
    <div className={`rounded-lg border bg-[var(--bg-secondary)] transition-colors ${
      onstage ? 'border-[var(--accent)]' : 'border-[var(--border)]'
    }`}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 bg-transparent border-none cursor-pointer text-left"
      >
        <span className="text-base shrink-0">{KIND_ICONS[entity.kind] || '•'}</span>
        <span className="font-medium text-sm text-[var(--text-primary)] shrink-0">{entity.name}</span>
        {entity.summary && (
          <span className="text-xs text-[var(--text-secondary)] truncate flex-1">
            {entity.summary}
          </span>
        )}
        {entity.first_appear_chapter != null && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)] shrink-0">
            CHA{entity.first_appear_chapter} 起
          </span>
        )}
        {onstage && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent)]/20 text-[var(--accent)] shrink-0">
            本章在场
          </span>
        )}
        <span className="text-[var(--text-muted)] text-xs shrink-0">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 border-t border-[var(--border)] pt-2.5">
          {editing ? (
            <div className="space-y-2">
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder="名称"
                className="w-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[var(--accent)]"
              />
              <input
                value={draft.summary}
                onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
                placeholder="一行摘要"
                className="w-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[var(--accent)]"
              />
              <textarea
                value={draft.detail}
                onChange={(e) => setDraft({ ...draft, detail: e.target.value })}
                placeholder="完整描述"
                rows={5}
                className="w-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm resize-y focus:outline-none focus:border-[var(--accent)]"
              />
              <div className="grid grid-cols-2 gap-2">
                {Object.keys(ATTR_LABELS).filter((k) =>
                  entity.kind === 'character'
                    ? ['role', 'age', 'relation', 'speech_habit', 'physical_mark'].includes(k)
                    : ['time', 'place', 'society', 'tech_level'].includes(k)
                ).map((k) => (
                  <label key={k} className="text-xs text-[var(--text-muted)]">
                    {ATTR_LABELS[k]}
                    <input
                      value={draft.attributes?.[k] || ''}
                      onChange={(e) => setDraft({
                        ...draft,
                        attributes: { ...draft.attributes, [k]: e.target.value },
                      })}
                      className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs focus:outline-none focus:border-[var(--accent)]"
                    />
                  </label>
                ))}
              </div>
              {showFirstAppear && (
                <label className="block text-xs text-[var(--text-muted)]">
                  首次出场章号（留空 = 贯穿全书。写 CHAn 时只会注入出场章号 ≤ n 的条目，防止叙述越界）
                  <input
                    type="number"
                    min={1}
                    value={draft.first_appear_chapter ?? ''}
                    onChange={(e) => setDraft({
                      ...draft,
                      first_appear_chapter: e.target.value ? Number(e.target.value) : null,
                    })}
                    className="w-24 mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs focus:outline-none focus:border-[var(--accent)]"
                  />
                </label>
              )}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={save}
                  disabled={saving}
                  className="px-3 py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer disabled:opacity-50"
                >
                  {saving ? '保存中…' : '保存'}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border-none rounded text-xs cursor-pointer"
                >
                  取消
                </button>
              </div>
            </div>
          ) : (
            <>
              {attrs.length > 0 && (
                <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
                  {attrs.map(([k, v]) => (
                    <span key={k} className="text-xs text-[var(--text-secondary)]">
                      <span className="text-[var(--text-muted)]">{ATTR_LABELS[k] || k}：</span>{v}
                    </span>
                  ))}
                </div>
              )}
              {entity.detail ? (
                <div className="markdown-body text-sm text-[var(--text-secondary)]">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{entity.detail}</ReactMarkdown>
                </div>
              ) : (
                <p className="text-xs text-[var(--text-muted)] m-0">（没有更详细的描述）</p>
              )}
              {(onSave || onDelete) && (
                <div className="flex gap-3 mt-2.5 pt-2 border-t border-[var(--border)]">
                  {onSave && (
                    <button onClick={startEdit}
                      className="text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
                      编辑
                    </button>
                  )}
                  {onDelete && (
                    <button onClick={() => onDelete(entity.id)}
                      className="text-xs text-[var(--danger)] bg-none border-none cursor-pointer hover:underline">
                      删除
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface EntityGroupsProps {
  entities: StoryEntity[];
  onSave?: (id: number, data: Partial<StoryEntity>) => Promise<void> | void;
  onDelete?: (id: number) => Promise<void> | void;
  onAdd?: (kind: string) => void;
  showFirstAppear?: boolean;
  onstageIds?: number[];
  emptyHint?: string;
}

/** 按类型分组渲染设定条目 */
export default function EntityGroups({
  entities, onSave, onDelete, onAdd, showFirstAppear,
  onstageIds = [], emptyHint = '暂无结构化设定',
}: EntityGroupsProps) {
  const groups = new Map<string, StoryEntity[]>();
  for (const e of entities) {
    if (!groups.has(e.kind)) groups.set(e.kind, []);
    groups.get(e.kind)!.push(e);
  }
  const kinds = KIND_ORDER.filter((k) => groups.has(k))
    .concat([...groups.keys()].filter((k) => !KIND_ORDER.includes(k)));

  const onstage = new Set(onstageIds);

  if (entities.length === 0) {
    return (
      <div className="text-sm text-[var(--text-muted)] py-4">
        <p className="m-0">{emptyHint}</p>
        {onAdd && (
          <div className="flex gap-2 mt-3">
            {(['character', 'worldview', 'setting'] as const).map((k) => (
              <button key={k} onClick={() => onAdd(k)}
                className="px-2.5 py-1 rounded text-xs border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:border-[var(--accent)] cursor-pointer">
                + {KIND_ICONS[k]} {k === 'character' ? '人物' : k === 'worldview' ? '世界观' : '设定'}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {kinds.map((kind) => {
        const items = groups.get(kind)!;
        const label = items[0].kind_label || kind;
        return (
          <div key={kind}>
            <div className="flex items-center gap-2 mb-1.5">
              <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase m-0">
                {KIND_ICONS[kind]} {label} ({items.length})
              </h4>
              {onAdd && (
                <button onClick={() => onAdd(kind)}
                  className="text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
                  + 新增
                </button>
              )}
            </div>
            <div className="space-y-1.5">
              {items.map((e) => (
                <EntityCard
                  key={e.id} entity={e}
                  onSave={onSave} onDelete={onDelete}
                  showFirstAppear={showFirstAppear}
                  onstage={onstage.has(e.id)}
                />
              ))}
            </div>
          </div>
        );
      })}
      {onAdd && kinds.length > 0 && (
        <div className="flex gap-2 pt-1">
          {(['character', 'worldview', 'setting'] as const)
            .filter((k) => !groups.has(k))
            .map((k) => (
              <button key={k} onClick={() => onAdd(k)}
                className="px-2.5 py-1 rounded text-xs border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:border-[var(--accent)] cursor-pointer">
                + {KIND_ICONS[k]} {k === 'character' ? '人物' : k === 'worldview' ? '世界观' : '设定'}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
