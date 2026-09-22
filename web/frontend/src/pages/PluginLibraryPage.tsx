import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, RefreshCw, Trash2, BookOpen, Loader2, Users, AlertTriangle, History, Star, Send, Sparkles, ChevronDown, ChevronUp, ScrollText } from 'lucide-react';
import {
  fetchLibraryPlugins, refreshPlugins, uninstallPlugin,
  fetchAccounts, pushPluginToAccounts, pushAllPlugins,
  setPluginDefault, applyDefaultPlugins,
} from '../api/client';
import type { LibraryPlugin, AccountSummary, BulkGroup } from '../api/types';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { UpdateDialog } from '../components/UpdateDialog';
import { PluginDrawer } from '../components/PluginDrawer';
import { PluginLogDialog } from '../components/PluginLogDialog';
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
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updateTarget, setUpdateTarget] = useState<{ name: string; oldVersion: string; newVersion: string } | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<LibraryPlugin | null>(null);
  const [disableInAccounts, setDisableInAccounts] = useState(false);
  const [drawerTarget, setDrawerTarget] = useState<{ name: string; tab?: string } | null>(null);
  // 插件日志弹窗：常驻入口 + 操作失败时自动打开
  const [logOpen, setLogOpen] = useState(false);
  const [logHint, setLogHint] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([fetchLibraryPlugins(), fetchAccounts()]);
      setPlugins(p);
      setAccounts(a);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  /** 执行一个带 loading 标记与结果提示的操作，完成后刷新列表。 */
  const act = async (key: string, fn: () => Promise<string>) => {
    setProcessing(key);
    try {
      showToast('success', await fn(), '');
      load();
    } catch (e: any) {
      showToast('error', '操作失败', e.message);
      // 失败时自动打开插件日志，便于直接看到报错与 traceback
      setLogHint(e.message || '');
      setLogOpen(true);
      load();
    } finally {
      setProcessing('');
    }
  };

  /** 待二次确认的批量操作——这类操作会波及多个账户，误触代价大 */
  const [bulkConfirm, setBulkConfirm] = useState<{
    key: string;
    title: string;
    message: string;
    confirmLabel: string;
    groups: BulkGroup[];
    run: () => Promise<string>;
  } | null>(null);
  const [bulkListOpen, setBulkListOpen] = useState(false);

  /**
   * 批量入口的统一流程：先取预览（dry_run）算出「将要动谁」，连同副作用说明
   * 一起放进确认弹窗展示明细；确实无事可做时直接提示，不弹一个空的确认框。
   */
  const askBulk = async (opts: {
    key: string;
    title: string;
    confirmLabel: string;
    caveat: string;
    emptyMessage: string;
    preview: () => Promise<{ groups: BulkGroup[]; message: string }>;
    run: () => Promise<string>;
  }) => {
    setProcessing(opts.key);
    try {
      const p = await opts.preview();
      if (p.groups.reduce((n, g) => n + g.items.length, 0) === 0) {
        showToast('success', opts.emptyMessage, '');
        return;
      }
      setBulkListOpen(false);
      setBulkConfirm({
        key: opts.key,
        title: opts.title,
        message: `${p.message}。${opts.caveat}`,
        confirmLabel: opts.confirmLabel,
        groups: p.groups,
        run: opts.run,
      });
    } catch (e: any) {
      showToast('error', '无法获取预览', e.message);
    } finally {
      setProcessing('');
    }
  };

  const runBulk = async () => {
    const job = bulkConfirm;
    if (!job) return;
    await act(job.key, job.run);
    setBulkConfirm(null);
  };

  /** 确认弹窗里的「将要动谁」明细，默认折叠 */
  const bulkDetail = bulkConfirm && bulkConfirm.groups.length > 0 ? (
    <div className="mt-3">
      <button type="button" onClick={() => setBulkListOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
        {bulkListOpen
          ? <ChevronUp className="w-3.5 h-3.5" />
          : <ChevronDown className="w-3.5 h-3.5" />}
        {bulkListOpen ? '收起' : '展开'}明细（
        {bulkConfirm.groups.reduce((n, g) => n + g.items.length, 0)} 项）
      </button>
      {bulkListOpen && (
        <div className="mt-2 max-h-52 overflow-y-auto rounded-lg border border-gray-200
                        dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700/60">
          {bulkConfirm.groups.map((g) => (
            <div key={g.label} className="px-3 py-2">
              <p className="text-xs font-medium text-gray-700 dark:text-gray-200">{g.label}</p>
              <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 break-all">
                {g.items.join('、')}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  ) : null;

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
      // 判定依据是响应体而非状态码:
      //   200 + action=update → 上传的是更高版本,后端尚未安装,等用户确认后走 /install/update
      //   409 + detail        → 版本不高于现有版本,属于拒绝,须按错误提示
      if (res.ok && body.action === 'update') {
        if (!body.name || !body.old_version || !body.new_version) {
          throw new Error('更新信息不完整,请重试');
        }
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
      // delete_data=true:彻底删除插件源文件;disableInAccounts:可选停用所有账户实例
      await uninstallPlugin(uninstallTarget.name, true, true, disableInAccounts);
      showToast('success', `${uninstallTarget.name} 已从插件库删除`, '');
      setUninstallTarget(null);
      setDisableInAccounts(false);
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
      {/* 窄屏下标题与操作分两行：操作组独占整行才不会挤成三行 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold">插件库</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            面板级统一安装管理,各账户按需启用 · {plugins.length} 个插件
          </p>
        </div>
        {/* 次要操作在窄屏只留图标（display:none 的元素不占 flex 间距，
            故不会多出一段空隙），5 个操作仍排得下一行；sm 起恢复文字 */}
        <div className="flex flex-wrap gap-1.5 sm:gap-2">
          <Button variant="secondary" size="sm" icon={<RefreshCw className="w-4 h-4" />}
            title="刷新" aria-label="刷新"
            onClick={async () => { await refreshPlugins(); load(); showToast('success', '已刷新', ''); }}>
            <span className="hidden sm:inline">刷新</span>
          </Button>
          <Button variant="secondary" size="sm" icon={<Send className="w-4 h-4" />}
            title="推送全部到账户" aria-label="推送全部到账户"
            loading={processing === '__push_all__'} disabled={!!processing}
            onClick={() => askBulk({
              key: '__push_all__',
              title: '推送到全部账户',
              confirmLabel: '确认推送',
              caveat: '更新会重启对应插件实例，其插件消息与内部状态会中断（配置与启用状态保留）',
              emptyMessage: '所有账户的插件均已是库版本，无需更新',
              preview: () => pushAllPlugins(true),
              run: async () => (await pushAllPlugins(false)).message,
            })}>
            <span className="hidden sm:inline">推送全部到账户</span>
          </Button>
          <Button variant="secondary" size="sm" icon={<Sparkles className="w-4 h-4" />}
            title="应用默认插件" aria-label="应用默认插件"
            loading={processing === '__apply_defaults__'} disabled={!!processing}
            onClick={() => askBulk({
              key: '__apply_defaults__',
              title: '应用默认插件到现有账户',
              confirmLabel: '确认应用',
              caveat: '未安装的装上并启用、已装未启用的启用、已启用的不动',
              emptyMessage: '所有账户均无需补齐默认插件',
              preview: () => applyDefaultPlugins(true),
              run: async () => (await applyDefaultPlugins(false)).message,
            })}>
            <span className="hidden sm:inline">应用默认插件</span>
          </Button>
          <Button variant="ghost" size="sm" icon={<ScrollText className="w-4 h-4" />}
            title="插件日志" aria-label="插件日志"
            onClick={() => { setLogHint(''); setLogOpen(true); }}>
            <span className="hidden sm:inline">插件日志</span>
          </Button>
          <Button variant="primary" size="sm" icon={<Upload className="w-4 h-4" />}
            onClick={() => fileRef.current?.click()}>
            安装插件
          </Button>
        </div>
      </div>

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
                      {p.is_default && (
                        <span title="新建账户时自动安装并启用"
                          className="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30
                                     text-amber-600 dark:text-amber-400 text-[10px] font-medium">
                          默认
                        </span>
                      )}
                      {p.last_error && (
                        <button
                          title={`初始化失败：${p.last_error}\n点击查看插件日志`}
                          onClick={() => { setLogHint(p.last_error || ''); setLogOpen(true); }}
                          className="px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30
                                     text-red-600 dark:text-red-400 text-[10px] font-medium
                                     hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors">
                          初始化失败
                        </button>
                      )}
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
                {/* 固定单行：逐个列出会让账户多的插件把卡片撑高，并由 grid 拉齐连累同排卡片。
                    只展示前几个 + 「+N」，其余走「使用账户」抽屉（那里还带账户名） */}
                <div className="flex flex-1 min-w-0 items-center gap-1 overflow-hidden">
                  {p.used_by_accounts.slice(0, 3).map((aid) => (
                    <span key={aid} className="badge badge-blue shrink-0 whitespace-nowrap">账户 {aid}</span>
                  ))}
                  {p.used_by_accounts.length > 3 && (
                    <button
                      onClick={() => openDrawer(p.name, 'accounts')}
                      title={`查看全部 ${p.used_by_accounts.length} 个账户`}
                      className="badge badge-blue shrink-0 whitespace-nowrap hover:brightness-95 dark:hover:brightness-110">
                      +{p.used_by_accounts.length - 3}
                    </button>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-0.5 lg:gap-1 flex-nowrap">
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
                  <IconBtn
                    icon={<Star className={`w-3.5 h-3.5 ${p.is_default ? 'fill-amber-400 text-amber-400' : ''}`} />}
                    label={p.is_default ? '取消默认插件' : '设为默认插件（新建账户自动安装并启用）'}
                    loading={processing === `default:${p.name}`} disabled={!!processing}
                    onClick={() => act(`default:${p.name}`, async () => {
                      await setPluginDefault(p.name, !p.is_default);
                      const label = p.display_name || p.name;
                      return p.is_default ? `已取消默认：${label}` : `已设为默认：${label}`;
                    })} />
                  <IconBtn icon={<Send className="w-3.5 h-3.5" />}
                    label="推送库版本到各账户副本"
                    loading={processing === `push:${p.name}`} disabled={!!processing}
                    onClick={() => askBulk({
                      key: `push:${p.name}`,
                      title: `推送「${p.display_name || p.name}」到全部账户`,
                      confirmLabel: '确认推送',
                      caveat: '更新会重启对应插件实例，其插件消息与内部状态会中断（配置与启用状态保留）',
                      emptyMessage: `各账户的「${p.display_name || p.name}」均已是库版本，无需更新`,
                      preview: () => pushPluginToAccounts(p.name, true),
                      run: async () => (await pushPluginToAccounts(p.name, false)).message,
                    })} />
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

      {/* 卸载弹窗:彻底删除源文件 + 可选停用所有账户实例 */}
      {uninstallTarget && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setUninstallTarget(null)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              卸载插件「{uninstallTarget.name}」
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              源文件将被彻底从插件库删除,此操作不可撤销。
            </p>
            <label className="flex items-center gap-3 cursor-pointer mt-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-900/40">
              <input type="checkbox" checked={disableInAccounts}
                onChange={(e) => setDisableInAccounts(e.target.checked)}
                className="w-4 h-4 accent-primary-600" />
              <span>
                <span className="block text-sm font-medium text-gray-900 dark:text-white">
                  停用所有账户的相关插件
                </span>
                <span className="block text-[11px] text-gray-500">
                  停用各账户中已启用的该插件实例(副本保留,可重新启用)
                </span>
              </span>
            </label>
            <div className="flex justify-end gap-2 mt-5">
              <Button variant="secondary" size="sm" onClick={() => setUninstallTarget(null)}>取消</Button>
              <Button variant="danger" size="sm" loading={processing === uninstallTarget.name}
                onClick={handleUninstall}>确认删除</Button>
            </div>
          </div>
        </div>
      )}

      {/* 批量操作二次确认——这类操作会波及多个账户，误触代价大 */}
      {bulkConfirm && (
        <ConfirmDialog
          open
          title={bulkConfirm.title}
          message={bulkConfirm.message}
          confirmLabel={bulkConfirm.confirmLabel}
          variant="warning"
          loading={processing === bulkConfirm.key}
          onConfirm={runBulk}
          onCancel={() => setBulkConfirm(null)}>
          {bulkDetail}
        </ConfirmDialog>
      )}

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

      <PluginLogDialog
        open={logOpen}
        hint={logHint}
        onClose={() => { setLogOpen(false); setLogHint(''); }}
      />
    </div>
  );
}
