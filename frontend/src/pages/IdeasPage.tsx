import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ideasApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import StreamOutput from '../components/StreamOutput';

export default function IdeasPage() {
  const { ideas, setIdeas, ragCategories, addToast } = useAppStore();
  const [prompt, setPrompt] = useState('');
  const [category, setCategory] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [fullText, setFullText] = useState('');
  const [ragResults, setRagResults] = useState<Record<string, Array<Record<string, unknown>>>>({ knowledge: [], reference: [], style: [] });
  const [showDone, setShowDone] = useState(false);
  const [customTags, setCustomTags] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('idea_prompt_tags') || '[]'); } catch { return []; }
  });
  const [newTag, setNewTag] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const DEFAULT_TAGS = [
    '尽量少使用破折号',
    '加强自嘲式幽默',
    '用具体数字代替形容词',
    '第一人称观察者视角',
    '结尾落在具体画面或动作上',
    '加入真实品牌和地名',
  ];

  useEffect(() => {
    ideasApi.list().then(setIdeas).catch(() => {});
  }, [setIdeas]);

  const handleGenerate = () => {
    if (!prompt.trim() || isStreaming) return;
    setStreamingText('');
    setFullText('');
    setRagResults({ knowledge: [], reference: [], style: [] });
    setIsStreaming(true);

    abortRef.current = ideasApi.generate(
      prompt.trim(),
      category || null,
      (text) => setStreamingText((prev) => prev + text),
      (data) => {
        setIsStreaming(false);
        if (data?.full_text) setFullText(data.full_text as string);
        if (data?.rag_results) setRagResults(data.rag_results as Record<string, Array<Record<string, unknown>>>);
        setShowDone(true);
        setTimeout(() => setShowDone(false), 5000);
      },
      (err) => { setIsStreaming(false); addToast(`生成失败: ${err}`, 'error'); },
    );
  };

  const handleSave = async () => {
    const titleMatch = fullText.match(/##\s*设定标题\s*\n(.+)/) || fullText.match(/^#\s*(.+)/m);
    const title = titleMatch ? titleMatch[1].trim() : '未命名创意';
    try {
      await ideasApi.save({ title, content: fullText, knowledge_context: JSON.stringify(ragResults) });
      addToast('创意已保存', 'success');
      ideasApi.list().then(setIdeas);
    } catch (e: unknown) {
      addToast(`保存失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await ideasApi.delete(id);
      addToast('已删除', 'success');
      ideasApi.list().then(setIdeas);
    } catch (e: unknown) {
      addToast(`删除失败: ${(e as Error).message}`, 'error');
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">💡 创意工坊</h1>
      <p className="text-[var(--text-secondary)] mb-6">RAG 知识库检索 + DeepSeek AI 辅助科幻创意生成</p>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Controls */}
        <div className="col-span-1 space-y-4">
          {/* Predefined prompt tags */}
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">预定义提示词（点击追加到输入框）</label>
            <div className="flex flex-wrap gap-1.5 max-h-[120px] overflow-auto">
              {[...DEFAULT_TAGS, ...customTags].map((tag) => (
                <button
                  key={tag}
                  onClick={() => setPrompt((p) => (p ? p + '；' + tag : tag))}
                  className="px-2 py-1 rounded text-xs border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] cursor-pointer transition-colors"
                >+ {tag}</button>
              ))}
            </div>
            {/* Add custom tag */}
            <div className="flex gap-1 mt-2">
              <input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newTag.trim()) {
                    const tag = newTag.trim();
                    const updated = [...customTags, tag];
                    setCustomTags(updated);
                    localStorage.setItem('idea_prompt_tags', JSON.stringify(updated));
                    setNewTag('');
                  }
                }}
                placeholder="自定义提示词..."
                className="flex-1 bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs focus:outline-none focus:border-[var(--accent)]"
              />
              {customTags.length > 0 && (
                <button
                  onClick={() => { setCustomTags([]); localStorage.removeItem('idea_prompt_tags'); }}
                  className="px-2 py-1 text-xs text-[var(--text-muted)] hover:text-[var(--danger)] bg-none border-none cursor-pointer"
                  title="清除自定义"
                >清除自定义</button>
              )}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">写作提示</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              placeholder="描述你想要的科幻创意，例如：潮汐锁定星球上的原住民如何发展文明？"
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">知识库分类过滤（可选）</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="">全部知识库</option>
              {ragCategories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <button
            onClick={handleGenerate}
            disabled={isStreaming || !prompt.trim()}
            className="w-full py-3 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isStreaming ? '⏳ 生成中...' : '🚀 生成创意'}
          </button>

          {/* RAG searching indicator */}
          {isStreaming && !streamingText && (
            <div className="flex items-center gap-2 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3">
              <img src="/搜索中.png" alt="搜索中" className="w-12 h-12 object-contain" />
              <span className="text-xs text-[var(--text-muted)]">正在检索知识库...</span>
            </div>
          )}

          {/* RAG results — three libraries */}
          {(ragResults.knowledge.length > 0 || ragResults.reference.length > 0 || ragResults.style.length > 0) && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <h3 className="text-sm font-semibold">🔍 检索参考来源</h3>
              {[
                { key: 'knowledge' as const, label: '📚 知识库', desc: '科学事实依据' },
                { key: 'reference' as const, label: '📖 参考库', desc: '叙事参考' },
                { key: 'style' as const, label: '🎨 风格库', desc: '风格启发' },
              ].map(({ key, label, desc }) => ragResults[key].length > 0 && (
                <div key={key}>
                  <div className="text-xs font-medium text-[var(--text-secondary)] mb-1">{label} · {desc} ({ragResults[key].length}条)</div>
                  <div className="space-y-1 max-h-[120px] overflow-auto">
                    {ragResults[key].map((r: Record<string, unknown>, i: number) => (
                      <div key={i} className="text-xs text-[var(--text-secondary)] p-1.5 rounded bg-[var(--bg-tertiary)] flex items-center gap-2">
                        <span className="text-[var(--text-primary)] truncate flex-1">{r.filename as string}</span>
                        <span className="text-[var(--text-muted)] shrink-0">{r.similarity as number}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Output */}
        <div className="col-span-2">
          <StreamOutput text={streamingText} isStreaming={isStreaming} className="min-h-[500px]" emptyImage="/空状态.png" loadingImage="/加载中.png" />
          {fullText && !isStreaming && (
            <div className="mt-4 flex gap-3 items-center">
              <button onClick={handleSave} className="px-6 py-2 bg-[var(--success)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:opacity-90 transition-opacity">
                💾 保存到数据库
              </button>
              {showDone && <img src="/创意完成.png" alt="完成" className="w-16 h-16 object-contain animate-bounce" />}
            </div>
          )}
        </div>
      </div>

      {/* Saved ideas */}
      <div className="mt-10">
        <h2 className="text-lg font-semibold mb-4">已保存的创意</h2>
        {ideas.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">暂无已保存的创意</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {ideas.map((idea) => (
              <div key={idea.id} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)] transition-colors">
                <h3 className="font-semibold mb-2">
                  <Link to={`/ideas/${idea.id}`} className="no-underline text-[var(--text-primary)] hover:text-[var(--accent)]">{idea.title}</Link>
                </h3>
                <p className="text-sm text-[var(--text-secondary)] line-clamp-3 mb-3">{idea.content.slice(0, 200)}</p>
                <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                  <span>{new Date(idea.updated_at).toLocaleDateString('zh-CN')}</span>
                  <button onClick={() => handleDelete(idea.id)} className="text-[var(--danger)] hover:underline bg-none border-none cursor-pointer">删除</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
