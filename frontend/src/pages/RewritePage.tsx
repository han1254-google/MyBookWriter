import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { rewriteApi } from '../api/client';
import { useAppStore } from '../store/appStore';

export default function RewritePage() {
  const { addToast } = useAppStore();
  const [originalText, setOriginalText] = useState('');
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null);
  const [rewrittenText, setRewrittenText] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isRewriting, setIsRewriting] = useState(false);
  const [instructions, setInstructions] = useState('');

  const handleAnalyze = async () => {
    if (!originalText.trim() || originalText.trim().length < 100) {
      addToast('请至少粘贴100字', 'error');
      return;
    }
    setIsAnalyzing(true);
    try {
      const result = await rewriteApi.analyze(originalText.trim());
      setAnalysis(result.analysis);
    } catch (e: unknown) {
      addToast(`分析失败: ${(e as Error).message}`, 'error');
    }
    setIsAnalyzing(false);
  };

  const handleRewrite = () => {
    if (!originalText.trim()) return;
    setRewrittenText('');
    setIsRewriting(true);

    rewriteApi.rewrite(
      originalText.trim(),
      instructions.trim() || null,
      (text) => setRewrittenText((prev) => prev + text),
      () => { setIsRewriting(false); addToast('改写完成', 'success'); },
      (err) => { setIsRewriting(false); addToast(`改写失败: ${err}`, 'error'); },
    );
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">🔧 改写工坊</h1>
      <p className="text-[var(--text-secondary)] mb-6">粘贴文章，AI 将进行风格诊断并给出改写建议</p>

      <div className="grid grid-cols-2 gap-6">
        {/* Left: Original + Analysis */}
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">粘贴原文</label>
            <textarea
              value={originalText}
              onChange={(e) => setOriginalText(e.target.value)}
              rows={20}
              placeholder="在此粘贴你要改写的文章..."
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:border-[var(--accent)] font-mono"
            />
            <div className="text-xs text-[var(--text-muted)] mt-1">{originalText.length} 字</div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleAnalyze}
              disabled={isAnalyzing || originalText.trim().length < 100}
              className="px-5 py-2.5 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
            >
              {isAnalyzing ? '⏳ 分析中...' : '🔍 分析文章'}
            </button>
            <button
              onClick={handleRewrite}
              disabled={isRewriting || !originalText.trim()}
              className="px-5 py-2.5 bg-[var(--success)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {isRewriting ? '⏳ 改写中...' : '✏️ 开始改写'}
            </button>
          </div>

          {/* Instructions */}
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">改写要求（可选）</label>
            <input
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="例如：加强自嘲式幽默、缩短对话..."
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            />
          </div>

          {/* Analysis result */}
          {analysis && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-5">
              <h3 className="font-semibold mb-3">📊 风格诊断</h3>
              {analysis.raw_analysis ? (
                <div className="markdown-body text-sm">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{analysis.raw_analysis as string}</ReactMarkdown>
                </div>
              ) : (
                <div className="space-y-3 text-sm">
                  {analysis.scores && (
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(analysis.scores as Record<string, number>).map(([k, v]) => (
                        <div key={k} className="flex justify-between bg-[var(--bg-tertiary)] rounded-lg px-3 py-2">
                          <span>{k}</span>
                          <span className={`font-bold ${v >= 7 ? 'text-[var(--success)]' : v >= 5 ? 'text-[var(--warning)]' : 'text-[var(--danger)]'}`}>{v}/10</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {analysis.strengths && (
                    <div>
                      <div className="font-medium text-[var(--success)] mb-1">✅ 优点</div>
                      <ul className="list-disc list-inside text-[var(--text-secondary)]">
                        {(analysis.strengths as string[]).map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  )}
                  {analysis.weaknesses && (
                    <div>
                      <div className="font-medium text-[var(--danger)] mb-1">⚠️ 问题</div>
                      <ul className="list-disc list-inside text-[var(--text-secondary)]">
                        {(analysis.weaknesses as string[]).map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
                    </div>
                  )}
                  {analysis.suggestions && (
                    <div>
                      <div className="font-medium text-[var(--accent)] mb-1">💡 建议</div>
                      <ul className="list-disc list-inside text-[var(--text-secondary)]">
                        {(analysis.suggestions as string[]).map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </div>
                  )}
                  {analysis.overall && <p className="text-[var(--text-primary)] italic">💬 {analysis.overall as string}</p>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Rewritten */}
        <div>
          <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">改写结果</label>
          {rewrittenText ? (
            <div className="markdown-body bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-6 min-h-[400px] max-h-[80vh] overflow-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{rewrittenText}</ReactMarkdown>
            </div>
          ) : (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-6 min-h-[400px] flex items-center justify-center text-[var(--text-muted)] text-sm">
              {isRewriting ? (
                <div className="text-center">
                  <p className="text-3xl mb-2">⏳</p>
                  <p>AI 正在改写中...</p>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-3xl mb-2">✏️</p>
                  <p>先粘贴原文，再点击"分析文章"或"开始改写"</p>
                </div>
              )}
            </div>
          )}
          {rewrittenText && (
            <button
              onClick={() => {
                navigator.clipboard.writeText(rewrittenText);
                addToast('已复制改写结果', 'success');
              }}
              className="mt-3 px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:border-[var(--accent)] transition-colors"
            >
              📋 复制改写结果
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
