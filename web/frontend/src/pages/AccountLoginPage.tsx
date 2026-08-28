import { useState } from 'react';
import { Bot as BotIcon } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { Button } from '../components/Button';

/** 账户入口登录页(user. 子域名)—— 凭用户名/密码确认账户身份。 */
export function AccountLoginPage() {
  const { login, logout } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await login(username.trim(), password);
      // 确认登录身份为账户(管理员凭据不能进入账户入口)
      const token = localStorage.getItem('auth_token');
      if (token) {
        const res = await fetch('/api/auth/check', {
          headers: { Authorization: `Bearer ${token}` },
        });
        const info = await res.json();
        if (info.valid && info.role === 'account') {
          window.location.reload();
          return;
        }
      }
      logout();
      setError('请使用账户凭据登录(管理员请访问面板入口)');
    } catch (e: any) {
      setError(e.message || '登录失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-950 p-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-primary-600 flex items-center justify-center mb-3">
            <BotIcon className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-xl font-bold text-surface-900 dark:text-white">
            MisMiss 账户
          </h1>
          <p className="text-sm text-surface-500 dark:text-surface-400 mt-1">
            直播机器人账户登录
          </p>
        </div>
        <div className="card">
          <div className="card-body space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">用户名</label>
              <input value={username} onChange={(e) => setUsername(e.target.value)}
                className="input w-full" placeholder="账户用户名" autoFocus />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">密码</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="input w-full" placeholder="账户密码"
                onKeyDown={(e) => { if (e.key === 'Enter') submit(); }} />
            </div>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            <Button className="w-full" onClick={submit} loading={busy}>
              登录
            </Button>
            <p className="text-xs text-gray-400 text-center">
              凭据由面板管理员创建/重置
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
