import { useState } from 'react';
import { Button } from './Button';
import { changeAccountPassword } from '../api/client';
import { showToast } from '../hooks/useToast';

interface Props {
  accountId: number;
  /** 改密成功后的收尾（账户端页面会登出重新登录；强制改密界面也一样） */
  onDone: () => void;
  /** 提交按钮文案 */
  submitLabel?: string;
}

/**
 * 账户自助改密表单（三个输入框 + 校验 + 调用接口）。
 *
 * 抽出来是因为有两个入口：「账户端 - 修改密码」页与「必须修改默认密码」的
 * 强制界面 —— 校验规则与接口调用只此一份，避免两边慢慢跑偏。
 */
export function AccountPasswordForm({ accountId, onDone, submitLabel = '修改密码' }: Props) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!current) { setError('请输入原密码'); return; }
    if (next.length < 4) { setError('新密码至少 4 位'); return; }
    if (next !== confirm) { setError('两次输入的新密码不一致'); return; }
    if (next === current) { setError('新密码不能与原密码相同'); return; }
    setBusy(true);
    setError('');
    try {
      await changeAccountPassword(accountId, current, next, confirm);
      showToast('success', '密码已修改，请重新登录', '');
      onDone();
    } catch (e: any) {
      setError(e.message || '修改失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">原密码</label>
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          className="input w-full" placeholder="当前使用的密码" autoFocus />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">新密码</label>
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
          className="input w-full" placeholder="至少 4 位" />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">确认新密码</label>
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
          autoComplete="new-password"
          className="input w-full" placeholder="再次输入新密码"
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }} />
      </div>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <Button className="w-full" onClick={submit} loading={busy}>{submitLabel}</Button>
    </div>
  );
}
