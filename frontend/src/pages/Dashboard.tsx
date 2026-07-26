import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ideasApi, outlinesApi, uploadApi } from '../api/client';

export default function Dashboard() {
  const [stats, setStats] = useState({ ideas: 0, outlines: 0, chapters: 0, files: 0 });
  const [ragInfo, setRagInfo] = useState<{ available: boolean; categories: string[] }>({ available: false, categories: [] });
  const [recentIdeas, setRecentIdeas] = useState<Array<Record<string, unknown>>>([]);
  const [recentOutlines, setRecentOutlines] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    ideasApi.list().then((ideas) => {
      setRecentIdeas(ideas.slice(0, 5));
      setStats((s) => ({ ...s, ideas: ideas.length }));
    }).catch(() => {});
    outlinesApi.list().then((outlines) => {
      setRecentOutlines(outlines.slice(0, 5));
      setStats((s) => ({ ...s, outlines: outlines.length }));
    }).catch(() => {});
    uploadApi.getLibraries().then((data) => {
      setStats((s) => ({ ...s, files: data.files.length }));
    }).catch(() => {});
    // RAG status via dashboard page - we'll get it from a simple availability check
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-6 mb-8 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-2xl p-6">
        <img src="/首页 Hero.png" alt="墨仔" className="w-36 h-36 object-contain flex-shrink-0" />
        <div>
          <h1 className="text-2xl font-bold mb-1">科幻写作助手</h1>
          <p className="text-[var(--text-secondary)]">知识库驱动的 AI 辅助科幻创作平台 · 你好，我是墨仔</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[
          { num: stats.ideas, label: '创意设定', to: '/ideas' },
          { num: stats.outlines, label: '故事大纲', to: '/outlines' },
          { num: stats.chapters, label: '完成章节', to: '/writing' },
          { num: stats.files, label: '资料文件', to: '/upload' },
        ].map((s) => (
          <Link key={s.label} to={s.to} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 no-underline hover:border-[var(--accent)] transition-colors">
            <div className="text-3xl font-bold text-[var(--accent)]">{s.num}</div>
            <div className="text-sm text-[var(--text-secondary)] mt-1">{s.label}</div>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { icon: '💡', title: '生成创意', desc: 'RAG + AI 科幻设定', to: '/ideas' },
          { icon: '📋', title: '创建大纲', desc: '从创意生成章节规划', to: '/outlines' },
          { icon: '✍️', title: '开始写作', desc: '逐章创作 PRECHA', to: '/writing' },
          { icon: '🔧', title: '文章改写', desc: '风格诊断与优化', to: '/rewrite' },
        ].map((a) => (
          <Link key={a.title} to={a.to} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 no-underline hover:border-[var(--accent)] hover:-translate-y-0.5 transition-all">
            <div className="text-3xl mb-2">{a.icon}</div>
            <div className="font-semibold mb-1">{a.title}</div>
            <div className="text-xs text-[var(--text-muted)]">{a.desc}</div>
          </Link>
        ))}
      </div>

      {/* Recent items */}
      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-semibold mb-3">
            最近创意 <Link to="/ideas" className="text-xs text-[var(--accent)] ml-2">全部 →</Link>
          </h2>
          {recentIdeas.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)]">暂无创意</p>
          ) : (
            <div className="space-y-2">
              {recentIdeas.map((idea: Record<string, unknown>) => (
                <Link key={idea.id as number} to={`/ideas/${idea.id}`} className="block bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3 no-underline hover:border-[var(--accent)] transition-colors">
                  <div className="font-medium text-sm">{idea.title as string}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">{new Date(idea.updated_at as string).toLocaleDateString('zh-CN')}</div>
                </Link>
              ))}
            </div>
          )}
        </div>
        <div>
          <h2 className="text-lg font-semibold mb-3">
            最近大纲 <Link to="/outlines" className="text-xs text-[var(--accent)] ml-2">全部 →</Link>
          </h2>
          {recentOutlines.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)]">暂无大纲</p>
          ) : (
            <div className="space-y-2">
              {recentOutlines.map((o: Record<string, unknown>) => (
                <Link key={o.id as number} to={`/outlines/${o.id}`} className="block bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3 no-underline hover:border-[var(--accent)] transition-colors">
                  <div className="font-medium text-sm">{o.title as string}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">{o.chapter_count as number} 章 · {new Date(o.updated_at as string).toLocaleDateString('zh-CN')}</div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
