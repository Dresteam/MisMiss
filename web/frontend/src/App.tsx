import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AccountsPage } from './pages/AccountsPage';
import { AccountDetailPage } from './pages/AccountDetailPage';
import {
  AccountOverviewPage, AccountLivePage, AccountBotPage, AccountTimerPage, AccountPluginsPage,
  AccountLibraryPage, AccountPasswordPage } from './pages/AccountPortalPages';
import { GuideOverlay, GuideActiveContext } from './components/GuideOverlay';
import { PluginLibraryPage } from './pages/PluginLibraryPage';
import { ServerPage } from './pages/ServerPage';
import { LogsPage } from './pages/LogsPage';
import { SettingsPage } from './pages/SettingsPage';
import { PluginPageView } from './pages/PluginPageView';
import { UpdatePage } from './pages/UpdatePage';
import { LoginPage } from './pages/LoginPage';
import { AccountSetup } from './components/AccountSetup';
import { ForcePasswordChange } from './components/ForcePasswordChange';
import { ChangelogDialog } from './components/ChangelogDialog';
import { ConfirmDialog } from './components/ConfirmDialog';
import { useToast, type Toast as ToastType } from './hooks/useToast';
import { AuthContext, useAuthState } from './hooks/useAuth';

interface ShellProps {
  dark: boolean;
  onToggleDark: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  /** 侧栏「重看指引」：起一次本地的指引蒙版（不落盘，刷新即失效） */
  onReplayGuide: () => void;
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
  // 「重看指引」纯本地：指引本身就是在主页上浮一层蒙版，没有自己的路由可去，
  // 所以重看不需要服务端把 guide_seen_version 改回未读（刷新即失效，可接受）
  const [replayGuide, setReplayGuide] = useState(false);
  // 重看前的二次确认。指引一浮起来就挡住内容区，误触代价不小，值得问一句
  const [confirmReplay, setConfirmReplay] = useState(false);
  // 每次重看自增，用作 Overlay 的 key 强制重挂载 —— 否则指引正浮着时点「重看」
  // 什么都不会发生，又成了「点了没反应」
  const [guideRun, setGuideRun] = useState(0);

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

  // **只有点「跳过」或「完成」才走这里**。从侧栏溜走、切页、卸载都不算读过 ——
  // 所以这个 ack 只能挂在那两个按钮上，不能挂在路由变化或组件卸载上
  const handleGuideDone = async () => {
    setReplayGuide(false);
    auth.clearShowGuide();
    // 版本号由服务端取当前 GUIDE_VERSION，客户端不上报
    try {
      await fetch('/api/auth/ack-guide', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + auth.token },
      });
    } catch { /* ignore */ }
  };

  // 指引期间浮一层全局蒙版。排掉另外两个全屏弹窗：它们都盖在内容上，
  // 叠在一起会互相压住 —— 何况那会儿用户还没轮到看指引
  const dialogUp = (auth.firstLogin && showAccountSetup)
    || (auth.role === 'account' && !!auth.pendingChangelog && !changelogDismissed);
  const guideUp = auth.role === 'account' && (auth.showGuide || replayGuide) && !dialogUp;

  const shell: ShellProps = {
    dark,
    onToggleDark: () => setDark(!dark),
    sidebarCollapsed,
    onToggleSidebar: () => setSidebarCollapsed(!sidebarCollapsed),
    // 指引已经浮着时再点「重看」没有歧义（用户就在指引里），直接从头重放，
    // **不弹确认框** —— 确认框是 z-[80]，在蒙版（z-84 起）之下，弹出来会
    // 既看不见也点不到，看着就是卡死
    onReplayGuide: () => (guideUp ? setGuideRun((n) => n + 1) : setConfirmReplay(true)),
    toasts,
    onRemoveToast: removeToast,
  };

  // 账户还在用默认密码：全屏挡住，改完为止。
  // 放在最前面且直接 return —— 不发更新日志、不渲染面板，避免「先关弹窗再改」
  // 或从侧边栏绕过。改密成功后服务端会作废该账户的 token，这里清掉本地登录态
  // 回到登录页用新密码登一次。
  if (auth.role === 'account' && auth.mustChangePassword && auth.accountId != null) {
    const handleForcedDone = () => {
      localStorage.removeItem('auth_token');
      window.location.reload();
    };
    return (
      <AuthContext.Provider value={auth}>
        <ForcePasswordChange accountId={auth.accountId} onDone={handleForcedDone} />
      </AuthContext.Provider>
    );
  }

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
      {/* 「重看指引」的二次确认。不用 z 硬压过蒙版，而是靠上面的 onReplayGuide
          在指引浮着时绕开确认框 —— 两条路各走各的，谁也不跟谁抢层级 */}
      <ConfirmDialog
        open={confirmReplay}
        title="重看操作指引"
        message="会从第一步重新走一遍。指引期间面板内容区点不动（免得误触兑换码、Bot 启停这类真动作），随时可以点「跳过」退出。"
        confirmLabel="开始"
        onConfirm={() => {
          setConfirmReplay(false);
          setReplayGuide(true);
          setGuideRun((n) => n + 1);
        }}
        onCancel={() => setConfirmReplay(false)}
      />
      {/* 告诉页面「指引正浮着」：直播间页据此在没绑直播间时渲染虚拟房间，
          好让「连接 / 断开」那一步有东西可讲。页面没有这份信号就只能
          不分场合地放假数据 —— 那样正常使用时也会冒出一个假房间 */}
      <GuideActiveContext.Provider value={guideUp}>
        <BrowserRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route element={<Layout {...shell} />}>
              {/* 指引没有自己的路由 —— 它就是在 /account/home 上浮一层蒙版，
                  所以无论看没看过，落地页都是主页 */}
              <Route index element={auth.role === 'account'
              ? <Navigate to="/account/home" replace />
              : <AccountsPage />} />
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
          {/* 操作指引：与 Routes **平级**，不能塞进任何一条 Route 里 ——
              它要跨路由存活，塞进去用户一切页蒙版就会卸载重来。
              又不渲染自己的界面：高亮与蒙版都盖在真实页面上 */}
          {guideUp && <GuideOverlay key={guideRun} onDone={handleGuideDone} />}
        </BrowserRouter>
      </GuideActiveContext.Provider>
    </AuthContext.Provider>
  );
}

export default App;
