import { useEffect, useState } from 'react';
import { Server, RefreshCw, Power, AlertTriangle, Activity } from 'lucide-react';
import { fetchServerStatus, reloadServer, shutdownServer } from '../api/client';
import type { ServerStatus } from '../api/types';
import { showToast } from '../hooks/useToast';
import { StatusBadge } from '../components/StatusBadge';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';

export function ServerPage() {
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  // Confirm dialogs
  const [showReload, setShowReload] = useState(false);
  const [showShutdown, setShowShutdown] = useState(false);

  const load = async () => {
    try {
      const s = await fetchServerStatus();
      setStatus(s);
    } catch (e: any) {
      showToast('error', '获取状态失败', e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const handleReload = async () => {
    setActionLoading(true);
    setShowReload(false);
    try {
      const res = await reloadServer();
      showToast('success', '服务器已重载', res.message);
      await load();
    } catch (e: any) {
      showToast('error', '重载失败', e.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleShutdown = async () => {
    setActionLoading(true);
    setShowShutdown(false);
    try {
      const res = await shutdownServer();
      showToast('success', '服务器已关闭', res.message);
      await load();
    } catch (e: any) {
      showToast('error', '关闭失败', e.message);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-2xl">
      <h1 className="text-2xl font-bold text-surface-900 dark:text-white">服务器设置</h1>

      {/* Status Card */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Server className="w-4 h-4 text-primary-500" />
          运行状态
        </div>
        <div className="card-body space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-surface-50 dark:bg-surface-900">
              <p className="text-xs text-surface-500">服务器</p>
              <div className="flex items-center gap-2 mt-1">
                <div className={`w-2.5 h-2.5 rounded-full ${status?.running ? 'bg-emerald-500 animate-pulse-dot' : 'bg-red-500'}`} />
                <span className="font-semibold text-surface-900 dark:text-white">
                  {status?.running ? '运行中' : '已停止'}
                </span>
              </div>
            </div>
            <div className="p-4 rounded-lg bg-surface-50 dark:bg-surface-900">
              <p className="text-xs text-surface-500">Bot</p>
              <p className="font-semibold text-surface-900 dark:text-white mt-1">
                {status?.bot_name || '(未配置)'}
              </p>
              {status && (
                <StatusBadge
                  status={status.bot_available ? 'online' : 'offline'}
                  label={status.bot_available ? '可用' : '不可用'}
                  size="sm"
                />
              )}
            </div>
            <div className="p-4 rounded-lg bg-surface-50 dark:bg-surface-900">
              <p className="text-xs text-surface-500">直播间</p>
              <p className="text-2xl font-bold text-surface-900 dark:text-white mt-1">
                {status?.livestream_count || 0}
              </p>
            </div>
            <div className="p-4 rounded-lg bg-surface-50 dark:bg-surface-900">
              <p className="text-xs text-surface-500">插件</p>
              <p className="text-2xl font-bold text-surface-900 dark:text-white mt-1">
                {status?.enabled_plugin_count || 0}
                <span className="text-sm font-normal text-surface-400">
                  /{status?.plugin_count || 0}
                </span>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Actions Card */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Activity className="w-4 h-4 text-amber-500" />
          服务器控制
        </div>
        <div className="card-body space-y-4">
          {/* Reload */}
          <div className="flex items-center justify-between gap-2 p-4 rounded-lg bg-surface-50 dark:bg-surface-900">
            <div className="min-w-0">
              <p className="font-medium text-surface-900 dark:text-white">重载服务器</p>
              <p className="text-xs text-surface-500 mt-0.5 line-clamp-2">
                关闭后重新启动，刷新所有插件和连接
              </p>
            </div>
            <Button variant="primary" icon={<RefreshCw />}
              onClick={() => setShowReload(true)}
              loading={actionLoading} className="shrink-0 whitespace-nowrap">重载</Button>
          </div>

          {/* Shutdown */}
          <div className="flex items-center justify-between gap-2 p-4 rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800">
            <div className="min-w-0">
              <p className="font-medium text-red-800 dark:text-red-300">关闭服务器</p>
              <p className="text-xs text-red-600 dark:text-red-400 mt-0.5 line-clamp-2">
                停用所有 Bot、断开所有直播间、卸载所有插件
              </p>
            </div>
            <Button variant="destructive" icon={<Power />}
              onClick={() => setShowShutdown(true)}
              loading={actionLoading} className="shrink-0 whitespace-nowrap">关闭</Button>
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
        <AlertTriangle className="w-5 h-5 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-blue-800 dark:text-blue-200">提示</p>
          <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
            关闭服务器后，Web API 也将不可用（因为 API 依赖 MissevanServer 实例）。
            如需重新启动，请重启整个 Python 进程。
          </p>
        </div>
      </div>

      <ConfirmDialog
        open={showReload}
        title="重载服务器"
        message="重载将关闭后重新启动，刷新所有插件和直播间连接。确定要继续吗？"
        variant="warning"
        confirmLabel="重载"
        onConfirm={handleReload}
        onCancel={() => setShowReload(false)}
        loading={actionLoading}
      />

      <ConfirmDialog
        open={showShutdown}
        title="关闭服务器"
        message="关闭后所有 Bot、直播间连接和插件都将停止。API 也将不可用。确定要关闭吗？"
        variant="danger"
        confirmLabel="确认关闭"
        onConfirm={handleShutdown}
        onCancel={() => setShowShutdown(false)}
        loading={actionLoading}
      />
    </div>
  );
}
