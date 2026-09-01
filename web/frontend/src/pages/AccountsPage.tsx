import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus, Settings2, Trash2, KeyRound, CalendarClock, Bot as BotIcon,
  Radio, Puzzle, Clock, AlertTriangle, Loader2, Lock, Hourglass,
} from 'lucide-react';
import {
  fetchPanelOverview, createAccount, deleteAccount, renewAccount, redeemAccount,
  resetAccountCredentials,
} from '../api/client';
import type { AccountSummary, AccountCreateRequest, PanelOverview, RenewRequest } from '../api/types';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { ExpiryBadge } from '../components/ExpiryBadge';
import { CreateAccountDialog, RenewDialog, CredentialsDialog } from '../components/AccountDialogs';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { showToast } from '../hooks/useToast';

export function AccountsPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<PanelOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [renewTarget, setRenewTarget] = useState<AccountSummary | null>(null);
  const [renewMode, setRenewMode] = useState<'days' | 'set' | 'code'>('days');
  const [renewing, setRenewing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AccountSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [credTarget, setCredTarget] = useState<AccountSummary | null>(null);
  const [credBusy, setCredBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchPanelOverview();
      setOverview(data);
    } catch (e: any) {
      // 401 由 client 统一处理;其他错误静默,保留旧数据
      if (e.status !== 401) showToast('error', '加载失败', e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const handleCreate = async (data: AccountCreateRequest) => {
    setCreating(true);
    try {
      const acc = await createAccount(data);
      showToast('success', `账户「${acc.name}」已创建`, '');
      setCreateOpen(false);
      load();
    } catch (e: any) {
      showToast('error', '创建失败', e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleRenew = async (id: number, data: RenewRequest) => {
    setRenewing(true);
    try {
      await renewAccount(id, data);
      showToast('success', '续期成功', '');
      setRenewTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '续期失败', e.message);
    } finally {
      setRenewing(false);
    }
  };

  const handleRedeem = async (id: number, code: string) => {
    setRenewing(true);
    try {
      await redeemAccount(id, code);
      showToast('success', '兑换成功', '');
      setRenewTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '兑换失败', e.message);
    } finally {
      setRenewing(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteAccount(deleteTarget.id, false);
      showToast('success', `账户「${deleteTarget.name}」已删除`, '');
      setDeleteTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '删除失败', e.message);
    } finally {
      setDeleting(false);
    }
  };

  if (loading && !overview) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  const accounts = overview?.accounts ?? [];

  return (
    <div className="space-y-6 animate-fade-in max-w-6xl">
      {/* 头部(移动端可换行) */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold">账户总览</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            每个账户对应一个直播间与一个 Bot
            {overview && ` · ${overview.total} 个账户 · ${overview.expired_count} 个已过期`}
          </p>
        </div>
        <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
          创建账户
        </Button>
      </div>

      {/* 公共 Bot 提示 */}
      {overview && !overview.public_bot_configured && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          面板公共 Cookie 尚未配置 —— 使用公共 Bot 的账户将无法工作,请前往
          <button className="underline font-medium" onClick={() => navigate('/settings')}>设置</button>
          配置。
        </div>
      )}

      {/* 账户卡片 */}
      {accounts.length === 0 ? (
        <div className="card">
          <div className="card-body flex flex-col items-center justify-center py-16 text-center">
            <p className="text-gray-500 dark:text-gray-400">暂无账户</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
              点击右上角「创建账户」开始
            </p>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {accounts.map((acc) => (
            <div key={acc.id} className="card hover:shadow-lg transition-shadow">
              <div className="card-header">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <h3 className="font-semibold truncate">{acc.name}</h3>
                    <span className={
                      'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ' +
                      (acc.bot_public
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                        : 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300')
                    }>
                      {acc.bot_public ? '公共 Bot' : '私有 Bot'}
                    </span>
                  </div>
                  {acc.username && (
                    <p className="text-xs text-gray-400 truncate" title={`登录用户名: ${acc.username}`}>
                      @{acc.username}
                    </p>
                  )}
                </div>
                <ExpiryBadge expiresAt={acc.expires_at} pausedReason={acc.paused_reason} />
              </div>
              <div className="card-body space-y-3">
                {/* 状态行 */}
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                    <BotIcon className="w-4 h-4" />
                    {acc.bot_name || (acc.bot_available ? '已连接' : '未配置')}
                  </div>
                  <div className="flex justify-end">
                    <StatusBadge status={acc.bot_enabled && acc.bot_available ? 'enabled' : 'disabled'} label="Bot" />
                  </div>
                  <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                    <Radio className="w-4 h-4" />
                    <span className="truncate">{acc.room_name || (acc.room_id ? `房间 ${acc.room_id}` : '未绑定房间')}</span>
                  </div>
                  <div className="flex justify-end">
                    <StatusBadge status={acc.room_connected ? 'online' : 'offline'} label={acc.room_connected ? '已连接' : '未连接'} />
                  </div>
                </div>
                {/* 统计 */}
                <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                  <span className="flex items-center gap-1"><Puzzle className="w-3.5 h-3.5" />插件 {acc.enabled_plugin_count}/{acc.plugin_count}</span>
                  <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />定时 {acc.timer_message_count}</span>
                </div>
                {acc.resume_error && (
                  <p className="text-xs text-red-600 dark:text-red-400 truncate" title={acc.resume_error}>
                    {acc.resume_error}
                  </p>
                )}
                {/* 操作 */}
                <div className="flex items-center justify-between pt-1 border-t border-gray-100 dark:border-gray-700">
                  <Button variant="primary" size="sm" onClick={() => navigate(`/account/${acc.id}`)}>
                    管理
                  </Button>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" icon={<CalendarClock className="w-4 h-4" />}
                      tooltip="续期" onClick={() => { setRenewMode('days'); setRenewTarget(acc); }} />
                    <Button variant="ghost" size="sm" icon={<Hourglass className="w-4 h-4" />}
                      tooltip="设置剩余天数" onClick={() => { setRenewMode('set'); setRenewTarget(acc); }} />
                    <Button variant="ghost" size="sm" icon={<KeyRound className="w-4 h-4" />}
                      tooltip="兑换授权码" onClick={() => { setRenewMode('code'); setRenewTarget(acc); }} />
                    <Button variant="ghost" size="sm" icon={<Lock className="w-4 h-4" />}
                      tooltip="重置登录凭据" onClick={() => setCredTarget(acc)} />
                    <Button variant="ghost" size="sm" icon={<Settings2 className="w-4 h-4" />}
                      tooltip="账户设置" onClick={() => navigate(`/account/${acc.id}`)} />
                    <Button variant="ghost" size="sm" icon={<Trash2 className="w-4 h-4 text-red-500" />}
                      tooltip="删除账户" onClick={() => setDeleteTarget(acc)} />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateAccountDialog
        open={createOpen}
        loading={creating}
        onConfirm={handleCreate}
        onCancel={() => setCreateOpen(false)}
      />
      <RenewDialog
        open={renewTarget !== null}
        accountId={renewTarget?.id ?? 0}
        accountName={renewTarget?.name ?? ''}
        mode={renewMode}
        loading={renewing}
        onRenew={handleRenew}
        onRedeem={handleRedeem}
        onCancel={() => setRenewTarget(null)}
      />
      <CredentialsDialog
        open={credTarget !== null}
        accountName={credTarget?.name ?? ''}
        currentUsername={credTarget?.username ?? ''}
        loading={credBusy}
        onConfirm={async (username, password) => {
          if (!credTarget) return;
          setCredBusy(true);
          try {
            await resetAccountCredentials(credTarget.id, username, password);
            showToast('success', `账户「${credTarget.name}」登录凭据已重置`, '');
            setCredTarget(null);
            load();
          } catch (e: any) {
            showToast('error', '重置失败', e.message);
          } finally { setCredBusy(false); }
        }}
        onCancel={() => setCredTarget(null)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除账户"
        message={`确定要删除账户「${deleteTarget?.name ?? ''}」吗？运行时数据目录将保留(可恢复)。`}
        danger
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
