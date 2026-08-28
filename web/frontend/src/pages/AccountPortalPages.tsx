/** 账户界面页面(v1.0.1 风格左侧导航,独立于面板)。 */

import { useCallback, useEffect, useState } from 'react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
} from 'recharts';
import { Bot as BotIcon, Radio, Puzzle, Clock, Loader2, KeyRound, RefreshCw, Plus } from 'lucide-react';
import {
  fetchAccountSummary, enableAccountBot, disableAccountBot, redeemAccountCode,
  fetchAccountLibrary, installAccountPlugin,
} from '../api/client';
import type { AccountSummary, LibraryPlugin } from '../api/types';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { ExpiryBadge } from '../components/ExpiryBadge';
import { MarqueeText } from '../components/MarqueeText';
import { RenewDialog } from '../components/AccountDialogs';
import { PluginDrawer } from '../components/PluginDrawer';
import { useAuth } from '../hooks/useAuth';
import { showToast } from '../hooks/useToast';
import {
  OverviewTab, LiveTab, BotTab, TimerTab, PluginsTab,
} from './AccountDetailPage';

// ================================================================== //
// 账户摘要 Hook
// ================================================================== //

export function useAccountSummary(pollMs?: number): { acc: AccountSummary | null; reload: () => void } {
  const auth = useAuth();
  const [acc, setAcc] = useState<AccountSummary | null>(null);

  const load = useCallback(async () => {
    if (!auth.accountId) return;
    try {
      setAcc(await fetchAccountSummary(auth.accountId));
    } catch { /* ignore */ }
  }, [auth.accountId]);

  useEffect(() => {
    load();
    if (!pollMs) return;
    const t = setInterval(load, pollMs);
    return () => clearInterval(t);
  }, [load, pollMs]);

  return { acc, reload: load };
}

// ================================================================== //
// 概览页(v1.0.1 仪表盘风格:统计卡片 + 饼图 + Bot 启停开关)
// ================================================================== //

const PIE_COLORS = ['#10b981', '#a1a1aa'];
const PIE_COLORS_BLUE = ['#2563eb', '#a1a1aa'];

export function AccountOverviewPage() {
  const auth = useAuth();
  const { acc, reload } = useAccountSummary(10000);
  const [toggling, setToggling] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [redeeming, setRedeeming] = useState(false);

  if (!acc) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  const toggleBot = async () => {
    if (!auth.accountId) return;
    setToggling(true);
    try {
      if (acc.bot_enabled) {
        await disableAccountBot(auth.accountId);
        showToast('success', 'Bot 已停用', '');
      } else {
        await enableAccountBot(auth.accountId);
        showToast('success', 'Bot 已启用', '');
      }
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
    } finally {
      setToggling(false);
    }
  };

  const liveData = [
    { name: '已连接', value: acc.room_connected ? 1 : 0 },
    { name: '未连接', value: acc.room_connected ? 0 : 1 },
  ];
  const pluginData = [
    { name: '已启用', value: acc.enabled_plugin_count },
    { name: '未启用', value: Math.max(0, acc.plugin_count - acc.enabled_plugin_count) },
  ];

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* 头部 */}
      <div className="flex items-center gap-2 flex-wrap">
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
        <div className="ml-auto">
          <Button size="sm" variant="secondary" icon={<KeyRound className="w-4 h-4" />}
            onClick={() => setRedeemOpen(true)}>
            兑换授权码
          </Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card">
          <div className="card-body">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                <BotIcon className="w-4 h-4" /> Bot 状态
              </div>
              <StatusBadge status={acc.bot_enabled && acc.bot_available ? 'enabled' : 'disabled'}
                label={acc.bot_enabled ? '已启用' : '已停用'} />
            </div>
            <p className="mt-2 font-semibold text-lg truncate">{acc.bot_name || '未配置 Bot'}</p>
            <div className="mt-3">
              <Button size="sm" variant={acc.bot_enabled ? 'secondary' : 'success'}
                loading={toggling} disabled={toggling || !acc.bot_available} onClick={toggleBot}>
                {acc.bot_enabled ? '停用 Bot' : '启用 Bot'}
              </Button>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                <Radio className="w-4 h-4" /> 直播间
              </div>
              <StatusBadge status={acc.room_connected ? 'online' : 'offline'}
                label={acc.room_connected ? '已连接' : '未连接'} />
            </div>
            <p className="mt-2 font-semibold text-lg truncate">
              {acc.room_name || (acc.room_id ? `房间 ${acc.room_id}` : '未绑定')}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              {acc.room_id ? '已绑定 1 个直播间' : '尚未绑定直播间'}
            </p>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Puzzle className="w-4 h-4" /> 插件
            </div>
            <p className="mt-2 font-semibold text-lg">{acc.enabled_plugin_count} 启用</p>
            <p className="text-xs text-gray-400 mt-1">共 {acc.plugin_count} 个插件</p>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Clock className="w-4 h-4" /> 定时消息
            </div>
            <p className="mt-2 font-semibold text-lg">{acc.timer_message_count} 条</p>
            <p className="text-xs text-gray-400 mt-1">按轮转间隔发送</p>
          </div>
        </div>
      </div>

      {/* 饼图 */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <div className="card-header"><h3 className="font-semibold">直播间状态</h3></div>
          <div className="card-body h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={liveData} dataKey="value" nameKey="name"
                  innerRadius="55%" outerRadius="80%" paddingAngle={2}>
                  {liveData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-header"><h3 className="font-semibold">插件状态</h3></div>
          <div className="card-body h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pluginData} dataKey="value" nameKey="name"
                  innerRadius="55%" outerRadius="80%" paddingAngle={2}>
                  {pluginData.map((_, i) => <Cell key={i} fill={PIE_COLORS_BLUE[i]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {acc.resume_error && (
        <div className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {acc.resume_error}
        </div>
      )}

      {/* 兑换授权码 */}
      <RenewDialog
        open={redeemOpen}
        accountId={auth.accountId ?? 0}
        accountName={acc.name}
        mode="code"
        loading={redeeming}
        onRenew={async () => {}}
        onRedeem={async (id, code) => {
          setRedeeming(true);
          try {
            await redeemAccountCode(id, code);
            showToast('success', '兑换成功', '');
            setRedeemOpen(false);
            reload();
          } catch (e: any) {
            showToast('error', '兑换失败', e.message);
          } finally { setRedeeming(false); }
        }}
        onCancel={() => setRedeemOpen(false)}
      />
    </div>
  );
}

// ================================================================== //
// 其余页面包装(标题 + 复用面板详情页的 Tab 组件)
// ================================================================== //

function PageShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <h1 className="text-2xl font-bold">{title}</h1>
      {children}
    </div>
  );
}

export function AccountLibraryPage() {
  const auth = useAuth();
  const { acc } = useAccountSummary();
  const [library, setLibrary] = useState<LibraryPlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [detailTarget, setDetailTarget] = useState<{ name: string; tab?: string } | null>(null);

  const load = useCallback(async () => {
    if (!auth.accountId) return;
    try {
      setLibrary(await fetchAccountLibrary(auth.accountId));
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [auth.accountId]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">插件库</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            安装 = 拷贝源码副本到本账户独立运行 · {library.length} 个插件
          </p>
        </div>
        <Button variant="secondary" icon={<RefreshCw className="w-4 h-4" />}
          onClick={() => { setLoading(true); load(); }}>
          刷新
        </Button>
      </div>

      {library.length === 0 ? (
        <div className="card"><div className="card-body text-center py-12 text-gray-400">插件库为空</div></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {library.map((p) => (
            <div key={p.name}
              className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-all duration-200 flex flex-col">
              {/* 卡片主体(v1.0.1 样式) */}
              <div className="p-5 flex-1">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-white">
                      <MarqueeText text={p.display_name || p.name} />
                    </h3>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs font-mono text-gray-400 dark:text-gray-500">v{p.version}</span>
                      <span className="text-gray-300 dark:text-gray-600">·</span>
                      <span className="text-xs text-gray-400 dark:text-gray-500">{p.author}</span>
                    </div>
                  </div>
                  <span className={
                    'inline-flex items-center gap-1.5 rounded-full font-medium text-[10px] px-1.5 py-0 ' +
                    (p.installed
                      ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400'
                      : 'bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-surface-400')
                  }>
                    <span className={`inline-block rounded-full w-1.5 h-1.5 ${p.installed ? 'bg-emerald-500' : 'bg-surface-400'}`} />
                    {p.installed ? '已安装' : '未安装'}
                  </span>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-1">
                  {p.short_desc || p.desc || '无描述'}
                </p>
                <p className="text-[11px] font-mono text-gray-400 dark:text-gray-500 truncate">
                  {p.plugin_id}
                </p>
              </div>
              {/* 底部操作区 */}
              <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100 dark:border-gray-700/50 bg-gray-50/50 dark:bg-gray-800/50 rounded-b-xl">
                <Button size="sm" variant="ghost"
                  onClick={() => setDetailTarget({ name: p.name, tab: 'readme' })}>
                  详情
                </Button>
                {!p.installed ? (
                  <Button size="sm" variant="success" icon={<Plus className="w-4 h-4" />}
                    loading={processing === p.name} disabled={processing === p.name}
                    onClick={async () => {
                      if (!auth.accountId) return;
                      setProcessing(p.name);
                      try {
                        await installAccountPlugin(auth.accountId, p.name);
                        showToast('success', `已安装 ${p.display_name || p.name}(默认停用)`);
                        load();
                      } catch (e: any) {
                        showToast('error', '安装失败', e.message);
                      } finally { setProcessing(''); }
                    }}>
                    安装
                  </Button>
                ) : (
                  <span className="text-xs text-gray-400">已安装 —— 请在「插件」页面启用与配置</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 插件详情抽屉(库模式:文档/更新日志/使用账户) */}
      {detailTarget && (() => {
        const meta = library.find((p) => p.name === detailTarget.name);
        return (
          <PluginDrawer
            pluginName={detailTarget.name}
            open
            onClose={() => setDetailTarget(null)}
            onUpdate={load}
            initialTab={detailTarget.tab}
            showAccountsTab={false}
            accounts={acc ? [{ id: acc.id, name: acc.name }] : []}
            usedByAccounts={meta?.used_by_accounts ?? []}
            libraryMeta={meta ? {
              name: meta.name,
              display_name: meta.display_name,
              plugin_id: meta.plugin_id,
              version: meta.version,
              has_readme: meta.has_readme,
              has_changelog: meta.has_changelog,
            } : undefined}
          />
        );
      })()}
    </div>
  );
}

export function AccountLivePage() {
  const { acc } = useAccountSummary(8000);
  if (!acc) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }
  return <PageShell title="直播间"><LiveTab acc={acc} /></PageShell>;
}

export function AccountBotPage() {
  const { acc, reload } = useAccountSummary();
  if (!acc) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }
  return <PageShell title="Bot"><BotTab acc={acc} onAccountChanged={reload} /></PageShell>;
}

export function AccountTimerPage() {
  const { acc } = useAccountSummary(30000);
  if (!acc) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }
  return <PageShell title="定时消息"><TimerTab acc={acc} /></PageShell>;
}

export function AccountPluginsPage() {
  const { acc } = useAccountSummary();
  if (!acc) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }
  return <PageShell title="插件"><PluginsTab acc={acc} /></PageShell>;
}
