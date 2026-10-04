/** 账户界面页面(v1.0.1 风格左侧导航,独立于面板)。 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
} from 'recharts';
import { Bot as BotIcon, Radio, Puzzle, Clock, Loader2, KeyRound, LayoutDashboard } from 'lucide-react';
import {
  fetchAccountSummary, enableAccountBot, disableAccountBot, redeemAccountCode,
} from '../api/client';
import type { AccountSummary } from '../api/types';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { ExpiryBadge } from '../components/ExpiryBadge';
import { RenewDialog } from '../components/AccountDialogs';
import { useAuth } from '../hooks/useAuth';
import { AccountPasswordForm } from '../components/AccountPasswordForm';
import { showToast } from '../hooks/useToast';
import {
  OverviewTab, LiveTab, BotTab, TimerTab, PluginsTab, LibraryTab,
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
            <p className="mt-2 font-semibold text-lg">{acc.normal_timer_message_count} 条</p>
            <p className="text-xs text-gray-400 mt-1">
              普通消息
              {acc.plugin_timer_message_count > 0
                && ` · 另有 ${acc.plugin_timer_message_count} 条插件消息`}
            </p>
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
  const { acc } = useAccountSummary();
  if (!acc) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }
  return <LibraryTab acc={acc} />;
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
export function AccountPasswordPage() {
  const auth = useAuth();
  return (
    <PageShell title="修改密码">
      <div className="card max-w-md">
        <div className="card-body space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            修改后需使用新密码重新登录
          </p>
          {/* 表单与「强制修改默认密码」界面共用，校验规则只此一份 */}
          <AccountPasswordForm
            accountId={auth.accountId ?? 0}
            onDone={() => setTimeout(() => auth.logout(), 1200)}
          />
        </div>
      </div>
    </PageShell>
  );
}


// ================================================================== //
// 操作指引
// ================================================================== //

/** 指引条目 —— 页面与文案分开列，改文案不用动结构 */
const GUIDE_SECTIONS: { icon: React.ReactNode; title: string; body: string }[] = [
  { icon: <LayoutDashboard className="w-4 h-4" />, title: '概览',
    body: '一眼看到自己的 Bot、直播间、插件与订阅状态。到期时间也在这里，快到期时卡片上会有提示。' },
  { icon: <Radio className="w-4 h-4" />, title: '直播间',
    body: '绑定或更换直播间。绑定后还要「连接」才会开始接收弹幕与礼物事件 —— 只绑定不连接是不会响应的。' },
  { icon: <BotIcon className="w-4 h-4" />, title: 'Bot',
    body: '查看 Bot 的 Cookie 模式。私有模式下可自助更新 Cookie（面板会指引你用书签脚本一键取回），不用再找管理员。' },
  { icon: <Clock className="w-4 h-4" />, title: '定时消息',
    body: '设置按间隔轮播的消息，用来维持直播间热度。可以调整间隔、上下移动顺序、复制或删除。' },
  { icon: <Puzzle className="w-4 h-4" />, title: '插件',
    body: '启用或停用插件、改配置、设权限。每个插件的功能不同，配置项由插件自己声明。' },
  { icon: <Puzzle className="w-4 h-4" />, title: '插件库',
    body: '面板统一维护的插件来源。库里有新版本时，插件页会提示更新；也可以一键更新全部。' },
  { icon: <KeyRound className="w-4 h-4" />, title: '修改密码',
    body: '更换本账户的登录密码。仍在使用初始密码时，面板会要求你先改密才能使用。' },
];

/**
 * 账户端操作指引。
 *
 * 首次登录时由 App 导到这里（见 useAuth 的 showGuide）；看过一次后标记落盘，
 * 之后只作为侧栏里的常驻入口存在，不再自动跳转。
 */
export function AccountGuidePage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const acked = useRef(false);

  const ack = useCallback(() => {
    if (acked.current || !auth.token) return;
    acked.current = true;
    // 上报失败不重试：指引看过就是看过了，万一下次登录再跳一次也无伤大雅，
    // 比在这里做重试队列划算得多
    fetch('/api/auth/ack-guide', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + auth.token },
    }).catch(() => { /* ignore */ });
    auth.clearShowGuide();
  }, [auth]);

  // 离开本页即视为看过 —— 用户完全可能直接点侧栏走人，
  // 不能只认「开始使用」那一个按钮，否则每次登录都要被跳一次
  useEffect(() => ack, [ack]);

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">操作指引</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          这里是你的直播间控制台。下面按侧栏顺序过一遍，看完就可以开始了。
        </p>
      </div>

      <div className="card">
        <div className="card-body space-y-4">
          {GUIDE_SECTIONS.map((s, i) => (
            <div key={s.title} className="flex gap-3">
              <span className="shrink-0 mt-0.5 flex items-center justify-center w-7 h-7 rounded-lg
                               bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400">
                {s.icon}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {i + 1}. {s.title}
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2">
        {/* 本页随时能从侧栏再进来，所以不强制「读完」 */}
        <Button variant="secondary" onClick={() => navigate('/account/home')}>稍后再看</Button>
        <Button variant="primary" onClick={() => { ack(); navigate('/account/home'); }}>开始使用</Button>
      </div>
    </div>
  );
}
