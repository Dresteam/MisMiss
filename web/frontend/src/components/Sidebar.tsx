import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Puzzle, Server, Settings,
  Moon, Sun, Terminal, ChevronLeft, ChevronRight, LogOut,
  Download, Radio, Bot, Clock, KeyRound, BookOpen, type LucideIcon } from 'lucide-react';
import { t } from '../i18n';
import { useAuth } from '../hooks/useAuth';

interface Props {
  dark: boolean;
  onToggleDark: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  /** 点「重看指引」—— 该入口不跳路由，理由见 NavItem.action */
  onReplayGuide: () => void;
}

/**
 * 导航项。多数项靠 `to` 跳路由；`action` 项**不占路由**，点了就地做一件事。
 * 「重看指引」是后者：指引现在就是在主页上浮的一层蒙版，没有独立页面可去。
 */
export interface NavItem {
  icon: LucideIcon;
  label: string;
  to?: string;
  end?: boolean;
  action?: 'replay-guide';
  /**
   * 操作指引的「切到这一页」步骤靠它高亮（值要与 GuideOverlay 的 navTarget 对上）。
   * 只有指引覆盖到的那几页标了 —— 定时消息、修改密码不在指引里，标了也没人用。
   */
  guide?: string;
}

export interface NavGroup { title: string; items: NavItem[] }

// 与移动端菜单相同的分组分类
const adminNavGroups: NavGroup[] = [
  {
    title: t('sidebar.groupMonitor'),
    items: [
      { to: '/', icon: LayoutDashboard, label: t('sidebar.accounts'), end: true },
      { to: '/logs', icon: Terminal, label: t('sidebar.logs') , end: false },
    ],
  },
  {
    title: t('sidebar.groupManage'),
    items: [
      { to: '/library', icon: Puzzle, label: t('sidebar.pluginLibrary') , end: false },
    ],
  },
  {
    title: t('sidebar.groupSystem'),
    items: [
      { to: '/server', icon: Server, label: t('sidebar.server') , end: false },
      { to: '/update', icon: Download, label: t('sidebar.update') , end: false },
      { to: '/settings', icon: Settings, label: t('sidebar.settings') , end: false },
    ],
  },
];

// 账户持有者:v1.0.1 风格左侧导航(无面板功能)
const accountNavGroups: NavGroup[] = [
  {
    title: '监控',
    items: [
      { to: '/account/home', icon: LayoutDashboard, label: '概览', end: true, guide: 'nav-home' },
    ],
  },
  {
    title: '管理',
    items: [
      { to: '/account/live', icon: Radio, label: '直播间' , end: false, guide: 'nav-live' },
      { to: '/account/bot', icon: Bot, label: 'Bot' , end: false, guide: 'nav-bot' },
      { to: '/account/timer', icon: Clock, label: '定时消息' , end: false },
      { to: '/account/plugins', icon: Puzzle, label: '插件' , end: false, guide: 'nav-plugins' },
      { to: '/account/library', icon: Puzzle, label: '插件库' , end: false, guide: 'nav-library' },
    ],
  },
  {
    title: '系统',
    items: [
      { to: '/account/password', icon: KeyRound, label: '修改密码' , end: false },
      { icon: BookOpen, label: '重看指引', action: 'replay-guide' },
    ],
  },
];

export function Sidebar({ dark, onToggleDark, collapsed, onToggleCollapse, onReplayGuide }: Props) {
  const { logout, role } = useAuth();
  const navGroups = role === 'account' ? accountNavGroups : adminNavGroups;
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
                    transition-[width] duration-300
                    ${collapsed ? 'w-16 overflow-visible' : 'w-64 overflow-hidden'}`}
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
        <nav className={`flex-1 py-4 px-2 space-y-4 ${collapsed ? 'overflow-visible' : 'overflow-y-auto'}`}>
          {navGroups.map((group) => (
            <div key={group.title}>
              {!collapsed && (
                <p className="px-3 mb-1 text-[10px] font-medium text-surface-500 dark:text-surface-400 uppercase tracking-wider">
                  {group.title}
                </p>
              )}
              <div className="space-y-1">
                {group.items.map((item) => {
                  const content = (
                    <>
                      <item.icon className="w-5 h-5 shrink-0" />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                      {collapsed && (
                        <span
                          role="tooltip"
                          className="pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50
                                     whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                                     bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                                     opacity-0 group-hover:opacity-100 transition-opacity duration-100"
                        >
                          {item.label}
                        </span>
                      )}
                    </>
                  );
                  // w-full 是给下面那个 <button> 用的：<a> 是块级盒子，宽度本来就撑满，
                  // 而按钮不写就只裹住文字，点起来比上面几项窄一截
                  const cls = (isActive: boolean) =>
                    `relative flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium
                     transition-all duration-200 group
                     ${isActive
                        ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                        : 'text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 hover:text-surface-900 dark:hover:text-surface-200'
                     }`;
                  // action 项点了就地做事、不跳路由，所以是 button 不是 NavLink
                  return item.to ? (
                    <NavLink key={item.label} to={item.to} end={item.end} data-guide={item.guide}
                      className={({ isActive }) => cls(isActive)}>
                      {content}
                    </NavLink>
                  ) : (
                    <button key={item.label} type="button" onClick={onReplayGuide}
                      className={cls(false)}>
                      {content}
                    </button>
                  );
                })}
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
            {collapsed && (
              <span
                role="tooltip"
                className="pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50
                           whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                           bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                           opacity-0 group-hover:opacity-100 transition-opacity duration-100"
              >
                {dark ? t('sidebar.lightMode') : t('sidebar.darkMode')}
              </span>
            )}
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
