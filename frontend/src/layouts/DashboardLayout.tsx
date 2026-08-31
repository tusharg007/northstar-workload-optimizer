import { useState } from 'react';
import { NavLink, Outlet, useLocation, Link } from 'react-router-dom';
import { cn } from '../lib/utils';
import {
  LayoutDashboard,
  PlusCircle,
  ClipboardCheck,
  BookOpen,
  Activity,
  Star,
  Menu,
  X,
  Sun,
  Moon
} from 'lucide-react';
import { useTheme } from '@/components/theme-provider';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/submit', icon: PlusCircle, label: 'Submit Expense' },
  { to: '/approvals', icon: ClipboardCheck, label: 'Approvals' },
  { to: '/context', icon: BookOpen, label: 'Governed Context' },
  { to: '/health', icon: Activity, label: 'System Health' },
];

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const location = useLocation();

  const getBreadcrumbs = () => {
    const path = location.pathname;
    if (path === '/') return [{ label: 'Dashboard', to: '/' }];
    
    const crumbs = [{ label: 'Dashboard', to: '/' }];
    if (path.startsWith('/submit')) crumbs.push({ label: 'Submit Expense', to: '/submit' });
    else if (path.startsWith('/approvals')) crumbs.push({ label: 'Approvals', to: '/approvals' });
    else if (path.startsWith('/expenses/')) crumbs.push({ label: 'Expense Detail', to: path });
    else if (path.startsWith('/context')) crumbs.push({ label: 'Governed Context', to: '/context' });
    else if (path.startsWith('/health')) crumbs.push({ label: 'System Health', to: '/health' });
    
    return crumbs;
  };

  const hostname = window.location.hostname;

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-950">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-brand-950 text-white transition-transform duration-200 lg:static lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 px-6 border-b border-brand-800">
          <Star className="h-7 w-7 text-amber-400 fill-amber-400" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">North Star</h1>
            <p className="text-[10px] uppercase tracking-widest text-brand-300">
              Expense Operations
            </p>
          </div>
        </div>

        {/* Nav links */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.to || (item.to !== '/' && location.pathname.startsWith(item.to));
            const reallyActive = item.to === '/' ? (location.pathname === '/' || location.pathname.startsWith('/expenses/')) : isActive;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  reallyActive
                    ? 'bg-brand-700 text-white'
                    : 'text-brand-200 hover:bg-brand-800 hover:text-white',
                )}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="border-t border-brand-800 px-6 py-4">
          <div className="flex items-center justify-between mb-4">
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="flex items-center justify-center w-8 h-8 rounded-md bg-brand-800 hover:bg-brand-700 text-brand-200 hover:text-white transition-colors"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
          <div className="flex items-center gap-2 text-xs text-brand-400">
            <div className="h-2 w-2 rounded-full bg-green-400 animate-pulse-dot" />
            <span>Governed Platform</span>
          </div>
          <div className="mt-1 flex gap-3 text-[10px] text-brand-500">
            <a href={`http://${hostname}:8000/docs`} target="_blank" rel="noreferrer" className="hover:text-brand-300">API Docs</a>
            <a href={`http://${hostname}:5679`} target="_blank" rel="noreferrer" className="hover:text-brand-300">n8n</a>
            <a href={`http://${hostname}:3000`} target="_blank" rel="noreferrer" className="hover:text-brand-300">Metabase</a>
          </div>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden dark:bg-gray-950">
        {/* Top bar */}
        <header className="flex h-16 items-center gap-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 lg:px-8">
          <button
            className="lg:hidden -ml-1 rounded-md p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
            onClick={() => setSidebarOpen(true)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          
          <div className="flex-1 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            {getBreadcrumbs().map((crumb, idx, arr) => (
              <span key={crumb.to} className="flex items-center gap-2">
                <Link to={crumb.to} className="hover:text-gray-900 dark:hover:text-gray-200 transition-colors">
                  {crumb.label}
                </Link>
                {idx < arr.length - 1 && <span>&gt;</span>}
              </span>
            ))}
          </div>

          <div className="flex items-center">
            <span className="border border-brand-300 text-brand-700 dark:border-brand-600 dark:text-brand-400 text-xs px-2 py-0.5 rounded-full">
              LOCAL DEV
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-8 dark:text-gray-100">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
