import { useState, useEffect, useCallback } from 'react';
import { uploadApi } from '../api/client';
import { useAppStore } from '../store/appStore';

interface FileInfo {
  id: number;
  library_type: string;
  folder_name: string;
  original_filename: string;
  stored_path: string;
  file_type: string;
  style_analysis: string;
  ai_summary: string;
  created_at: string;
}

export default function UploadPage() {
  const { addToast } = useAppStore();
  const [libraries, setLibraries] = useState<Record<string, Record<string, string[]>>>({});
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [activeLib, setActiveLib] = useState('知识库');
  const [selectedLib, setSelectedLib] = useState('知识库');
  const [uploading, setUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileInfo | null>(null);
  const [summarizing, setSummarizing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<FileInfo[] | null>(null);

  const loadData = useCallback(() => {
    uploadApi.getLibraries().then((data) => {
      setLibraries(data.structure);
      setFiles(data.files as FileInfo[]);
    }).catch(() => {});
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const result = await uploadApi.upload(file, selectedLib);
      addToast(`${file.name} → ${result.library_type}/${result.folder_name}`, 'success');
      setUploadDone(true);
      setTimeout(() => setUploadDone(false), 3000);
      loadData();
    } catch (e: unknown) {
      addToast(`${(e as Error).message}`, 'error');
    }
    setUploading(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    Array.from(e.dataTransfer.files).forEach(handleUpload);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) Array.from(e.target.files).forEach(handleUpload);
  };

  const handleDelete = async (id: number) => {
    try {
      await uploadApi.deleteFile(id);
      if (selectedFile?.id === id) setSelectedFile(null);
      addToast('已删除', 'success');
      loadData();
    } catch (e: unknown) {
      addToast(`删除失败: ${(e as Error).message}`, 'error');
    }
  };

  const handleSelect = async (f: FileInfo) => {
    setSelectedFile(f);
    if (!f.ai_summary) {
      setSummarizing(true);
      try {
        const resp = await fetch(`/api/libraries/${f.id}/summarize`, { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
          setSelectedFile({ ...f, ai_summary: data.summary });
          // Update in list too
          setFiles((prev) => prev.map((pf) => pf.id === f.id ? { ...pf, ai_summary: data.summary } : pf));
        }
      } catch { /* ignore */ }
      setSummarizing(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    try {
      const resp = await fetch(`/api/libraries/search?q=${encodeURIComponent(searchQuery.trim())}`);
      const data = await resp.json();
      setSearchResults(data as FileInfo[]);
    } catch { /* ignore */ }
  };

  const showFiles = searchResults ?? files;
  const filteredByCurrentLib = showFiles.filter((f) => f.library_type === activeLib);

  const downloadUrl = (id: number) => `/api/libraries/${id}/download`;

  return (
    <div className="flex h-full">
      {/* Main area */}
      <div className="flex-1 overflow-auto p-6">
        <h1 className="text-2xl font-bold mb-1">📁 资料管理</h1>
        <p className="text-[var(--text-secondary)] mb-4">上传PDF/EPUB/Word/TXT文件，AI自动分类、索引、摘要</p>

        {/* Search bar */}
        <div className="flex gap-2 mb-4">
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="搜索文件名或内容关键词..."
            className="flex-1 bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-[var(--accent)]"
          />
          <button onClick={handleSearch} className="px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm cursor-pointer hover:bg-[var(--accent-hover)] transition-colors">
            🔍 搜索
          </button>
          {searchResults && (
            <button onClick={() => { setSearchQuery(''); setSearchResults(null); }} className="px-3 py-2 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border-none rounded-lg text-sm cursor-pointer">
              清除
            </button>
          )}
        </div>

        {/* Library type selector for upload */}
        <div className="flex items-center gap-3 mb-3">
          <span className="text-sm text-[var(--text-secondary)] whitespace-nowrap">上传到：</span>
          {['知识库', '参考库', '风格库'].map((lib) => (
            <button key={lib} onClick={() => setSelectedLib(lib)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                selectedLib === lib ? 'bg-[var(--accent)] text-white border-[var(--accent)]' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)] hover:border-[var(--accent)]'
              }`}>
              {{ '知识库': '📚', '参考库': '📖', '风格库': '🎨' }[lib]} {lib}
            </button>
          ))}
        </div>

        {/* Upload zone */}
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          className={`border-2 border-dashed rounded-xl p-6 text-center mb-6 transition-colors cursor-pointer ${
            dragOver ? 'border-[var(--accent)] bg-[var(--accent)]/5' : 'border-[var(--border)]'
          }`}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          {uploadDone ? (
            <img src="/上传成功.png" alt="ok" className="w-20 h-20 mx-auto mb-2 object-contain" />
          ) : (
            <div className="text-4xl mb-2">{uploading ? '⏳' : '📤'}</div>
          )}
          <p className="text-sm font-medium">{uploadDone ? '上传成功！' : uploading ? '上传分析中...' : '拖拽文件或点击选择'}</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">PDF / EPUB / DOCX / TXT / MD</p>
          <input id="file-input" type="file" hidden multiple accept=".pdf,.epub,.docx,.doc,.txt,.md" onChange={handleFileInput} />
        </div>

        {/* Library tabs */}
        <div className="flex gap-2 mb-4">
          {['知识库', '参考库', '风格库'].map((lib) => (
            <button key={lib} onClick={() => setActiveLib(lib)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                activeLib === lib ? 'bg-[var(--accent)] text-white border-[var(--accent)]' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)] hover:border-[var(--accent)]'
              }`}>
              {{ '知识库': '📚', '参考库': '📖', '风格库': '🎨' }[lib]} {lib}
            </button>
          ))}
          <span className="ml-auto text-xs text-[var(--text-muted)] self-center">{filteredByCurrentLib.length} 个文件</span>
        </div>

        {/* File list */}
        {filteredByCurrentLib.length > 0 ? (
          <div className="space-y-4">
            {Object.entries(
              filteredByCurrentLib.reduce((acc, f) => {
                (acc[f.folder_name] ??= []).push(f);
                return acc;
              }, {} as Record<string, FileInfo[]>)
            ).map(([folder, folderFiles]) => (
              <div key={folder} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <span>📂</span> {folder}
                  <span className="text-xs text-[var(--text-muted)] font-normal">({folderFiles.length})</span>
                </h3>
                <div className="space-y-1">
                  {folderFiles.map((f) => (
                    <div key={f.id}
                      onClick={() => handleSelect(f)}
                      className={`flex items-center gap-2 text-sm py-2 px-3 rounded-lg cursor-pointer transition-colors ${
                        selectedFile?.id === f.id ? 'bg-[var(--accent)]/15 text-[var(--accent)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
                      }`}>
                      <span>📄</span>
                      <span className="flex-1 truncate">{f.original_filename}</span>
                      {f.ai_summary && <span className="text-xs text-[var(--success)] shrink-0">已摘要</span>}
                      <span className="text-xs text-[var(--text-muted)] shrink-0">{f.file_type}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-16 text-[var(--text-muted)]">
            <img src="/空状态.png" alt="" className="w-40 h-40 mx-auto mb-4 object-contain" />
            <p>{searchResults ? '无搜索结果' : '暂无文件，上传后自动分类'}</p>
          </div>
        )}
      </div>

      {/* Right panel: file detail */}
      <div className="w-96 border-l border-[var(--border)] flex flex-col bg-[var(--bg-secondary)] overflow-auto">
        {selectedFile ? (
          <div className="p-5">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">📄</span>
              <h3 className="font-semibold text-sm flex-1 break-all">{selectedFile.original_filename}</h3>
            </div>

            {/* Meta */}
            <div className="space-y-2 text-xs text-[var(--text-secondary)] mb-4">
              <div className="flex justify-between"><span>资料库</span><span className="text-[var(--text-primary)]">{selectedFile.library_type}</span></div>
              <div className="flex justify-between"><span>文件夹</span><span className="text-[var(--text-primary)]">{selectedFile.folder_name}</span></div>
              <div className="flex justify-between"><span>格式</span><span className="text-[var(--text-primary)]">{selectedFile.file_type}</span></div>
              <div className="flex justify-between"><span>上传时间</span><span className="text-[var(--text-primary)]">{new Date(selectedFile.created_at).toLocaleDateString('zh-CN')}</span></div>
            </div>

            {/* AI Summary */}
            <div className="mb-4">
              <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                🤖 AI 摘要
                {!selectedFile.ai_summary && !summarizing && (
                  <button onClick={() => handleSelect(selectedFile)} className="text-xs text-[var(--accent)] bg-none border-none cursor-pointer hover:underline">生成</button>
                )}
              </h4>
              {summarizing ? (
                <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                  <img src="/加载中.png" alt="" className="w-8 h-8 object-contain" />
                  正在生成摘要...
                </div>
              ) : selectedFile.ai_summary ? (
                <p className="text-sm text-[var(--text-secondary)] bg-[var(--bg-tertiary)] rounded-lg p-3 leading-relaxed">{selectedFile.ai_summary}</p>
              ) : (
                <p className="text-xs text-[var(--text-muted)]">暂无摘要，点击生成</p>
              )}
            </div>

            {/* Style analysis (for 风格库) */}
            {selectedFile.style_analysis && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold mb-2">🎨 风格分析</h4>
                <pre className="text-xs text-[var(--text-secondary)] bg-[var(--bg-tertiary)] rounded-lg p-3 whitespace-pre-wrap leading-relaxed">{selectedFile.style_analysis}</pre>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              <a href={downloadUrl(selectedFile.id)} download
                className="flex-1 text-center px-4 py-2 bg-[var(--accent)] text-white border-none rounded-lg text-sm no-underline cursor-pointer hover:bg-[var(--accent-hover)] transition-colors">
                ⬇ 下载
              </a>
              <button onClick={() => handleDelete(selectedFile.id)}
                className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--danger)] border border-[var(--border)] rounded-lg text-sm cursor-pointer hover:bg-[var(--danger)]/10 transition-colors">
                🗑 删除
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-[var(--text-muted)] p-6 text-center">
            <div>
              <img src="/基础形象.png" alt="" className="w-32 h-32 mx-auto mb-4 object-contain opacity-50" />
              <p>点击左侧文件<br />查看详情和 AI 摘要</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
