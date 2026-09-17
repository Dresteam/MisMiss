import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AccountsPage } from './pages/AccountsPage';
import { AccountDetailPage } from './pages/AccountDetailPage';
import {
  AccountOverviewPage, AccountLivePage, AccountBotPage, AccountTimerPage, AccountPluginsPage,
  AccountLibraryPage, AccountPasswordPage,
} from './pages/AccountPortalPages';
import { PluginLibraryPage } from './pages/PluginLibraryPage';
import { ServerPage } from './pages/ServerPage';
import { LogsPage } from './pages/LogsPage';
import { SettingsPage } from './pages/SettingsPage';
import { PluginPageView } from './pages/PluginPageView';
import { UpdatePage } from './pages/UpdatePage';
import { LoginPage } from './pages/LoginPage';
import { AccountSetup } from './components/AccountSetup';
import { ChangelogDialog } from './components/ChangelogDialog';
import { useToast, type Toast as ToastType } from './hooks/useToast';
import { AuthContext, useAuthState } from './hooks/useAuth';

interface ShellProps {
  dark: boolean;
  onToggleDark: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  toasts: ToastType[];
  onRemoveToast: (id: number) => void;
}

function App() {
  const auth = useAuthState();
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    if (saved) return saved === 'dark';
    return false; // 默认白色主题
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('sidebar_collapsed') === 'true';
  });

  useEffect(() => {
    localStorage.setItem('sidebar_collapsed', String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const { toasts, removeToast } = useToast();

  // 本地控制首次登录对话框——跳过即隐藏，不依赖 server 端 first_login 标志
  const [showAccountSetup, setShowAccountSetup] = useState(true);
  // 本地控制更新日志弹窗——关闭即隐藏，同时向服务端 ack
  const [changelogDismissed, setChangelogDismissed] = useState(false);

  if (auth.loading) {
    return <div className="min-h-screen bg-gray-100 dark:bg-gray-950" />;
  }

  // 未登录:管理端与账户端共用同一个登录页，身份由凭据决定
  if (!auth.token) {
    return (
      <AuthContext.Provider value={auth}>
        <LoginPage />
      </AuthContext.Provider>
    );
  }

  const handleAccountDone = async () => {
    setShowAccountSetup(false);
    // 告知后端跳过首次登录引导，下次不再弹出
    try {
      await fetch('/api/auth/skip-first-login', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + auth.token },
      });
    } catch { /* ignore */ }
  };

  const handleChangelogClose = async () => {
    setChangelogDismissed(true);
    // 版本号由服务端取当前版本，客户端不上报
    try {
      await fetch('/api/auth/ack-changelog', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + auth.token },
      });
    } catch { /* ignore */ }
  };

  const shell: ShellProps = {
    dark,
    onToggleDark: () => setDark(!dark),
    sidebarCollapsed,
    onToggleSidebar: () => setSidebarCollapsed(!sidebarCollapsed),
    toasts,
    onRemoveToast: removeToast,
  };

  return (
    <AuthContext.Provider value={auth}>
      {auth.firstLogin && showAccountSetup && (
        <AccountSetup firstLogin token={auth.token} onDone={handleAccountDone} />
      )}
      {auth.role === 'account' && auth.pendingChangelog && !changelogDismissed && (
        <ChangelogDialog
          open
          version={auth.pendingChangelog.version}
          title={auth.pendingChangelog.title}
          body={auth.pendingChangelog.body}
          onClose={handleChangelogClose}
        />
      )}
      <BrowserRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route element={<Layout {...shell} />}>
            <Route index element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <AccountsPage />} />
            <Route path="account/home" element={<AccountOverviewPage />} />
            <Route path="account/live" element={auth.role === 'account' ? <AccountLivePage /> : <Navigate to="/" replace />} />
            <Route path="account/bot" element={auth.role === 'account' ? <AccountBotPage /> : <Navigate to="/" replace />} />
            <Route path="account/timer" element={auth.role === 'account' ? <AccountTimerPage /> : <Navigate to="/" replace />} />
            <Route path="account/plugins" element={auth.role === 'account' ? <AccountPluginsPage /> : <Navigate to="/" replace />} />
            <Route path="account/library" element={auth.role === 'account' ? <AccountLibraryPage /> : <Navigate to="/" replace />} />
            <Route path="account/password" element={auth.role === 'account' ? <AccountPasswordPage /> : <Navigate to="/" replace />} />
            <Route path="account/plugin/:name/page" element={auth.role === 'account' ? <PluginPageView /> : <Navigate to="/" replace />} />
            <Route path="account/:id" element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <AccountDetailPage />} />
            <Route path="account/:id/plugin/:name/page" element={<PluginPageView />} />
            <Route path="library" element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <PluginLibraryPage />} />
            <Route path="server" element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <ServerPage />} />
            <Route path="logs" element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <LogsPage />} />
            <Route path="settings" element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <SettingsPage />} />
            <Route path="update" element={auth.role === 'account' ? <Navigate to="/account/home" replace /> : <UpdatePage />} />
            <Route path="*" element={<Navigate to={auth.role === 'account' ? '/account/home' : '/'} replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

export default App;
