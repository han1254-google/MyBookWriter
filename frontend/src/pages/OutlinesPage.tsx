import { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { outlinesApi, ideasApi, projectsApi } from '../api/client';
import type { Idea } from '../api/client';
import { useAppStore } from '../store/appStore';
import StreamOutput from '../components/StreamOutput';

interface ParsedChapter {
  chapter_number: number;
  title: string;
  plan_scene: string;
  plan_events: string;
  plan_emotion: string;
  plan_settings: string;
}

interface Parsed {
  title: string;
  synopsis: string;
  themes: string;
  chapters: ParsedChapter[];
  parsed_ok: boolean;
}

export default function OutlinesPage() {
  const { outlines, setOutlines, addToast } = useAppStore();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [mode, setMode] = useState<'idea' | 'scratch'>(searchParams.get('idea_id') ? 'idea' : 'scratch');
  const [selectedIdeaId, setSelectedIdeaId] = useState(searchParams.get('idea_id') || '');
  const [prompt, setPrompt] = useState('');
  const [chapterCount, setChapterCount] = useState<string>('');
  const [structureHint, setStructureHint] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [fullText, setFullText] = useState('');
  const [parsed, setParsed] = useState<Parsed | null>(null);

  useEffect(() => {
    outlinesApi.list().then(setOutlines).catch(() => {});
    ideasApi.list().then(setIdeas).catch(() => {});
  }, [setOutlines]);

  const handleGenerate = () => {
    const body: { idea_id?: number; prompt?: string; chapter_count?: number | null; structure_hint?: string } = {};
    if (mode === 'idea' && selectedIdeaId) body.idea_id = Number(selectedIdeaId);
    else if (mode === 'scratch' && prompt.trim()) body.prompt = prompt.trim();
    else { addToast('请先选择创意或输入场景描述', 'error'); return; }

    if (chapterCount.trim()) body.chapter_count = Number(chapterCount);
    if (structureHint.trim()) body.structure_hint = structureHint.trim();

    setIsStreaming(true);
    setStreamingText('');
    setFullText('');
    setParsed(null);

    outlinesApi.generate(
      body,
      (text) => setStreamingText((p) => p + text),
      (data) => {
        setIsStreaming(false);
        if (data?.full_text) setFullText(data.full_text as string);
        if (data?.parsed) setParsed(data.parsed as unknown as Parsed);
      },
      (err) => { setIsStreaming(false); addToast(`生成失败: ${err}`, 'error'); },
    );
  };

  const handleSave = async () => {
    try {
      const r = await outlinesApi.save({
        idea_id: mode === 'idea' && selectedIdeaId ? Number(selectedIdeaId) : undefined,
        content: fullText,
        parsed: (parsed as unknown as Record<string, unknown>) || undefined,
      });
      addToast(`大纲已保存，解析出 ${r.chapters.length} 个章节`, 'success');
      outlinesApi.list().then(setOutlines);
      navigate(`/outlines/${r.id}`);
    } catch (e) {
      addToast(`保存失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('删除这个大纲？已写好的章节会保留在对应作品里。')) return;
    try {
      await outlinesApi.delete(id);
      addToast('已删除', 'success');
      outlinesApi.list().then(setOutlines);
    } catch (e) { addToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  const startWriting = async (outlineId: number, projectId: number | null) => {
    if (projectId) { navigate(`/projects/${projectId}`); return; }
    try {
      const r = await projectsApi.create({ source_type: 'outline', outline_id: outlineId });
      navigate(`/projects/${r.project.id}`);
    } catch (e) { addToast(`创建作品失败: ${(e as Error).message}`, 'error'); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">📋 大纲工坊</h1>
      <p className="text-[var(--text-secondary)] mb-6">
        章节数由故事需要决定，不套起承转合模板。生成后每章会成为可点开的独立 item
      </p>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-1 space-y-4">
          <div className="flex gap-2">
            {(['idea', 'scratch'] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)}
                className={`flex-1 py-2 rounded-lg text-sm border cursor-pointer transition-colors ${
                  mode === m
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                    : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)]'
                }`}>
                {m === 'idea' ? '从创意' : '从零开始'}
              </button>
            ))}
          </div>

          {mode === 'idea' ? (
            <div>
              <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">选择创意</label>
              <select value={selectedIdeaId} onChange={(e) => setSelectedIdeaId(e.target.value)}
                className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm">
                <option value="">— 选择创意 —</option>
                {ideas.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}
              </select>
              {selectedIdeaId && (
                <p className="text-xs text-[var(--text-muted)] mt-1.5 m-0">
                  创意里已有的人物会写进提示词，大纲不会另起一套人名
                </p>
              )}
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">场景描述</label>
              <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4}
                placeholder="描述你想要的故事框架…"
                className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:border-[var(--accent)]" />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-1.5 text-[var(--text-secondary)]">
              章节数
            </label>
            <input type="number" min={1} max={60} value={chapterCount}
              onChange={(e) => setChapterCount(e.target.value)}
              placeholder="留空 = 由 AI 按故事需要决定"
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--accent)]" />
            <p className="text-xs text-[var(--text-muted)] mt-1 m-0">
              不填的话，短故事可能 5 章、长故事 20 章，不会硬凑
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5 text-[var(--text-secondary)]">
              结构要求（可选）
            </label>
            <textarea value={structureHint} onChange={(e) => setStructureHint(e.target.value)} rows={2}
              placeholder="例如：全篇情绪平缓下沉，不要高潮章；或：用双线交替叙事"
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-[var(--accent)]" />
          </div>

          <button onClick={handleGenerate} disabled={isStreaming}
            className="w-full py-3 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors">
            {isStreaming ? '⏳ 生成中…' : '📋 生成大纲'}
          </button>

          {parsed && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <h3 className="text-sm font-semibold mb-2">
                🧩 解析出 {parsed.chapters.length} 章
                {!parsed.parsed_ok && (
                  <span className="ml-2 text-xs text-[var(--warning)]">未识别到章节标题</span>
                )}
              </h3>
              <div className="space-y-0.5 max-h-[260px] overflow-auto">
                {parsed.chapters.map((c) => (
                  <div key={c.chapter_number} className="text-xs text-[var(--text-secondary)] flex gap-2">
                    <span className="font-mono text-[var(--text-muted)] w-11 shrink-0">CHA{c.chapter_number}</span>
                    <span className="truncate">{c.title}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="col-span-2">
          <StreamOutput text={streamingText} isStreaming={isStreaming} className="min-h-[500px]" emptyImage="/空状态.png" loadingImage="/加载中.png" />
          {fullText && !isStreaming && (
            <button onClick={handleSave}
              className="mt-4 px-6 py-2 bg-[var(--success)] text-white border-none rounded-lg text-sm font-medium cursor-pointer">
              💾 保存大纲（同时创建作品和章节）
            </button>
          )}
        </div>
      </div>

      {/* 已保存的大纲 */}
      <div className="mt-10">
        <h2 className="text-lg font-semibold mb-4">已保存的大纲</h2>
        {outlines.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">暂无已保存的大纲</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {outlines.map((o) => (
              <div key={o.id} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)] transition-colors">
                <h3 className="font-semibold mb-1">
                  <Link to={`/outlines/${o.id}`} className="no-underline text-[var(--text-primary)] hover:text-[var(--accent)]">
                    {o.title}
                  </Link>
                </h3>
                {o.synopsis && (
                  <p className="text-xs text-[var(--text-secondary)] line-clamp-2 mb-2 m-0">{o.synopsis}</p>
                )}
                <p className="text-xs text-[var(--text-muted)] mb-3">
                  {o.chapter_count} 章 · {new Date(o.updated_at).toLocaleDateString('zh-CN')}
                  {o.chapter_count === 0 && (
                    <span className="ml-2 text-[var(--warning)]">章节未解析</span>
                  )}
                </p>
                <div className="flex gap-2">
                  <button onClick={() => startWriting(o.id, o.project_id)}
                    className="px-3 py-1.5 bg-[var(--accent)] text-white border-none rounded text-xs cursor-pointer hover:bg-[var(--accent-hover)] transition-colors">
                    ✍️ 开始创作
                  </button>
                  <Link to={`/outlines/${o.id}`}
                    className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] no-underline border border-[var(--border)] rounded text-xs hover:border-[var(--accent)]">
                    查看章节
                  </Link>
                  <button onClick={() => handleDelete(o.id)}
                    className="ml-auto px-3 py-1.5 text-[var(--danger)] border-none bg-transparent cursor-pointer text-xs hover:underline">
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
