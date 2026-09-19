import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { projectsApi, outlinesApi, ideasApi } from '../api/client';
import type { Project, Outline, Idea } from '../api/client';
import { useAppStore } from '../store/appStore';

const SOURCE_LABEL: Record<string, string> = {
  outline: '来自大纲',
  idea: '来自创意',
  blank: '空白新建',
};

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { addToast } = useAppStore();

  const [projects, setProjects] = useState<Project[]>([]);
  const [outlines, setOutlines] = useState<Outline[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [creating, setCreating] = useState<'outline' | 'idea' | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, o, i] = await Promise.all([
        projectsApi.list(), outlinesApi.list(), ideasApi.list(),
      ]);
      setProjects(p);
      setOutlines(o);
      setIdeas(i);
    } catch (e) { addToast(`加载失败: ${(e as Error).message}`, 'error'); }
  }, [addToast]);

  useEffect(() => { load(); }, [load]);

  const create = async (
    source: 'outline' | 'idea' | 'blank',
    refId?: number,
  ) => {
    setBusy(true);
    try {
      const r = await projectsApi.create(
        source === 'outline' ? { source_type: 'outline', outline_id: refId }
        : source === 'idea' ? { source_type: 'idea', idea_id: refId }
        : { source_type: 'blank' },
      );
      const n = r.project.entities?.length ?? 0;
      addToast(
        source === 'blank' ? '已创建空白作品'
        : `已创建作品${n ? `，复制了 ${n} 条人物/世界观设定` : ''}`,
        'success',
      );
      navigate(`/projects/${r.project.id}`);
    } catch (e) {
      addToast(`创建失败: ${(e as Error).message}`, 'error');
    } finally { setBusy(false); setCreating(null); }
  };

  const remove = async (p: Project) => {
    if (!confirm(`删除作品《${p.title}》？${p.chapter_count} 个章节和 ${p.word_count} 字正文将一并删除，不可恢复。`)) return;
    try {
      await projectsApi.delete(p.id);
      addToast('作品已删除', 'success');
      load();
    } catch (e) { addToast(`删除失败: ${(e as Error).message}`, 'error'); }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">✍️ 创作</h1>
      <p className="text-[var(--text-secondary)] mb-6">
        从大纲创建（带章节计划），或从创意创建（带人物与世界观，章节自己一章一章加）
      </p>

      {/* 三种建法 */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <button
          onClick={() => setCreating(creating === 'outline' ? null : 'outline')}
          disabled={busy}
          className={`text-left p-4 rounded-xl border cursor-pointer transition-colors disabled:opacity-50 ${
            creating === 'outline'
              ? 'bg-[var(--accent)]/10 border-[var(--accent)]'
              : 'bg-[var(--bg-secondary)] border-[var(--border)] hover:border-[var(--accent)]'
          }`}
        >
          <div className="text-xl mb-1.5">📋</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">从大纲创建</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            章节计划直接带过来，每章点开就有场景、事件、情感弧线
          </div>
        </button>

        <button
          onClick={() => setCreating(creating === 'idea' ? null : 'idea')}
          disabled={busy}
          className={`text-left p-4 rounded-xl border cursor-pointer transition-colors disabled:opacity-50 ${
            creating === 'idea'
              ? 'bg-[var(--accent)]/10 border-[var(--accent)]'
              : 'bg-[var(--bg-secondary)] border-[var(--border)] hover:border-[var(--accent)]'
          }`}
        >
          <div className="text-xl mb-1.5">💡</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">从创意创建</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            空作品，带人物与世界观。新建章节时自动从前一章生成 PRECHA
          </div>
        </button>

        <button
          onClick={() => create('blank')}
          disabled={busy}
          className="text-left p-4 rounded-xl border bg-[var(--bg-secondary)] border-[var(--border)] hover:border-[var(--accent)] cursor-pointer transition-colors disabled:opacity-50"
        >
          <div className="text-xl mb-1.5">📄</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">空白创建</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            什么都不带，纯手写
          </div>
        </button>
      </div>

      {/* 来源选择 */}
      {creating === 'outline' && (
        <div className="mb-8 border border-[var(--accent)] rounded-xl bg-[var(--bg-secondary)] p-4">
          <h3 className="text-sm font-semibold m-0 mb-3">选一个大纲</h3>
          {outlines.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)] m-0">
              还没有大纲，先去<Link to="/outlines" className="text-[var(--accent)]">大纲工坊</Link>生成一个
            </p>
          ) : (
            <div className="space-y-1.5">
              {outlines.map((o) => (
                <button key={o.id} onClick={() => create('outline', o.id)} disabled={busy}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] hover:border-[var(--accent)] cursor-pointer text-left disabled:opacity-50">
                  <span className="text-sm text-[var(--text-primary)] flex-1 truncate">{o.title}</span>
                  <span className="text-xs text-[var(--text-muted)] shrink-0">{o.chapter_count} 章</span>
                  {o.project_id && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--warning)]/20 text-[var(--warning)] shrink-0">
                      已有作品
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {creating === 'idea' && (
        <div className="mb-8 border border-[var(--accent)] rounded-xl bg-[var(--bg-secondary)] p-4">
          <h3 className="text-sm font-semibold m-0 mb-3">选一个创意</h3>
          {ideas.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)] m-0">
              还没有创意，先去<Link to="/ideas" className="text-[var(--accent)]">创意工坊</Link>生成一个
            </p>
          ) : (
            <div className="space-y-1.5 max-h-[320px] overflow-auto">
              {ideas.map((i) => (
                <button key={i.id} onClick={() => create('idea', i.id)} disabled={busy}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] hover:border-[var(--accent)] cursor-pointer text-left disabled:opacity-50">
                  <span className="text-sm text-[var(--text-primary)] shrink-0 max-w-[40%] truncate">{i.title}</span>
                  <span className="text-xs text-[var(--text-muted)] truncate flex-1">{i.one_liner}</span>
                  {!i.structured_ok && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--warning)]/20 text-[var(--warning)] shrink-0"
                      title="这个创意还没拆出人物/世界观，建议先去详情页点「重新结构化」">
                      未结构化
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 进行中的作品 */}
      <h2 className="text-lg font-semibold mb-3">我的作品</h2>
      {projects.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">还没有作品，从上面三种方式建一个</p>
      ) : (
        <div className="space-y-2">
          {projects.map((p) => {
            const pct = p.chapter_count ? Math.round(100 * p.completed_count / p.chapter_count) : 0;
            return (
              <div key={p.id}
                className="flex items-center gap-4 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4 hover:border-[var(--accent)] transition-colors">
                <span className="text-2xl shrink-0">📖</span>
                <div className="flex-1 min-w-0">
                  <Link to={`/projects/${p.id}`}
                    className="font-semibold text-[var(--text-primary)] no-underline hover:text-[var(--accent)]">
                    {p.title}
                  </Link>
                  {p.synopsis && (
                    <p className="text-xs text-[var(--text-secondary)] m-0 mt-0.5 truncate">{p.synopsis}</p>
                  )}
                  <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mt-1 flex-wrap">
                    <span className="px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)]">
                      {SOURCE_LABEL[p.source_type] || p.source_type}
                    </span>
                    <span>{p.chapter_count} 章</span>
                    <span>·</span>
                    <span>{p.word_count.toLocaleString('zh-CN')} 字</span>
                    <span>·</span>
                    <span>定稿 {p.completed_count}/{p.chapter_count}</span>
                    <span>·</span>
                    <span>{new Date(p.updated_at).toLocaleDateString('zh-CN')}</span>
                  </div>
                </div>

                <div className="w-24 shrink-0">
                  <div className="h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                    <div className="h-full bg-[var(--success)] transition-all"
                      style={{ width: `${pct}%` }} />
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)] text-right mt-0.5">{pct}%</div>
                </div>

                <div className="flex flex-col gap-1 shrink-0">
                  <Link to={`/projects/${p.id}`}
                    className="px-3 py-1.5 bg-[var(--accent)] text-white no-underline rounded text-xs text-center hover:bg-[var(--accent-hover)]">
                    继续写
                  </Link>
                  <button onClick={() => remove(p)}
                    className="px-3 py-1 text-[var(--danger)] bg-none border-none cursor-pointer text-xs hover:underline">
                    删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
