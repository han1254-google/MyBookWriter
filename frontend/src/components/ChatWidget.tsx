import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface ChatWidgetProps {
  messages: Message[];
  onSend: (message: string) => Promise<void> | void;
  isStreaming: boolean;
  streamingText: string;
  placeholder?: string;
}

export default function ChatWidget({
  messages,
  onSend,
  isStreaming,
  streamingText,
  placeholder = '输入修改建议...',
}: ChatWidgetProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput('');
  }, [input, isStreaming, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {messages.length === 0 && !isStreaming && (
          <div className="text-center text-[var(--text-muted)] py-8">
            <p>💬 在此处与 AI 对话修改内容</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
              msg.role === 'user'
                ? 'bg-[var(--accent)] text-white rounded-br-sm'
                : 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] rounded-bl-sm'
            }`}>
              {msg.role === 'assistant' ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              ) : (
                <p className="m-0 whitespace-pre-wrap">{msg.content}</p>
              )}
            </div>
          </div>
        ))}
        {isStreaming && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-xl rounded-bl-sm px-4 py-2.5 text-sm bg-[var(--bg-tertiary)] stream-cursor">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-[var(--border)] p-3">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={2}
            disabled={isStreaming}
            className="flex-1 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            className="px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors self-end"
          >
            {isStreaming ? '...' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
