import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
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
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/submit', icon: PlusCircle, label: 'Submit Expense' },
  { to: '/approvals', icon: ClipboardCheck, label: 'Approvals' },
  { to: '/context', icon: BookOpen, label: 'Governed Context' },
  { to: '/health', icon: Activity, label: 'System Health' },
];

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
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
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-700 text-white'
                    : 'text-brand-200 hover:bg-brand-800 hover:text-white',
                )
              }
            >
              <item.icon className="h-5 w-5 flex-shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-brand-800 px-6 py-4">
          <div className="flex items-center gap-2 text-xs text-brand-400">
            <div className="h-2 w-2 rounded-full bg-green-400 animate-pulse-dot" />
            <span>Governed Platform</span>
          </div>
          <div className="mt-1 flex gap-3 text-[10px] text-brand-500">
            <a
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="hover:text-brand-300"
            >
              API Docs
            </a>
            <a
              href="http://127.0.0.1:5679"
              target="_blank"
              rel="noreferrer"
              className="hover:text-brand-300"
            >
              n8n
            </a>
            <a
              href="http://127.0.0.1:3000"
              target="_blank"
              rel="noreferrer"
              className="hover:text-brand-300"
            >
              Metabase
            </a>
          </div>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-16 items-center gap-4 border-b border-gray-200 bg-white px-4 lg:px-8">
          <button
            className="lg:hidden -ml-1 rounded-md p-2 text-gray-500 hover:bg-gray-100"
            onClick={() => setSidebarOpen(true)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="hidden sm:inline">Deterministic Policy • Governed Context • Immutable Provenance</span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
