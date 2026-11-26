/** 浏览器登录猫耳：验证码 / 密码，登录成功后直接写入账户私有 Cookie。 */

import { useState } from 'react';
import { KeyRound, Loader2, MessageSquare } from 'lucide-react';
import { startBrowserLogin, submitBrowserLoginSms } from '../api/client';
import { Button } from './Button';
import { showToast } from '../hooks/useToast';

type Method = 'sms' | 'password';

interface Props {
  accountId: number;
  onDone: () => void;
}

export function BrowserLogin({ accountId, onDone }: Props) {
  const [method, setMethod] = useState<Method>('sms');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [busy, setBusy] = useState(false);

  const start = async () => {
    if (!phone.trim()) {
      showToast('error', '请输入手机号', '');
      return;
    }
    if (method === 'password' && !password) {
      showToast('error', '请输入密码', '');
      return;
    }
    setBusy(true);
    try {
      const res = await startBrowserLogin(accountId, method, phone.trim(), password);
      if (method === 'sms') {
        setSessionId(res.session_id);
        showToast('success', res.message || '验证码已发送', '把手机收到的验证码填到下方');
      } else {
        showToast('success', '登录成功', res.username ? `已登录 ${res.username}` : '');
        setPassword('');
        onDone();
      }
    } catch (e) {
      showToast('error', '登录失败', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const submitSms = async () => {
    if (!code.trim()) {
      showToast('error', '请输入验证码', '');
      return;
    }
    setBusy(true);
    try {
      const res = await submitBrowserLoginSms(accountId, sessionId, code.trim());
      showToast('success', '登录成功', res.username ? `已登录 ${res.username}` : '');
      setCode('');
      setSessionId('');
      onDone();
    } catch (e) {
      showToast('error', '验证码登录失败', e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 space-y-3">
      <div className="flex items-center gap-2">
        <KeyRound className="w-4 h-4 text-gray-500" />
        <span className="text-sm font-medium">浏览器登录猫耳</span>
      </div>
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg w-fit">
        <button
          type="button"
          onClick={() => { setMethod('sms'); setSessionId(''); }}
          className={`px-2 py-1 text-xs rounded-md ${method === 'sms'
            ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-gray-500'}`}
        >
          验证码登录
        </button>
        <button
          type="button"
          onClick={() => { setMethod('password'); setSessionId(''); }}
          className={`px-2 py-1 text-xs rounded-md ${method === 'password'
            ? 'bg-white dark:bg-gray-700 shadow-sm' : 'text-gray-500'}`}
        >
          密码登录
        </button>
      </div>

      <input
        className="input w-full"
        placeholder={method === 'password' ? '手机号 / 邮箱' : '手机号'}
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        autoComplete="username"
      />
      {method === 'password' && (
        <input
          className="input w-full"
          placeholder="密码"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      )}

      {method === 'sms' && sessionId && (
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="短信验证码"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputMode="numeric"
          />
          <Button onClick={submitSms} disabled={busy}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : '登录'}
          </Button>
        </div>
      )}

      {!(method === 'sms' && sessionId) && (
        <Button onClick={start} disabled={busy} className="w-full">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : (
            method === 'sms' ? <><MessageSquare className="w-4 h-4" /> 获取验证码</> : '登录'
          )}
        </Button>
      )}

      <p className="text-xs text-gray-400">
        登录在服务器上的真实浏览器中完成，不会保存密码；成功后自动写入该账户的私有 Cookie。
      </p>
    </div>
  );
}
