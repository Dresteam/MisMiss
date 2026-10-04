import { useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { Sidebar, type NavGroup } from './Sidebar';
import { ToastContainer } from './Toast';
import { Menu, X, Moon, Sun, LogOut, LayoutDashboard, Puzzle, Server, Settings, Terminal, Download, Radio, Bot, Clock, KeyRound, BookOpen } from 'lucide-react';
import type { Toast as ToastType } from '../hooks/useToast';
import { useAuth } from '../hooks/useAuth';

interface Props {
  dark: boolean;
  onToggleDark: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  /** 透传给侧栏的「重看指引」 */
  onReplayGuide: () => void;
  toasts: ToastType[];
  onRemoveToast: (id: number) => void;
}

const mobileGroups: NavGroup[] = [
  {
    title: '监控',
    items: [
      { to: '/', icon: LayoutDashboard, label: '账户总览', end: true },
      { to: '/logs', icon: Terminal, label: '日志' , end: false },
    ],
  },
  {
    title: '管理',
    items: [
      { to: '/library', icon: Puzzle, label: '插件库' , end: false },
    ],
  },
  {
    title: '系统',
    items: [
      { to: '/server', icon: Server, label: '服务器' , end: false },
      { to: '/update', icon: Download, label: '程序更新' , end: false },
      { to: '/settings', icon: Settings, label: '设置' , end: false },
    ],
  },
];

const accountMobileGroups: NavGroup[] = [
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

export function Layout({
  dark,
  onToggleDark,
  sidebarCollapsed,
  onToggleSidebar,
  onReplayGuide,
  toasts,
  onRemoveToast,
}: Props) {
  const { logout, role } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const groups = role === 'account' ? accountMobileGroups : mobileGroups;

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      {/* Desktop sidebar */}
      <div className="hidden lg:block">
        <Sidebar
          dark={dark}
          onToggleDark={onToggleDark}
          collapsed={sidebarCollapsed}
          onToggleCollapse={onToggleSidebar}
          onReplayGuide={onReplayGuide}
        />
      </div>

      {/* Mobile top bar */}
      <div className="lg:hidden sticky top-0 z-20 flex items-center justify-between h-12 px-3
                      bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        {/* data-guide="nav-menu"：手机端「切到某页」那一步的兜底锚点 ——
            抽屉没拉开时导航项都不存在，只能圈这个按钮 */}
        <button onClick={() => setMobileMenuOpen(true)} data-guide="nav-menu"
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="打开菜单">
          <Menu className="w-5 h-5" />
        </button>
        <span className="font-semibold text-gray-900 dark:text-white">MisMiss Console</span>
        <button onClick={onToggleDark}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="切换主题">
          {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
            onClick={() => setMobileMenuOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-64 bg-white dark:bg-gray-900
                          shadow-2xl animate-slide-in-left flex flex-col">
            <div className="flex items-center justify-between h-12 px-4 border-b border-gray-200 dark:border-gray-700">
              <span className="font-bold text-gray-900 dark:text-white">MisMiss</span>
              <button onClick={() => setMobileMenuOpen(false)}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
                <X className="w-4 h-4" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
              {groups.map((group) => (
                <div key={group.title}>
                  <p className="px-3 mb-1 text-[10px] font-medium text-gray-400 uppercase tracking-wider">
                    {group.title}
                  </p>
                  <div className="space-y-0.5">
                    {group.items.map((item) => {
                      // w-full：<a> 本来就撑满，<button> 不写只裹住文字，两者点击区就对不齐
                      const cls = (isActive: boolean) =>
                        `flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                         ${isActive
                          ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`;
                      // action 项（「重看指引」）不跳路由。点完必须先把抽屉关掉 ——
                      // 抽屉是整屏的，不关就盖在蒙版上面
                      return item.to ? (
                        <NavLink key={item.label} to={item.to} end={item.end} data-guide={item.guide}
                          onClick={() => setMobileMenuOpen(false)}
                          className={({ isActive }) => cls(isActive)}>
                          <item.icon className="w-5 h-5 shrink-0" />
                          {item.label}
                        </NavLink>
                      ) : (
                        <button key={item.label} type="button"
                          onClick={() => { setMobileMenuOpen(false); onReplayGuide(); }}
                          className={cls(false)}>
                          <item.icon className="w-5 h-5 shrink-0" />
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>
            <div className="p-2 border-t border-gray-200 dark:border-gray-700">
              <button onClick={logout}
                className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                <LogOut className="w-5 h-5" />
                退出登录
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className={`transition-all duration-300 lg:ml-16 ${!sidebarCollapsed ? 'lg:ml-64' : ''}`}>
        <div className="p-3 lg:p-6">
          <Outlet />
        </div>
      </main>

      <ToastContainer toasts={toasts} onRemove={onRemoveToast} />
    </div>
  );
}
