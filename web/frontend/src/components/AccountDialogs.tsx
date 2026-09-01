import { useState } from 'react';
import { X, Loader2 } from 'lucide-react';
import { Button } from './Button';
import type { AccountCreateRequest, RenewRequest } from '../api/types';

// ================================================================== //
// 创建账户对话框
// ================================================================== //

interface CreateAccountDialogProps {
  open: boolean;
  loading?: boolean;
  onConfirm: (data: AccountCreateRequest) => void;
  onCancel: () => void;
}

export function CreateAccountDialog({ open, loading, onConfirm, onCancel }: CreateAccountDialogProps) {
  const [name, setName] = useState('');
  const [roomId, setRoomId] = useState('');
  const [botMode, setBotMode] = useState<'private' | 'public'>('public');
  const [cookie, setCookie] = useState('');
  const [durationDays, setDurationDays] = useState('-1');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  if (!open) return null;

  const submit = () => {
    if (!name.trim()) { setError('请输入账户名称'); return; }
    if (!username.trim()) { setError('登录用户名必填'); return; }
    const rid = roomId.trim() ? Number(roomId) : null;
    if (roomId.trim() && (!Number.isInteger(rid!) || rid! <= 0)) { setError('直播间 ID 必须为正整数'); return; }
    const days = Number(durationDays);
    if (!Number.isInteger(days)) { setError('有效时长必须为整数(天),-1 表示永久'); return; }
    if (botMode === 'private' && !cookie.trim()) { setError('私有模式必须填写 Cookie'); return; }
    if (password && password.trim().length < 4) { setError('密码至少 4 位'); return; }
    onConfirm({
      name: name.trim(),
      room_id: rid,
      bot_mode: botMode,
      cookie: cookie.trim(),
      duration_days: days,
      username: username.trim(),
      password: password.trim(),
    });
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 animate-slide-in-up">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white">创建账户</h3>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">账户名称 *</label>
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="input w-full" placeholder="如:主播A-场控" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">直播间 ID(可选)</label>
            <input value={roomId} onChange={(e) => setRoomId(e.target.value)}
              className="input w-full" placeholder="如 869198039" inputMode="numeric" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">Bot 模式</label>
            <div className="flex gap-2">
              {(['public', 'private'] as const).map((m) => (
                <button key={m} onClick={() => setBotMode(m)}
                  className={
                    'flex-1 h-9 rounded-lg border text-sm transition-colors ' +
                    (botMode === m
                      ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                      : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700')
                  }>
                  {m === 'public' ? '公共 Cookie' : '私有 Cookie'}
                </button>
              ))}
            </div>
          </div>
          {botMode === 'private' && (
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">Cookie *</label>
              <textarea value={cookie} onChange={(e) => setCookie(e.target.value)} rows={2}
                className="input w-full font-mono text-xs" placeholder="粘贴 Missevan Cookie..." />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
              有效时长(天)
            </label>
            <input value={durationDays} onChange={(e) => setDurationDays(e.target.value)}
              className="input w-full" inputMode="numeric"
              placeholder="30 表示 30 天;-1 表示永久" />
            <p className="text-xs text-gray-400 mt-1">填 30 表示有效 30 天,填 -1 表示永久</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                登录用户名 *
              </label>
              <input value={username} onChange={(e) => setUsername(e.target.value)}
                className="input w-full" placeholder="必填,用于账户分辨,不可重复" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                登录密码
              </label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="input w-full" placeholder="至少 4 位,留空随机生成" />
            </div>
          </div>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-5 pb-4">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" size="sm" onClick={submit} loading={loading}>创建</Button>
        </div>
      </div>
    </div>
  );
}

// ================================================================== //
// 续期 / 兑换对话框
// ================================================================== //

interface RenewDialogProps {
  open: boolean;
  accountId: number;
  accountName: string;
  /** days=续期叠加天数 set=直接设置剩余天数(覆盖) code=兑换授权码 */
  mode: 'days' | 'set' | 'code';
  loading?: boolean;
  onRenew: (id: number, data: RenewRequest) => void;
  onRedeem: (id: number, code: string) => void;
  onCancel: () => void;
}

const MODE_TITLE: Record<string, string> = {
  days: '续期',
  set: '设置剩余天数',
  code: '兑换授权码',
};

export function RenewDialog({ open, accountId, accountName, mode, loading, onRenew, onRedeem, onCancel }: RenewDialogProps) {
  const [days, setDays] = useState('30');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');

  if (!open) return null;

  const submit = () => {
    if (mode === 'days' || mode === 'set') {
      const d = Number(days);
      if (!Number.isInteger(d) || d <= 0) { setError('请输入正整数天数'); return; }
      if (mode === 'days') {
        onRenew(accountId, { days: d });
      } else {
        // 直接覆盖到期时间 = 当前时间 + N 天(用于调整永久/剩余天数)
        onRenew(accountId, { expires_at: new Date(Date.now() + d * 86400000).toISOString() });
      }
    } else {
      if (!code.trim()) { setError('请输入授权码'); return; }
      onRedeem(accountId, code.trim().toUpperCase());
    }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white">
            {MODE_TITLE[mode]} · {accountName}
          </h3>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          {mode === 'code' ? (
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">授权码</label>
              <input value={code} onChange={(e) => setCode(e.target.value)}
                className="input w-full font-mono" placeholder="MM-XXXX-XXXX-XXXX" />
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                {mode === 'days' ? '续期天数' : '剩余天数'}
              </label>
              <input value={days} onChange={(e) => setDays(e.target.value)}
                className="input w-full" inputMode="numeric" placeholder="30" />
              <p className="text-xs text-gray-400 mt-1">
                {mode === 'days'
                  ? '在当前到期时间基础上叠加 N 天'
                  : '直接设置为 N 天后到期(忽略当前到期时间,可用于永久账户改为限时)'}
              </p>
            </div>
          )}
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-5 pb-4">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" size="sm" onClick={submit} loading={loading}>
            {mode === 'days' ? '续期' : mode === 'set' ? '设置' : '兑换'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ================================================================== //
// 重置账户登录凭据对话框
// ================================================================== //

interface CredentialsDialogProps {
  open: boolean;
  accountName: string;
  currentUsername: string;
  loading?: boolean;
  onConfirm: (username: string, password: string) => void;
  onCancel: () => void;
}

export function CredentialsDialog({
  open, accountName, currentUsername, loading, onConfirm, onCancel,
}: CredentialsDialogProps) {
  const [username, setUsername] = useState(currentUsername);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  if (!open) return null;

  const submit = () => {
    if (password.trim().length < 4) { setError('密码至少 4 位'); return; }
    onConfirm(username.trim(), password.trim());
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white">重置登录凭据 · {accountName}</h3>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">用户名</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)}
              className="input w-full" placeholder="留空保持不变" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">新密码</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              className="input w-full" placeholder="至少 4 位" />
          </div>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-5 pb-4">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" size="sm" onClick={submit} loading={loading}>重置</Button>
        </div>
      </div>
    </div>
  );
}

// ================================================================== //
// 通用操作中状态
// ================================================================== //

export function InlineLoader() {
  return <Loader2 className="w-4 h-4 animate-spin" />;
}
