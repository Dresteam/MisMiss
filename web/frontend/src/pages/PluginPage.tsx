import { useEffect, useState, useCallback, useRef } from 'react';
import { Puzzle, RefreshCw, AlertTriangle, Eye, FolderSync, Loader2, Upload, BookOpen, Trash2, X } from 'lucide-react';
import { fetchPluginList, enablePlugin, disablePlugin, reloadPlugin,
  fetchFailedPlugins, retryFailedPlugin, refreshPlugins, fetchPluginReadme, uninstallPlugin } from '../api/client';
import type { PluginSummary, FailedPluginInfo } from '../api/types';
import { showToast } from '../hooks/useToast';
import { StatusBadge } from '../components/StatusBadge';
import { Button } from '../components/Button';
import { PluginDrawer } from '../components/PluginDrawer';
import { ReadmeModal } from '../components/ReadmeModal';
import { UninstallDialog } from '../components/UninstallDialog';
import { UpdateDialog } from '../components/UpdateDialog';

export function PluginPage() {
  const [plugins, setPlugins] = useState<PluginSummary[]>([]);
  const [failedPlugins, setFailedPlugins] = useState<FailedPluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState<'all'|'enabled'|'disabled'|'failed'>('all');
  const [processingMap, setProcessingMap] = useState<Record<string, string | null>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [readmeModal, setReadmeModal] = useState<{ title: string; content: string } | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<string | null>(null);
  const [uninstalling, setUninstalling] = useState(false);
  const [errorModal, setErrorModal] = useState<{ name: string; traceback: string } | null>(null);
  const [updateInfo, setUpdateInfo] = useState<{ name: string; oldVersion: string; newVersion: string; enabled: boolean } | null>(null);
  const [updating, setUpdating] = useState(false);
  const updateFileRef = useRef<File | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState('');

  const load = useCallback(async () => {
    try {
      const [pList, fList] = await Promise.all([fetchPluginList(), fetchFailedPlugins()]);
      setPlugins(pList.sort((a, b) => a.name.localeCompare(b.name))); setFailedPlugins(fList);
    } catch (e: any) { showToast('error', '加载失败', e.message);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const setProcessing = (name: string, action: string | null) => {
    setProcessingMap((prev) => ({ ...prev, [name]: action }));
  };

  const handleToggle = async (plugin: PluginSummary) => {
    if (processingMap[plugin.name]) return;
    setProcessing(plugin.name, 'toggle');
    try {
      if (plugin.enabled) { await disablePlugin(plugin.name); showToast('success', plugin.name + ' 已禁用'); }
      else { await enablePlugin(plugin.name); showToast('success', plugin.name + ' 已启用'); }
      await load();
    } catch (e: any) { showToast('error', '操作失败', e.message);
    } finally { setProcessing(plugin.name, null); }
  };

  const handleReload = async (pluginName: string) => {
    if (processingMap[pluginName]) return;
    setProcessing(pluginName, 'reload');
    try {
      const res = await reloadPlugin(pluginName);
      showToast('success', res.name + ' 已重载'); await load();
    } catch (e: any) { showToast('error', '重载失败', e.message);
    } finally { setProcessing(pluginName, null); }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    try { const res = await refreshPlugins(); showToast('success', res.message); await load(); }
    catch (e: any) { showToast('error', '刷新失败', e.message); }
    finally { setRefreshing(false); }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/plugin/install', {
        method: 'POST', body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      const data = await res.json();

      if (data.action === 'update') {
        // 需要确认更新
        updateFileRef.current = file;
        setUpdateInfo({ name: data.name, oldVersion: data.old_version, newVersion: data.new_version, enabled: data.enabled });
        setUploading(false);
        e.target.value = '';
        return;
      }

      showToast('success', `${data.plugin.name} 安装成功`);
      await load();
      if (data.readme) {
        setReadmeModal({ title: data.plugin.display_name || data.plugin.name, content: data.readme });
      }
    } catch (e: any) {
      showToast('error', '安装失败', e.message);
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleConfirmUpdate = async () => {
    if (!updateFileRef.current || !updateInfo) return;
    setUpdating(true);
    try {
      const form = new FormData();
      form.append('file', updateFileRef.current);
      const token = localStorage.getItem('auth_token');
      const wasEnabled = updateInfo.enabled ? 'true' : 'false';
      const res = await fetch(`/api/plugin/install/update?was_enabled=${wasEnabled}`, {
        method: 'POST', body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      const data = await res.json();
      showToast('success', `${data.plugin.name} v${data.plugin.version} 更新完成`);
      setUpdateInfo(null);
      updateFileRef.current = null;
      await load();
      if (data.changelog) {
        setReadmeModal({ title: `${data.plugin.display_name || data.plugin.name} v${data.plugin.version} 更新公告`, content: data.changelog });
      }
    } catch (e: any) {
      showToast('error', '更新失败', e.message);
    } finally {
      setUpdating(false);
    }
  };

  const handleUninstall = async (deleteConfig: boolean, deleteData: boolean) => {
    if (!uninstallTarget) return;
    setUninstalling(true);
    try {
      await uninstallPlugin(uninstallTarget, deleteConfig, deleteData);
      showToast('success', `${uninstallTarget} 已卸载`);
      setUninstallTarget(null);
      await load();
    } catch (e: any) {
      showToast('error', '卸载失败', e.message);
    } finally {
      setUninstalling(false);
    }
  };

  const handleViewReadme = async (plugin: PluginSummary) => {
    try {
      const data = await fetchPluginReadme(plugin.name);
      setReadmeModal({ title: plugin.display_name || plugin.name, content: data.content || '' });
    } catch {
      showToast('error', '加载文档失败');
    }
  };

  const handleRetryFailed = async (dirName: string) => {
    try { await retryFailedPlugin(dirName); showToast('success', '加载成功'); await load(); }
    catch (e: any) { showToast('error', '重试失败', e.message); }
  };

  const openDrawer = (name: string) => { setSelectedPlugin(name); setDrawerOpen(true); };

  const filteredPlugins = activeFilter === 'failed' ? []
    : activeFilter === 'enabled' ? plugins.filter((p) => p.enabled)
    : activeFilter === 'disabled' ? plugins.filter((p) => !p.enabled) : plugins;
  const showFailed = activeFilter === 'failed' || activeFilter === 'all';

  if (loading) {
    return (<div className="flex items-center justify-center h-96">
      <Loader2 className="w-8 h-8 text-primary-500 animate-spin" /></div>);
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">插件中心</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {plugins.length} 个插件 · {plugins.filter((p) => p.enabled).length} 个已启用
            {failedPlugins.length > 0 && (<span className="text-red-500 ml-2">· {failedPlugins.length} 个加载失败</span>)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
            bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300
            border border-gray-200 dark:border-gray-700
            hover:bg-gray-50 dark:hover:bg-gray-750
            disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer
            ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {uploading ? '安装中...' : '安装插件'}
            <input type="file" accept=".zip" onChange={handleUpload} disabled={uploading}
              className="hidden" />
          </label>
          <button onClick={handleRefreshAll} disabled={refreshing}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-750 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderSync className="w-4 h-4" />}
            {refreshing ? '扫描中...' : '扫描新插件'}
          </button>
        </div>
      </div>
      <div className="flex gap-1 p-1 rounded-lg bg-gray-100 dark:bg-gray-800 w-fit">
        {(([['all','全部'],['enabled','已启用'],['disabled','已禁用'],['failed','失败 (' + String(failedPlugins.length) + ')']] as const)).map(([key, label]) => (
          <button key={key} onClick={() => setActiveFilter(key)}
            className={('px-3 py-1.5 text-xs font-medium rounded-md transition-all ' + (activeFilter === key ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'))}>
            {label}
            {key === 'failed' && failedPlugins.length > 0 && (<span className="ml-1.5 px-1 py-0.5 rounded-full bg-red-500 text-white text-[10px] font-bold">{failedPlugins.length}</span>)}
          </button>))}
      </div>
      {filteredPlugins.length === 0 && activeFilter !== 'failed' ? (
        <div className="text-center py-16 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <Puzzle className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-gray-400">{activeFilter === 'all' ? '暂无插件' : '无' + (activeFilter === 'enabled' ? '已启用' : '已禁用') + '的插件'}</p>
        </div>) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredPlugins.map((plugin) => {
            const isBusy = !!processingMap[plugin.name];
            const isToggling = processingMap[plugin.name] === 'toggle';
            const isReloading = processingMap[plugin.name] === 'reload';
            return (
              <div key={plugin.name} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-all duration-200 flex flex-col">
                <div className="p-5 flex-1">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-semibold text-gray-900 dark:text-white truncate">{plugin.display_name || plugin.name}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs font-mono text-gray-400 dark:text-gray-500">v{plugin.version}</span>
                        <span className="text-gray-300 dark:text-gray-600">&middot;</span>
                        <span className="text-xs text-gray-400 dark:text-gray-500">{plugin.author}</span>
                      </div>
                    </div>
                    <StatusBadge status={plugin.enabled ? 'enabled' : 'disabled'} size="sm" />
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-1">{plugin.short_desc || plugin.desc || '无描述'}</p>
                  <p className="text-[11px] font-mono text-gray-400 dark:text-gray-500 truncate">{plugin.plugin_id}</p>
                </div>
                <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-gray-700/50 bg-gray-50/50 dark:bg-gray-800/50 rounded-b-xl">
                  <button onClick={(e) => { e.stopPropagation(); handleToggle(plugin); }} disabled={isBusy}
                    className={'relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed ' + (plugin.enabled ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600')}
                    title={plugin.enabled ? '点击禁用' : '点击启用'}>
                    {isToggling ? (<span className="absolute inset-0 flex items-center justify-center"><Loader2 className="w-4 h-4 text-white animate-spin" /></span>)
                    : (<span className={'inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ' + (plugin.enabled ? 'translate-x-6' : 'translate-x-1')} />)}
                  </button>
                  <div className="flex items-center gap-1.5">
                    <Button variant="ghost" size="sm" icon={<Eye />}
                      onClick={(e) => { e.stopPropagation(); openDrawer(plugin.name); }}>详情</Button>
                    {plugin.has_readme && (
                      <Button variant="ghost" size="sm" icon={<BookOpen />}
                        onClick={(e) => { e.stopPropagation(); handleViewReadme(plugin); }}>文档</Button>
                    )}
                    <Button variant="ghost" size="sm" icon={<RefreshCw />}
                      onClick={(e) => { e.stopPropagation(); handleReload(plugin.name); }}
                      loading={isReloading} disabled={isBusy}>重载</Button>
                    <Button variant="ghost" size="sm" icon={<Trash2 />}
                      onClick={(e) => { e.stopPropagation(); setUninstallTarget(plugin.name); }}
                      disabled={isBusy}>卸载</Button>
                  </div>
                </div>
              </div>);})}
        </div>)}
      {showFailed && failedPlugins.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-red-500" />加载失败的插件</h2>
          <div className="space-y-2">
            {failedPlugins.map((f) => (
              <div key={f.dir_name} className="bg-white dark:bg-gray-800 rounded-xl border border-red-200 dark:border-red-800 overflow-hidden">
                <div className="flex items-start justify-between gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-900 dark:text-white">{f.dir_name}</p>
                    <p className="text-xs text-red-600 dark:text-red-400 mt-1 font-mono break-all">{f.error}</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {f.traceback && (
                      <button onClick={() => setErrorModal({ name: f.dir_name, traceback: f.traceback! })}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg
                                   bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300
                                   hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
                        查看日志
                      </button>
                    )}
                    <button onClick={() => handleRetryFailed(f.dir_name)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg
                                 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300
                                 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
                      <RefreshCw className="w-3 h-3" /> 重试
                    </button>
                  </div>
                </div>
              </div>))}
          </div></div>)}
      <PluginDrawer pluginName={selectedPlugin} open={drawerOpen} onClose={() => { setDrawerOpen(false); load(); }} onUpdate={load} />
      <ReadmeModal open={!!readmeModal} title={readmeModal?.title || ''} content={readmeModal?.content || ''}
        onClose={() => setReadmeModal(null)} />
      <UpdateDialog open={!!updateInfo} name={updateInfo?.name || ''}
        oldVersion={updateInfo?.oldVersion || ''} newVersion={updateInfo?.newVersion || ''}
        onConfirm={handleConfirmUpdate}
        onCancel={() => { setUpdateInfo(null); updateFileRef.current = null; }}
        loading={updating} />
      {errorModal && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
            onClick={() => setErrorModal(null)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col animate-slide-in-up">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
              <h3 className="font-semibold text-gray-900 dark:text-white">{errorModal.name} · 错误日志</h3>
              <button onClick={() => setErrorModal(null)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-900 rounded-b-xl">
              <pre className="text-xs text-red-600 dark:text-red-400 font-mono leading-relaxed whitespace-pre-wrap break-all">
                {errorModal.traceback}
              </pre>
            </div>
          </div>
        </div>
      )}
      <UninstallDialog open={!!uninstallTarget} pluginName={uninstallTarget || ''}
        onConfirm={handleUninstall}
        onCancel={() => setUninstallTarget(null)}
        loading={uninstalling} />
    </div>);
}