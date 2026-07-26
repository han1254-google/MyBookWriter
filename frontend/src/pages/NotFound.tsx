import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] p-8">
      <img src="/404.png" alt="404" className="w-56 h-56 object-contain mb-6" />
      <h1 className="text-2xl font-bold mb-2 text-[var(--text-primary)]">页面未找到</h1>
      <p className="text-[var(--text-secondary)] mb-6">墨仔也迷路了...</p>
      <Link to="/" className="px-5 py-2.5 bg-[var(--accent)] text-white no-underline rounded-lg text-sm hover:bg-[var(--accent-hover)] transition-colors">
        返回首页
      </Link>
    </div>
  );
}
