import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ideasApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import ChatWidget from '../components/ChatWidget';

interface Message { role: 'user' | 'assistant'; content: string; }

export default function IdeasDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useAppStore();
  const [idea, setIdea] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [sources, setSources] = useState<Record<string, Array<Record<string, unknown>>>>({ knowledge: [], reference: [], style: [] });

  useEffect(() => {
    ideasApi.get(Number(id)).then((data) => {
      setIdea(data);
      try {
        const history = JSON.parse(data.chat_history as string || '[]');
        setMessages(history);
      } catch { /* empty */ }
      try {
        const ctx = JSON.parse(data.knowledge_context as string || '{}');
        setSources(ctx.knowledge ? ctx : { knowledge: ctx as unknown as Array<Record<string, unknown>> || [], reference: [], style: [] });
      } catch { setSources({ knowledge: [], reference: [], style: [] }); }
    }).catch(() => navigate('/ideas'));
  }, [id, navigate]);

  const handleChat = (message: string) => {
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setStreamingText('');
    setIsStreaming(true);

    ideasApi.chat(
      Number(id), message,
      (text) => setStreamingText((prev) => prev + text),
      () => {
        setIsStreaming(false);
        setMessages((prev) => [...prev, { role: 'assistant', content: streamingText }]);
        setStreamingText('');
        // Refresh idea data
        ideasApi.get(Number(id)).then(setIdea);
      },
      (err) => { setIsStreaming(false); addToast(`对话失败: ${err}`, 'error'); },
    );
  };

  const handleSaveEdit = async () => {
    if (!idea) return;
    try {
      await ideasApi.save({ title: idea.title as string, content: editContent, chat_history: idea.chat_history as string });
      addToast('已保存', 'success');
      setEditing(false);
      ideasApi.get(Number(id)).then(setIdea);
    } catch (e: unknown) {
      addToast(`保存失败: ${(e as Error).message}`, 'error');
    }
  };

  if (!idea) return <div className="p-6 text-[var(--text-muted)]">加载中...</div>;

  return (
    <div className="flex h-full">
      {/* Left: Content */}
      <div className="flex-1 overflow-auto p-6">
        <Link to="/ideas" className="text-sm text-[var(--accent)] no-underline hover:underline">← 返回创意列表</Link>
        <h1 className="text-2xl font-bold mt-2 mb-1">{idea.title as string}</h1>
        <p className="text-xs text-[var(--text-muted)] mb-6">
          {new Date(idea.updated_at as string).toLocaleString('zh-CN')}
        </p>

        {/* Reference sources */}
        {(sources.knowledge.length > 0 || sources.reference.length > 0 || sources.style.length > 0) && (
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 mb-6">
            <h3 className="text-sm font-semibold mb-2">🔍 生成来源</h3>
            <div className="flex flex-wrap gap-3">
              {sources.knowledge.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
                  <span>📚 知识库</span>
                  {sources.knowledge.map((r, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-primary)]">{r.filename as string}</span>
                  ))}
                </div>
              )}
              {sources.reference.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
                  <span>📖 参考库</span>
                  {sources.reference.map((r, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-primary)]">{r.filename as string}</span>
                  ))}
                </div>
              )}
              {sources.style.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
                  <span>🎨 风格库</span>
                  {sources.style.map((r, i) => (
                    <span key={i} className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-primary)]">{r.filename as string}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {editing ? (
          <div>
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full min-h-[400px] bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg p-4 text-sm font-mono resize-none focus:outline-none focus:border-[var(--accent)]"
            />
            <div className="flex gap-2 mt-3">
              <button onClick={handleSaveEdit} className="px-4 py-2 bg-[var(--success)] text-white border-none rounded-lg text-sm cursor-pointer">保存修改</button>
              <button onClick={() => setEditing(false)} className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border-none rounded-lg text-sm cursor-pointer">取消</button>
            </div>
          </div>
        ) : (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{idea.content as string}</ReactMarkdown>
          </div>
        )}

        {!editing && (
          <div className="flex gap-3 mt-6 pt-6 border-t border-[var(--border)]">
            <button
              onClick={() => { setEditContent(idea.content as string); setEditing(true); }}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border-none rounded-lg text-sm cursor-pointer hover:bg-[var(--border)] transition-colors"
            >
              ✏️ 编辑
            </button>
            <button
              onClick={() => navigate(`/outlines?idea_id=${id}`)}
              className="px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm cursor-pointer hover:bg-[var(--accent-hover)] transition-colors"
            >
              📋 基于此创意创建大纲
            </button>
          </div>
        )}
      </div>

      {/* Right: Chat */}
      <div className="w-96 border-l border-[var(--border)] flex flex-col">
        <div className="p-4 border-b border-[var(--border)]">
          <h2 className="text-sm font-semibold m-0">💬 对话修改</h2>
        </div>
        <ChatWidget
          messages={messages}
          onSend={handleChat}
          isStreaming={isStreaming}
          streamingText={streamingText}
          placeholder="输入修改建议，如：增加信息素交流设定..."
        />
      </div>
    </div>
  );
}
