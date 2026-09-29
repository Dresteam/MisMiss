import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { Button } from './Button';
import type { AccountCreateRequest, RenewRequest } from '../api/types';
import { parseLiveId } from '../utils/live';

// ================================================================== //
// 创建账户对话框
// ================================================================== //

interface CreateAccountDialogProps {
  open: boolean;
  loading?: boolean;
  onConfirm: (data: AccountCreateRequest) => void;
  onCancel: () => void;
  /** 预填的默认用户名（调用方按「账户总数 + 1」算好，并避开已占用的名字） */
  defaultUsername?: string;
}

export function CreateAccountDialog({ open, loading, onConfirm, onCancel, defaultUsername }: CreateAccountDialogProps) {
  const [name, setName] = useState('');
  const [roomId, setRoomId] = useState('');
  const [botMode, setBotMode] = useState<'private' | 'public'>('public');
  const [cookie, setCookie] = useState('');
  const [durationDays, setDurationDays] = useState('-1');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  // 打开时预填默认凭据（仍可改）。用 useEffect 而非 useState 初值：
  // 账户列表是异步取到的，弹窗挂载时可能还没有
  useEffect(() => {
    if (!open) return;
    setName('');
    setRoomId('');
    setBotMode('public');
    setCookie('');
    setDurationDays('-1');
    setUsername(defaultUsername ?? '');
    setPassword('user123');
    setError('');
  }, [open, defaultUsername]);

  if (!open) return null;

  const submit = () => {
    if (!name.trim()) { setError('请输入账户名称'); return; }
    if (!username.trim()) { setError('登录用户名必填'); return; }
    const rid = roomId.trim() ? parseLiveId(roomId) : null;
    if (roomId.trim() && rid === null) {
      setError('直播间 ID 或链接无法识别，请粘贴形如 https://fm.missevan.com/live/869198039 的链接');
      return;
    }
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
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="off"
              className="input w-full" placeholder="如:主播A-场控" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">直播间 ID 或链接(可选)</label>
            <input value={roomId} onChange={(e) => setRoomId(e.target.value)} autoComplete="off"
              className="input w-full" placeholder="如 869198039，或粘贴直播间链接" />
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
              <textarea value={cookie} onChange={(e) => setCookie(e.target.value)} rows={2} autoComplete="off"
                className="input w-full font-mono text-xs" placeholder="粘贴 Missevan Cookie..." />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
              有效时长(天)
            </label>
            <input value={durationDays} onChange={(e) => setDurationDays(e.target.value)}
              className="input w-full" inputMode="numeric" autoComplete="off"
              placeholder="30 表示 30 天;-1 表示永久" />
            <p className="text-xs text-gray-400 mt-1">填 30 表示有效 30 天,填 -1 表示永久</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                登录用户名 *
              </label>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off"
                className="input w-full" placeholder="必填,用于账户分辨,不可重复" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                登录密码
              </label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className="input w-full" placeholder="至少 4 位,默认 user123" />
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
  /** 打开时的初始模式（对话框内可切换）。
   *  days=续期叠加天数 set=直接设置剩余天数(覆盖) code=兑换授权码
   *  permanent=设为永久 expire=设为过期停用 */
  mode: RenewMode;
  /** 允许在对话框内切换的模式，默认全部。
   *  账户端只兑换授权码，传 ['code'] 即可 —— 那里的用户不该看到「设为停用」 */
  availableModes?: RenewMode[];
  loading?: boolean;
  onRenew: (id: number, data: RenewRequest) => void;
  onRedeem: (id: number, code: string) => void;
  /** 设为过期停用（无请求体，单列一个回调）。
   *  可选：账户端只用来兑换授权码，不该有权把自己停用 */
  onExpire?: (id: number) => void;
  onCancel: () => void;
}

type RenewMode = 'days' | 'set' | 'code' | 'permanent' | 'expire';

const MODE_TITLE: Record<RenewMode, string> = {
  days: '续期',
  set: '设置剩余天数',
  code: '兑换授权码',
  permanent: '设为永久',
  expire: '设为过期停用',
};

/** 切换器里的顺序：按常用程度排，续期在最前 */
const MODE_ORDER: RenewMode[] = ['days', 'set', 'code', 'permanent', 'expire'];

/** 切换器用的短标签 —— 全称在 max-w-sm 里会折成两行、最后一行只剩一个按钮 */
const MODE_SHORT: Record<RenewMode, string> = {
  days: '续期',
  set: '剩余天数',
  code: '授权码',
  permanent: '永久',
  expire: '过期停用',
};

export function RenewDialog({
  open, accountId, accountName, mode, availableModes, loading,
  onRenew, onRedeem, onExpire, onCancel,
}: RenewDialogProps) {
  const [days, setDays] = useState('30');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  // 对话框内可切换模式：一次打开就能把时长相关的事都办了，不必回卡片上换按钮
  const [activeMode, setActiveMode] = useState<RenewMode>(mode);
  const modes = availableModes ?? MODE_ORDER;

  useEffect(() => {
    if (open) { setActiveMode(mode); setError(''); }
  }, [open, mode]);

  if (!open) return null;
  const m = activeMode;

  const submit = () => {
    if (m === 'expire') {
      onExpire?.(accountId);
    } else if (m === 'permanent') {
      onRenew(accountId, { permanent: true });
    } else if (m === 'days' || m === 'set') {
      const d = Number(days);
      if (!Number.isInteger(d) || d <= 0) { setError('请输入正整数天数'); return; }
      if (m === 'days') {
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
            {MODE_TITLE[m]} · {accountName}
          </h3>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        {/* 模式切换器：时长相关的几件事在同一处办完，不必回卡片换按钮。
            只有一种可选模式时（账户端只兑换授权码）不显示 */}
        {modes.length > 1 && (
          <div className="flex flex-wrap gap-1 px-5 pt-3">
            {MODE_ORDER.filter((x) => modes.includes(x)).map((x) => (
              <button key={x} type="button"
                onClick={() => { setActiveMode(x); setError(''); }}
                className={`px-2.5 py-1 text-xs rounded-lg border transition-colors
                  ${x === m
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
                {MODE_SHORT[x]}
              </button>
            ))}
          </div>
        )}
        <div className="p-5 space-y-4">
          {m === 'code' ? (
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">授权码</label>
              <input value={code} onChange={(e) => setCode(e.target.value)}
                className="input w-full font-mono" placeholder="MM-XXXX-XXXX-XXXX" />
            </div>
          ) : m === 'expire' ? (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              将 <span className="font-medium">{accountName}</span> 的到期时间置为过去，
              并<span className="font-medium">立刻停用</span>其 Bot、断开直播间、暂停插件。
              之后续期即可恢复。
            </p>
          ) : m === 'permanent' ? (
            <p className="text-sm text-gray-600 dark:text-gray-300">
              将 <span className="font-medium">{accountName}</span> 设为<span className="font-medium">永不过期</span>。
              该账户不会再因到期被停用。
            </p>
          ) : (
            <div>
              <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                {m === 'days' ? '续期天数' : '剩余天数'}
              </label>
              <input value={days} onChange={(e) => setDays(e.target.value)}
                className="input w-full" inputMode="numeric" placeholder="30" />
              <p className="text-xs text-gray-400 mt-1">
                {m === 'days'
                  ? '在当前到期时间基础上叠加 N 天(永久账户保持不变)'
                  : '直接设置为 N 天后到期(忽略当前到期时间,可用于永久账户改为限时)'}
              </p>
            </div>
          )}
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 px-5 pb-4">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" size="sm" onClick={submit} loading={loading}>
            {m === 'days' ? '续期'
              : m === 'set' ? '设置'
              : m === 'permanent' ? '设为永久'
              : m === 'expire' ? '确认停用'
              : '兑换'}
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
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off"
              className="input w-full" placeholder="留空保持不变" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">新密码</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
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

