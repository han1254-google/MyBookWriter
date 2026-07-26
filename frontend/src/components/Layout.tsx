import { NavLink, Outlet } from 'react-router-dom';
import { useAppStore } from '../store/appStore';
import Toast from './Toast';

const navItems = [
  { to: '/', icon: '🏠', label: '首页' },
  { to: '/upload', icon: '📁', label: '资料管理' },
  { to: '/ideas', icon: '💡', label: '创意工坊' },
  { to: '/outlines', icon: '📋', label: '大纲工坊' },
  { to: '/writing', icon: '✍️', label: '写作工坊' },
  { to: '/rewrite', icon: '🔧', label: '改写工坊' },
];

export default function Layout() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore();

  return (
    <div className="flex h-screen bg-[var(--bg-primary)] text-[var(--text-primary)]">
      {/* Sidebar */}
      <aside className={`flex flex-col bg-[var(--bg-secondary)] border-r border-[var(--border)] transition-all duration-200 ${sidebarCollapsed ? 'w-16' : 'w-56'}`}>
        <div className="p-4 border-b border-[var(--border)]">
          <div className="flex items-center justify-between">
            {!sidebarCollapsed && (
              <div>
                <h1 className="text-lg font-bold m-0">📚 MyBookApps</h1>
                <p className="text-xs text-[var(--text-muted)] m-0">科幻写作助手</p>
              </div>
            )}
            <button onClick={toggleSidebar} className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-lg bg-none border-none cursor-pointer">
              {sidebarCollapsed ? '▶' : '◀'}
            </button>
          </div>
        </div>

        <nav className="flex-1 py-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 text-sm no-underline transition-colors ${
                  isActive
                    ? 'bg-[var(--accent)] bg-opacity-15 text-[var(--accent)] border-r-2 border-[var(--accent)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]'
                }`
              }
            >
              <span className="text-lg">{item.icon}</span>
              {!sidebarCollapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-[var(--border)]">
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="w-2 h-2 rounded-full bg-[var(--success)]" />
            {!sidebarCollapsed && 'DeepSeek API'}
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>

      <Toast />
    </div>
  );
}
