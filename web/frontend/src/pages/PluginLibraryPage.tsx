import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, RefreshCw, Trash2, BookOpen, Loader2, Users, AlertTriangle, History } from 'lucide-react';
import {
  fetchLibraryPlugins, fetchFailedPlugins, refreshPlugins, uninstallPlugin,
  retryFailedPlugin, fetchAccounts,
} from '../api/client';
import type { LibraryPlugin, FailedPluginInfo, AccountSummary } from '../api/types';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { UpdateDialog } from '../components/UpdateDialog';
import { PluginDrawer } from '../components/PluginDrawer';
import { MarqueeText } from '../components/MarqueeText';
import { showToast } from '../hooks/useToast';

/** 图标按钮(带悬浮提示,v1.0.1 样式) */
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

/** 插件库页 —— 面板级安装/更新/卸载,各账户从库中启用。 */
export function PluginLibraryPage() {
  const [plugins, setPlugins] = useState<LibraryPlugin[]>([]);
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [failed, setFailed] = useState<FailedPluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updateTarget, setUpdateTarget] = useState<{ name: string; oldVersion: string; newVersion: string } | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<LibraryPlugin | null>(null);
  const [drawerTarget, setDrawerTarget] = useState<{ name: string; tab?: string } | null>(null);
  const [errorLog, setErrorLog] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [p, f, a] = await Promise.all([
        fetchLibraryPlugins(), fetchFailedPlugins(), fetchAccounts(),
      ]);
      setPlugins(p);
      setFailed(f);
      setAccounts(a);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDrawer = (name: string, tab?: string) => {
    setDrawerTarget({ name, tab });
  };

  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/plugin/install', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 409) {
        setUpdateTarget({
          name: body.name,
          oldVersion: body.old_version,
          newVersion: body.new_version,
        });
        return;
      }
      if (!res.ok) throw new Error(body.detail || res.statusText);
      showToast('success', '插件已加入插件库', '');
      setPendingFile(null);
      load();
    } catch (e: any) {
      showToast('error', '安装失败', e.message);
      setPendingFile(null);
    }
  };

  const handleUpdate = async () => {
    if (!updateTarget || !pendingFile) return;
    const fd = new FormData();
    fd.append('file', pendingFile);
    setUpdating(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/plugin/install/update', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || res.statusText);
      showToast('success', `${updateTarget.name} 更新完成`, '');
      setUpdateTarget(null);
      setPendingFile(null);
      load();
    } catch (e: any) {
      showToast('error', '更新失败', e.message);
    } finally {
      setUpdating(false);
    }
  };

  const handleUninstall = async () => {
    if (!uninstallTarget) return;
    setProcessing(uninstallTarget.name);
    try {
      await uninstallPlugin(uninstallTarget.name, true, false);
      showToast('success', `${uninstallTarget.name} 已卸载`, '');
      setUninstallTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '卸载失败', e.message);
    } finally { setProcessing(''); }
  };

  if (loading) {
    return <div className="flex justify-center py-24"><Loader2 className="w-8 h-8 animate-spin text-primary-500" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">插件库</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            面板级统一安装管理,各账户按需启用 · {plugins.length} 个插件
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" icon={<RefreshCw className="w-4 h-4" />}
            onClick={async () => { await refreshPlugins(); load(); showToast('success', '已刷新', ''); }}>
            刷新
          </Button>
          <Button variant="primary" icon={<Upload className="w-4 h-4" />}
            onClick={() => fileRef.current?.click()}>
            安装插件
          </Button>
        </div>
      </div>

      {/* 失败插件 */}
      {failed.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="font-semibold flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" /> 加载失败的插件
            </h3>
          </div>
          <div className="card-body space-y-2">
            {failed.map((f) => (
              <div key={f.dir_name} className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{f.dir_name}</p>
                  <p className="text-xs text-red-500 truncate">{f.error}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button size="sm" variant="ghost"
                    onClick={async () => {
                      try {
                        const tb = await fetch(`/api/plugin/failed/${f.dir_name}`, { headers: { Authorization: 'Bearer ' + localStorage.getItem('auth_token') } })
                          .then((r) => r.json().catch(() => ({})));
                        setErrorLog(tb.traceback || f.error || '');
                      } catch { /* ignore */ }
                    }}>日志</Button>
                  <Button size="sm" variant="secondary"
                    onClick={async () => { await retryFailedPlugin(f.dir_name); load(); }}>重试</Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 插件卡片 */}
      {plugins.length === 0 ? (
        <div className="card"><div className="card-body text-center py-14 text-gray-400">
          插件库为空 —— 点击右上角「安装插件」上传 zip 包
        </div></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {plugins.map((p) => (
            <div key={p.name}
              className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-all duration-200 flex flex-col">
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
                  <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 shrink-0">
                    <Users className="w-3.5 h-3.5" />
                    {p.used_by_accounts.length > 0 ? `${p.used_by_accounts.length} 个账户启用` : '未启用'}
                  </span>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-1">
                  {p.short_desc || p.desc || '无描述'}
                </p>
                <p className="text-[11px] font-mono text-gray-400 dark:text-gray-500 truncate">
                  {p.plugin_id}
                </p>
              </div>
              <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-gray-700/50 bg-gray-50/50 dark:bg-gray-800/50 rounded-b-xl">
                <div className="flex flex-wrap gap-1">
                  {p.used_by_accounts.map((aid) => (
                    <span key={aid} className="badge badge-blue">账户 {aid}</span>
                  ))}
                </div>
                <div className="flex items-center gap-0.5 lg:gap-1 flex-nowrap">
                  {p.has_readme && (
                    <IconBtn icon={<BookOpen className="w-3.5 h-3.5" />} label="文档"
                      onClick={() => openDrawer(p.name, 'readme')} />
                  )}
                  {p.has_changelog && (
                    <IconBtn icon={<History className="w-3.5 h-3.5" />} label="更新日志"
                      onClick={() => openDrawer(p.name, 'changelog')} />
                  )}
                  <IconBtn icon={<Users className="w-3.5 h-3.5" />} label="使用账户"
                    onClick={() => openDrawer(p.name, 'accounts')} />
                  <IconBtn icon={<Trash2 className="w-3.5 h-3.5" />} label="卸载"
                    loading={processing === p.name} disabled={processing === p.name}
                    onClick={() => setUninstallTarget(p)} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 版本更新确认 */}
      {updateTarget && (
        <UpdateDialog
          open
          name={updateTarget.name}
          oldVersion={updateTarget.oldVersion}
          newVersion={updateTarget.newVersion}
          loading={updating}
          onConfirm={handleUpdate}
          onCancel={() => { setUpdateTarget(null); setPendingFile(null); }}
        />
      )}

      <ConfirmDialog
        open={uninstallTarget !== null}
        title="卸载插件"
        message={`确定从插件库卸载「${uninstallTarget?.name ?? ''}」吗？所有账户中已启用的实例将被禁用。`}
        danger
        loading={processing === uninstallTarget?.name}
        onConfirm={handleUninstall}
        onCancel={() => setUninstallTarget(null)}
      />

      {/* 插件详情抽屉(面板库模式:仅 文档/更新日志/使用账户) */}
      {drawerTarget && (() => {
        const meta = plugins.find((p) => p.name === drawerTarget.name);
        return (
          <PluginDrawer
            pluginName={drawerTarget.name}
            open
            onClose={() => setDrawerTarget(null)}
            onUpdate={load}
            accounts={accounts.map((a) => ({ id: a.id, name: a.name }))}
            usedByAccounts={meta?.used_by_accounts ?? []}
            initialTab={drawerTarget.tab}
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

      {/* 隐藏的文件输入,install 时触发 */}
      <input ref={fileRef} type="file" accept=".zip" className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            setPendingFile(f);
            upload(f);
          }
          e.target.value = '';
        }} />

      {errorLog && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setErrorLog('')} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-5">
            <h3 className="font-semibold mb-3">错误日志</h3>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs bg-gray-100 dark:bg-gray-900 p-3 rounded-lg">{errorLog}</pre>
            <div className="flex justify-end mt-4">
              <Button variant="ghost" size="sm" onClick={() => setErrorLog('')}>关闭</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
