import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { MobileNav } from './MobileNav';
import { ToastContainer } from './Toast';
import type { Toast as ToastType } from '../hooks/useToast';

interface Props {
  dark: boolean;
  onToggleDark: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  toasts: ToastType[];
  onRemoveToast: (id: number) => void;
}

export function Layout({
  dark,
  onToggleDark,
  sidebarCollapsed,
  onToggleSidebar,
  toasts,
  onRemoveToast,
}: Props) {
  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      <div className="hidden lg:block">
        <Sidebar
          dark={dark}
          onToggleDark={onToggleDark}
          collapsed={sidebarCollapsed}
          onToggleCollapse={onToggleSidebar}
        />
      </div>
      <main
        className={`transition-all duration-300 pb-16 lg:pb-0
          lg:ml-16 ${!sidebarCollapsed ? 'lg:ml-64' : ''}`}
      >
        <div className="p-4 lg:p-6">
          <Outlet />
        </div>
      </main>
      <MobileNav />
      <ToastContainer toasts={toasts} onRemove={onRemoveToast} />
    </div>
  );
}
