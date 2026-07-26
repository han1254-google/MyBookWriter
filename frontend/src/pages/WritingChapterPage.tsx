import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { outlinesApi, writingApi, ideasApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import ChatWidget from '../components/ChatWidget';

interface Message { role: 'user' | 'assistant'; content: string; }

export default function WritingChapterPage() {
  const { outline_id, chapter_num } = useParams<{ outline_id: string; chapter_num?: string }>();
  const { addToast } = useAppStore();
  const [outline, setOutline] = useState<Record<string, unknown> | null>(null);
  const [idea, setIdea] = useState<Record<string, unknown> | null>(null);
  const [chapters, setChapters] = useState<Array<Record<string, unknown>>>([]);
  const [currentChapter, setCurrentChapter] = useState<Record<string, unknown> | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatStream, setChatStream] = useState('');
  const [isChatStreaming, setIsChatStreaming] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [exportText, setExportText] = useState('');
  const [saveDone, setSaveDone] = useState(false);

  const cn = Number(chapter_num || 1);
  const oid = Number(outline_id);

  const loadData = () => {
    outlinesApi.get(oid).then((data) => {
      setOutline(data);
      if (data.idea_id) ideasApi.get(data.idea_id as number).then(setIdea).catch(() => {});
    }).catch(() => {});
    writingApi.getChapters(oid).then(setChapters).catch(() => {});
  };

  useEffect(() => { loadData(); }, [oid]);

  useEffect(() => {
    const ch = chapters.find((c: Record<string, unknown>) => c.chapter_number === cn);
    setCurrentChapter(ch || null);
  }, [chapters, cn]);

  const handleGenerate = () => {
    if (isStreaming) return;
    setStreamingText('');
    setIsStreaming(true);

    if (cn === 1) {
      writingApi.startWriting(oid,
        (text) => setStreamingText((prev) => prev + text),
        (data) => {
          setIsStreaming(false);
          addToast('第一章生成完成！请审核后点击"同意"保存', 'success');
        },
        (err) => { setIsStreaming(false); addToast(`生成失败: ${err}`, 'error'); },
      );
    } else {
      writingApi.generateChapter(oid, cn,
        (text) => setStreamingText((prev) => prev + text),
        (data) => {
          setIsStreaming(false);
          addToast(`第${cn}章生成完成！请审核后点击"同意"保存`, 'success');
        },
        (err) => { setIsStreaming(false); addToast(`生成失败: ${err}`, 'error'); },
      );
    }
  };

  const handleApprove = async () => {
    if (!streamingText) return;
    const titleMatch = streamingText.match(/#\s*CHA\d+\s*(.+)/);
    const title = titleMatch ? titleMatch[1].trim() : `第${cn}章`;

    try {
      await writingApi.saveChapter({
        outline_id: oid,
        chapter_number: cn,
        title,
        content: streamingText,
        status: 'completed',
      });
      addToast(`第${cn}章已保存！`, 'success');
      setSaveDone(true);
      setTimeout(() => setSaveDone(false), 4000);
      loadData();
    } catch (e: unknown) {
      addToast(`保存失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleChat = (message: string) => {
    if (!currentChapter) { addToast('请先生成章节', 'error'); return; }
    setChatMessages((prev) => [...prev, { role: 'user', content: message }]);
    setChatStream('');
    setIsChatStreaming(true);

    writingApi.chatChapter(
      currentChapter.id as number, message,
      (text) => setChatStream((prev) => prev + text),
      () => {
        setIsChatStreaming(false);
        setChatMessages((prev) => [...prev, { role: 'assistant', content: chatStream }]);
        setChatStream('');
      },
      (err) => { setIsChatStreaming(false); addToast(`对话失败: ${err}`, 'error'); },
    );
  };

  const handleDelete = async (chapterId: number) => {
    if (!confirm(`确定删除 CHA${cn} 吗？此操作不可恢复。`)) return;
    try {
      await writingApi.deleteChapter(chapterId);
      addToast('章节已删除', 'success');
      loadData();
    } catch (e: unknown) {
      addToast(`删除失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleExport = async () => {
    try {
      const result = await writingApi.exportBook(oid);
      setExportText(result.full_text);
      setShowExport(true);
    } catch (e: unknown) {
      addToast(`导出失败: ${(e as Error).message}`, 'error');
    }
  };

  return (
    <div className="flex h-full">
      {/* Left: Context */}
      <div className="w-72 overflow-auto p-4 border-r border-[var(--border)] space-y-4">
        <Link to="/writing" className="text-xs text-[var(--accent)] no-underline hover:underline">← 返回</Link>

        {idea && (
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">IDEA 设定</h3>
            <div className="text-xs text-[var(--text-secondary)] max-h-[200px] overflow-auto markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{(idea.content as string)?.slice(0, 500)}</ReactMarkdown>
            </div>
          </div>
        )}

        {outline && (
          <div>
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">大纲</h3>
            <div className="text-xs text-[var(--text-secondary)] max-h-[300px] overflow-auto markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{(outline.content as string)?.slice(0, 1000)}</ReactMarkdown>
            </div>
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">章节列表</h3>
          {chapters.map((ch: Record<string, unknown>) => (
            <div key={ch.chapter_number as number} className="flex items-center gap-1">
              <Link
                to={`/writing/${oid}/${ch.chapter_number}`}
                className={`flex-1 flex items-center gap-2 text-xs py-1.5 px-2 rounded no-underline transition-colors ${
                  ch.chapter_number === cn
                    ? 'bg-[var(--accent)]/20 text-[var(--accent)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${ch.status === 'completed' ? 'bg-[var(--success)]' : 'bg-[var(--warning)]'}`} />
                CHA{ch.chapter_number} {ch.title as string}
              </Link>
              <button
                onClick={() => handleDelete(ch.id as number)}
                className="text-[var(--text-muted)] hover:text-[var(--danger)] bg-none border-none cursor-pointer text-xs px-1"
                title="删除此章"
              >🗑</button>
            </div>
          ))}
          {!chapters.find((c: Record<string, unknown>) => c.chapter_number === cn) && (
            <div className="text-xs text-[var(--text-muted)] px-2 py-1.5">CHA{cn} 待写作</div>
          )}
        </div>

        <button
          onClick={handleExport}
          className="w-full py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-xs cursor-pointer hover:border-[var(--accent)] transition-colors"
        >
          📦 导出全书
        </button>
      </div>

      {/* Center: Chapter content */}
      <div className="flex-1 overflow-auto p-6">
        {currentChapter ? (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{currentChapter.content as string}</ReactMarkdown>
          </div>
        ) : isStreaming || streamingText ? (
          <div className={`markdown-body ${isStreaming ? 'stream-cursor' : ''}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
          </div>
        ) : isStreaming ? (
          <div className="flex flex-col items-center justify-center py-20 text-[var(--text-muted)]">
            <img src="/加载中.png" alt="加载中" className="w-32 h-32 object-contain mb-4" />
            <p className="text-sm">墨仔正在写第{cn}章...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-[var(--text-muted)]">
            <img src="/空状态.png" alt="空状态" className="w-40 h-40 object-contain mb-4" />
            <p className="text-sm">点击下方按钮开始生成第{cn}章</p>
          </div>
        )}

        {/* Save success popup */}
        {saveDone && (
          <div className="fixed bottom-8 right-8 z-50 animate-bounce">
            <img src="/章节保存.png" alt="保存成功" className="w-24 h-24 object-contain" />
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 mt-6 pt-6 border-t border-[var(--border)]">
          {!currentChapter && (
            <button
              onClick={handleGenerate}
              disabled={isStreaming}
              className="px-6 py-2.5 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
            >
              {isStreaming ? '⏳ 生成中...' : cn === 1 ? '🚀 生成第一章' : `📝 生成第${cn}章`}
            </button>
          )}
          {streamingText && !isStreaming && !currentChapter && (
            <button
              onClick={handleApprove}
              className="px-6 py-2.5 bg-[var(--success)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:opacity-90 transition-opacity"
            >
              ✅ 同意，保存本章
            </button>
          )}

          {/* Chapter navigator */}
          <div className="flex gap-2 ml-auto">
            {cn > 1 && (
              <Link to={`/writing/${oid}/${cn - 1}`} className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] no-underline rounded-lg text-sm hover:bg-[var(--border)] transition-colors">
                ← 上一章
              </Link>
            )}
            <Link to={`/writing/${oid}/${cn + 1}`} className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] no-underline rounded-lg text-sm hover:bg-[var(--border)] transition-colors">
              下一章 →
            </Link>
          </div>
        </div>
      </div>

      {/* Right: Chat */}
      <div className="w-80 border-l border-[var(--border)] flex flex-col">
        <div className="p-4 border-b border-[var(--border)]">
          <h2 className="text-sm font-semibold m-0">💬 AI 协作</h2>
        </div>
        <ChatWidget
          messages={chatMessages}
          onSend={handleChat}
          isStreaming={isChatStreaming}
          streamingText={chatStream}
          placeholder="对这一章提修改意见..."
        />
      </div>

      {/* Export modal */}
      {showExport && (
        <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50" onClick={() => setShowExport(false)}>
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-2xl p-6 max-w-4xl w-full max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold">📦 导出全书</h2>
              <button onClick={() => setShowExport(false)} className="text-[var(--text-muted)] hover:text-[var(--text-primary)] bg-none border-none text-xl cursor-pointer">✕</button>
            </div>
            <div className="flex gap-3 mb-4">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(exportText);
                  addToast('已复制到剪贴板', 'success');
                }}
                className="px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm cursor-pointer"
              >
                📋 复制全文
              </button>
              <button
                onClick={() => {
                  const blob = new Blob([exportText], { type: 'text/markdown' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url; a.download = `${outline?.title || 'book'}.md`;
                  a.click(); URL.revokeObjectURL(url);
                }}
                className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer"
              >
                💾 下载 MD
              </button>
            </div>
            <pre className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap font-mono bg-[var(--bg-tertiary)] p-4 rounded-lg max-h-[50vh] overflow-auto">
              {exportText}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
