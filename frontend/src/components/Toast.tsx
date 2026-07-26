import { useAppStore } from '../store/appStore';

const emojiMap: Record<string, string> = {
  success: '/表情包-写完了.png',
  error: '/错误.png',
  info: '/表情包-查到了.png',
};

export default function Toast() {
  const { toasts, removeToast } = useAppStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => removeToast(t.id)}
          className={`flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-sm cursor-pointer transition-all animate-bounce ${
            t.type === 'success' ? 'bg-[var(--success)] text-white' :
            t.type === 'error' ? 'bg-[var(--danger)] text-white' :
            'bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)]'
          }`}
        >
          <img
            src={emojiMap[t.type] || '/toast.png'}
            alt=""
            className="w-8 h-8 object-contain rounded-full flex-shrink-0"
          />
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
