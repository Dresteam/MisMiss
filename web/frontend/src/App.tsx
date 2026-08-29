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
import { AccountLoginPage } from './pages/AccountLoginPage';
import { AccountSetup } from './components/AccountSetup';
import { useToast, type Toast as ToastType } from './hooks/useToast';
import { AuthContext, useAuthState } from './hooks/useAuth';
import { isAccountPortalHost } from './utils/host';

// ------------------------------------------------------------------ #
// 账户入口路由树(user. 子域名):仅账户界面,无任何面板功能
// ------------------------------------------------------------------ #

function AccountPortalApp({
  dark, onToggleDark, sidebarCollapsed, onToggleSidebar, toasts, onRemoveToast,
}: {
  dark: boolean;
  onToggleDark: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  toasts: ToastType[];
  onRemoveToast: (id: number) => void;
}) {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route
          element={
            <Layout
              dark={dark}
              onToggleDark={onToggleDark}
              sidebarCollapsed={sidebarCollapsed}
              onToggleSidebar={onToggleSidebar}
              toasts={toasts}
              onRemoveToast={onRemoveToast}
            />
          }
        >
          <Route index element={<Navigate to="/account/home" replace />} />
          <Route path="account/home" element={<AccountOverviewPage />} />
          <Route path="account/live" element={<AccountLivePage />} />
          <Route path="account/bot" element={<AccountBotPage />} />
          <Route path="account/timer" element={<AccountTimerPage />} />
          <Route path="account/plugins" element={<AccountPluginsPage />} />
          <Route path="account/library" element={<AccountLibraryPage />} />
          <Route path="account/password" element={<AccountPasswordPage />} />
          <Route path="account/plugin/:name/page" element={<PluginPageView />} />
          <Route path="*" element={<Navigate to="/account/home" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
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

  // 固定子域名账户入口(user.localhost / user.<域名>)
  const accountPortal = isAccountPortalHost();

  if (auth.loading) {
    return <div className="min-h-screen bg-gray-100 dark:bg-gray-950" />;
  }

  // ------------------------------------------------------------------ #
  // 账户入口:user. 子域名 → 仅账户登录 + 账户管理界面
  // 身份完全由登录时输入的用户名/密码决定
  // ------------------------------------------------------------------ #
  if (accountPortal) {
    return (
      <AuthContext.Provider value={auth}>
        {(!auth.token || auth.role !== 'account') ? (
          // 未登录 / 管理员 token → 一律显示账户登录页
          <AccountLoginPage />
        ) : (
          <AccountPortalApp
            dark={dark}
            onToggleDark={() => setDark(!dark)}
            sidebarCollapsed={sidebarCollapsed}
            onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
            toasts={toasts}
            onRemoveToast={removeToast}
          />
        )}
      </AuthContext.Provider>
    );
  }

  // ------------------------------------------------------------------ #
  // 面板入口(主域名)
  // ------------------------------------------------------------------ #
  if (!auth.token) {
    return <LoginPage onLogin={() => window.location.reload()} />;
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

  return (
    <AuthContext.Provider value={auth}>
      {auth.firstLogin && showAccountSetup && (
        <AccountSetup firstLogin token={auth.token} onDone={handleAccountDone} />
      )}
      <BrowserRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            element={
              <Layout
                dark={dark}
                onToggleDark={() => setDark(!dark)}
                sidebarCollapsed={sidebarCollapsed}
                onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
                toasts={toasts}
                onRemoveToast={removeToast}
              />
            }
          >
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
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

export default App;
