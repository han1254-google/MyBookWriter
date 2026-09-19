import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ideasApi, uploadApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import StreamOutput from '../components/StreamOutput';

interface RagFile {
  source: string;
  filename: string;
  library_type: string;
  category: string;
  chunks: number;
}

interface Citation {
  filename: string;
  category: string;
  library_type: string;
  similarity: number;
  matched_queries?: number;
}

type RagResults = { knowledge: Citation[]; reference: Citation[]; style: Citation[] };

const EMPTY_RAG: RagResults = { knowledge: [], reference: [], style: [] };

const DEFAULT_TAGS = [
  '尽量少使用破折号',
  '加强自嘲式幽默',
  '用具体数字代替形容词',
  '第一人称观察者视角',
  '结尾落在具体画面或动作上',
  '加入真实品牌和地名',
];

export default function IdeasPage() {
  const { ideas, setIdeas, addToast } = useAppStore();
  const [prompt, setPrompt] = useState('');
  const [ragFiles, setRagFiles] = useState<RagFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [fullText, setFullText] = useState('');
  const [ragResults, setRagResults] = useState<RagResults>(EMPTY_RAG);
  const [subQueries, setSubQueries] = useState<string[]>([]);
  const [statusMsg, setStatusMsg] = useState('');
  const [structure, setStructure] = useState<Record<string, unknown> | null>(null);
  const [customTags, setCustomTags] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('idea_prompt_tags') || '[]'); } catch { return []; }
  });
  const [newTag, setNewTag] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    ideasApi.list().then(setIdeas).catch(() => {});
    uploadApi.ragFiles().then(setRagFiles).catch(() => {});
  }, [setIdeas]);

  const toggleFile = (source: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source); else next.add(source);
      return next;
    });
  };

  const selectedFileNames = ragFiles.filter((f) => selectedFiles.has(f.source)).map((f) => f.filename);

  const handleGenerate = () => {
    if (!prompt.trim() || isStreaming) return;
    setStreamingText('');
    setFullText('');
    setStructure(null);
    setSubQueries([]);
    setRagResults(EMPTY_RAG);
    setStatusMsg('正在拆解检索查询…');
    setIsStreaming(true);

    const files = selectedFiles.size > 0 ? Array.from(selectedFiles) : null;
    abortRef.current = ideasApi.generate(
      prompt.trim(), files,
      (text) => setStreamingText((p) => p + text),
      (data) => {
        setIsStreaming(false);
        setStatusMsg('');
        if (data?.full_text) setFullText(data.full_text as string);
        if (data?.rag_results) setRagResults(data.rag_results as unknown as RagResults);
        if (data?.structure) setStructure(data.structure as Record<string, unknown>);
      },
      (err) => { setIsStreaming(false); setStatusMsg(''); addToast(`生成失败: ${err}`, 'error'); },
      (type, data) => {
        if (type === 'plan') {
          setSubQueries((data.queries as string[]) || []);
          setStatusMsg('正在检索三库…');
        } else if (type === 'status') {
          setStatusMsg(String(data.content || ''));
        }
      },
    );
  };

  const handleSave = async () => {
    try {
      const r = await ideasApi.save({
        content: fullText,
        structure: structure || undefined,
        knowledge_context: ragResults,
      });
      const n = r.idea.entities?.length ?? 0;
      addToast(`创意已保存${n ? `，拆出 ${n} 条人物/世界观` : ''}`, 'success');
      ideasApi.list().then(setIdeas);
    } catch (e) {
      addToast(`保存失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除这个创意？')) return;
    try {
      await ideasApi.delete(id);
      addToast('已删除', 'success');
      ideasApi.list().then(setIdeas);
    } catch (e) {
      addToast(`删除失败: ${(e as Error).message}`, 'error');
    }
  };

  const entityPreview = (structure?.entities as Array<Record<string, unknown>>) || [];

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">💡 创意工坊</h1>
      <p className="text-[var(--text-secondary)] mb-6">
        提示词会先被拆成多条正交的检索子查询，再按来源配额取样，避免被单本书带偏
      </p>

      <div className="grid grid-cols-3 gap-6">
        {/* 左：控制区 */}
        <div className="col-span-1 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">
              预定义提示词（点击追加到输入框）
            </label>
            <div className="flex flex-wrap gap-1.5 max-h-[120px] overflow-auto">
              {[...DEFAULT_TAGS, ...customTags].map((tag) => (
                <button key={tag}
                  onClick={() => setPrompt((p) => (p ? p + '；' + tag : tag))}
                  className="px-2 py-1 rounded text-xs border border-[var(--border)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] cursor-pointer transition-colors"
                >+ {tag}</button>
              ))}
            </div>
            <div className="flex gap-1 mt-2">
              <input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newTag.trim()) {
                    const updated = [...customTags, newTag.trim()];
                    setCustomTags(updated);
                    localStorage.setItem('idea_prompt_tags', JSON.stringify(updated));
                    setNewTag('');
                  }
                }}
                placeholder="自定义提示词…"
                className="flex-1 bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded px-2 py-1 text-xs focus:outline-none focus:border-[var(--accent)]"
              />
              {customTags.length > 0 && (
                <button
                  onClick={() => { setCustomTags([]); localStorage.removeItem('idea_prompt_tags'); }}
                  className="px-2 py-1 text-xs text-[var(--text-muted)] hover:text-[var(--danger)] bg-none border-none cursor-pointer"
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
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-[var(--text-secondary)]">指定文件检索（可选）</label>
              <button
                onClick={() => setShowFilePicker((v) => !v)}
                className="text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline"
              >
                {showFilePicker ? '收起' : `选择文件 (${selectedFiles.size})`}
              </button>
            </div>
            {selectedFileNames.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2 max-h-[60px] overflow-auto">
                {selectedFileNames.map((name) => (
                  <span key={name} className="px-2 py-0.5 rounded text-xs bg-[var(--accent)]/15 text-[var(--accent)] truncate max-w-[140px]">{name}</span>
                ))}
              </div>
            )}
            {showFilePicker && (
              <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-2 max-h-[240px] overflow-auto">
                {ragFiles.length === 0 && (
                  <p className="text-xs text-[var(--text-muted)] p-2">向量库为空，请先在资料管理上传文件</p>
                )}
                {(['知识库', '参考库', '风格库'] as const).map((lib) => {
                  const libFiles = ragFiles.filter((f) => f.library_type === lib);
                  if (libFiles.length === 0) return null;
                  return (
                    <div key={lib} className="mb-2">
                      <div className="text-xs font-medium text-[var(--text-muted)] mb-1 px-1">
                        {{ 知识库: '📚', 参考库: '📖', 风格库: '🎨' }[lib]} {lib} ({libFiles.length})
                      </div>
                      {libFiles.map((f) => (
                        <label key={f.source} className="flex items-center gap-2 px-1 py-1 rounded cursor-pointer hover:bg-[var(--bg-tertiary)] text-xs text-[var(--text-secondary)]">
                          <input type="checkbox" checked={selectedFiles.has(f.source)} onChange={() => toggleFile(f.source)} />
                          <span className="truncate flex-1" title={`${f.category} / ${f.source}`}>{f.filename}</span>
                          <span className="text-[var(--text-muted)] shrink-0">{f.chunks}块</span>
                        </label>
                      ))}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <button
            onClick={handleGenerate}
            disabled={isStreaming || !prompt.trim()}
            className="w-full py-3 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isStreaming ? '⏳ 生成中…' : '🚀 生成创意'}
          </button>

          {statusMsg && (
            <div className="flex items-center gap-2 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3">
              <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse shrink-0" />
              <span className="text-xs text-[var(--text-muted)]">{statusMsg}</span>
            </div>
          )}

          {/* 检索子查询 —— 让你看清它到底去查了什么 */}
          {subQueries.length > 0 && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <h3 className="text-sm font-semibold mb-2">🎯 检索子查询</h3>
              <ul className="text-xs text-[var(--text-secondary)] space-y-1 pl-4 m-0">
                {subQueries.map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            </div>
          )}

          {/* 检索命中 */}
          {(ragResults.knowledge.length > 0 || ragResults.reference.length > 0 || ragResults.style.length > 0) && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 space-y-3">
              <h3 className="text-sm font-semibold">🔍 检索命中</h3>
              {([
                { key: 'knowledge', label: '📚 知识库', desc: '科学事实依据' },
                { key: 'reference', label: '📖 参考库', desc: '叙事参考' },
                { key: 'style', label: '🎨 风格库', desc: '风格启发' },
              ] as const).map(({ key, label, desc }) => {
                const hits = ragResults[key];
                if (hits.length === 0) return null;
                const files = new Set(hits.map((h) => h.filename)).size;
                return (
                  <div key={key}>
                    <div className="text-xs font-medium text-[var(--text-secondary)] mb-1">
                      {label} · {desc}（{hits.length} 条 / {files} 个文件）
                    </div>
                    <div className="space-y-1 max-h-[140px] overflow-auto">
                      {hits.map((r, i) => (
                        <div key={i} className="text-xs text-[var(--text-secondary)] p-1.5 rounded bg-[var(--bg-tertiary)] flex items-center gap-2">
                          <span className="text-[var(--text-primary)] truncate flex-1" title={r.category}>{r.filename}</span>
                          <span className="text-[var(--text-muted)] shrink-0">{r.similarity}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 右：输出 */}
        <div className="col-span-2">
          <StreamOutput text={streamingText} isStreaming={isStreaming} className="min-h-[500px]" emptyImage="/空状态.png" loadingImage="/加载中.png" />

          {structure && (
            <div className="mt-4 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <h3 className="text-sm font-semibold mb-2">
                🧩 结构化结果
                {structure.structured_ok
                  ? <span className="ml-2 text-xs text-[var(--success)]">解析完整</span>
                  : <span className="ml-2 text-xs text-[var(--warning)]">解析不完整，保存后可在详情页重试</span>}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {entityPreview.map((e, i) => (
                  <span key={i} className="px-2 py-0.5 rounded text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                    {e.kind === 'character' ? '👤' : e.kind === 'worldview' ? '🌍' : '⚙️'} {String(e.name)}
                  </span>
                ))}
                {entityPreview.length === 0 && (
                  <span className="text-xs text-[var(--text-muted)]">没拆出条目</span>
                )}
              </div>
            </div>
          )}

          {fullText && !isStreaming && (
            <div className="mt-4 flex gap-3 items-center">
              <button onClick={handleSave}
                className="px-6 py-2 bg-[var(--success)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:opacity-90 transition-opacity">
                💾 保存到数据库
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 已保存的创意 */}
      <div className="mt-10">
        <h2 className="text-lg font-semibold mb-4">已保存的创意</h2>
        {ideas.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">暂无已保存的创意</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {ideas.map((idea) => (
              <div key={idea.id} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)] transition-colors">
                <h3 className="font-semibold mb-1">
                  <Link to={`/ideas/${idea.id}`} className="no-underline text-[var(--text-primary)] hover:text-[var(--accent)]">
                    {idea.title}
                  </Link>
                </h3>
                <p className="text-sm text-[var(--text-secondary)] line-clamp-3 mb-3">
                  {idea.one_liner || idea.content.slice(0, 160)}
                </p>
                <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                  <span>
                    {new Date(idea.updated_at).toLocaleDateString('zh-CN')}
                    {!idea.structured_ok && <span className="ml-2 text-[var(--warning)]">未结构化</span>}
                  </span>
                  <button onClick={() => handleDelete(idea.id)}
                    className="text-[var(--danger)] hover:underline bg-none border-none cursor-pointer">删除</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
