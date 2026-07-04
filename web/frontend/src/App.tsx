import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { BotPage } from './pages/BotPage';
import { LivePage } from './pages/LivePage';
import { PluginPage } from './pages/PluginPage';
import { ServerPage } from './pages/ServerPage';
import { LogsPage } from './pages/LogsPage';
import { SettingsPage } from './pages/SettingsPage';
import { LoginPage } from './pages/LoginPage';
import { AccountSetup } from './components/AccountSetup';
import { useToast } from './hooks/useToast';
import { AuthContext, useAuthState } from './hooks/useAuth';

function App() {
  const auth = useAuthState();
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
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

  if (auth.loading) {
    return <div className="min-h-screen bg-gray-100 dark:bg-gray-950" />;
  }

  if (!auth.token) {
    return <LoginPage onLogin={() => window.location.reload()} />;
  }

  return (
    <AuthContext.Provider value={auth}>
      {auth.firstLogin && (
        <AccountSetup token={auth.token} onDone={() => window.location.reload()} />
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
            <Route index element={<Dashboard />} />
            <Route path="bot" element={<BotPage />} />
            <Route path="live" element={<LivePage />} />
            <Route path="plugin" element={<PluginPage />} />
            <Route path="server" element={<ServerPage />} />
            <Route path="logs" element={<LogsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

export default App;
