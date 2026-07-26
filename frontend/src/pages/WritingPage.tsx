import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { outlinesApi, writingApi } from '../api/client';

export default function WritingPage() {
  const [outlines, setOutlines] = useState<Array<Record<string, unknown>>>([]);
  const [writingOutlines, setWritingOutlines] = useState<Array<{ outline: Record<string, unknown>; chapterCount: number }>>([]);

  useEffect(() => {
    outlinesApi.list().then(async (data) => {
      setOutlines(data);
      const withChapters = await Promise.all(
        data.map(async (o: Record<string, unknown>) => {
          try {
            const chs = await writingApi.getChapters(o.id as number);
            return { outline: o, chapterCount: chs.length };
          } catch { return { outline: o, chapterCount: 0 }; }
        })
      );
      setWritingOutlines(withChapters.filter((w) => w.chapterCount > 0));
    });
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">✍️ 写作工坊</h1>
      <p className="text-[var(--text-secondary)] mb-6">选择大纲开始逐章写作，或直接输入提示词自动走完 RAG→大纲→写作</p>

      {/* Start from outline */}
      <div className="mb-10">
        <h2 className="text-lg font-semibold mb-4">从历史大纲开始</h2>
        {outlines.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">暂无大纲，请先在<a href="/outlines" className="text-[var(--accent)]">大纲工坊</a>创建</p>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {outlines.map((o: Record<string, unknown>) => (
              <div key={o.id as number} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)] transition-colors">
                <h3 className="font-semibold mb-2">{o.title as string}</h3>
                <p className="text-xs text-[var(--text-muted)] mb-4">
                  {o.chapter_count as number} 章 · {new Date(o.updated_at as string).toLocaleDateString('zh-CN')}
                </p>
                <Link
                  to={`/writing/${o.id}`}
                  className="inline-block px-4 py-2 bg-[var(--accent)] text-white no-underline rounded-lg text-sm hover:bg-[var(--accent-hover)] transition-colors"
                >
                  开始写作 →
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* In-progress books */}
      {writingOutlines.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">进行中的作品</h2>
          <div className="space-y-3">
            {writingOutlines.map(({ outline, chapterCount }) => (
              <Link
                key={outline.id as number}
                to={`/writing/${outline.id}`}
                className="flex items-center gap-4 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 no-underline hover:border-[var(--accent)] transition-colors"
              >
                <span className="text-2xl">📖</span>
                <div className="flex-1">
                  <div className="font-semibold">{outline.title as string}</div>
                  <div className="text-xs text-[var(--text-muted)]">已写 {chapterCount} 章</div>
                </div>
                <span className="text-[var(--text-muted)]">→</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
