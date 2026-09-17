import { useState, useEffect } from 'react';
import { Terminal, Key, User, Lock, Eye, EyeOff } from 'lucide-react';
import { Button } from '../components/Button';
import { useAuth } from '../hooks/useAuth';

/**
 * 登录页 —— 管理端与账户端共用。
 *
 * 身份完全由凭据决定:面板管理员进面板,账户持有者进账户界面,
 * 登录后由 App 的路由守卫按 ``role`` 分流。
 */
export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [logging, setLogging] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');

  // 启动时自动同步端口配置
  useEffect(() => {
    fetch('/api/health').then(r => r.json()).then(d => {
      if (d.api_port) localStorage.setItem('api_port', String(d.api_port));
      if (d.web_port) localStorage.setItem('web_port', String(d.web_port));
    }).catch(() => {});
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLogging(true);
    try {
      await login(username.trim(), password);
      setError('');
      // 整页刷新后 useAuthState 重新拉 /api/auth/check，按 role 分流
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
      setLogging(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-950 p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-primary-600 flex items-center justify-center mx-auto mb-4">
            <Terminal className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">MisMiss Console</h1>
          <p className="text-sm text-gray-500 mt-1">请使用你的账号登录</p>
        </div>

        <form onSubmit={handleLogin} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 space-y-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">用户名</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type="text" value={username} onChange={e => { setUsername(e.target.value); setError(''); }}
                className="input pl-9" placeholder="用户名" autoFocus />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">密码</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type={showPwd ? 'text' : 'password'} value={password}
                onChange={e => { setPassword(e.target.value); setError(''); }}
                className="input pl-9 pr-9" placeholder="密码" />
              <button type="button" onClick={() => setShowPwd(!showPwd)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <Button variant="primary" className="w-full" icon={<Key />}
            loading={logging} type="submit">登录</Button>
          {error && (
            <div className="mt-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-center">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}
          <p className="text-xs text-gray-400 text-center">账户凭据由面板管理员创建 / 重置</p>
        </form>
      </div>
    </div>
  );
}
