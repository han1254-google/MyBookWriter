import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { outlinesApi, chaptersApi, projectsApi } from '../api/client';
import type { Outline, ChapterSummary, Chapter } from '../api/client';
import { useAppStore } from '../store/appStore';
import CommandBar from '../components/CommandBar';

const PLAN_FIELDS: Array<{ key: keyof Chapter; label: string }> = [
  { key: 'plan_scene', label: '场景' },
  { key: 'plan_events', label: '关键事件' },
  { key: 'plan_emotion', label: '情感弧线' },
  { key: 'plan_settings', label: '需要展现的设定' },
  { key: 'plan_notes', label: '备注' },
];

const PRECHA_FIELDS: Array<{ key: keyof Chapter; label: string }> = [
  { key: 'precha_time', label: '时间' },
  { key: 'precha_place', label: '地点' },
  { key: 'precha_chars', label: '人物' },
  { key: 'precha_cause', label: '起' },
  { key: 'precha_process', label: '经' },
  { key: 'precha_result', label: '结' },
  { key: 'precha_media', label: '媒' },
];

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  planned: { label: '仅计划', cls: 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]' },
  draft: { label: '草稿', cls: 'bg-[var(--warning)]/20 text-[var(--warning)]' },
  completed: { label: '已定稿', cls: 'bg-[var(--success)]/20 text-[var(--success)]' },
};

/**
 * 章节 item —— 折叠时一行，点开显示计划 + PRECHA + 正文状态，全部可就地编辑。
 * 改这里的标题，创作界面看到的也是同一个标题（共用同一行 Chapter 数据）。
 */
function ChapterItem({
  summary, projectId, onChanged, onToast,
}: {
  summary: ChapterSummary;
  projectId: number | null;
  onChanged: () => void;
  onToast: (msg: string, type?: 'success' | 'error' | 'info') => void;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<Chapter | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<Partial<Chapter>>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editTitle, setEditTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(summary.title);

  const expand = async () => {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (detail) return;
    setLoading(true);
    try {
      const d = await chaptersApi.get(summary.id);
      setDetail(d);
      setDraft(d);
    } catch (e) {
      onToast(`加载章节失败: ${(e as Error).message}`, 'error');
    } finally { setLoading(false); }
  };

  const setField = (key: keyof Chapter, v: string) => {
    setDraft((p) => ({ ...p, [key]: v }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload: Partial<Chapter> = {};
      for (const { key } of [...PLAN_FIELDS, ...PRECHA_FIELDS]) {
        if (draft[key] !== undefined) (payload as Record<string, unknown>)[key] = draft[key];
      }
      const r = await chaptersApi.update(summary.id, payload);
      setDetail(r.chapter);
      setDraft(r.chapter);
      setDirty(false);
      onToast('章节已保存', 'success');
      onChanged();
    } catch (e) {
      onToast(`保存失败: ${(e as Error).message}`, 'error');
    } finally { setSaving(false); }
  };

  const saveTitle = async () => {
    const t = titleDraft.trim();
    if (t === summary.title) { setEditTitle(false); return; }
    try {
      const r = await chaptersApi.update(summary.id, { title: t });
      setDetail((p) => (p ? { ...p, title: r.chapter.title } : p));
      setEditTitle(false);
      onToast('章节名已改，创作界面同步生效', 'success');
      onChanged();
    } catch (e) {
      onToast(`改名失败: ${(e as Error).message}`, 'error');
    }
  };

  const remove = async () => {
    const warn = summary.has_content
      ? `CHA${summary.chapter_number} 已经有 ${summary.word_count} 字正文，删除后不可恢复。确定？`
      : `确定删除 CHA${summary.chapter_number}？`;
    if (!confirm(warn)) return;
    try {
      await chaptersApi.delete(summary.id);
      onToast('章节已删除', 'success');
      onChanged();
    } catch (e) { onToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  const st = STATUS_STYLE[summary.status] || STATUS_STYLE.planned;

  return (
    <div className="border border-[var(--border)] rounded-lg bg-[var(--bg-secondary)]">
      {/* 折叠头 */}
      <div className="flex items-center gap-2 px-3 py-2.5">
        <button onClick={expand}
          className="text-[var(--text-muted)] text-xs bg-none border-none cursor-pointer p-0 w-3">
          {open ? '▾' : '▸'}
        </button>
        <span className="text-xs font-mono text-[var(--text-muted)] w-14 shrink-0">
          CHA{summary.chapter_number}
        </span>

        {editTitle ? (
          <input
            autoFocus
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={saveTitle}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveTitle();
              if (e.key === 'Escape') { setTitleDraft(summary.title); setEditTitle(false); }
            }}
            className="flex-1 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--accent)] rounded px-2 py-0.5 text-sm focus:outline-none"
          />
        ) : (
          <button
            onClick={() => { setTitleDraft(summary.title); setEditTitle(true); }}
            title="点击改名"
            className="flex-1 text-left text-sm font-medium text-[var(--text-primary)] bg-none border-none cursor-text hover:text-[var(--accent)] p-0 truncate"
          >
            {summary.title || <span className="text-[var(--text-muted)] italic">未命名</span>}
          </button>
        )}

        <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${st.cls}`}>{st.label}</span>
        {summary.word_count > 0 && (
          <span className="text-xs text-[var(--text-muted)] shrink-0 w-16 text-right">
            {summary.word_count} 字
          </span>
        )}
        {projectId && (
          <Link to={`/projects/${projectId}?chapter=${summary.id}`}
            className="text-xs text-[var(--accent)] no-underline hover:underline shrink-0">
            去写 →
          </Link>
        )}
      </div>

      {/* 展开体 */}
      {open && (
        <div className="px-3 pb-3 border-t border-[var(--border)] pt-3 space-y-3">
          {loading && <p className="text-xs text-[var(--text-muted)] m-0">加载中…</p>}

          {detail && (
            <>
              {/* 大纲计划 */}
              <div>
                <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-1.5 mt-0">
                  大纲计划
                </h4>
                <div className="space-y-1.5">
                  {PLAN_FIELDS.map(({ key, label }) => (
                    <label key={key} className="block">
                      <span className="text-xs text-[var(--text-muted)]">{label}</span>
                      <textarea
                        value={String(draft[key] ?? '')}
                        onChange={(e) => setField(key, e.target.value)}
                        rows={key === 'plan_events' ? 3 : 2}
                        className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1.5 text-xs resize-y focus:outline-none focus:border-[var(--accent)]"
                      />
                    </label>
                  ))}
                </div>
              </div>

              {/* PRECHA */}
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase m-0">
                    PRECHA（上一章摘要）
                  </h4>
                  {detail.precha_auto
                    ? <span className="text-[10px] text-[var(--text-muted)]">自动生成</span>
                    : <span className="text-[10px] text-[var(--warning)]">已手改</span>}
                </div>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <label className="text-xs text-[var(--text-muted)]">
                    prechaName
                    <input value={String(draft.precha_name ?? '')}
                      onChange={(e) => setField('precha_name', e.target.value)}
                      className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs focus:outline-none focus:border-[var(--accent)]" />
                  </label>
                  <label className="text-xs text-[var(--text-muted)]">
                    prechaLink
                    <input value={String(draft.precha_link ?? '')}
                      onChange={(e) => setField('precha_link', e.target.value)}
                      className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs font-mono focus:outline-none focus:border-[var(--accent)]" />
                  </label>
                </div>
                <div className="space-y-1.5">
                  {PRECHA_FIELDS.map(({ key, label }) => (
                    <label key={key} className="flex gap-2 items-start">
                      <span className="text-xs text-[var(--text-muted)] w-8 pt-1.5 shrink-0">{label}</span>
                      <textarea
                        value={String(draft[key] ?? '')}
                        onChange={(e) => setField(key, e.target.value)}
                        rows={['precha_process', 'precha_result'].includes(key as string) ? 3 : 1}
                        className="flex-1 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs resize-y focus:outline-none focus:border-[var(--accent)]"
                      />
                    </label>
                  ))}
                </div>
              </div>

              {/* 正文预览 */}
              <div>
                <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-1.5 mt-0">
                  正文
                </h4>
                {detail.content ? (
                  <div className="text-xs text-[var(--text-secondary)] bg-[var(--bg-tertiary)] rounded p-2 max-h-[160px] overflow-auto whitespace-pre-wrap">
                    {detail.content.slice(0, 900)}
                    {detail.content.length > 900 && '……'}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--text-muted)] m-0">
                    还没有正文。去创作界面写。
                  </p>
                )}
              </div>

              {/* 操作 */}
              <div className="flex gap-2 items-center pt-1">
                <button onClick={save} disabled={!dirty || saving}
                  className="px-3 py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                  {saving ? '保存中…' : dirty ? '保存修改' : '无改动'}
                </button>
                {projectId && (
                  <Link to={`/projects/${projectId}?chapter=${summary.id}`}
                    className="px-3 py-1.5 bg-[var(--accent)] text-white no-underline rounded text-xs">
                    去创作界面写这一章
                  </Link>
                )}
                <button onClick={remove}
                  className="ml-auto text-xs text-[var(--danger)] bg-none border-none cursor-pointer hover:underline">
                  删除本章
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function OutlinesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const outlineId = Number(id);
  const navigate = useNavigate();
  const { addToast } = useAppStore();

  const [outline, setOutline] = useState<Outline | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [streaming, setStreaming] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [busy, setBusy] = useState('');
  const [editHead, setEditHead] = useState(false);
  const [headDraft, setHeadDraft] = useState({ title: '', synopsis: '', themes: '', structure_note: '' });

  const load = useCallback(async () => {
    try {
      const d = await outlinesApi.get(outlineId);
      setOutline(d);
      setChapters(d.chapters || []);
      setHeadDraft({
        title: d.title, synopsis: d.synopsis,
        themes: d.themes, structure_note: d.structure_note,
      });
    } catch {
      navigate('/outlines');
    }
  }, [outlineId, navigate]);

  useEffect(() => { load(); }, [load]);

  const reparse = async () => {
    setBusy('正在从原文重新解析章节…');
    try {
      const r = await outlinesApi.reparse(outlineId);
      setChapters(r.chapters);
      addToast(`已解析出 ${r.chapter_count} 个章节`, 'success');
      load();
    } catch (e) {
      addToast(`解析失败: ${(e as Error).message}`, 'error');
    } finally { setBusy(''); }
  };

  const saveHead = async () => {
    try {
      const r = await outlinesApi.update(outlineId, headDraft);
      setOutline(r.outline);
      setEditHead(false);
      addToast('已保存', 'success');
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  const addChapter = async () => {
    if (!outline?.project_id) {
      addToast('这个大纲还没有关联作品，先点「重新解析章节」', 'error');
      return;
    }
    const title = prompt('新章节的名字');
    if (title === null) return;
    try {
      const r = await projectsApi.createChapter(outline.project_id, {
        title: title.trim(), auto_precha: true,
      });
      addToast(
        r.precha_from
          ? `已新建 CHA${r.chapter.chapter_number}，PRECHA 自动从 CHA${r.precha_from} 抽取`
          : `已新建 CHA${r.chapter.chapter_number}`,
        'success',
      );
      load();
    } catch (e) { addToast(`新建失败: ${(e as Error).message}`, 'error'); }
  };

  const runCommand = (_op: string, instruction: string) => {
    if (!instruction.trim()) { addToast('请先输入修改意见', 'error'); return; }
    setStreaming('');
    setIsStreaming(true);
    outlinesApi.command(
      outlineId, instruction,
      (t) => setStreaming((p) => p + t),
      (data) => {
        setIsStreaming(false);
        setStreaming('');
        addToast(`大纲已重写，解析出 ${data?.chapter_count ?? '?'} 章`, 'success');
        load();
      },
      (err) => { setIsStreaming(false); addToast(`重写失败: ${err}`, 'error'); },
    );
  };

  const startWriting = async () => {
    if (outline?.project_id) { navigate(`/projects/${outline.project_id}`); return; }
    try {
      const r = await projectsApi.create({ source_type: 'outline', outline_id: outlineId });
      navigate(`/projects/${r.project.id}`);
    } catch (e) { addToast(`创建作品失败: ${(e as Error).message}`, 'error'); }
  };

  if (!outline) return <div className="p-6 text-[var(--text-muted)]">加载中…</div>;

  const written = chapters.filter((c) => c.has_content).length;
  const totalWords = chapters.reduce((s, c) => s + c.word_count, 0);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-4">
          <Link to="/outlines" className="text-sm text-[var(--accent)] no-underline hover:underline">
            ← 返回大纲列表
          </Link>

          {editHead ? (
            <div className="space-y-2 border border-[var(--border)] rounded-xl bg-[var(--bg-secondary)] p-4">
              <input value={headDraft.title}
                onChange={(e) => setHeadDraft({ ...headDraft, title: e.target.value })}
                placeholder="大纲标题"
                className="w-full bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-3 py-2 text-lg font-bold focus:outline-none focus:border-[var(--accent)]" />
              {([['synopsis', '故事概要'], ['themes', '核心主题'],
                 ['structure_note', '结构说明（可留空，不强制起承转合）']] as const).map(([k, label]) => (
                <label key={k} className="block text-xs text-[var(--text-muted)]">
                  {label}
                  <textarea value={headDraft[k]} rows={3}
                    onChange={(e) => setHeadDraft({ ...headDraft, [k]: e.target.value })}
                    className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm resize-y focus:outline-none focus:border-[var(--accent)]" />
                </label>
              ))}
              <div className="flex gap-2">
                <button onClick={saveHead}
                  className="px-3 py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer">保存</button>
                <button onClick={() => setEditHead(false)}
                  className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border-none rounded text-xs cursor-pointer">取消</button>
              </div>
            </div>
          ) : (
            <div>
              <div className="flex items-start gap-3">
                <h1 className="text-2xl font-bold mt-2 mb-1 flex-1">{outline.title}</h1>
                <button onClick={() => setEditHead(true)}
                  className="mt-3 text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
                  编辑
                </button>
              </div>
              <div className="flex items-center gap-3 text-xs text-[var(--text-muted)] flex-wrap">
                <span>{new Date(outline.updated_at).toLocaleString('zh-CN')}</span>
                <span>·</span>
                <span>{chapters.length} 章，已写 {written} 章，{totalWords} 字</span>
                {!outline.parsed_ok && chapters.length === 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-[var(--warning)]/20 text-[var(--warning)]">
                    章节未解析
                  </span>
                )}
              </div>
              {outline.synopsis && (
                <div className="mt-3 border-l-2 border-[var(--accent)] pl-3 py-1">
                  <p className="text-sm text-[var(--text-secondary)] m-0">{outline.synopsis}</p>
                </div>
              )}
              {outline.themes && (
                <div className="mt-3 markdown-body text-sm text-[var(--text-secondary)]">
                  <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase">核心主题</h3>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{outline.themes}</ReactMarkdown>
                </div>
              )}
              {outline.structure_note && (
                <div className="mt-2 markdown-body text-sm text-[var(--text-secondary)]">
                  <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase">结构说明</h3>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{outline.structure_note}</ReactMarkdown>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-2 flex-wrap">
            <button onClick={startWriting}
              className="px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm cursor-pointer hover:bg-[var(--accent-hover)]">
              ✍️ 开始创作
            </button>
            <button onClick={addChapter}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:border-[var(--accent)]">
              + 新增章节
            </button>
            <button onClick={reparse} disabled={!!busy}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:border-[var(--accent)] disabled:opacity-50">
              {busy ? '解析中…' : '🔄 从原文重新解析章节'}
            </button>
          </div>

          {/* 章节 item 列表 */}
          <div>
            <h2 className="text-lg font-semibold mb-3">章节规划</h2>
            {chapters.length === 0 ? (
              <div className="border border-dashed border-[var(--border)] rounded-xl p-6 text-center">
                <p className="text-sm text-[var(--text-muted)] m-0">
                  还没有章节 item。点上面「从原文重新解析章节」把大纲正文拆成章节。
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {chapters.map((c) => (
                  <ChapterItem
                    key={c.id}
                    summary={c}
                    projectId={outline.project_id}
                    onChanged={load}
                    onToast={addToast}
                  />
                ))}
              </div>
            )}
          </div>

          {isStreaming && (
            <div className="border border-[var(--accent)] rounded-xl bg-[var(--bg-secondary)] p-4">
              <div className="text-xs text-[var(--text-muted)] mb-2">AI 正在重写大纲…</div>
              <div className="markdown-body text-sm stream-cursor max-h-[400px] overflow-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streaming}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </div>

      <CommandBar
        actions={[{ op: 'rewrite', label: '按意见重写大纲', requiresInstruction: true, variant: 'primary' }]}
        onRun={runCommand}
        isRunning={isStreaming}
        placeholder="输入修改意见，例如：把第 5 章拆成两章；删掉第 8 章的回忆线；结尾不要那么圆满…"
        status={busy || undefined}
      />
    </div>
  );
}
