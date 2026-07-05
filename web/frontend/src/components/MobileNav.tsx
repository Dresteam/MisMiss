import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Bot, Radio, Puzzle, Terminal,
  Moon, Sun, LogOut,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const items = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘', end: true },
  { to: '/bot', icon: Bot, label: 'Bot' },
  { to: '/live', icon: Radio, label: '直播间' },
  { to: '/plugin', icon: Puzzle, label: '插件' },
  { to: '/logs', icon: Terminal, label: '日志' },
];

interface Props {
  dark: boolean;
  onToggleDark: () => void;
}

export function MobileNav({ dark, onToggleDark }: Props) {
  const { logout } = useAuth();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-30 lg:hidden
                    bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700
                    safe-bottom">
      <div className="flex items-center justify-around h-14">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-0.5 min-w-0 flex-1 h-full
               transition-colors
               ${isActive
                  ? 'text-primary-600 dark:text-primary-400'
                  : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400'
               }`
            }
          >
            <item.icon className="w-5 h-5 shrink-0" />
            <span className="text-[10px] leading-none truncate">{item.label}</span>
          </NavLink>
        ))}
        {/* Theme toggle */}
        <button onClick={onToggleDark}
          className="flex flex-col items-center justify-center gap-0.5 min-w-0 flex-1 h-full
                     text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400">
          {dark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          <span className="text-[10px] leading-none truncate">{dark ? '浅色' : '深色'}</span>
        </button>
        {/* Logout */}
        <button onClick={logout}
          className="flex flex-col items-center justify-center gap-0.5 min-w-0 flex-1 h-full
                     text-gray-400 dark:text-gray-500 hover:text-red-500 transition-colors">
          <LogOut className="w-5 h-5" />
          <span className="text-[10px] leading-none truncate">退出</span>
        </button>
      </div>
    </nav>
  );
}
