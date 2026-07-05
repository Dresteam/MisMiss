import { useState } from 'react';
import { Shield, User, Lock, Eye, EyeOff } from 'lucide-react';
import { Button } from './Button';
import { showToast } from '../hooks/useToast';

interface Props {
  token: string;
  firstLogin?: boolean;
  onDone: () => void;
}

export function AccountSetup({ token, firstLogin = false, onDone }: Props) {
  const [newUsername, setNewUsername] = useState('');
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [saving, setSaving] = useState(false);
  const [showPwd, setShowPwd] = useState(false);

  const handleSave = async () => {
    if (!firstLogin && !currentPwd) { showToast('warning', '请输入当前密码'); return; }
    if (newPwd && newPwd !== confirmPwd) { showToast('warning', '两次输入的密码不一致'); return; }
    if (newPwd && newPwd.length < 4) { showToast('warning', '新密码至少4位'); return; }
    setSaving(true);
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, current_password: currentPwd, new_username: newUsername, new_password: newPwd }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      const data = await res.json();
      showToast('success', data.message || '已更新');
      localStorage.removeItem('auth_token');
      setTimeout(() => window.location.reload(), 1000);
    } catch (err: any) {
      showToast('error', '修改失败', err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onDone} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4 animate-slide-in-up">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center">
            <Shield className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {firstLogin ? '首次登录' : '修改账户'}
            </h3>
            <p className="text-xs text-gray-500">
              {firstLogin ? '建议修改默认用户名和密码' : '修改用户名或密码后需重新登录'}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          {!firstLogin && (
            <div>
              <label className="block text-xs text-gray-500 mb-1">当前密码</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input type={showPwd ? 'text' : 'password'} value={currentPwd}
                  onChange={e => setCurrentPwd(e.target.value)}
                  className="input pl-9 pr-9" placeholder="输入当前密码" />
                <button type="button" onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
          )}
          <div>
            <label className="block text-xs text-gray-500 mb-1">新用户名（可选）</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type="text" value={newUsername} onChange={e => setNewUsername(e.target.value)}
                className="input pl-9" placeholder="留空则不修改" />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">新密码（可选）</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type={showPwd ? 'text' : 'password'} value={newPwd}
                onChange={e => setNewPwd(e.target.value)}
                className="input pl-9 pr-9" placeholder="至少4位，留空不修改" />
              <button type="button" onClick={() => setShowPwd(!showPwd)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          {newPwd && (
            <div>
              <label className="block text-xs text-gray-500 mb-1">确认密码</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input type={showPwd ? 'text' : 'password'} value={confirmPwd}
                  onChange={e => setConfirmPwd(e.target.value)}
                  className={`input pl-9 pr-9 ${confirmPwd && newPwd !== confirmPwd ? 'border-red-500' : ''}`}
                  placeholder="再次输入密码" />
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 mt-5">
          <Button variant="ghost" onClick={onDone}>{firstLogin ? '跳过' : '取消'}</Button>
          <Button variant="primary" onClick={handleSave} loading={saving}>保存</Button>
        </div>
      </div>
    </div>
  );
}
