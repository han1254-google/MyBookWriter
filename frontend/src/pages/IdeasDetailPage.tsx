import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ideasApi, entitiesApi, projectsApi } from '../api/client';
import type { Idea, StoryEntity, Revision } from '../api/client';
import { useAppStore } from '../store/appStore';
import CommandBar from '../components/CommandBar';
import EntityGroups from '../components/EntityCards';

/** 可折叠 + 可就地编辑的正文分区 */
function Section({
  title, value, onSave, defaultOpen = true, mono = false,
}: {
  title: string;
  value: string;
  onSave?: (v: string) => Promise<void> | void;
  defaultOpen?: boolean;
  mono?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setDraft(value); }, [value]);

  const save = async () => {
    if (!onSave) return;
    setSaving(true);
    try { await onSave(draft); setEditing(false); }
    finally { setSaving(false); }
  };

  const empty = !value?.trim();

  return (
    <div className="border border-[var(--border)] rounded-xl bg-[var(--bg-secondary)]">
      <div className="flex items-center gap-2 px-4 py-2.5">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 bg-none border-none cursor-pointer text-left flex-1 p-0"
        >
          <span className="text-[var(--text-muted)] text-xs">{open ? '▾' : '▸'}</span>
          <span className="text-sm font-semibold text-[var(--text-primary)]">{title}</span>
          {empty && <span className="text-xs text-[var(--text-muted)]">（空）</span>}
        </button>
        {onSave && open && !editing && (
          <button onClick={() => { setDraft(value); setEditing(true); }}
            className="text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
            编辑
          </button>
        )}
      </div>
      {open && (
        <div className="px-4 pb-3 border-t border-[var(--border)] pt-3">
          {editing ? (
            <>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={8}
                className={`w-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm resize-y focus:outline-none focus:border-[var(--accent)] ${mono ? 'font-mono' : ''}`}
              />
              <div className="flex gap-2 mt-2">
                <button onClick={save} disabled={saving}
                  className="px-3 py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer disabled:opacity-50">
                  {saving ? '保存中…' : '保存'}
                </button>
                <button onClick={() => setEditing(false)}
                  className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border-none rounded text-xs cursor-pointer">
                  取消
                </button>
              </div>
            </>
          ) : empty ? (
            <p className="text-sm text-[var(--text-muted)] m-0">这一节还没有内容</p>
          ) : (
            <div className="markdown-body text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function IdeasDetailPage() {
  const { id } = useParams<{ id: string }>();
  const ideaId = Number(id);
  const navigate = useNavigate();
  const { addToast } = useAppStore();

  const [idea, setIdea] = useState<Idea | null>(null);
  const [entities, setEntities] = useState<StoryEntity[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [showRevisions, setShowRevisions] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [streaming, setStreaming] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await ideasApi.get(ideaId);
      setIdea(data);
      setEntities(data.entities || []);
    } catch {
      navigate('/ideas');
    }
  }, [ideaId, navigate]);

  useEffect(() => { load(); }, [load]);

  const loadRevisions = async () => {
    try { setRevisions(await ideasApi.revisions(ideaId)); } catch { /* 忽略 */ }
  };

  // ---- 分区保存 ----
  const saveField = (field: keyof Idea) => async (v: string) => {
    try {
      const r = await ideasApi.update(ideaId, { [field]: v } as Partial<Idea>);
      setIdea(r.idea);
      addToast('已保存', 'success');
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  const saveRaw = async (v: string) => {
    try {
      const r = await ideasApi.update(ideaId, { content: v });
      setIdea(r.idea);
      setEntities(r.idea.entities || []);
      addToast('正文已保存，结构化已重算', 'success');
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  // ---- 设定条目 ----
  const saveEntity = async (eid: number, data: Partial<StoryEntity>) => {
    try {
      const r = await entitiesApi.update(eid, data);
      setEntities((prev) => prev.map((e) => (e.id === eid ? r.entity : e)));
      addToast('条目已保存', 'success');
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  const deleteEntity = async (eid: number) => {
    if (!confirm('确定删除这个条目？')) return;
    try {
      await entitiesApi.delete(eid);
      setEntities((prev) => prev.filter((e) => e.id !== eid));
      addToast('已删除', 'success');
    } catch (e) { addToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  const addEntity = async (kind: string) => {
    const name = prompt(`新条目的名称（${kind === 'character' ? '人物' : kind === 'worldview' ? '世界观' : '设定'}）`);
    if (!name?.trim()) return;
    try {
      const r = await ideasApi.createEntity(ideaId, { kind, name: name.trim() });
      setEntities((prev) => [...prev, r.entity]);
    } catch (e) { addToast(`新增失败: ${(e as Error).message}`, 'error'); }
  };

  // ---- 重新结构化 ----
  const restructure = async () => {
    setBusy('AI 正在重新拆解设定…');
    try {
      const r = await ideasApi.restructure(ideaId);
      setIdea(r.idea);
      setEntities(r.idea.entities || []);
      addToast(`已重新结构化，拆出 ${r.entity_count} 个条目`, 'success');
    } catch (e) {
      addToast(`结构化失败: ${(e as Error).message}`, 'error');
    } finally { setBusy(''); }
  };

  // ---- 底部命令行 ----
  const runCommand = (_op: string, instruction: string) => {
    if (!instruction.trim()) {
      addToast('请先输入修改意见', 'error');
      return;
    }
    setStreaming('');
    setIsStreaming(true);
    ideasApi.command(
      ideaId, instruction, null,
      (t) => setStreaming((p) => p + t),
      () => {
        setIsStreaming(false);
        setStreaming('');
        addToast('设定已按你的意见重写', 'success');
        load();
        if (showRevisions) loadRevisions();
      },
      (err) => { setIsStreaming(false); addToast(`重写失败: ${err}`, 'error'); },
    );
  };

  const revert = async (versionNo: number) => {
    if (!confirm(`回滚到 v${versionNo}？当前内容会先存成一版，可以再滚回来。`)) return;
    try {
      const r = await ideasApi.revert(ideaId, versionNo);
      setIdea(r.idea);
      setEntities(r.idea.entities || []);
      addToast(`已回滚到 v${versionNo}`, 'success');
      loadRevisions();
    } catch (e) { addToast(`回滚失败: ${(e as Error).message}`, 'error'); }
  };

  const createProject = async () => {
    try {
      const r = await projectsApi.create({ source_type: 'idea', idea_id: ideaId });
      addToast('已创建作品，人物与世界观已复制过去', 'success');
      navigate(`/projects/${r.project.id}`);
    } catch (e) { addToast(`创建失败: ${(e as Error).message}`, 'error'); }
  };

  if (!idea) return <div className="p-6 text-[var(--text-muted)]">加载中…</div>;

  const characters = entities.filter((e) => e.kind === 'character');

  return (
    <div className="flex flex-col h-full">
      {/* 内容区 */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-4">
          <Link to="/ideas" className="text-sm text-[var(--accent)] no-underline hover:underline">
            ← 返回创意列表
          </Link>

          <div>
            <h1 className="text-2xl font-bold mt-2 mb-1">{idea.title}</h1>
            <div className="flex items-center gap-3 text-xs text-[var(--text-muted)] flex-wrap">
              <span>{new Date(idea.updated_at).toLocaleString('zh-CN')}</span>
              <span>·</span>
              <span>{characters.length} 个人物 / {entities.length} 条设定</span>
              {!idea.structured_ok && (
                <span className="px-1.5 py-0.5 rounded bg-[var(--warning)]/20 text-[var(--warning)]">
                  结构化不完整
                </span>
              )}
            </div>
          </div>

          {idea.one_liner && (
            <div className="border-l-2 border-[var(--accent)] pl-3 py-1">
              <p className="text-sm text-[var(--text-secondary)] m-0 italic">{idea.one_liner}</p>
            </div>
          )}

          {/* 操作 */}
          <div className="flex gap-2 flex-wrap">
            <button onClick={createProject}
              className="px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm cursor-pointer hover:bg-[var(--accent-hover)]">
              ✍️ 从此创意开始创作
            </button>
            <button onClick={() => navigate(`/outlines?idea_id=${ideaId}`)}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:border-[var(--accent)]">
              📋 生成大纲
            </button>
            <button onClick={restructure} disabled={!!busy}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:border-[var(--accent)] disabled:opacity-50">
              {busy ? '拆解中…' : '🔄 重新结构化'}
            </button>
            <button onClick={() => setShowRaw((v) => !v)}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:border-[var(--accent)]">
              {showRaw ? '隐藏原文' : '📄 查看原文'}
            </button>
          </div>

          {/* 结构化分区 */}
          <Section title="核心科幻概念" value={idea.core_concept}
                   onSave={saveField('core_concept')} />
          <Section title="世界观" value={idea.worldview}
                   onSave={saveField('worldview')} />

          {/* 人物与设定 */}
          <div className="border border-[var(--border)] rounded-xl bg-[var(--bg-secondary)] px-4 py-3">
            <h3 className="text-sm font-semibold m-0 mb-3">人物与设定</h3>
            <EntityGroups
              entities={entities}
              onSave={saveEntity}
              onDelete={deleteEntity}
              onAdd={addEntity}
              emptyHint="还没有拆出结构化条目。点「重新结构化」让 AI 从正文里抽取人物和世界观。"
            />
          </div>

          <Section title="故事主题" value={idea.themes} onSave={saveField('themes')} />
          <Section title="开篇构想" value={idea.opening} onSave={saveField('opening')} />

          {/* 引用来源 */}
          {idea.sources.length > 0 && (
            <div className="border border-[var(--border)] rounded-xl bg-[var(--bg-secondary)] px-4 py-3">
              <h3 className="text-sm font-semibold m-0 mb-2">
                🔍 生成时检索到的资料（{idea.sources.length} 条）
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {idea.sources.map((s, i) => {
                  const o = s as Record<string, unknown>;
                  return (
                    <span key={i}
                      title={`${o.library_type} / ${o.category} / 相似度 ${o.similarity}`}
                      className="px-2 py-0.5 rounded text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                      {String(o.filename).slice(0, 30)}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* 原文 */}
          {showRaw && (
            <Section title="AI 原始输出（改这里会重算所有结构化字段）"
                     value={idea.content} onSave={saveRaw} mono />
          )}

          {/* 版本历史 */}
          <div className="border border-[var(--border)] rounded-xl bg-[var(--bg-secondary)] px-4 py-3">
            <button
              onClick={() => { setShowRevisions((v) => !v); if (!showRevisions) loadRevisions(); }}
              className="flex items-center gap-2 bg-none border-none cursor-pointer p-0 text-sm font-semibold text-[var(--text-primary)]"
            >
              <span className="text-[var(--text-muted)] text-xs">{showRevisions ? '▾' : '▸'}</span>
              版本历史
            </button>
            {showRevisions && (
              <div className="mt-2 space-y-1">
                {revisions.length === 0 ? (
                  <p className="text-xs text-[var(--text-muted)] m-0">暂无历史版本</p>
                ) : revisions.map((r) => (
                  <div key={r.id} className="flex items-center gap-2 text-xs py-1">
                    <span className="text-[var(--text-muted)] w-10">v{r.version_no}</span>
                    <span className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                      {r.op_label}
                    </span>
                    <span className="text-[var(--text-secondary)] truncate flex-1">
                      {r.instruction || '—'}
                    </span>
                    <span className="text-[var(--text-muted)]">{r.char_count} 字符</span>
                    <button onClick={() => revert(r.version_no)}
                      className="text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
                      回滚
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 流式输出预览 */}
          {isStreaming && (
            <div className="border border-[var(--accent)] rounded-xl bg-[var(--bg-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)] mb-2">AI 正在重写…</div>
              <div className="markdown-body text-sm stream-cursor max-h-[400px] overflow-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streaming}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 底部命令行（取代原右侧对话框） */}
      <CommandBar
        actions={[{ op: 'rewrite', label: '按意见重写', requiresInstruction: true, variant: 'primary' }]}
        onRun={runCommand}
        isRunning={isStreaming}
        placeholder="输入修改意见，例如：把主角的职业改成管线维修工，加强信息素交流的设定…"
        status={busy || undefined}
      />
    </div>
  );
}
