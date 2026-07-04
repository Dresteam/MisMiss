import { useEffect, useState } from 'react';
import {
  Bot,
  Radio,
  Puzzle,
  Zap,
  TrendingUp,
  AlertCircle,
  MessageSquare,
  Activity,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { fetchDashboard, enableBot, disableBot } from '../api/client';
import type { DashboardData } from '../api/types';
import { showToast } from '../hooks/useToast';
import { StatusBadge } from '../components/StatusBadge';

const COLORS = {
  online: '#10b981',
  offline: '#94a3b8',
  enabled: '#10b981',
  disabled: '#94a3b8',
};

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const load = async () => {
    try {
      const d = await fetchDashboard();
      setData(d);
    } catch (e: any) {
      showToast('error', '加载失败', e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000); // Auto-refresh every 10s
    return () => clearInterval(timer);
  }, []);

  const handleToggleBot = async () => {
    if (!data?.bot) return;
    setToggling(true);
    try {
      if (data.bot.enabled) {
        await disableBot();
        showToast('success', 'Bot 已停用');
      } else {
        await enableBot();
        showToast('success', 'Bot 已启用');
      }
      await load();
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
    } finally {
      setToggling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-surface-500">加载仪表盘...</span>
        </div>
      </div>
    );
  }

  const bot = data?.bot;

  // Pie chart data
  const livePie = [
    { name: '在线', value: data?.livestream_online || 0, color: COLORS.online },
    { name: '离线', value: data?.livestream_offline || 0, color: COLORS.offline },
  ].filter((d) => d.value > 0);

  const pluginPie = [
    { name: '已启用', value: data?.plugin_enabled || 0, color: COLORS.enabled },
    { name: '已禁用', value: data?.plugin_disabled || 0, color: COLORS.disabled },
  ].filter((d) => d.value > 0);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-white">
            仪表盘
          </h1>
          <p className="text-sm text-surface-500 mt-1">
            MisMiss 服务器运行状态概览
          </p>
        </div>
        <button
          onClick={handleToggleBot}
          disabled={toggling || !bot}
          className={`btn-lg rounded-xl font-semibold ${
            bot?.enabled ? 'btn-danger' : 'btn-success'
          }`}
        >
          <Activity className="w-5 h-5" />
          {bot?.enabled ? '停用 Bot' : '启用 Bot'}
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-surface-500">Bot 状态</p>
              <p className="text-2xl font-bold mt-1 text-surface-900 dark:text-white">
                {bot?.name || '(未配置)'}
              </p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center">
              <Bot className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <StatusBadge status={bot?.enabled ? 'enabled' : 'disabled'} />
            {bot?.available && <StatusBadge status="online" label="可用" />}
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-surface-500">直播间</p>
              <p className="text-2xl font-bold mt-1 text-surface-900 dark:text-white">
                {data?.livestream_count || 0}
              </p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
              <Radio className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <StatusBadge status="online" label={`${data?.livestream_online || 0} 在线`} />
            <span className="text-xs text-surface-400">
              {data?.livestream_offline || 0} 离线
            </span>
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-surface-500">插件</p>
              <p className="text-2xl font-bold mt-1 text-surface-900 dark:text-white">
                {data?.plugin_count || 0}
              </p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-purple-100 dark:bg-purple-900/40 flex items-center justify-center">
              <Puzzle className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <StatusBadge status="enabled" label={`${data?.plugin_enabled || 0} 启用`} />
            <span className="text-xs text-surface-400">
              {data?.plugin_disabled || 0} 禁用
            </span>
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-surface-500">定时消息</p>
              <p className="text-2xl font-bold mt-1 text-surface-900 dark:text-white">
                {data?.timer_message_count || 0}
              </p>
            </div>
            <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center">
              <MessageSquare className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-xs text-surface-400">活跃轮转消息</span>
          </div>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Livestream pie */}
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <Radio className="w-4 h-4 text-emerald-500" />
            直播间状态
          </div>
          <div className="card-body">
            {livePie.length > 0 ? (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width={160} height={160}>
                  <PieChart>
                    <Pie
                      data={livePie}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={70}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {livePie.map((entry, i) => (
                        <Cell key={i} fill={entry.color} stroke="none" />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2">
                  {livePie.map((item) => (
                    <div key={item.name} className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-sm text-surface-600 dark:text-surface-400">
                        {item.name}
                      </span>
                      <span className="text-sm font-semibold text-surface-900 dark:text-white">
                        {item.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-surface-400 py-8 text-center">暂无直播间</p>
            )}
          </div>
        </div>

        {/* Plugin pie */}
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <Puzzle className="w-4 h-4 text-purple-500" />
            插件状态
          </div>
          <div className="card-body">
            {pluginPie.length > 0 ? (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width={160} height={160}>
                  <PieChart>
                    <Pie
                      data={pluginPie}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={70}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {pluginPie.map((entry, i) => (
                        <Cell key={i} fill={entry.color} stroke="none" />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2">
                  {pluginPie.map((item) => (
                    <div key={item.name} className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-sm text-surface-600 dark:text-surface-400">
                        {item.name}
                      </span>
                      <span className="text-sm font-semibold text-surface-900 dark:text-white">
                        {item.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-surface-400 py-8 text-center">暂无插件</p>
            )}
          </div>
        </div>
      </div>

      {/* Bot permission tags */}
      {bot && bot.permissions.length > 0 && (
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            Bot 权限汇总
          </div>
          <div className="card-body">
            <div className="flex flex-wrap gap-2">
              {bot.permissions.map((p) => (
                <span key={p} className="badge-blue">
                  {p}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Failed plugins warning */}
      {data && data.failed_plugin_count > 0 && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
          <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
          <p className="text-sm text-amber-800 dark:text-amber-200">
            有 {data.failed_plugin_count} 个插件加载失败，请前往
            <a href="/plugin" className="underline font-medium mx-1">
              插件中心
            </a>
            查看详情
          </p>
        </div>
      )}
    </div>
  );
}
