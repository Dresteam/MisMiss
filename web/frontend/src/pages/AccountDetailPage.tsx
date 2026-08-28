import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft, Bot as BotIcon, Radio, Puzzle, Clock, Send, RefreshCw,
  Plus, Trash2, Pencil, ChevronUp, ChevronDown, SkipForward, Loader2, Eye, EyeOff,
  Power, XCircle, CalendarClock, KeyRound, ExternalLink,
} from 'lucide-react';
import {
  fetchAccountSummary, fetchAccountBot, createAccountBot, refreshAccountBot,
  verifyAccountBot, enableAccountBot, disableAccountBot, deleteAccountBot,
  setAccountBotMode,
  fetchAccountLive, addAccountLive, removeAccountLive, refreshAccountLive,
  enableAccountLive, disableAccountLive, joinAccountLive, quitAccountLive,
  sendAccountLiveMessage, fetchAccountTimers, addAccountTimer, updateAccountTimer,
  deleteAccountTimer, moveAccountTimer, skipAccountTimer, sendAccountTimerNow,
  setAccountTimerInterval, fetchAccountPlugins, enableAccountPlugin,
  disableAccountPlugin, reloadAccountPlugin, renewAccount, redeemAccount,
  fetchAccountPluginReadme, fetchAccountPluginConfig, updateAccountPluginConfig,
  getAccountBotCookie, uninstallAccountPluginFromAccount, fetchAccountLibrary,
} from '../api/client';
import type {
  AccountSummary, BotInfo, LivestreamInfo, PluginSummary, TimerData, TimerMessageItem,
} from '../api/types';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { ExpiryBadge } from '../components/ExpiryBadge';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { RenewDialog } from '../components/AccountDialogs';
import { ReadmeModal } from '../components/ReadmeModal';
import { PluginDrawer } from '../components/PluginDrawer';
import { UninstallDialog } from '../components/UninstallDialog';
import { MarqueeText } from '../components/MarqueeText';
import { showToast } from '../hooks/useToast';

const PERM_NAMES = ['SEND_LIVESTREAM_MESSAGE', 'SEND_PRIVATE_MESSAGE', 'SEND_BACKPACK_GIFT', 'SEND_GIFT', 'EXPOSE_COOKIE'];
const PERM_LABELS: Record<string, string> = {
  SEND_LIVESTREAM_MESSAGE: '发送直播间消息',
  SEND_PRIVATE_MESSAGE: '发送私信',
  SEND_BACKPACK_GIFT: '赠送背包礼物',
  SEND_GIFT: '赠送直售礼物',
  EXPOSE_COOKIE: '查看完整 Cookie',
};

// ================================================================== //
// 概览 Tab
// ================================================================== //

export function OverviewTab({ acc, onRenew, panelMode }: { acc: AccountSummary; onRenew: (mode: 'days' | 'code') => void; panelMode?: boolean }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="card">
        <div className="card-header"><h3 className="font-semibold">Bot</h3>
          <StatusBadge status={acc.bot_enabled && acc.bot_available ? 'enabled' : 'disabled'}
            label={acc.bot_enabled ? '已启用' : '已停用'} />
        </div>
        <div className="card-body space-y-2 text-sm">
          <p className="text-gray-600 dark:text-gray-300">{acc.bot_name || '未配置 Bot'}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {acc.bot_public ? '使用面板公共 Cookie(账户内不可查看)' : '账户私有 Cookie'}
          </p>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h3 className="font-semibold">直播间</h3>
          <StatusBadge status={acc.room_connected ? 'online' : 'offline'} label={acc.room_connected ? '已连接' : '未连接'} />
        </div>
        <div className="card-body space-y-2 text-sm">
          <p className="text-gray-600 dark:text-gray-300">{acc.room_name || (acc.room_id ? `房间 ${acc.room_id}` : '未绑定直播间')}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">启用状态: {acc.room_enabled ? '已启用' : '已停用'}</p>
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h3 className="font-semibold">插件</h3></div>
        <div className="card-body text-sm text-gray-600 dark:text-gray-300">
          已启用 {acc.enabled_plugin_count} / {acc.plugin_count} 个插件 · 定时消息 {acc.timer_message_count} 条
        </div>
      </div>
      <div className="card">
        <div className="card-header"><h3 className="font-semibold">订阅</h3>
          <ExpiryBadge expiresAt={acc.expires_at} pausedReason={acc.paused_reason} />
        </div>
        <div className="card-body space-y-3">
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {acc.expires_at
              ? `到期时间: ${new Date(acc.expires_at).toLocaleString()}`
              : '永不过期'}
          </p>
          {acc.resume_error && (
            <p className="text-xs text-red-600 dark:text-red-400">{acc.resume_error}</p>
          )}
          {panelMode !== false && (
            <div className="flex gap-2">
              <Button size="sm" icon={<CalendarClock className="w-4 h-4" />} onClick={() => onRenew('days')}>续期</Button>
              <Button size="sm" variant="secondary" icon={<KeyRound className="w-4 h-4" />} onClick={() => onRenew('code')}>兑换授权码</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ================================================================== //
// 直播间 Tab(单房间)
// ================================================================== //

export function LiveTab({ acc }: { acc: AccountSummary }) {
  const [room, setRoom] = useState<LivestreamInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [liveIdInput, setLiveIdInput] = useState('');
  const [switching, setSwitching] = useState(false); // 更换直播间输入态
  const [msgText, setMsgText] = useState('');
  const [msgPriority, setMsgPriority] = useState(0);

  const load = useCallback(async () => {
    try {
      const data = await fetchAccountLive(acc.id);
      setRoom(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [acc.id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const act = async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
    setProcessing(key);
    try {
      await fn();
      showToast('success', okMsg, '');
      load();
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
    } finally { setProcessing(''); }
  };

  const btn = (key: string, disabled = false) => processing === key || disabled;

  return (
    <div className="space-y-4">
      {loading && !room ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary-500" /></div>
      ) : room === null ? (
        <div className="card">
          <div className="card-body">
            <div className="flex gap-2">
              <input value={liveIdInput} onChange={(e) => setLiveIdInput(e.target.value)}
                className="input flex-1" placeholder="输入直播间 ID..." inputMode="numeric" />
              <Button loading={processing === 'add'} disabled={btn('add')}
                onClick={() => act('add', () => addAccountLive(acc.id, Number(liveIdInput)), '直播间已绑定')}>
                绑定
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <>
        {/* 更换直播间输入行 */}
        {switching && (
          <div className="card">
            <div className="card-body">
              <div className="flex gap-2">
                <input value={liveIdInput} onChange={(e) => setLiveIdInput(e.target.value)}
                  className="input flex-1" placeholder="输入新的直播间 ID..." inputMode="numeric" autoFocus />
                <Button loading={processing === 'switch'} disabled={btn('switch')}
                  onClick={() => act('switch', () => addAccountLive(acc.id, Number(liveIdInput)).then(() => {
                    setSwitching(false);
                    setLiveIdInput('');
                  }), '直播间已更换')}>
                  确认更换
                </Button>
                <Button variant="ghost" disabled={btn('switch')}
                  onClick={() => { setSwitching(false); setLiveIdInput(''); }}>
                  取消
                </Button>
              </div>
              <p className="text-xs text-gray-400 mt-2">更换后原直播间自动断开,新直播间需手动启用</p>
            </div>
          </div>
        )}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
          {/* 封面 */}
          {room.cover_url && (
            <div className="relative h-40 sm:h-52 bg-surface-100 dark:bg-surface-900">
              <img
                src={`/api/proxy/image?url=${encodeURIComponent(room.cover_url)}`}
                alt="cover"
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
              {/* 开播状态 */}
              <div className="absolute top-3 left-3">
                <span className={
                  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium backdrop-blur ' +
                  (room.is_streaming
                    ? 'bg-red-500/90 text-white'
                    : 'bg-gray-900/70 text-gray-200')
                }>
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${room.is_streaming ? 'bg-white animate-pulse' : 'bg-gray-400'}`} />
                  {room.is_streaming ? '开播中' : '未开播'}
                </span>
              </div>
              {/* 房间名 */}
              <div className="absolute bottom-3 left-4 right-4">
                <p className="text-white font-semibold text-lg drop-shadow">
                  {room.room_name} ({room.live_id})
                </p>
              </div>
            </div>
          )}

          <div className="p-5 space-y-4">
            {/* 主播信息 */}
            <div className="flex items-start gap-3">
              {room.creator_avatar ? (
                <img
                  src={`/api/proxy/image?url=${encodeURIComponent(room.creator_avatar)}`}
                  alt="avatar"
                  className="w-12 h-12 rounded-full object-cover shrink-0 bg-white border border-gray-200 dark:border-gray-700"
                />
              ) : (
                <div className="w-12 h-12 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center shrink-0">
                  <BotIcon className="w-6 h-6 text-primary-500" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-gray-900 dark:text-white">{room.creator_name || '未知主播'}</p>
                  <StatusBadge status={room.creator_is_online ? 'online' : 'offline'}
                    label={room.creator_is_online ? '主播在线' : '主播离线'} />
                  <StatusBadge status={room.is_connected ? 'online' : 'offline'}
                    label={room.is_connected ? '已连接' : '未连接'} />
                </div>
                {room.creator_intro && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{room.creator_intro}</p>
                )}
              </div>
            </div>

            {/* 房间简介 */}
            {room.room_description && (
              <div className="rounded-lg bg-gray-50 dark:bg-gray-900/40 px-4 py-3">
                <p className="text-[10px] text-gray-400 mb-0.5">直播间简介</p>
                <p className="text-sm text-gray-700 dark:text-gray-300">{room.room_description}</p>
              </div>
            )}

            {/* 统计 */}
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-gray-50 dark:bg-gray-900/40 py-3">
                <p className="text-gray-400 text-xs">热度</p>
                <p className="font-semibold text-lg mt-0.5">{room.score >= 0 ? room.score : '-'}</p>
              </div>
              <div className="rounded-lg bg-gray-50 dark:bg-gray-900/40 py-3">
                <p className="text-gray-400 text-xs">在线人数</p>
                <p className="font-semibold text-lg mt-0.5">{room.online_count}</p>
              </div>
              <div className="rounded-lg bg-gray-50 dark:bg-gray-900/40 py-3">
                <p className="text-gray-400 text-xs">粉丝勋章</p>
                <p className="font-semibold text-lg mt-0.5 truncate">{room.medal_name || '-'}</p>
              </div>
            </div>

            {/* 操作:启用即自动进入,停用即断开 */}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant={room.enabled ? 'secondary' : 'success'}
                loading={processing === 'enable'} disabled={btn('enable')}
                onClick={() => act('enable', () => room.enabled
                  ? disableAccountLive(acc.id)
                  : enableAccountLive(acc.id), room.enabled ? '直播间已停用' : '直播间已启用并自动进入')}>
                {room.enabled ? '停用' : '启用'}
              </Button>
              <Button size="sm" variant="ghost" icon={<RefreshCw className="w-4 h-4" />}
                loading={processing === 'refresh'} disabled={btn('refresh')}
                onClick={() => act('refresh', () => refreshAccountLive(acc.id), '已刷新')} />
              <Button size="sm" variant="secondary" icon={<Radio className="w-4 h-4" />}
                loading={processing === 'switch'} disabled={btn('switch')}
                onClick={() => { setSwitching(!switching); setLiveIdInput(''); }}>
                更换直播间
              </Button>
              <Button size="sm" variant="ghost" icon={<Trash2 className="w-4 h-4 text-red-500" />}
                loading={processing === 'remove'} disabled={btn('remove')}
                onClick={() => act('remove', () => removeAccountLive(acc.id), '已解除绑定')} />
            </div>

            {/* 发弹幕 */}
            <div className="flex gap-2 pt-3 border-t border-gray-100 dark:border-gray-700">
              <input value={msgText} onChange={(e) => setMsgText(e.target.value)}
                className="input flex-1" placeholder="输入要发送的弹幕..." />
              <select value={msgPriority} onChange={(e) => setMsgPriority(Number(e.target.value))} className="input w-28">
                <option value={0}>普通</option>
                <option value={1}>优先</option>
              </select>
              <Button icon={<Send className="w-4 h-4" />} loading={processing === 'send'} disabled={btn('send')}
                onClick={() => act('send', () => sendAccountLiveMessage(acc.id, msgText, msgPriority).then(() => setMsgText('')), '消息已发送')}>
                发送
              </Button>
            </div>
          </div>
        </div>
        </>
      )}
    </div>
  );
}

// ================================================================== //
// ================================================================== //
// Bot Tab(模式选择 + Bot 卡片)
// ================================================================== //
// ================================================================== //
// Bot Tab(模式选择 + Bot 卡片)
// ================================================================== //

export function BotTab({ acc, onAccountChanged }: {
  acc: AccountSummary;
  onAccountChanged?: () => void;
}) {
  const [bot, setBot] = useState<BotInfo | null>(null);
  const [mode, setMode] = useState<'public' | 'private'>(acc.bot_public ? 'public' : 'private');
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [cookie, setCookie] = useState('');
  const [perms, setPerms] = useState<string[]>(['SEND_LIVESTREAM_MESSAGE']);
  const [showCookie, setShowCookie] = useState(false);
  const [viewedCookie, setViewedCookie] = useState('');

  const load = useCallback(async () => {
    try {
      setBot(await fetchAccountBot(acc.id));
    } catch { /* 未配置 */ }
    finally { setLoading(false); }
  }, [acc.id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setMode(acc.bot_public ? 'public' : 'private'); }, [acc.bot_public]);

  const act = async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
    setProcessing(key);
    try {
      await fn();
      showToast('success', okMsg, '');
      load();
      onAccountChanged?.();
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
    } finally { setProcessing(''); }
  };

  const switchMode = (m: 'public' | 'private') => {
    if (m === mode) return;
    if (m === 'public') {
      // 切到公共:使用面板公共 Cookie(后端未配置时给出提示)
      act('mode', () => setAccountBotMode(acc.id, 'public'), '已切换为公共 Cookie')
        .then(() => setMode('public'));
    } else {
      // 切到自定义:需先填写 Cookie(下方表单提交时切换)
      setMode('private');
      showToast('success', '请在下方输入自定义 Cookie 并保存', '');
    }
  };

  const savePrivateCookie = () => {
    if (!cookie.trim()) {
      showToast('error', '请输入 Cookie', '');
      return;
    }
    act('mode', () => setAccountBotMode(acc.id, 'private', cookie.trim(), perms), '已使用自定义 Cookie')
      .then(() => { setCookie(''); setMode('private'); });
  };

  const togglePerm = (p: string) => {
    setPerms((prev) => prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]);
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary-500" /></div>;
  }

  return (
    <div className="space-y-4">
      {/* 模式选择 */}
      <div className="card">
        <div className="card-body">
          <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">Cookie 来源</label>
          <div className="flex gap-2">
            {(['public', 'private'] as const).map((m) => (
              <button key={m} onClick={() => switchMode(m)}
                className={
                  'flex-1 h-9 rounded-lg border text-sm transition-colors ' +
                  (mode === m
                    ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                    : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700')
                }>
                {m === 'public' ? '公共 Cookie' : '自定义 Cookie'}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {mode === 'public'
              ? '使用面板统一配置的公共 Cookie，账户内不可查看。'
              : '使用本账户独立的 Cookie，可查看与随时更换。'}
          </p>
        </div>
      </div>

      {/* Bot 卡片 */}
      {bot ? (
        <div className="card">
          <div className="card-header">
            <div className="flex items-center gap-2 min-w-0">
              {bot.icon_url ? (
                <img
                  src={`/api/proxy/image?url=${encodeURIComponent(bot.icon_url)}`}
                  alt="avatar"
                  className="w-8 h-8 rounded-full object-cover shrink-0 bg-white"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center shrink-0">
                  <BotIcon className="w-4 h-4 text-primary-500" />
                </div>
              )}
              <h3 className="font-semibold truncate">{bot.name || 'Bot'}</h3>
            </div>
            <StatusBadge status={bot.enabled && bot.available ? 'enabled' : 'disabled'}
              label={bot.enabled ? '已启用' : '已停用'} />
          </div>
          <div className="card-body space-y-3">
            <p className="text-sm text-gray-600 dark:text-gray-300">
              用户 ID: {bot.user_id} · 可用: {bot.available ? '是' : '否'}
            </p>
            {bot.introduction && (
              <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{bot.introduction}</p>
            )}
            <div className="flex flex-wrap gap-1">
              {PERM_NAMES.filter((p) => bot.permissions.includes(p)).map((p) => (
                <span key={p} className="badge badge-blue">{p}</span>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-100 dark:border-gray-700">
              <Button size="sm" variant={bot.enabled ? 'secondary' : 'success'}
                loading={processing === 'toggle'} disabled={processing === 'toggle'}
                onClick={() => act('toggle', () => bot.enabled ? disableAccountBot(acc.id) : enableAccountBot(acc.id),
                  bot.enabled ? 'Bot 已停用' : 'Bot 已启用')}>
                {bot.enabled ? '停用' : '启用'}
              </Button>
              <Button size="sm" variant="ghost" icon={<RefreshCw className="w-4 h-4" />}
                loading={processing === 'refresh'} disabled={processing === 'refresh'}
                onClick={() => act('refresh', () => refreshAccountBot(acc.id), '已刷新')}>刷新</Button>
              {mode === 'private' && (
                <>
                  <Button size="sm" variant="ghost" icon={<Eye className="w-4 h-4" />}
                    loading={processing === 'cookie'} disabled={processing === 'cookie'}
                    onClick={() => act('cookie', async () => {
                      const r = await getAccountBotCookie(acc.id);
                      setViewedCookie(r.cookie);
                      setShowCookie(true);
                    }, '')}>查看 Cookie</Button>
                  <Button size="sm" variant="ghost" icon={<Trash2 className="w-4 h-4 text-red-500" />}
                    loading={processing === 'del'} disabled={processing === 'del'}
                    onClick={() => act('del', () => deleteAccountBot(acc.id), 'Bot 已删除')}>删除</Button>
                </>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-body">
            <p className="text-sm text-gray-500">
              {mode === 'public'
                ? '尚未使用公共 Cookie 连接（可能面板尚未配置公共 Cookie）。'
                : '尚未配置 Bot，请在下方输入自定义 Cookie。'}
            </p>
          </div>
        </div>
      )}

      {/* 自定义 Cookie 表单(含完整权限设置) */}
      {mode === 'private' && (
        <div className="card">
          <div className="card-header"><h3 className="font-semibold">{bot ? '更换 Cookie' : '配置自定义 Cookie'}</h3></div>
          <div className="card-body space-y-3">
            <textarea value={cookie} onChange={(e) => setCookie(e.target.value)} rows={3}
              className="input w-full font-mono text-xs" placeholder="粘贴 Missevan Cookie..." />
            <div>
              <p className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
                Bot 权限设置(自定义 Cookie 可完整设置)
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {PERM_NAMES.map((p) => (
                  <label key={p}
                    className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 dark:bg-gray-900/40 cursor-pointer text-sm">
                    <input type="checkbox" checked={perms.includes(p)}
                      onChange={() => togglePerm(p)}
                      className="w-4 h-4 accent-primary-600" />
                    <span className="flex-1">
                      <span className="block font-mono text-xs">{p}</span>
                      <span className="block text-[10px] text-gray-400">{PERM_LABELS[p] || p}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <Button loading={processing === 'mode'} disabled={processing === 'mode'}
              onClick={savePrivateCookie}>
              {bot ? '保存并使用此 Cookie' : '创建 Bot'}
            </Button>
          </div>
        </div>
      )}

      {/* Cookie 查看弹框 */}
      {showCookie && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setShowCookie(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-5">
            <h3 className="font-semibold mb-3">Cookie 信息</h3>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs bg-gray-100 dark:bg-gray-900 p-3 rounded-lg">{viewedCookie}</pre>
            <div className="flex justify-end mt-4">
              <Button variant="ghost" size="sm" onClick={() => setShowCookie(false)}>关闭</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// 定时消息 Tab(v1.0.1 布局:间隔卡 + 直播间行 + 消息卡)
// ================================================================== //

export function TimerTab({ acc }: { acc: AccountSummary }) {
  const [data, setData] = useState<TimerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [intervalInput, setIntervalInput] = useState('60');
  const [editor, setEditor] = useState<{ messageId?: string; text: string } | null>(null);
  const [editorSaving, setEditorSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TimerMessageItem | null>(null);
  // 本地 1s 倒计时:每秒重渲染,减去自上次拉取以来的流逝秒数
  const [, setTick] = useState(0);
  const loadedAtRef = useRef(Date.now());

  const load = useCallback(async () => {
    try {
      const d = await fetchAccountTimers(acc.id);
      setData(d);
      setIntervalInput(String(d.interval));
      loadedAtRef.current = Date.now();
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [acc.id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    const ticker = setInterval(() => setTick((x) => x + 1), 1000);
    return () => { clearInterval(t); clearInterval(ticker); };
  }, [load]);

  const act = async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
    setProcessing(key);
    try {
      await fn();
      showToast('success', okMsg, '');
      load();
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
    } finally { setProcessing(''); }
  };

  if (loading && !data) {
    return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary-500" /></div>;
  }

  const messages = data?.global ?? [];
  const position = data?.rooms?.[0]?.position ?? 0;
  const pointer = messages.length > 0 ? position % messages.length : 0;
  // 本地流逝秒数:倒计时每秒递减(30s 静默重同步校正漂移)
  const elapsed = Math.floor((Date.now() - loadedAtRef.current) / 1000);
  const liveCountdown = (s: number) => Math.max(0, s - elapsed);

  const fmtCountdown = (s: number) => {
    if (s >= 60) return `${Math.floor(s / 60)}分${s % 60}秒`;
    return `${s}秒`;
  };

  const saveEditor = async () => {
    if (!editor || !editor.text.trim()) return;
    setEditorSaving(true);
    try {
      if (editor.messageId) {
        await updateAccountTimer(acc.id, editor.messageId, editor.text.trim());
        showToast('success', '消息已更新', '');
      } else {
        await addAccountTimer(acc.id, editor.text.trim());
        showToast('success', '已添加定时消息', '');
      }
      setEditor(null);
      load();
    } catch (e: any) {
      showToast('error', '保存失败', e.message);
    } finally { setEditorSaving(false); }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* 页面头部 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">定时消息队列</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {messages.length} 条消息 · 按轮转间隔发送
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" icon={<RefreshCw className="w-4 h-4" />}
            loading={processing === 'refresh'} disabled={processing === 'refresh'}
            onClick={() => act('refresh', () => load(), '已刷新')}>
            刷新
          </Button>
          <Button variant="primary" icon={<Plus className="w-4 h-4" />}
            onClick={() => setEditor({ text: '' })}>
            添加消息
          </Button>
        </div>
      </div>

      {/* 发送间隔 */}
      <div className="flex items-center gap-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
        <TimerIcon className="w-5 h-5 text-primary-500 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-200">发送间隔</p>
          <p className="text-[10px] text-gray-400">修改后实时生效，不重置执行位置指针</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <input type="number" min={1} value={intervalInput}
            onChange={(e) => setIntervalInput(e.target.value)}
            className="w-24 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
          <span className="text-sm text-gray-500">秒</span>
          <Button size="sm" loading={processing === 'interval'} disabled={processing === 'interval'}
            onClick={() => act('interval', () => setAccountTimerInterval(acc.id, Number(intervalInput)), '间隔已更新')}>
            保存
          </Button>
        </div>
      </div>

      {/* 直播间 */}
      <div className="flex items-center gap-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
        <RadioIcon className="w-5 h-5 text-emerald-500 shrink-0" />
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200 shrink-0">直播间</span>
        <div className="flex-1 max-w-xs">
          <span className="text-xs text-gray-600 dark:text-gray-300">
            {acc.room_name ? `[${acc.room_id}] ${acc.room_name}` : (acc.room_id ? `直播间 ${acc.room_id}` : '未绑定直播间')}
          </span>
        </div>
      </div>

      {/* 消息卡 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-3">
          <RadioIcon className="w-4 h-4 text-emerald-500" />
          {acc.room_name ? `${acc.room_name}（${acc.room_id}）` : `直播间 ${acc.room_id ?? '未绑定'}`} 定时消息
          <span className="text-xs text-gray-400 font-normal">（{messages.length} 条 · 指针 #{messages.length ? pointer + 1 : 0}）</span>
        </h2>
        {messages.length === 0 ? (
          <p className="text-center text-gray-400 py-6 text-sm">暂无定时消息</p>
        ) : (
          <div className="space-y-3">
            {messages.map((m, idx) => (
              <div key={m.message_id}
                className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-sm transition-shadow">
                <span className="text-xs font-bold text-gray-400 w-8 text-center shrink-0">#{idx + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="overflow-hidden text-sm text-gray-800 dark:text-gray-200">
                    <MarqueeText text={m.message} />
                  </div>
                  <p className="text-[10px] text-gray-400 font-mono mt-0.5">
                    直播间 {acc.room_id ?? '-'} · {m.message_id}
                    {idx === pointer && (
                      <span className="ml-2 text-primary-500 font-semibold">▶ 即将执行</span>
                    )}
                  </p>
                </div>
                <span className="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                  <TimerIcon className="w-3 h-3 inline mr-0.5 -mt-0.5" />
                  {fmtCountdown(liveCountdown(m.seconds_until_next))}
                </span>
                <div className="flex items-center gap-1 shrink-0 w-full lg:w-auto justify-end
                                border-t border-gray-100 dark:border-gray-700/50 pt-2 mt-1
                                lg:border-t-0 lg:pt-0 lg:mt-0">
                  <button className="relative group p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 transition-colors"
                    disabled={idx === 0 || processing === m.message_id}
                    onClick={() => act(m.message_id, () => moveAccountTimer(acc.id, m.message_id, -1), '已移动')}>
                    <ChevronUp className="w-4 h-4" />
                  </button>
                  <button className="relative group p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 transition-colors"
                    disabled={idx === messages.length - 1 || processing === m.message_id}
                    onClick={() => act(m.message_id, () => moveAccountTimer(acc.id, m.message_id, 1), '已移动')}>
                    <ChevronDown className="w-4 h-4" />
                  </button>
                  <button className="relative group p-1.5 rounded-lg hover:bg-emerald-100 dark:hover:bg-emerald-900/30 text-emerald-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    disabled={idx !== pointer || processing === m.message_id}
                    onClick={() => act(m.message_id, () => sendAccountTimerNow(acc.id, m.message_id), '已发送')}>
                    <Send className="w-4 h-4" />
                    <TooltipLabel text="立即发送（仅即将执行的消息）" />
                  </button>
                  <button className="relative group p-1.5 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30 text-amber-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    disabled={idx !== pointer || processing === m.message_id}
                    onClick={() => act(m.message_id, () => skipAccountTimer(acc.id, m.message_id), '已跳过')}>
                    <SkipForward className="w-4 h-4" />
                    <TooltipLabel text="跳过当前待执行消息（指针后移）" />
                  </button>
                  <button className="relative group p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                    onClick={() => setEditor({ messageId: m.message_id, text: m.message })}
                    title="编辑">
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button className="relative group p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-colors"
                    onClick={() => setDeleteTarget(m)}>
                    <Trash2 className="w-4 h-4" />
                    <TooltipLabel text="删除" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 添加/编辑弹框 */}
      {editor && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setEditor(null)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 p-5">
            <h3 className="font-semibold mb-3">{editor.messageId ? '编辑定时消息' : '添加定时消息'}</h3>
            <textarea value={editor.text} onChange={(e) => setEditor({ ...editor, text: e.target.value })}
              rows={3} autoFocus className="input w-full" placeholder="输入定时消息内容..." />
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="ghost" size="sm" onClick={() => setEditor(null)}>取消</Button>
              <Button size="sm" loading={editorSaving} onClick={saveEditor}>
                {editor.messageId ? '保存' : '添加'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹框 */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除定时消息"
        message="确定删除这条定时消息吗？"
        danger
        loading={processing === deleteTarget?.message_id}
        onConfirm={async () => {
          if (!deleteTarget) return;
          setProcessing(deleteTarget.message_id);
          try {
            await deleteAccountTimer(acc.id, deleteTarget.message_id);
            showToast('success', '已删除', '');
            setDeleteTarget(null);
            load();
          } catch (e: any) {
            showToast('error', '删除失败', e.message);
          } finally { setProcessing(''); }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

/** 悬浮提示标签(v1.0.1 样式) */
function TooltipLabel({ text }: { text: string }) {
  return (
    <span role="tooltip"
      className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 z-50
                 whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                 opacity-0 group-hover:opacity-100 transition-opacity duration-100">
      {text}
    </span>
  );
}

function TimerIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="10" x2="14" y1="2" y2="2" />
      <line x1="12" x2="15" y1="14" y2="11" />
      <circle cx="12" cy="14" r="8" />
    </svg>
  );
}

function RadioIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9" />
      <path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5" />
      <circle cx="12" cy="12" r="2" />
      <path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5" />
      <path d="M19.1 4.9C23 8.8 23 15.1 19.1 19" />
    </svg>
  );
}

// 插件 Tab(v1.0.1 卡片样式:底部开关 + 图标按钮组)
// ================================================================== //

const PLUGIN_FILTERS = [
  { id: 'all', label: '全部' },
  { id: 'enabled', label: '已启用' },
  { id: 'disabled', label: '已禁用' },
] as const;
type PluginFilter = (typeof PLUGIN_FILTERS)[number]['id'];

export function PluginsTab({ acc, pluginPageBase }: { acc: AccountSummary; pluginPageBase?: string }) {
  const [plugins, setPlugins] = useState<PluginSummary[]>([]);
  const [libraryVersions, setLibraryVersions] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<PluginFilter>('all');
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [drawerTarget, setDrawerTarget] = useState<{ name: string; tab?: string } | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<PluginSummary | null>(null);

  const load = useCallback(async () => {
    try {
      const [installed, library] = await Promise.all([
        fetchAccountPlugins(acc.id),
        fetchAccountLibrary(acc.id).catch(() => []),
      ]);
      setPlugins(installed);
      const versions: Record<string, string> = {};
      for (const p of library) {
        versions[p.name] = p.version;
      }
      setLibraryVersions(versions);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [acc.id]);

  useEffect(() => { load(); }, [load]);

  const act = async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
    setProcessing(key);
    try {
      await fn();
      showToast('success', okMsg, '');
      load();
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
    } finally { setProcessing(''); }
  };

  // 已安装版本低于插件库版本 → 可更新
  const updateVersion = (p: PluginSummary): string | null => {
    const libV = libraryVersions[p.name];
    if (!libV) return null;
    const a = String(p.version).split('.').map((x) => parseInt(x, 10) || 0);
    const b = libV.split('.').map((x) => parseInt(x, 10) || 0);
    const len = Math.max(a.length, b.length);
    for (let i = 0; i < len; i++) {
      const x = a[i] ?? 0;
      const y = b[i] ?? 0;
      if (x !== y) return x < y ? libV : null;
    }
    return null;
  };

  const openDrawer = (name: string, tab?: string) => {
    setDrawerTarget({ name, tab });
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-primary-500" /></div>;
  }

  const enabledCount = plugins.filter((p) => p.enabled).length;
  const visible = plugins.filter((p) =>
    filter === 'all' ? true : filter === 'enabled' ? p.enabled : !p.enabled
  );

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">已安装插件</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {plugins.length} 个插件 · {enabledCount} 个已启用
          </p>
        </div>
        <Link to="/account/library">
          <Button size="sm" variant="secondary" icon={<Plus className="w-4 h-4" />}>插件库</Button>
        </Link>
      </div>

      {/* 筛选 */}
      <div className="flex gap-1 p-1 rounded-lg bg-gray-100 dark:bg-gray-800 w-fit">
        {PLUGIN_FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={
              'px-3 py-1.5 text-xs font-medium rounded-md transition-all ' +
              (filter === f.id
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300')
            }>
            {f.label}
          </button>
        ))}
      </div>

      {/* 卡片网格 */}
      {visible.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="p-10 text-center text-gray-400 text-sm">
            {plugins.length === 0 ? '尚未安装任何插件 —— 请前往插件库安装' : '该分类下暂无插件'}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {visible.map((p) => (
            <div key={p.name}
              className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-all duration-200 flex flex-col">
              {/* 卡片主体 */}
              <div className="p-5 flex-1">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-white">
                      <MarqueeText text={p.display_name || p.name} />
                    </h3>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs font-mono text-gray-400 dark:text-gray-500">v{p.version}</span>
                      {updateVersion(p) && (
                        <span
                          className="inline-flex items-center gap-1 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium text-[10px] px-1.5 py-0"
                          title={`插件库最新版本 v${updateVersion(p)}`}
                        >
                          <span className="inline-block rounded-full w-1.5 h-1.5 bg-blue-500" />
                          可更新
                        </span>
                      )}
                      <span className="text-gray-300 dark:text-gray-600">·</span>
                      <span className="text-xs text-gray-400 dark:text-gray-500">{p.author}</span>
                    </div>
                  </div>
                  <span className={
                    'inline-flex items-center gap-1.5 rounded-full font-medium text-[10px] px-1.5 py-0 ' +
                    (p.enabled
                      ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400'
                      : 'bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-surface-400')
                  }>
                    <span className={`inline-block rounded-full w-1.5 h-1.5 ${p.enabled ? 'bg-emerald-500' : 'bg-surface-400'}`} />
                    {p.enabled ? '已启用' : '未启用'}
                  </span>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-1">
                  {p.short_desc || p.desc || '无描述'}
                </p>
                <p className="text-[11px] font-mono text-gray-400 dark:text-gray-500 truncate">
                  {p.plugin_id}
                </p>
              </div>

              {/* 底部:开关 + 图标按钮组 */}
              <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-gray-700/50 bg-gray-50/50 dark:bg-gray-800/50 rounded-b-xl">
                <button
                  onClick={() => act(p.name, () => p.enabled ? disableAccountPlugin(acc.id, p.name) : enableAccountPlugin(acc.id, p.name),
                    p.enabled ? '已禁用' : '已启用')}
                  disabled={processing === p.name}
                  className={
                    'relative group inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ' +
                    'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ' +
                    'disabled:cursor-not-allowed disabled:opacity-60 ' +
                    (p.enabled ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600')
                  }>
                  <span className={
                    'inline-block h-4 w-4 rounded-full bg-white shadow-sm flex items-center justify-center transition-transform duration-200 ' +
                    (p.enabled ? 'translate-x-6' : 'translate-x-1')
                  }>
                    {processing === p.name && <Loader2 className="h-2.5 w-2.5 animate-spin text-primary-500" />}
                  </span>
                  <span role="tooltip"
                    className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 z-50
                               whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                               bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                               opacity-0 group-hover:opacity-100 transition-opacity duration-100">
                    {p.enabled ? '点击禁用' : '点击启用'}
                  </span>
                </button>

                <div className="flex items-center gap-0.5 lg:gap-1 flex-nowrap">
                  <IconBtn icon={<Eye className="w-3.5 h-3.5" />} label="基本信息" onClick={() => openDrawer(p.name, 'info')} />
                  <IconBtn icon={<SettingsIcon />} label="配置" onClick={() => openDrawer(p.name, 'config')} />
                  <IconBtn icon={<RefreshCw className="w-3.5 h-3.5" />} label="重载"
                    loading={processing === `reload-${p.name}`} disabled={processing === `reload-${p.name}`}
                    onClick={() => act(`reload-${p.name}`, () => reloadAccountPlugin(acc.id, p.name), '已重载')} />
                  {p.has_ui && (
                    <Link to={`${pluginPageBase ?? '/account/plugin'}/${p.name}/page`}>
                      <IconBtn icon={<ExternalLink className="w-3.5 h-3.5" />} label="插件主页" />
                    </Link>
                  )}
                  <IconBtn icon={<BookOpenIcon />} label="文档" onClick={() => openDrawer(p.name, 'readme')} />
                  <IconBtn icon={<Trash2 className="w-3.5 h-3.5" />} label="卸载" onClick={() => setUninstallTarget(p)} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 详情抽屉(账户模式:含配置/权限) */}
      {drawerTarget && (
        <PluginDrawer
          pluginName={drawerTarget.name}
          open
          accountId={acc.id}
          initialTab={drawerTarget.tab}
          onClose={() => setDrawerTarget(null)}
          onUpdate={load}
        />
      )}

      {/* 卸载确认(v1.0.1 风格:可选删除配置/持久化数据) */}
      <UninstallDialog
        open={uninstallTarget !== null}
        pluginName={(uninstallTarget?.display_name || uninstallTarget?.name) ?? ''}
        loading={processing === `del-${uninstallTarget?.name}`}
        onConfirm={async (deleteConfig, deleteData) => {
          if (!uninstallTarget) return;
          setProcessing(`del-${uninstallTarget.name}`);
          try {
            await uninstallAccountPluginFromAccount(acc.id, uninstallTarget.name, deleteConfig, deleteData);
            showToast('success', '已卸载');
            setUninstallTarget(null);
            load();
          } catch (e: any) {
            showToast('error', '卸载失败', e.message);
          } finally { setProcessing(''); }
        }}
        onCancel={() => setUninstallTarget(null)}
      />
    </div>
  );
}

/** 底部图标按钮(v1.0.1 样式:ghost + 悬浮提示) */
function IconBtn({ icon, label, onClick, loading, disabled }: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  loading?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="relative group inline-flex items-center justify-center font-medium rounded-lg
                 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2
                 disabled:opacity-50 disabled:cursor-not-allowed
                 bg-transparent text-gray-600 dark:text-gray-400
                 hover:bg-gray-100 dark:hover:bg-gray-800 focus:ring-gray-400
                 h-8 px-3 text-xs gap-1.5">
      <span className="h-3.5 w-3.5 [&_svg]:h-full [&_svg]:w-full shrink-0">
        {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      </span>
      <span role="tooltip"
        className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 z-50
                   whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                   bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                   opacity-0 group-hover:opacity-100 transition-opacity duration-100">
        {label}
      </span>
    </button>
  );
}

function SettingsIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function BookOpenIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
      <path d="M12 7v14" />
      <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
    </svg>
  );
}

// ================================================================== //
// 页面主体
// ================================================================== //

type TabKey = 'overview' | 'live' | 'bot' | 'timer' | 'plugins';

const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
  { key: 'overview', label: '概览', icon: <BotIcon className="w-4 h-4" /> },
  { key: 'live', label: '直播间', icon: <Radio className="w-4 h-4" /> },
  { key: 'bot', label: 'Bot', icon: <BotIcon className="w-4 h-4" /> },
  { key: 'timer', label: '定时消息', icon: <Clock className="w-4 h-4" /> },
  { key: 'plugins', label: '插件', icon: <Puzzle className="w-4 h-4" /> },
];

export function AccountDetailPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);
  const [acc, setAcc] = useState<AccountSummary | null>(null);
  const [tab, setTab] = useState<TabKey>('overview');
  const [loading, setLoading] = useState(true);
  const [renewOpen, setRenewOpen] = useState(false);
  const [renewMode, setRenewMode] = useState<'days' | 'code'>('days');
  const [renewing, setRenewing] = useState(false);

  const load = useCallback(async () => {
    try {
      setAcc(await fetchAccountSummary(accountId));
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [accountId]);

  useEffect(() => { load(); }, [load]);

  if (loading || !acc) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
        {!loading && <p className="text-sm text-gray-400">账户不存在</p>}
        <Link to="/" className="flex items-center gap-1 text-sm text-primary-600 hover:underline">
          <ArrowLeft className="w-4 h-4" /> 返回账户总览
        </Link>
      </div>
    );
  }

  const handleRenew = async (aid: number, data: { days?: number }) => {
    setRenewing(true);
    try {
      await renewAccount(aid, data);
      showToast('success', '续期成功', '');
      setRenewOpen(false);
      load();
    } catch (e: any) {
      showToast('error', '续期失败', e.message);
    } finally { setRenewing(false); }
  };

  const handleRedeem = async (aid: number, code: string) => {
    setRenewing(true);
    try {
      await redeemAccount(aid, code);
      showToast('success', '兑换成功', '');
      setRenewOpen(false);
      load();
    } catch (e: any) {
      showToast('error', '兑换失败', e.message);
    } finally { setRenewing(false); }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">{acc.name}</h1>
              <span className={
                'rounded-full px-2 py-0.5 text-xs font-medium ' +
                (acc.bot_public
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                  : 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300')
              }>
                {acc.bot_public ? '公共 Bot' : '私有 Bot'}
              </span>
              <ExpiryBadge expiresAt={acc.expires_at} pausedReason={acc.paused_reason} />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              直播间 {acc.room_id ?? '未绑定'} · 插件 {acc.enabled_plugin_count}/{acc.plugin_count}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" icon={<KeyRound className="w-4 h-4" />}
            onClick={() => { setRenewMode('code'); setRenewOpen(true); }}>兑换</Button>
          <Button size="sm" icon={<CalendarClock className="w-4 h-4" />}
            onClick={() => { setRenewMode('days'); setRenewOpen(true); }}>续期</Button>
        </div>
      </div>

      {/* Tabs(移动端均分,无横向滚动条) */}
      <div className="flex border-b border-gray-200 dark:border-gray-700">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={
              'flex-1 min-w-0 flex items-center justify-center gap-1 sm:gap-1.5 px-1 sm:px-4 py-2.5 text-xs sm:text-sm font-medium border-b-2 -mb-px transition-colors ' +
              (tab === t.key
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300')
            }>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab acc={acc} onRenew={(m) => { setRenewMode(m); setRenewOpen(true); }} />}
      {tab === 'live' && <LiveTab acc={acc} />}
      {tab === 'bot' && <BotTab acc={acc} onAccountChanged={load} />}
      {tab === 'timer' && <TimerTab acc={acc} />}
      {tab === 'plugins' && <PluginsTab acc={acc} pluginPageBase={`/account/${acc.id}/plugin`} />}

      <RenewDialog
        open={renewOpen}
        accountId={acc.id}
        accountName={acc.name}
        mode={renewMode}
        loading={renewing}
        onRenew={handleRenew}
        onRedeem={handleRedeem}
        onCancel={() => setRenewOpen(false)}
      />
    </div>
  );
}
