import { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { outlinesApi, ideasApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import StreamOutput from '../components/StreamOutput';

export default function OutlinesPage() {
  const { outlines, setOutlines, addToast } = useAppStore();
  const [searchParams] = useSearchParams();
  const [ideas, setIdeas] = useState<Array<Record<string, unknown>>>([]);
  const [mode, setMode] = useState<'idea' | 'scratch'>(searchParams.get('idea_id') ? 'idea' : 'scratch');
  const [selectedIdeaId, setSelectedIdeaId] = useState(searchParams.get('idea_id') || '');
  const [prompt, setPrompt] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [fullText, setFullText] = useState('');

  useEffect(() => {
    outlinesApi.list().then(setOutlines);
    ideasApi.list().then(setIdeas);
  }, [setOutlines]);

  const handleGenerate = () => {
    setIsStreaming(true);
    setStreamingText('');
    setFullText('');

    const body: { idea_id?: number; prompt?: string } = {};
    if (mode === 'idea' && selectedIdeaId) body.idea_id = Number(selectedIdeaId);
    else if (mode === 'scratch' && prompt.trim()) body.prompt = prompt.trim();
    else { setIsStreaming(false); return; }

    outlinesApi.generate(
      body,
      (text) => setStreamingText((prev) => prev + text),
      (data) => { setIsStreaming(false); if (data?.full_text) setFullText(data.full_text as string); },
      (err) => { setIsStreaming(false); addToast(`生成失败: ${err}`, 'error'); },
    );
  };

  const handleSave = async () => {
    const titleMatch = fullText.match(/^#\s*(.+)/m);
    const title = titleMatch ? titleMatch[1].trim() : '未命名大纲';
    try {
      await outlinesApi.save({ idea_id: mode === 'idea' ? Number(selectedIdeaId) : undefined, title, content: fullText });
      addToast('大纲已保存', 'success');
      outlinesApi.list().then(setOutlines);
    } catch (e: unknown) {
      addToast(`保存失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await outlinesApi.delete(id);
      addToast('已删除', 'success');
      outlinesApi.list().then(setOutlines);
    } catch (e: unknown) { addToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">📋 大纲工坊</h1>
      <p className="text-[var(--text-secondary)] mb-6">从创意或直接生成章节规划大纲</p>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-1 space-y-4">
          <div className="flex gap-2">
            <button
              onClick={() => setMode('idea')}
              className={`flex-1 py-2 rounded-lg text-sm border transition-colors ${mode === 'idea' ? 'bg-[var(--accent)] text-white border-[var(--accent)]' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)]'}`}
            >从创意</button>
            <button
              onClick={() => setMode('scratch')}
              className={`flex-1 py-2 rounded-lg text-sm border transition-colors ${mode === 'scratch' ? 'bg-[var(--accent)] text-white border-[var(--accent)]' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)]'}`}
            >从零开始</button>
          </div>

          {mode === 'idea' ? (
            <div>
              <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">选择创意</label>
              <select
                value={selectedIdeaId}
                onChange={(e) => setSelectedIdeaId(e.target.value)}
                className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm"
              >
                <option value="">-- 选择创意 --</option>
                {ideas.map((i: Record<string, unknown>) => (
                  <option key={i.id as number} value={i.id as number}>{i.title as string}</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">场景描述</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={4}
                placeholder="描述你想要的故事框架..."
                className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
          )}

          <button
            onClick={handleGenerate}
            disabled={isStreaming}
            className="w-full py-3 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
          >
            {isStreaming ? '⏳ 生成中...' : '📋 生成大纲'}
          </button>
        </div>

        <div className="col-span-2">
          <StreamOutput text={streamingText} isStreaming={isStreaming} className="min-h-[500px]" emptyImage="/空状态.png" loadingImage="/加载中.png" />
          {fullText && !isStreaming && (
            <button onClick={handleSave} className="mt-4 px-6 py-2 bg-[var(--success)] text-white border-none rounded-lg text-sm font-medium cursor-pointer">
              💾 保存大纲
            </button>
          )}
        </div>
      </div>

      {/* Saved outlines */}
      <div className="mt-10">
        <h2 className="text-lg font-semibold mb-4">已保存的大纲</h2>
        {outlines.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">暂无已保存的大纲</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {outlines.map((o) => (
              <div key={o.id} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)] transition-colors">
                <h3 className="font-semibold mb-2">
                  <Link to={`/outlines/${o.id}`} className="no-underline text-[var(--text-primary)] hover:text-[var(--accent)]">{o.title}</Link>
                </h3>
                <p className="text-xs text-[var(--text-muted)] mb-3">{o.chapter_count} 章 · {new Date(o.updated_at).toLocaleDateString('zh-CN')}</p>
                <div className="flex gap-2">
                  <Link to={`/writing/${o.id}`} className="px-3 py-1.5 bg-[var(--accent)] text-white no-underline rounded text-xs hover:bg-[var(--accent-hover)] transition-colors">✍️ 开始写作</Link>
                  <button onClick={() => handleDelete(o.id)} className="px-3 py-1.5 text-[var(--danger)] border-none bg-transparent cursor-pointer text-xs hover:underline">删除</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
