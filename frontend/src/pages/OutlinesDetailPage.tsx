import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { outlinesApi, writingApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import ChatWidget from '../components/ChatWidget';

interface Message { role: 'user' | 'assistant'; content: string; }

export default function OutlinesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToast } = useAppStore();
  const [outline, setOutline] = useState<Record<string, unknown> | null>(null);
  const [chapters, setChapters] = useState<Array<Record<string, unknown>>>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    outlinesApi.get(Number(id)).then(setOutline).catch(() => navigate('/outlines'));
    writingApi.getChapters(Number(id)).then(setChapters).catch(() => {});
  }, [id, navigate]);

  const handleChat = (message: string) => {
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setStreamingText('');
    setIsStreaming(true);
    outlinesApi.chat(
      Number(id), message,
      (text) => setStreamingText((prev) => prev + text),
      () => {
        setIsStreaming(false);
        setMessages((prev) => [...prev, { role: 'assistant', content: streamingText }]);
        setStreamingText('');
        outlinesApi.get(Number(id)).then(setOutline);
      },
      (err) => { setIsStreaming(false); addToast(`对话失败: ${err}`, 'error'); },
    );
  };

  if (!outline) return <div className="p-6 text-[var(--text-muted)]">加载中...</div>;

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-auto p-6">
        <Link to="/outlines" className="text-sm text-[var(--accent)] no-underline hover:underline">← 返回大纲列表</Link>
        <h1 className="text-2xl font-bold mt-2 mb-1">{outline.title as string}</h1>
        <p className="text-xs text-[var(--text-muted)] mb-6">{new Date(outline.updated_at as string).toLocaleString('zh-CN')}</p>

        <div className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{outline.content as string}</ReactMarkdown>
        </div>

        <div className="mt-6 flex gap-3 pt-6 border-t border-[var(--border)]">
          <Link to={`/writing/${id}`} className="px-4 py-2 bg-[var(--accent)] text-white no-underline rounded-lg text-sm hover:bg-[var(--accent-hover)] transition-colors">
            ✍️ 开始写作
          </Link>
        </div>

        {/* Chapter list */}
        {chapters.length > 0 && (
          <div className="mt-10">
            <h2 className="text-lg font-semibold mb-4">已写章节</h2>
            <div className="space-y-2">
              {chapters.map((ch: Record<string, unknown>) => (
                <Link
                  key={ch.id as number}
                  to={`/writing/${id}/${ch.chapter_number}`}
                  className="flex items-center gap-3 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3 no-underline hover:border-[var(--accent)] transition-colors"
                >
                  <span className={`w-2 h-2 rounded-full ${ch.status === 'completed' ? 'bg-[var(--success)]' : 'bg-[var(--warning)]'}`} />
                  <span className="font-medium text-sm text-[var(--text-primary)]">CHA{ch.chapter_number} {ch.title as string}</span>
                  <span className="text-xs text-[var(--text-muted)] ml-auto">{ch.status === 'completed' ? '已完成' : '草稿'}</span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="w-96 border-l border-[var(--border)] flex flex-col">
        <div className="p-4 border-b border-[var(--border)]">
          <h2 className="text-sm font-semibold m-0">💬 对话修改大纲</h2>
        </div>
        <ChatWidget
          messages={messages}
          onSend={handleChat}
          isStreaming={isStreaming}
          streamingText={streamingText}
          placeholder="输入对大纲的修改建议..."
        />
      </div>
    </div>
  );
}
