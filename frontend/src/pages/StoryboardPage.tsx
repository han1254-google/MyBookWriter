import { useState, useEffect, useRef } from 'react';
import { ideasApi } from '../api/client';
import { useAppStore } from '../store/appStore';
import StreamOutput from '../components/StreamOutput';

interface Scene {
  scene_number: number;
  scene_title: string;
  time_of_day: string;
  description: string;
  image_prompt: string;
  subtitle: string;
}

interface Preset {
  key: string;
  label: string;
  preview: string;
}

interface SubPos {
  key: string;
  label: string;
}

export default function StoryboardPage() {
  const { addToast } = useAppStore();
  const [ideas, setIdeas] = useState<Array<Record<string, unknown>>>([]);
  const [selectedIdeaId, setSelectedIdeaId] = useState<number | ''>('');
  const [sceneCount, setSceneCount] = useState(5);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [subPositions, setSubPositions] = useState<SubPos[]>([]);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [customPrefix, setCustomPrefix] = useState('');
  const [useCustomPrefix, setUseCustomPrefix] = useState(false);
  const [subtitlePosition, setSubtitlePosition] = useState('bottom-center');
  const [customNotes, setCustomNotes] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [rawText, setRawText] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    ideasApi.list().then(setIdeas).catch(() => {});
    fetch('/api/storyboard/presets')
      .then(r => r.json())
      .then(d => { setPresets(d.presets); setSubPositions(d.subtitle_positions); })
      .catch(() => {});
  }, []);

  const handleGenerate = () => {
    if (!selectedIdeaId || isStreaming) return;
    setStreamingText('');
    setScenes([]);
    setRawText('');
    setIsStreaming(true);

    const body: Record<string, unknown> = {
      idea_id: selectedIdeaId,
      scene_count: sceneCount,
      preset_key: useCustomPrefix ? '' : selectedPreset,
      custom_prefix: useCustomPrefix ? customPrefix : '',
      subtitle_position: subtitlePosition,
      custom_notes: customNotes,
    };

    fetch('/api/storyboard/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(async (resp) => {
      const reader = resp.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'text') setStreamingText((prev) => prev + data.content);
            else if (data.type === 'done') {
              setIsStreaming(false);
              if (data.scenes) setScenes(data.scenes as Scene[]);
              if (data.raw_text) setRawText(data.raw_text as string);
              if (data.scenes) addToast(`${(data.scenes as Scene[]).length} 个分镜已生成`, 'success');
            } else if (data.type === 'error') {
              setIsStreaming(false);
              addToast(`生成失败: ${data.content}`, 'error');
            }
          } catch { /* skip */ }
        }
      }
    }).catch(err => {
      setIsStreaming(false);
      addToast(`请求失败: ${err.message}`, 'error');
    });
  };

  const handleCopyPrompt = async (text: string) => {
    await navigator.clipboard.writeText(text);
    addToast('已复制提示词', 'success');
  };

  const handleCopyAll = async () => {
    const all = scenes.map(s => `## Scene ${s.scene_number}: ${s.scene_title}\n${s.image_prompt}\n`).join('\n');
    await navigator.clipboard.writeText(all);
    addToast('已复制全部提示词', 'success');
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">🎬 视觉化 · 分镜生成</h1>
      <p className="text-[var(--text-secondary)] mb-6">基于已有创意，生成场景分镜 + AI 绘图提示词</p>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Controls */}
        <div className="col-span-1 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">选择创意</label>
            <select
              value={selectedIdeaId}
              onChange={(e) => setSelectedIdeaId(Number(e.target.value) || '')}
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            >
              <option value="">-- 选择 --</option>
              {ideas.map((i) => (
                <option key={i.id as number} value={i.id as number}>{i.title as string}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">分镜数量 (2-20)</label>
            <input
              type="number" min={2} max={20} value={sceneCount}
              onChange={(e) => setSceneCount(Math.min(20, Math.max(2, Number(e.target.value) || 2)))}
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            />
          </div>

          {/* Prefix */}
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">统一前缀</label>
            <div className="flex items-center gap-2 mb-2">
              <input type="checkbox" checked={useCustomPrefix} onChange={(e) => setUseCustomPrefix(e.target.checked)} id="use-custom" />
              <label htmlFor="use-custom" className="text-xs text-[var(--text-muted)]">自定义前缀</label>
            </div>
            {useCustomPrefix ? (
              <textarea
                value={customPrefix}
                onChange={(e) => setCustomPrefix(e.target.value)}
                rows={4}
                placeholder="输入自定义统一前缀（英文）..."
                className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs resize-none focus:outline-none focus:border-[var(--accent)]"
              />
            ) : (
              <select
                value={selectedPreset}
                onChange={(e) => setSelectedPreset(e.target.value)}
                className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
              >
                <option value="">无前缀</option>
                {presets.map((p) => (
                  <option key={p.key} value={p.key}>{p.label}</option>
                ))}
              </select>
            )}
          </div>

          {/* Subtitle position */}
          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">字幕位置</label>
            <select
              value={subtitlePosition}
              onChange={(e) => setSubtitlePosition(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
            >
              {subPositions.map((p) => (
                <option key={p.key} value={p.key}>{p.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2 text-[var(--text-secondary)]">额外要求（可选）</label>
            <textarea
              value={customNotes}
              onChange={(e) => setCustomNotes(e.target.value)}
              rows={2}
              placeholder="例如：所有场景加一句回忆旁白..."
              className="w-full bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs resize-none focus:outline-none focus:border-[var(--accent)]"
            />
          </div>

          <button
            onClick={handleGenerate}
            disabled={isStreaming || !selectedIdeaId}
            className="w-full py-3 bg-[var(--accent)] text-white border-none rounded-lg text-sm font-medium cursor-pointer hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors"
          >
            {isStreaming ? '⏳ 生成中...' : '🎬 生成分镜'}
          </button>
        </div>

        {/* Right: Output */}
        <div className="col-span-2">
          {scenes.length > 0 ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-[var(--text-secondary)]">{scenes.length} 个分镜</span>
                <button onClick={handleCopyAll} className="px-3 py-1.5 bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg text-xs cursor-pointer hover:border-[var(--accent)]">📋 复制全部提示词</button>
              </div>
              {scenes.map((s) => (
                <div key={s.scene_number} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-lg font-bold text-[var(--accent)]">#{s.scene_number}</span>
                    <span className="font-semibold">{s.scene_title}</span>
                    <span className="text-xs text-[var(--text-muted)]">{s.time_of_day}</span>
                  </div>
                  <p className="text-sm text-[var(--text-secondary)] mb-3">{s.description}</p>
                  <div className="mb-2">
                    <span className="text-xs text-[var(--text-muted)]">字幕：</span>
                    <span className="text-sm text-[var(--text-primary)] italic">{s.subtitle}</span>
                  </div>
                  <div className="relative">
                    <div className="text-xs text-[var(--text-muted)] mb-1">🎨 绘图提示词</div>
                    <pre className="text-xs text-[var(--text-secondary)] bg-[var(--bg-tertiary)] p-3 rounded-lg whitespace-pre-wrap overflow-x-auto max-h-40">{s.image_prompt}</pre>
                    <button
                      onClick={() => handleCopyPrompt(s.image_prompt)}
                      className="absolute top-6 right-2 px-2 py-1 bg-[var(--bg-secondary)] text-[var(--accent)] border border-[var(--border)] rounded text-xs cursor-pointer hover:bg-[var(--bg-tertiary)]"
                    >复制</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <StreamOutput text={streamingText} isStreaming={isStreaming} className="min-h-[500px]" emptyImage="/空状态.png" loadingImage="/加载中.png" />
          )}
        </div>
      </div>
    </div>
  );
}
