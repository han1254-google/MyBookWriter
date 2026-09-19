import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ideasApi, outlinesApi, projectsApi, uploadApi } from '../api/client';
import type { Idea, Outline, Project } from '../api/client';

export default function Dashboard() {
  const [stats, setStats] = useState({ ideas: 0, outlines: 0, chapters: 0, words: 0, files: 0 });
  const [recentIdeas, setRecentIdeas] = useState<Idea[]>([]);
  const [recentOutlines, setRecentOutlines] = useState<Outline[]>([]);
  const [recentProjects, setRecentProjects] = useState<Project[]>([]);

  useEffect(() => {
    ideasApi.list().then((ideas) => {
      setRecentIdeas(ideas.slice(0, 5));
      setStats((s) => ({ ...s, ideas: ideas.length }));
    }).catch(() => {});
    outlinesApi.list().then((outlines) => {
      setRecentOutlines(outlines.slice(0, 5));
      setStats((s) => ({ ...s, outlines: outlines.length }));
    }).catch(() => {});
    projectsApi.list().then((projects) => {
      setRecentProjects(projects.slice(0, 5));
      setStats((s) => ({
        ...s,
        chapters: projects.reduce((n, p) => n + p.completed_count, 0),
        words: projects.reduce((n, p) => n + p.word_count, 0),
      }));
    }).catch(() => {});
    uploadApi.getLibraries().then((data) => {
      setStats((s) => ({ ...s, files: data.files.length }));
    }).catch(() => {});
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
          { num: stats.chapters, label: '定稿章节', to: '/projects' },
          { num: stats.files, label: '资料文件', to: '/upload' },
        ].map((s) => (
          <Link key={s.label} to={s.to} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 no-underline hover:border-[var(--accent)] transition-colors">
            <div className="text-3xl font-bold text-[var(--accent)]">{s.num}</div>
            <div className="text-sm text-[var(--text-secondary)] mt-1">{s.label}</div>
          </Link>
        ))}
      </div>

      {stats.words > 0 && (
        <p className="text-sm text-[var(--text-muted)] -mt-4 mb-8">
          累计写了 <span className="text-[var(--text-primary)] font-medium">
            {stats.words.toLocaleString('zh-CN')}
          </span> 字
        </p>
      )}

      {/* Quick actions */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { icon: '💡', title: '生成创意', desc: 'RAG + AI 科幻设定', to: '/ideas' },
          { icon: '📋', title: '创建大纲', desc: '从创意生成章节规划', to: '/outlines' },
          { icon: '✍️', title: '开始创作', desc: '逐章写作 · PRECHA', to: '/projects' },
          { icon: '🔧', title: '文章改写', desc: '风格诊断与优化', to: '/rewrite' },
        ].map((a) => (
          <Link key={a.title} to={a.to} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5 no-underline hover:border-[var(--accent)] hover:-translate-y-0.5 transition-all">
            <div className="text-3xl mb-2">{a.icon}</div>
            <div className="font-semibold mb-1">{a.title}</div>
            <div className="text-xs text-[var(--text-muted)]">{a.desc}</div>
          </Link>
        ))}
      </div>

      {/* 进行中的作品 */}
      {recentProjects.length > 0 && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-3">
            进行中的作品 <Link to="/projects" className="text-xs text-[var(--accent)] ml-2">全部 →</Link>
          </h2>
          <div className="space-y-2">
            {recentProjects.map((p) => (
              <Link key={p.id} to={`/projects/${p.id}`}
                className="flex items-center gap-3 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3 no-underline hover:border-[var(--accent)] transition-colors">
                <span className="text-xl">📖</span>
                <span className="font-medium text-sm text-[var(--text-primary)] flex-1 truncate">{p.title}</span>
                <span className="text-xs text-[var(--text-muted)]">
                  {p.completed_count}/{p.chapter_count} 章 · {p.word_count.toLocaleString('zh-CN')} 字
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

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
              {recentIdeas.map((idea) => (
                <Link key={idea.id} to={`/ideas/${idea.id}`} className="block bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3 no-underline hover:border-[var(--accent)] transition-colors">
                  <div className="font-medium text-sm">{idea.title}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">{new Date(idea.updated_at).toLocaleDateString('zh-CN')}</div>
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
              {recentOutlines.map((o) => (
                <Link key={o.id} to={`/outlines/${o.id}`} className="block bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-3 no-underline hover:border-[var(--accent)] transition-colors">
                  <div className="font-medium text-sm">{o.title}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-1">{o.chapter_count} 章 · {new Date(o.updated_at).toLocaleDateString('zh-CN')}</div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
