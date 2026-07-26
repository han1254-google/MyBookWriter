import { useState, useEffect, useCallback } from 'react';
import { uploadApi } from '../api/client';
import { useAppStore } from '../store/appStore';

export default function UploadPage() {
  const { addToast } = useAppStore();
  const [libraries, setLibraries] = useState<Record<string, Record<string, string[]>>>({});
  const [files, setFiles] = useState<Array<Record<string, unknown>>>([]);
  const [activeLib, setActiveLib] = useState('知识库');
  const [uploading, setUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const loadData = useCallback(() => {
    uploadApi.getLibraries().then((data) => {
      setLibraries(data.structure);
      setFiles(data.files);
    }).catch(() => {});
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const result = await uploadApi.upload(file);
      addToast(`✅ ${file.name} → ${result.library_type}/${result.folder_name}`, 'success');
      setUploadDone(true);
      setTimeout(() => setUploadDone(false), 3000);
      loadData();
    } catch (e: unknown) {
      addToast(`❌ ${(e as Error).message}`, 'error');
    }
    setUploading(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    Array.from(e.dataTransfer.files).forEach(handleUpload);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      Array.from(e.target.files).forEach(handleUpload);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await uploadApi.deleteFile(id);
      addToast('已删除', 'success');
      loadData();
    } catch (e: unknown) {
      addToast(`删除失败: ${(e as Error).message}`, 'error');
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-1">📁 资料管理</h1>
      <p className="text-[var(--text-secondary)] mb-6">上传 PDF/EPUB/Word/TXT 文件，AI 自动分类</p>

      {/* Upload zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        className={`border-2 border-dashed rounded-xl p-10 text-center mb-8 transition-colors cursor-pointer ${
          dragOver ? 'border-[var(--accent)] bg-[var(--accent)] bg-opacity-5' : 'border-[var(--border)]'
        }`}
        onClick={() => document.getElementById('file-input')?.click()}
      >
        {uploadDone ? (
          <img src="/上传成功.png" alt="上传成功" className="w-24 h-24 mx-auto mb-3 object-contain animate-bounce" />
        ) : (
          <div className="text-5xl mb-3">{uploading ? '⏳' : '📤'}</div>
        )}
        <p className="text-lg font-medium">{uploadDone ? '上传成功！AI 已自动分类' : uploading ? '正在上传并分析...' : '拖拽文件到此处，或点击选择'}</p>
        <p className="text-sm text-[var(--text-muted)] mt-1">支持 PDF / EPUB / DOCX / TXT / MD</p>
        <input id="file-input" type="file" hidden multiple accept=".pdf,.epub,.docx,.doc,.txt,.md" onChange={handleFileInput} />
      </div>

      {/* Library tabs */}
      <div className="flex gap-2 mb-4">
        {['知识库', '参考库', '风格库'].map((lib) => (
          <button
            key={lib}
            onClick={() => setActiveLib(lib)}
            className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
              activeLib === lib
                ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border)] hover:border-[var(--accent)]'
            }`}
          >
            {{ '知识库': '📚', '参考库': '📖', '风格库': '🎨' }[lib]} {lib}
          </button>
        ))}
      </div>

      {/* Files by folder */}
      {libraries[activeLib] && Object.keys(libraries[activeLib]).length > 0 ? (
        <div className="space-y-4">
          {Object.entries(libraries[activeLib]).map(([folder, folderFiles]) => (
            <div key={folder} className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl p-4">
              <h3 className="font-semibold mb-2 flex items-center gap-2">
                <span>📂</span> {folder}
                <span className="text-xs text-[var(--text-muted)] font-normal">({folderFiles.length} 个文件)</span>
              </h3>
              <div className="space-y-1">
                {folderFiles.map((f) => (
                  <div key={f} className="flex items-center gap-2 text-sm text-[var(--text-secondary)] py-1 px-2 rounded hover:bg-[var(--bg-tertiary)]">
                    <span>📄</span>
                    <span className="flex-1 truncate">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 text-[var(--text-muted)]">
          <img src="/空状态.png" alt="空状态" className="w-40 h-40 mx-auto mb-4 object-contain" />
          <p>暂无文件，上传后自动分类到这里</p>
        </div>
      )}

      {/* Recent uploads table */}
      {files.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold mb-3">最近上传</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[var(--text-muted)] border-b border-[var(--border)]">
                  <th className="pb-2 font-medium">文件名</th>
                  <th className="pb-2 font-medium">资料库</th>
                  <th className="pb-2 font-medium">文件夹</th>
                  <th className="pb-2 font-medium">时间</th>
                  <th className="pb-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f: Record<string, unknown>) => (
                  <tr key={f.id as number} className="border-b border-[var(--border)] last:border-0">
                    <td className="py-2 truncate max-w-[200px]">{f.original_filename as string}</td>
                    <td className="py-2">
                      <span className="px-2 py-0.5 rounded text-xs bg-[var(--bg-tertiary)]">{f.library_type as string}</span>
                    </td>
                    <td className="py-2 text-[var(--text-secondary)]">{f.folder_name as string}</td>
                    <td className="py-2 text-[var(--text-muted)] text-xs">{new Date(f.created_at as string).toLocaleDateString('zh-CN')}</td>
                    <td className="py-2">
                      <button onClick={() => handleDelete(f.id as number)} className="text-[var(--danger)] hover:underline text-xs bg-none border-none cursor-pointer">删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
