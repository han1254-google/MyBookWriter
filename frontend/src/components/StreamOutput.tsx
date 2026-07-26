import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface StreamOutputProps {
  text: string;
  isStreaming: boolean;
  className?: string;
  emptyImage?: string;    // 空状态图
  loadingImage?: string;  // 加载中图
}

export default function StreamOutput({ text, isStreaming, className = '', emptyImage, loadingImage }: StreamOutputProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current && isStreaming) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [text, isStreaming]);

  return (
    <div
      ref={containerRef}
      className={`markdown-body overflow-auto p-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] ${className}`}
    >
      {text ? (
        <div className={isStreaming ? 'stream-cursor' : ''}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : isStreaming ? (
        <div className="text-center text-[var(--text-muted)] py-8">
          {loadingImage ? (
            <img src={loadingImage} alt="加载中" className="w-32 h-32 mx-auto mb-4 object-contain" />
          ) : (
            <p className="text-4xl mb-3">⏳</p>
          )}
          <p>AI 正在生成中...</p>
        </div>
      ) : (
        <div className="text-center text-[var(--text-muted)] py-8">
          {emptyImage ? (
            <img src={emptyImage} alt="空状态" className="w-40 h-40 mx-auto mb-4 object-contain" />
          ) : (
            <p className="text-4xl mb-3">📝</p>
          )}
          <p>点击生成按钮开始</p>
          <p className="text-xs mt-2">AI 将检索知识库中的相关科学资料，生成内容</p>
        </div>
      )}
    </div>
  );
}
