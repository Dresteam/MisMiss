import { useEffect, useState } from 'react';
import {
  Bot, Key, RefreshCw, ShieldCheck, Eye, EyeOff, Copy, Check, User,
} from 'lucide-react';
import {
  fetchBotInfo, createBot, refreshBot, verifyBot, getBotCookieRaw, enableBot, disableBot, deleteBot,
} from '../api/client';
import type { BotInfo } from '../api/types';
import { showToast } from '../hooks/useToast';
import { StatusBadge } from '../components/StatusBadge';
import { Button } from '../components/Button';
import { HoverTip } from '../components/HoverTip';
import { MarqueeText } from '../components/MarqueeText';
import { ConfirmDialog } from '../components/ConfirmDialog';

const ALL_PERMISSIONS = [
  'SEND_LIVESTREAM_MESSAGE',
  'SEND_PRIVATE_MESSAGE',
  'SEND_BACKPACK_GIFT',
  'SEND_GIFT',
  'EXPOSE_COOKIE',
];

const PERM_DESC: Record<string, string> = {
  SEND_LIVESTREAM_MESSAGE: '发送直播间消息',
  SEND_PRIVATE_MESSAGE: '发送私信',
  SEND_BACKPACK_GIFT: '赠送背包礼物',
  SEND_GIFT: '赠送直售礼物',
  EXPOSE_COOKIE: 'Cookie完全访问',
};

export function BotPage() {
  const [bot, setBot] = useState<BotInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // Create form
  const [cookie, setCookie] = useState('');
  const [showCookie, setShowCookie] = useState(false);
  const [selectedPerms, setSelectedPerms] = useState<string[]>(['SEND_LIVESTREAM_MESSAGE']);
  const [creating, setCreating] = useState(false);
  const [actionLoading, setActionLoading] = useState<Set<string>>(new Set());

  // Cookie view
  const [cookieData, setCookieData] = useState<string | null>(null);
  const [showCookieDialog, setShowCookieDialog] = useState(false);
  const [cookieCopied, setCookieCopied] = useState(false);

  // Confirm dialogs
  const [confirmAction, setConfirmAction] = useState<{
    type: 'enable' | 'disable' | 'delete';
    run: () => Promise<void>;
  } | null>(null);

  const load = async () => {
    try {
      const info = await fetchBotInfo();
      setBot(info);
    } catch (e: any) {
      // Bot not configured yet — that's ok
      setBot(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!cookie.trim()) {
      showToast('warning', '请输入 Cookie');
      return;
    }
    setCreating(true);
    try {
      const info = await createBot({ cookie: cookie.trim(), permissions: selectedPerms });
      setBot(info);
      setCookie('');
      showToast('success', 'Bot 创建成功', `${info.name} (ID: ${info.user_id})`);
    } catch (e: any) {
      showToast('error', '创建失败', e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleRefresh = async () => {
    setActionLoading((prev) => new Set(prev).add('refresh'));
    try {
      await refreshBot();
      await load();
      showToast('success', '刷新完成');
    } catch (e: any) {
      showToast('error', '刷新失败', e.message);
    } finally {
      setActionLoading((prev) => { const n = new Set(prev); n.delete('refresh'); return n; });
    }
  };

  const handleVerify = async () => {
    setActionLoading((prev) => new Set(prev).add('verify'));
    try {
      const res = await verifyBot();
      showToast(res.success ? 'success' : 'warning', res.message);
    } catch (e: any) {
      showToast('error', '验证失败', e.message);
    } finally {
      setActionLoading((prev) => { const n = new Set(prev); n.delete('verify'); return n; });
    }
  };

  const handleViewCookie = async () => {
    try {
      const data = await getBotCookieRaw();
      setCookieData(data.cookie);
      setShowCookieDialog(true);
    } catch (e: any) {
      showToast('error', '无法获取 Cookie', e.message);
    }
  };

  const handleTogglePerm = (perm: string) => {
    setSelectedPerms((prev) =>
      prev.includes(perm) ? prev.filter((p) => p !== perm) : [...prev, perm],
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl">
      <h1 className="text-2xl font-bold text-surface-900 dark:text-white">Bot 管理</h1>

      {/* Bot Info Card */}
      {bot && bot.user_id > 0 ? (
        <div className="card">
          <div className="card-header flex items-center justify-between gap-2">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center overflow-hidden shrink-0">
                {bot.icon_url ? (
                  <img src={`/api/proxy/image?url=${encodeURIComponent(bot.icon_url)}`} alt="" className="w-full h-full object-cover" />
                ) : (
                  <User className="w-5 h-5 text-primary-600" />
                )}
              </div>
              <div className="min-w-0">
                <h3 className="font-semibold">
                  <MarqueeText text={bot.name} />
                </h3>
                <p className="text-xs text-surface-500">ID: {bot.user_id}</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0 whitespace-nowrap">
              <StatusBadge status={bot.enabled ? 'enabled' : 'disabled'} />
              <StatusBadge
                status={bot.available ? 'online' : 'offline'}
                label={bot.available ? '可用' : '不可用'}
              />
            </div>
          </div>
          <div className="card-body space-y-4">
            {bot.introduction && (
              <div>
                <p className="text-xs text-surface-500 mb-1">简介</p>
                <p className="text-sm text-surface-700 dark:text-surface-300">{bot.introduction}</p>
              </div>
            )}
            <div>
              <p className="text-xs text-surface-500 mb-1">权限</p>
              <div className="flex flex-wrap gap-1.5">
                {bot.permissions.map((p) => (
                  <span key={p} className="badge-blue relative group">
                    {p}
                    <HoverTip text={PERM_DESC[p]} />
                  </span>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button variant="secondary" size="sm" icon={<RefreshCw />}
                onClick={handleRefresh}
                loading={actionLoading.has('refresh')}>刷新信息</Button>
              <Button variant="secondary" size="sm" icon={<ShieldCheck />}
                onClick={handleVerify}
                loading={actionLoading.has('verify')}>验证 Cookie</Button>
              <Button variant="secondary" size="sm" icon={<Eye />}
                onClick={handleViewCookie}>查看 Cookie</Button>
              {bot.enabled ? (
                <Button variant="destructive" size="sm"
                  onClick={() => setConfirmAction({
                    type: 'disable',
                    run: async () => {
                      setActionLoading((prev) => new Set(prev).add('disable'));
                      await disableBot(); await load();
                      showToast('success', 'Bot 已停用');
                      setActionLoading((prev) => { const n = new Set(prev); n.delete('disable'); return n; });
                    },
                  })}
                  loading={actionLoading.has('disable')}>停用 Bot</Button>
              ) : (
                <Button variant="success" size="sm"
                  onClick={() => setConfirmAction({
                    type: 'enable',
                    run: async () => {
                      setActionLoading((prev) => new Set(prev).add('enable'));
                      await enableBot(); await load();
                      showToast('success', 'Bot 已启用');
                      setActionLoading((prev) => { const n = new Set(prev); n.delete('enable'); return n; });
                    },
                  })}
                  loading={actionLoading.has('enable')}>启用 Bot</Button>
              )}
              <Button variant="destructive" size="sm"
                onClick={() => setConfirmAction({
                  type: 'delete',
                  run: async () => {
                    setActionLoading((prev) => new Set(prev).add('delete'));
                    await deleteBot(); await load();
                    showToast('success', 'Bot 已删除');
                    setActionLoading((prev) => { const n = new Set(prev); n.delete('delete'); return n; });
                  },
                })}
                loading={actionLoading.has('delete')}>删除 Bot</Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-body text-center py-12">
            <Bot className="w-12 h-12 text-surface-300 mx-auto mb-3" />
            <p className="text-surface-500">尚未配置 Bot</p>
            <p className="text-xs text-surface-400 mt-1">请在下方输入 Cookie 创建</p>
          </div>
        </div>
      )}

      {/* Create / Update Bot Form */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Key className="w-4 h-4 text-primary-500" />
          {bot && bot.user_id > 0 ? '更新 Bot' : '创建 Bot'}
        </div>
        <div className="card-body space-y-4">
          {/* Cookie input */}
          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-1.5">
              Cookie
            </label>
            <div className="relative">
              <input
                type={showCookie ? 'text' : 'password'}
                value={cookie}
                onChange={(e) => setCookie(e.target.value)}
                placeholder="粘贴 Missevan Cookie..."
                className="input pr-10 font-mono text-xs"
              />
              <button
                onClick={() => setShowCookie(!showCookie)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600"
              >
                {showCookie ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {cookie && (
              <p className="text-xs text-surface-400 mt-1">长度: {cookie.length} 字符</p>
            )}
          </div>

          {/* Permission selection */}
          <div>
            <label className="block text-sm font-medium text-surface-700 dark:text-surface-300 mb-2">
              权限设置
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {ALL_PERMISSIONS.map((perm) => (
                <label
                  key={perm}
                  className={`flex items-center gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-all ${
                    selectedPerms.includes(perm)
                      ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                      : 'border-surface-200 dark:border-surface-700 hover:border-surface-300'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedPerms.includes(perm)}
                    onChange={() => handleTogglePerm(perm)}
                    className="rounded text-primary-600 focus:ring-primary-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-surface-900 dark:text-surface-100">
                      {perm}
                    </p>
                    <p className="text-[10px] text-surface-500">{PERM_DESC[perm]}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <Button variant="primary" size="lg" className="w-full"
            onClick={handleCreate} loading={creating}
            disabled={!cookie.trim()}
            icon={creating ? undefined : <Key />}>
            {creating ? '创建中...' : bot && bot.user_id > 0 ? '更新 Cookie' : '创建 Bot'}
          </Button>
        </div>
      </div>

      {/* Cookie View Dialog */}
      {showCookieDialog && cookieData && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowCookieDialog(false)} />
          <div className="relative bg-white dark:bg-surface-800 rounded-xl shadow-2xl p-6 max-w-2xl w-full mx-4 animate-slide-in-up">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-amber-500" />
                Cookie 信息
              </h3>
              <Button variant="secondary" size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(cookieData);
                  setCookieCopied(true);
                  setTimeout(() => setCookieCopied(false), 2000);
                  showToast('success', '已复制到剪贴板');
                }}
                icon={cookieCopied ? <Check /> : <Copy />}>
                {cookieCopied ? '已复制' : '复制'}
              </Button>
            </div>
            <div className="bg-surface-100 dark:bg-surface-900 rounded-lg p-4 max-h-60 overflow-y-auto">
              <p className="text-xs font-mono break-all text-surface-600 dark:text-surface-400 select-all">
                {cookieData}
              </p>
            </div>
            <p className="text-xs text-surface-400 mt-2">长度: {cookieData.length} 字符</p>
            <div className="mt-4 flex justify-end">
              <Button variant="secondary" onClick={() => setShowCookieDialog(false)}>关闭</Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={!!confirmAction}
        title={
          confirmAction?.type === 'disable' ? '停用 Bot' :
          confirmAction?.type === 'delete' ? '删除 Bot' : '启用 Bot'}
        message={
          confirmAction?.type === 'disable' ? '停用后 Bot 将停止所有消息发送和事件处理，确定要继续吗？' :
          confirmAction?.type === 'delete' ? '删除 Bot 将清除 Cookie 和权限信息，服务器恢复为无 Bot 状态。此操作不可撤销！' :
          '确定要启用 Bot 吗？'}
        variant={confirmAction?.type === 'disable' || confirmAction?.type === 'delete' ? 'danger' : 'default'}
        confirmLabel={
          confirmAction?.type === 'disable' ? '停用' :
          confirmAction?.type === 'delete' ? '确认删除' : '启用'}
        onConfirm={async () => {
          if (confirmAction) {
            await confirmAction.run();
            setConfirmAction(null);
          }
        }}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}
