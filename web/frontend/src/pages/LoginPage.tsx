import { useState } from 'react';
import { Terminal, Key, User, Lock, Eye, EyeOff } from 'lucide-react';
import { Button } from '../components/Button';
import { showToast } from '../hooks/useToast';

interface Props {
  onLogin: (token: string) => void;
}

export function LoginPage({ onLogin }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [logging, setLogging] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLogging(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      const data = await res.json();
      setError('');
      localStorage.setItem('auth_token', data.token);
      onLogin(data.token);
    } catch (err: any) {
      setError(err.message);
    } finally {
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
          <p className="text-sm text-gray-500 mt-1">默认用户名和密码均为 MisMiss</p>
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
              <p className="text-xs text-red-500 dark:text-red-400/70 mt-1">提示：默认用户名和密码均为 MisMiss</p>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
