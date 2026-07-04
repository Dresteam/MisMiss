import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Bot, Radio, Puzzle, Server, Settings,
  Moon, Sun, Terminal, ChevronLeft, ChevronRight, LogOut,
} from 'lucide-react';
import { t } from '../i18n';
import { useAuth } from '../hooks/useAuth';

interface Props {
  dark: boolean;
  onToggleDark: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const navItems = [
  { to: '/', icon: LayoutDashboard, label: t('sidebar.dashboard'), end: true },
  { to: '/bot', icon: Bot, label: t('sidebar.botManagement') },
  { to: '/live', icon: Radio, label: t('sidebar.livestream') },
  { to: '/plugin', icon: Puzzle, label: t('sidebar.pluginCenter') },
  { to: '/server', icon: Server, label: t('sidebar.server') },
  { to: '/logs', icon: Terminal, label: t('sidebar.logs') },
  { to: '/settings', icon: Settings, label: t('sidebar.settings') },
];

export function Sidebar({ dark, onToggleDark, collapsed, onToggleCollapse }: Props) {
  const { logout } = useAuth();
  return (
    <>
      {/* Mobile overlay */}
      {!collapsed && (
        <div
          className="fixed inset-0 bg-black/50 z-20 lg:hidden"
          onClick={onToggleCollapse}
        />
      )}

      <aside
        className={`fixed top-0 left-0 h-full z-30 flex flex-col
                    bg-white dark:bg-surface-900 border-r border-surface-200 dark:border-surface-700
                    transition-[width] duration-300 overflow-hidden
                    ${collapsed ? 'w-16' : 'w-64'}`}
      >
        {/* Logo */}
        <div className="flex items-center h-16 px-4 border-b border-surface-200 dark:border-surface-700">
          <div className="flex items-center gap-3 min-w-0">
            <div className="shrink-0 w-9 h-9 rounded-lg bg-primary-600 flex items-center justify-center">
              <Terminal className="w-5 h-5 text-white" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <h1 className="text-lg font-bold text-surface-900 dark:text-white truncate">
                  {t('sidebar.appName')}
                </h1>
                <p className="text-[10px] text-surface-500 dark:text-surface-400 leading-tight">
                  {t('sidebar.appSubtitle')}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                 transition-all duration-200 group
                 ${isActive
                    ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                    : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-900 dark:hover:text-surface-200'
                 }`
              }
            >
              <item.icon className="w-5 h-5 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Footer actions */}
        <div className="p-2 border-t border-surface-200 dark:border-surface-700 space-y-1">
          <button
            onClick={logout}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm
                       text-surface-600 dark:text-surface-400
                       hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          >
            <LogOut className="w-5 h-5 shrink-0" />
            {!collapsed && <span className="whitespace-nowrap">退出登录</span>}
          </button>
          <button
            onClick={onToggleDark}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm
                       text-surface-600 dark:text-surface-400
                       hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
            title={dark ? t('sidebar.lightMode') : t('sidebar.darkMode')}
          >
            {dark ? <Sun className="w-5 h-5 shrink-0" /> : <Moon className="w-5 h-5 shrink-0" />}
            {!collapsed && <span className="whitespace-nowrap">{dark ? t('sidebar.lightMode') : t('sidebar.darkMode')}</span>}
          </button>

          <button
            onClick={onToggleCollapse}
            className="hidden lg:flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm
                       text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          >
            {collapsed ? (
              <ChevronRight className="w-5 h-5 shrink-0" />
            ) : (
              <ChevronLeft className="w-5 h-5 shrink-0" />
            )}
            {!collapsed && <span className="whitespace-nowrap">{t('sidebar.collapse')}</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
