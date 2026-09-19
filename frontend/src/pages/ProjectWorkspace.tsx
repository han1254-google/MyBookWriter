import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom';
import { projectsApi, chaptersApi, entitiesApi, exportApi } from '../api/client';
import type { Project, Chapter, ChapterSummary, StoryEntity, Revision } from '../api/client';
import { useAppStore } from '../store/appStore';
import CommandBar from '../components/CommandBar';
import EntityGroups from '../components/EntityCards';

const PRECHA_FIELDS: Array<{ key: keyof Chapter; label: string; rows: number }> = [
  { key: 'precha_time', label: '时间', rows: 1 },
  { key: 'precha_place', label: '地点', rows: 1 },
  { key: 'precha_chars', label: '人物', rows: 1 },
  { key: 'precha_cause', label: '起', rows: 2 },
  { key: 'precha_process', label: '经', rows: 3 },
  { key: 'precha_result', label: '结', rows: 2 },
  { key: 'precha_media', label: '媒', rows: 2 },
];

const PLAN_FIELDS: Array<{ key: keyof Chapter; label: string }> = [
  { key: 'plan_scene', label: '场景' },
  { key: 'plan_events', label: '关键事件' },
  { key: 'plan_emotion', label: '情感弧线' },
  { key: 'plan_settings', label: '需要展现的设定' },
  { key: 'plan_notes', label: '备注' },
];

const STATUS_DOT: Record<string, string> = {
  planned: 'bg-[var(--text-muted)]',
  draft: 'bg-[var(--warning)]',
  completed: 'bg-[var(--success)]',
};

type Panel = 'precha' | 'plan' | 'entities' | 'revisions' | 'context' | null;

export default function ProjectWorkspace() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { addToast } = useAppStore();

  const [project, setProject] = useState<Project | null>(null);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [current, setCurrent] = useState<Chapter | null>(null);
  const [entities, setEntities] = useState<StoryEntity[]>([]);
  const [revisions, setRevisions] = useState<Revision[]>([]);

  const [panel, setPanel] = useState<Panel>('precha');
  const [draftContent, setDraftContent] = useState('');
  const [contentDirty, setContentDirty] = useState(false);
  const [precha, setPrecha] = useState<Partial<Chapter>>({});
  const [prechaDirty, setPrechaDirty] = useState(false);
  const [plan, setPlan] = useState<Partial<Chapter>>({});
  const [planDirty, setPlanDirty] = useState(false);

  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState('');
  const [streamText, setStreamText] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  const selectedId = Number(searchParams.get('chapter')) || null;

  // ---- 加载 ----
  const loadProject = useCallback(async () => {
    try {
      const p = await projectsApi.get(projectId);
      setProject(p);
      setChapters(p.chapters || []);
      setEntities(p.entities || []);
      return p;
    } catch {
      addToast('作品不存在', 'error');
      navigate('/projects');
      return null;
    }
  }, [projectId, navigate, addToast]);

  useEffect(() => { loadProject(); }, [loadProject]);

  const loadChapter = useCallback(async (cid: number) => {
    try {
      const c = await chaptersApi.get(cid);
      setCurrent(c);
      setDraftContent(c.content);
      setContentDirty(false);
      setPrecha(c);
      setPrechaDirty(false);
      setPlan(c);
      setPlanDirty(false);
      setStreamText('');
      if (c.entities) setEntities(c.entities);
    } catch (e) {
      addToast(`加载章节失败: ${(e as Error).message}`, 'error');
    }
  }, [addToast]);

  // 选中章节：URL 里指定的，或列表第一个。
  //
  // 依赖里**不能**放 current：loadChapter 每次都 setCurrent 成一个全新的对象，
  // 放进去会让这个 effect 每轮渲染都重跑 → 再加载 → current 又变 → 无限请求。
  // 表现就是同一秒几十次 GET /api/chapters/:id，连接被占满后前端报 failed to fetch。
  useEffect(() => {
    if (selectedId) { loadChapter(selectedId); return; }
    if (chapters.length > 0) {
      setSearchParams({ chapter: String(chapters[0].id) }, { replace: true });
    }
  }, [selectedId, chapters, loadChapter, setSearchParams]);

  const selectChapter = (cid: number) => {
    if (contentDirty && !confirm('当前章节有未保存的正文改动，切换会丢失。继续？')) return;
    setSearchParams({ chapter: String(cid) });
  };

  // ---- 保存 ----
  const saveContent = async () => {
    if (!current) return;
    try {
      const r = await chaptersApi.update(current.id, { content: draftContent });
      setCurrent(r.chapter);
      setContentDirty(false);
      addToast(`已保存，${r.chapter.word_count} 字`, 'success');
      loadProject();
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  const savePrecha = async () => {
    if (!current) return;
    const payload: Record<string, unknown> = { precha_name: precha.precha_name, precha_link: precha.precha_link };
    for (const { key } of PRECHA_FIELDS) payload[key] = precha[key];
    try {
      const r = await chaptersApi.update(current.id, payload as Partial<Chapter>);
      setCurrent(r.chapter);
      setPrecha(r.chapter);
      setPrechaDirty(false);
      addToast('PRECHA 已保存', 'success');
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  const savePlan = async () => {
    if (!current) return;
    const payload: Record<string, unknown> = {};
    for (const { key } of PLAN_FIELDS) payload[key] = plan[key];
    try {
      const r = await chaptersApi.update(current.id, payload as Partial<Chapter>);
      setCurrent(r.chapter);
      setPlan(r.chapter);
      setPlanDirty(false);
      addToast('章节计划已保存', 'success');
      loadProject();
    } catch (e) { addToast(`保存失败: ${(e as Error).message}`, 'error'); }
  };

  const renameChapter = async (cid: number, oldTitle: string) => {
    const t = prompt('章节名', oldTitle);
    if (t === null) return;
    try {
      const r = await chaptersApi.update(cid, { title: t.trim() });
      addToast('章节名已改，大纲页同步生效', 'success');
      if (current?.id === cid) setCurrent(r.chapter);
      loadProject();
    } catch (e) { addToast(`改名失败: ${(e as Error).message}`, 'error'); }
  };

  const setStatusOf = async (s: string) => {
    if (!current) return;
    try {
      const r = await chaptersApi.update(current.id, { status: s });
      setCurrent(r.chapter);
      addToast(s === 'completed' ? '已标记为定稿' : '已标记为草稿', 'success');
      loadProject();
    } catch (e) { addToast(`操作失败: ${(e as Error).message}`, 'error'); }
  };

  // ---- 新建 / 删除章节 ----
  const addChapter = async () => {
    const title = prompt('新章节的名字（可留空）');
    if (title === null) return;
    setStatus('正在从前一章提取 PRECHA…');
    try {
      const r = await projectsApi.createChapter(projectId, {
        title: title.trim(), auto_precha: true,
      });
      addToast(
        r.precha_from
          ? `已新建 CHA${r.chapter.chapter_number}，PRECHA 已自动从 CHA${r.precha_from} 抽取`
          : `已新建 CHA${r.chapter.chapter_number}（首章，无前情）`,
        'success',
      );
      await loadProject();
      setSearchParams({ chapter: String(r.chapter.id) });
    } catch (e) {
      addToast(`新建失败: ${(e as Error).message}`, 'error');
    } finally { setStatus(''); }
  };

  const deleteChapter = async (cid: number, summary: ChapterSummary) => {
    const warn = summary.has_content
      ? `CHA${summary.chapter_number} 有 ${summary.word_count} 字正文，删除不可恢复。确定？`
      : `确定删除 CHA${summary.chapter_number}？`;
    if (!confirm(warn)) return;
    try {
      await chaptersApi.delete(cid);
      addToast('章节已删除', 'success');
      if (current?.id === cid) { setCurrent(null); setSearchParams({}); }
      loadProject();
    } catch (e) { addToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  const regeneratePrecha = async () => {
    if (!current) return;
    setStatus('AI 正在重新提取 PRECHA…');
    try {
      const r = await chaptersApi.regeneratePrecha(current.id);
      setCurrent(r.chapter);
      setPrecha(r.chapter);
      setPrechaDirty(false);
      addToast(`PRECHA 已从 CHA${r.precha_from} 重新提取`, 'success');
    } catch (e) {
      addToast(`提取失败: ${(e as Error).message}`, 'error');
    } finally { setStatus(''); }
  };

  // ---- 命令行 ----
  const runCommand = (op: string, instruction: string) => {
    if (!current) { addToast('请先选择或新建一个章节', 'error'); return; }
    if (contentDirty && !confirm('正文有未保存的改动，AI 生成会覆盖。继续？')) return;

    setIsRunning(true);
    setStreamText('');
    setStatus(op === 'continue' ? '正在续写…' : op === 'rewrite' ? '正在重写…' : '正在生成本章…');

    abortRef.current = chaptersApi.command(
      current.id, op as 'generate' | 'continue' | 'rewrite', instruction,
      (t) => setStreamText((p) => p + t),
      (data) => {
        setIsRunning(false);
        setStatus('');
        const ch = data?.chapter as Chapter | undefined;
        if (ch) {
          setCurrent(ch);
          setDraftContent(ch.content);
          setContentDirty(false);
        }
        setStreamText('');
        const audit = data?.audit as { ok: boolean; issues: string[] } | undefined;
        if (audit && !audit.ok) {
          addToast(`注意：叙述范围自检发现 ${audit.issues.length} 个问题`, 'error');
        } else {
          addToast(op === 'continue' ? '续写完成' : op === 'rewrite' ? '重写完成' : '生成完成', 'success');
        }
        loadProject();
        if (panel === 'revisions') loadRevisions();
      },
      (err) => {
        setIsRunning(false);
        setStatus('');
        addToast(`失败: ${err}`, 'error');
      },
      (type, data) => {
        if (type === 'context') {
          const s = data.snapshot as Record<string, unknown>;
          const hidden = Number(s?.hidden_future_entities ?? 0);
          setStatus(
            `已注入 ${s?.entity_count ?? 0} 条设定`
            + (hidden ? `（屏蔽 ${hidden} 条未来才出场的）` : '')
            + `，章节计划给到 CHA${s?.plan_upto}，检索命中 ${s?.rag_hits ?? 0} 条`,
          );
        }
      },
    );
  };

  const stopCommand = () => {
    abortRef.current?.abort();
    setIsRunning(false);
    setStatus('');
    addToast('已停止', 'info');
  };

  // ---- 版本 ----
  const loadRevisions = useCallback(async () => {
    if (!current) return;
    try { setRevisions(await chaptersApi.revisions(current.id)); } catch { /* 忽略 */ }
  }, [current]);

  useEffect(() => { if (panel === 'revisions') loadRevisions(); }, [panel, loadRevisions]);

  const revert = async (versionNo: number) => {
    if (!current) return;
    if (!confirm(`回滚到 v${versionNo}？当前正文会先存成一版，可以再滚回来。`)) return;
    try {
      const r = await chaptersApi.revert(current.id, versionNo);
      setCurrent(r.chapter);
      setDraftContent(r.chapter.content);
      setContentDirty(false);
      addToast(`已回滚到 v${versionNo}`, 'success');
      loadRevisions();
      loadProject();
    } catch (e) { addToast(`回滚失败: ${(e as Error).message}`, 'error'); }
  };

  // ---- 设定 ----
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
    } catch (e) { addToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  const addEntity = async (kind: string) => {
    const name = prompt(`新条目的名称（${kind === 'character' ? '人物' : kind === 'worldview' ? '世界观' : '设定'}）`);
    if (!name?.trim()) return;
    try {
      const r = await projectsApi.createEntity(projectId, { kind, name: name.trim() });
      setEntities((prev) => [...prev, r.entity]);
    } catch (e) { addToast(`新增失败: ${(e as Error).message}`, 'error'); }
  };

  // ---- 导出 ----
  const exportFile = async (fmt: 'epub' | 'pdf') => {
    setStatus(`正在导出 ${fmt.toUpperCase()}…`);
    try {
      const blob = await exportApi.file(projectId, fmt);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${project?.title || 'book'}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
      addToast(`${fmt.toUpperCase()} 导出完成`, 'success');
    } catch (e) {
      addToast(`导出失败: ${(e as Error).message}`, 'error');
    } finally { setStatus(''); }
  };

  if (!project) return <div className="p-6 text-[var(--text-muted)]">加载中…</div>;

  const hasContent = !!(current?.content || '').trim();
  const actions = [
    hasContent
      ? { op: 'continue', label: '续写', variant: 'primary' as const }
      : { op: 'generate', label: '生成本章', variant: 'primary' as const },
    {
      op: 'rewrite', label: '重写',
      disabledReason: hasContent ? undefined : '本章还没有正文',
    },
  ];

  return (
    <div className="flex h-full">
      {/* 左：章节 item 列表 */}
      <aside className="w-64 shrink-0 border-r border-[var(--border)] flex flex-col bg-[var(--bg-secondary)]">
        <div className="p-3 border-b border-[var(--border)]">
          <Link to="/projects" className="text-xs text-[var(--accent)] no-underline hover:underline">
            ← 作品列表
          </Link>
          <h2 className="text-sm font-bold mt-1.5 mb-0.5 truncate" title={project.title}>
            {project.title}
          </h2>
          <p className="text-[11px] text-[var(--text-muted)] m-0">
            {project.chapter_count} 章 · {project.word_count} 字 · 定稿 {project.completed_count}
          </p>
        </div>

        <div className="flex-1 overflow-auto py-1">
          {chapters.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] px-3 py-4 m-0">
              还没有章节。点下面「新建章节」开始。
            </p>
          ) : chapters.map((c) => (
            <div key={c.id}
              className={`group flex items-center gap-1.5 px-2.5 py-2 cursor-pointer transition-colors ${
                c.id === current?.id
                  ? 'bg-[var(--accent)]/15 border-l-2 border-[var(--accent)]'
                  : 'border-l-2 border-transparent hover:bg-[var(--bg-tertiary)]'
              }`}
              onClick={() => selectChapter(c.id)}
            >
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[c.status] || ''}`} />
              <span className="text-[11px] font-mono text-[var(--text-muted)] shrink-0 w-11">
                CHA{c.chapter_number}
              </span>
              <span className={`text-xs truncate flex-1 ${
                c.id === current?.id ? 'text-[var(--accent)]' : 'text-[var(--text-secondary)]'
              }`}>
                {c.title || <span className="italic text-[var(--text-muted)]">未命名</span>}
              </span>
              {c.word_count > 0 && (
                <span className="text-[10px] text-[var(--text-muted)] shrink-0">
                  {(c.word_count / 1000).toFixed(1)}k
                </span>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); renameChapter(c.id, c.title); }}
                title="改名"
                className="opacity-0 group-hover:opacity-100 text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] bg-none border-none cursor-pointer px-0.5 shrink-0"
              >✎</button>
              <button
                onClick={(e) => { e.stopPropagation(); deleteChapter(c.id, c); }}
                title="删除"
                className="opacity-0 group-hover:opacity-100 text-[10px] text-[var(--text-muted)] hover:text-[var(--danger)] bg-none border-none cursor-pointer px-0.5 shrink-0"
              >🗑</button>
            </div>
          ))}
        </div>

        <div className="p-2.5 border-t border-[var(--border)] space-y-1.5">
          <button onClick={addChapter}
            className="w-full py-2 bg-[var(--accent)] text-white border-none rounded-lg text-xs font-medium cursor-pointer hover:bg-[var(--accent-hover)]">
            + 新建章节
          </button>
          <div className="flex gap-1.5">
            <button onClick={() => exportFile('epub')}
              className="flex-1 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border)] rounded text-[11px] cursor-pointer hover:border-[var(--accent)]">
              EPUB
            </button>
            <button onClick={() => exportFile('pdf')}
              className="flex-1 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border)] rounded text-[11px] cursor-pointer hover:border-[var(--accent)]">
              PDF
            </button>
          </div>
        </div>
      </aside>

      {/* 中：正文 + 侧栏面板 */}
      <div className="flex-1 flex flex-col min-w-0">
        {!current ? (
          <div className="flex-1 flex flex-col items-center justify-center text-[var(--text-muted)]">
            <img src="/空状态.png" alt="" className="w-40 h-40 object-contain mb-4 opacity-70" />
            <p className="text-sm">
              {chapters.length === 0 ? '先新建一个章节' : '从左侧选一个章节'}
            </p>
          </div>
        ) : (
          <>
            {/* 章节头 */}
            <div className="border-b border-[var(--border)] px-5 py-3 flex items-center gap-3 flex-wrap">
              <span className="text-xs font-mono text-[var(--text-muted)]">{current.label}</span>
              <button onClick={() => renameChapter(current.id, current.title)}
                className="text-lg font-bold text-[var(--text-primary)] bg-none border-none cursor-text hover:text-[var(--accent)] p-0"
                title="点击改名（大纲页同步生效）">
                {current.title || <span className="italic text-[var(--text-muted)]">未命名</span>}
              </button>
              <span className="text-xs text-[var(--text-muted)]">
                {current.word_count} 字
              </span>
              {current.audit && !current.audit.ok && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--danger)]/20 text-[var(--danger)]"
                  title={current.audit.issues.join('\n')}>
                  叙述范围有 {current.audit.issues.length} 个问题
                </span>
              )}

              <div className="ml-auto flex gap-1.5">
                {(['precha', 'plan', 'entities', 'revisions'] as const).map((p) => (
                  <button key={p}
                    onClick={() => setPanel(panel === p ? null : p)}
                    className={`px-2.5 py-1 rounded text-xs border cursor-pointer transition-colors ${
                      panel === p
                        ? 'bg-[var(--accent)]/15 text-[var(--accent)] border-[var(--accent)]'
                        : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border-[var(--border)] hover:border-[var(--accent)]'
                    }`}>
                    {p === 'precha' ? 'PRECHA' : p === 'plan' ? '章节计划'
                      : p === 'entities' ? `设定 ${entities.length}` : '版本'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 flex min-h-0">
              {/* 正文编辑区 */}
              <div className="flex-1 flex flex-col min-w-0">
                {isRunning && streamText ? (
                  <div className="flex-1 overflow-auto p-5">
                    <div className="text-xs text-[var(--text-muted)] mb-2">
                      AI 正在写…（完成后会写入正文）
                    </div>
                    <div className="whitespace-pre-wrap text-[15px] leading-8 text-[var(--text-secondary)] stream-cursor font-serif">
                      {streamText}
                    </div>
                  </div>
                ) : (
                  <textarea
                    ref={editorRef}
                    value={draftContent}
                    onChange={(e) => { setDraftContent(e.target.value); setContentDirty(true); }}
                    placeholder="在这里手写正文，或用下面的命令行让 AI 生成。&#10;&#10;两种方式可以混用：先手写一段开头定调，再让 AI 续写。"
                    className="flex-1 w-full bg-transparent text-[var(--text-primary)] border-none px-5 py-4 text-[15px] leading-8 resize-none focus:outline-none font-serif"
                  />
                )}

                <div className="border-t border-[var(--border)] px-5 py-2 flex items-center gap-3">
                  <button onClick={saveContent} disabled={!contentDirty}
                    className="px-3 py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                    {contentDirty ? '保存正文' : '已保存'}
                  </button>
                  {current.status !== 'completed' ? (
                    <button onClick={() => setStatusOf('completed')} disabled={!hasContent}
                      className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded text-xs cursor-pointer hover:border-[var(--success)] disabled:opacity-40">
                      标记定稿
                    </button>
                  ) : (
                    <button onClick={() => setStatusOf('draft')}
                      className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border)] rounded text-xs cursor-pointer">
                      取消定稿
                    </button>
                  )}
                  <span className="ml-auto text-xs text-[var(--text-muted)]">
                    {draftContent.length} 字符
                    {contentDirty && <span className="text-[var(--warning)]"> · 未保存</span>}
                  </span>
                </div>
              </div>

              {/* 右侧面板（不是对话框，是数据面板） */}
              {panel && (
                <aside className="w-80 shrink-0 border-l border-[var(--border)] overflow-auto bg-[var(--bg-secondary)] p-3">
                  {panel === 'precha' && (
                    <>
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="text-sm font-semibold m-0">PRECHA</h3>
                        {current.precha_auto
                          ? <span className="text-[10px] text-[var(--text-muted)]">自动</span>
                          : <span className="text-[10px] text-[var(--warning)]">已手改</span>}
                        <button onClick={regeneratePrecha}
                          className="ml-auto text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
                          重新提取
                        </button>
                      </div>
                      <p className="text-[11px] text-[var(--text-muted)] mt-0 mb-2">
                        上一章的压缩摘要。写本章时只给 AI 看这个，不给它看后面的章节。
                      </p>
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        {(['precha_name', 'precha_link'] as const).map((k) => (
                          <label key={k} className="text-[11px] text-[var(--text-muted)]">
                            {k === 'precha_name' ? 'prechaName' : 'prechaLink'}
                            <input value={String(precha[k] ?? '')}
                              onChange={(e) => { setPrecha({ ...precha, [k]: e.target.value }); setPrechaDirty(true); }}
                              className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs font-mono focus:outline-none focus:border-[var(--accent)]" />
                          </label>
                        ))}
                      </div>
                      <div className="space-y-1.5">
                        {PRECHA_FIELDS.map(({ key, label, rows }) => (
                          <label key={key} className="flex gap-2 items-start">
                            <span className="text-[11px] text-[var(--text-muted)] w-7 pt-1.5 shrink-0">{label}</span>
                            <textarea
                              value={String(precha[key] ?? '')}
                              onChange={(e) => { setPrecha({ ...precha, [key]: e.target.value }); setPrechaDirty(true); }}
                              rows={rows}
                              className="flex-1 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs resize-y focus:outline-none focus:border-[var(--accent)]"
                            />
                          </label>
                        ))}
                      </div>
                      <button onClick={savePrecha} disabled={!prechaDirty}
                        className="mt-2 w-full py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                        {prechaDirty ? '保存 PRECHA' : '已保存'}
                      </button>
                    </>
                  )}

                  {panel === 'plan' && (
                    <>
                      <h3 className="text-sm font-semibold m-0 mb-2">章节计划</h3>
                      <p className="text-[11px] text-[var(--text-muted)] mt-0 mb-2">
                        来自大纲。改这里，大纲页也会更新。
                      </p>
                      <div className="space-y-2">
                        {PLAN_FIELDS.map(({ key, label }) => (
                          <label key={key} className="block">
                            <span className="text-[11px] text-[var(--text-muted)]">{label}</span>
                            <textarea
                              value={String(plan[key] ?? '')}
                              onChange={(e) => { setPlan({ ...plan, [key]: e.target.value }); setPlanDirty(true); }}
                              rows={key === 'plan_events' ? 4 : 2}
                              className="w-full mt-0.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1.5 text-xs resize-y focus:outline-none focus:border-[var(--accent)]"
                            />
                          </label>
                        ))}
                      </div>
                      <button onClick={savePlan} disabled={!planDirty}
                        className="mt-2 w-full py-1.5 bg-[var(--success)] text-white border-none rounded text-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                        {planDirty ? '保存计划' : '已保存'}
                      </button>
                    </>
                  )}

                  {panel === 'entities' && (
                    <>
                      <h3 className="text-sm font-semibold m-0 mb-1">人物与设定</h3>
                      <p className="text-[11px] text-[var(--text-muted)] mt-0 mb-3">
                        来自创意的结构化数据。设了「首次出场章」的条目，
                        只会在到达那一章之后才进入 AI 的视野。
                      </p>
                      <EntityGroups
                        entities={entities}
                        onSave={saveEntity}
                        onDelete={deleteEntity}
                        onAdd={addEntity}
                        showFirstAppear
                        onstageIds={current.onstage_entity_ids}
                        emptyHint="这个作品还没有人物和世界观设定。"
                      />
                    </>
                  )}

                  {panel === 'revisions' && (
                    <>
                      <h3 className="text-sm font-semibold m-0 mb-1">版本历史</h3>
                      <p className="text-[11px] text-[var(--text-muted)] mt-0 mb-3">
                        每次生成/续写/重写/手动保存都会存一版，重写踩雷可以滚回来。
                      </p>
                      {revisions.length === 0 ? (
                        <p className="text-xs text-[var(--text-muted)]">暂无历史版本</p>
                      ) : (
                        <div className="space-y-1.5">
                          {revisions.map((r) => (
                            <div key={r.id} className="border border-[var(--border)] rounded p-2 bg-[var(--bg-tertiary)]">
                              <div className="flex items-center gap-2 mb-0.5">
                                <span className="text-xs font-mono text-[var(--text-muted)]">v{r.version_no}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
                                  {r.op_label}
                                </span>
                                <span className="text-[10px] text-[var(--text-muted)] ml-auto">
                                  {r.char_count} 字符
                                </span>
                              </div>
                              {r.instruction && (
                                <p className="text-[11px] text-[var(--text-secondary)] m-0 mb-1 line-clamp-2">
                                  {r.instruction}
                                </p>
                              )}
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] text-[var(--text-muted)]">
                                  {new Date(r.created_at).toLocaleString('zh-CN')}
                                </span>
                                <button onClick={() => revert(r.version_no)}
                                  className="ml-auto text-[11px] text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">
                                  回滚到这一版
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </aside>
              )}
            </div>
          </>
        )}

        {/* 底部命令行 */}
        <CommandBar
          actions={actions}
          onRun={runCommand}
          isRunning={isRunning}
          onStop={stopCommand}
          status={status || undefined}
          placeholder={
            hasContent
              ? '留空直接续写；或写修改意见后点「重写」，例如：把老贺的对白削掉一半，结尾落在示波器的读数上'
              : '留空直接按计划生成；也可以写额外要求，例如：开头从雨声写起，不要出现回忆'
          }
        />
      </div>
    </div>
  );
}
