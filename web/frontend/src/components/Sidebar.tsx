import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Bot, Radio, Puzzle, Server, Settings,
  Moon, Sun, Terminal, ChevronLeft, ChevronRight, LogOut,
  Clock, Download,
} from 'lucide-react';
import { t } from '../i18n';
import { useAuth } from '../hooks/useAuth';
import { HoverTip } from './HoverTip';

interface Props {
  dark: boolean;
  onToggleDark: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

// 与移动端菜单相同的分组分类
const navGroups = [
  {
    title: t('sidebar.groupMonitor'),
    items: [
      { to: '/', icon: LayoutDashboard, label: t('sidebar.dashboard'), end: true },
      { to: '/logs', icon: Terminal, label: t('sidebar.logs') },
    ],
  },
  {
    title: t('sidebar.groupManage'),
    items: [
      { to: '/bot', icon: Bot, label: t('sidebar.botManagement') },
      { to: '/live', icon: Radio, label: t('sidebar.livestream') },
      { to: '/plugin', icon: Puzzle, label: t('sidebar.pluginCenter') },
      { to: '/timer', icon: Clock, label: t('sidebar.timer') },
    ],
  },
  {
    title: t('sidebar.groupSystem'),
    items: [
      { to: '/server', icon: Server, label: t('sidebar.server') },
      { to: '/update', icon: Download, label: t('sidebar.update') },
      { to: '/settings', icon: Settings, label: t('sidebar.settings') },
    ],
  },
];

export function Sidebar({ dark, onToggleDark, collapsed, onToggleCollapse }: Props) {
  const { logout } = useAuth();
  const [version, setVersion] = useState('');

  // 当前版本号（显示在 Logo 旁）
  useEffect(() => {
    (async () => {
      try {
        const token = localStorage.getItem('auth_token');
        const res = await fetch('/api/update/info', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const data = await res.json();
        if (data?.current_version) setVersion(data.current_version);
      } catch { /* ignore */ }
    })();
  }, []);

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
                  {version && (
                    <span className="ml-1.5 text-[10px] font-normal text-surface-500 dark:text-surface-400 leading-none">
                      v{version}
                    </span>
                  )}
                </h1>
                <p className="text-[10px] text-surface-500 dark:text-surface-400 leading-tight">
                  {t('sidebar.appSubtitle')}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-2 space-y-4 overflow-y-auto">
          {navGroups.map((group) => (
            <div key={group.title}>
              {!collapsed && (
                <p className="px-3 mb-1 text-[10px] font-medium text-surface-500 dark:text-surface-400 uppercase tracking-wider">
                  {group.title}
                </p>
              )}
              <div className="space-y-1">
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                       transition-all duration-200 group
                       ${isActive
                          ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                          : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-900 dark:hover:text-surface-200'
                       }`
                    }
                  >
                    <item.icon className="w-5 h-5 shrink-0" />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                    {collapsed && <HoverTip text={item.label} />}
                  </NavLink>
                ))}
              </div>
            </div>
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
            className="relative group flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm
                       text-surface-600 dark:text-surface-400
                       hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors"
          >
            {dark ? <Sun className="w-5 h-5 shrink-0" /> : <Moon className="w-5 h-5 shrink-0" />}
            {!collapsed && <span className="whitespace-nowrap">{dark ? t('sidebar.lightMode') : t('sidebar.darkMode')}</span>}
            {collapsed && <HoverTip text={dark ? t('sidebar.lightMode') : t('sidebar.darkMode')} />}
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
