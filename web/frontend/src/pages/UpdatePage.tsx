import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Download, RefreshCw, RotateCcw, Loader2, Globe, Shield,
  ChevronLeft, ChevronRight, ScrollText, X,
} from 'lucide-react';
import { showToast } from '../hooks/useToast';
import { Button } from '../components/Button';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

interface ReleaseInfo {
  tag: string;
  name: string;
  published_at: string;
  body: string;
  prerelease: boolean;
  assets: { name: string; url: string }[];
}

interface UpdateInfo {
  current_version: string;
  repo: string;
  mirror: string;
  proxy: string;
  has_backup: boolean;
  backup_version: string;
}

/** 常用 GitHub 镜像站（URL 前缀代理，同时加速 API 与下载） */
const MIRROR_PRESETS = [
  { name: 'gh-proxy.com', url: 'https://gh-proxy.com/' },
  { name: 'ghproxy.net', url: 'https://ghproxy.net/' },
  { name: 'mirror.ghproxy.com', url: 'https://mirror.ghproxy.com/' },
  { name: 'ghfast.top', url: 'https://ghfast.top/' },
  { name: 'hub.gitmirror.com', url: 'https://hub.gitmirror.com/' },
];

/** 版本列表每页条数 */
const PAGE_SIZE = 6;

/** 将 ISO 时间格式化为 ``2026/8/13 01:03:15`` 样式 */
function formatDateTime(iso: string): string {
  if (!iso) return '-';
  const [date, time] = iso.replace('T', ' ').slice(0, 19).split(' ');
  const [, month, day] = date.split('-');
  return `${date.slice(0, 4)}/${Number(month)}/${Number(day)} ${time}`;
}

/** 程序更新页面 */
export function UpdatePage() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [releases, setReleases] = useState<ReleaseInfo[]>([]);
  const [latest, setLatest] = useState<string | null>(null);
  const [upToDate, setUpToDate] = useState(true);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [confirmUpdate, setConfirmUpdate] = useState<ReleaseInfo | null>(null);
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [showChangelog, setShowChangelog] = useState(false);
  const [showPre, setShowPre] = useState(false);
  const [page, setPage] = useState(1);
  const [changelogTarget, setChangelogTarget] = useState<ReleaseInfo | null>(null);

  // 设置
  const [repo, setRepo] = useState('');
  const [mirror, setMirror] = useState('');
  const [mirrorCustom, setMirrorCustom] = useState(false); // 是否处于「自定义地址」模式
  const [proxy, setProxy] = useState('');

  const api = async (path: string, method = 'GET', body?: any) => {
    const token = localStorage.getItem('auth_token');
    const res = await fetch('/api/update' + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '请求失败');
    }
    return res.json();
  };

  const loadInfo = useCallback(async () => {
    try {
      const data = await api('/info');
      setInfo(data);
      setRepo(data.repo);
      setMirror(data.mirror);
      // 已保存的值不在预设列表中 → 视为自定义地址
      setMirrorCustom(Boolean(data.mirror) && !MIRROR_PRESETS.some(m => m.url === data.mirror));
      setProxy(data.proxy);
    } catch (e: any) { showToast('error', '加载失败', e.message); }
    finally { setLoading(false); }
  }, []);

  const checkUpdate = useCallback(async () => {
    setChecking(true);
    try {
      const data = await api('/check');
      setLatest(data.latest);
      setUpToDate(data.up_to_date);
      setReleases(data.releases || []);
      setPage(1);
    } catch (e: any) { showToast('error', '检测失败', e.message); }
    finally { setChecking(false); }
  }, []);

  useEffect(() => { loadInfo(); checkUpdate(); }, [loadInfo, checkUpdate]);

  const saveSettings = async () => {
    try {
      await api('/settings', 'POST', { repo, mirror, proxy });
      showToast('success', '更新配置已保存');
    } catch (e: any) { showToast('error', '保存失败', e.message); }
  };

  const handleApply = async () => {
    if (!confirmUpdate) return;
    setApplying(true);
    try {
      const assetName = confirmUpdate.assets.find(a => a.name.endsWith('.zip'))?.name
        || confirmUpdate.assets[0]?.name || '';
      const res = await api('/apply', 'POST', { version: confirmUpdate.tag, asset_name: assetName });
      showToast('success', res.message);
      setConfirmUpdate(null);
    } catch (e: any) { showToast('error', '更新失败', e.message); }
    finally { setApplying(false); }
  };

  const handleRollback = async () => {
    setApplying(true);
    try {
      const res = await api('/rollback', 'POST');
      showToast('success', res.message);
      setConfirmRollback(false);
    } catch (e: any) { showToast('error', '回滚失败', e.message); }
    finally { setApplying(false); }
  };

  // ------------------------------------------------------------------ #
  // 版本列表：预发布过滤 + 分页
  // ------------------------------------------------------------------ #

  const stableReleases = useMemo(() => releases.filter(r => !r.prerelease), [releases]);
  // 全部都是预发布时强制显示，避免空列表
  const showPreEffective = showPre || stableReleases.length === 0;
  const visible = showPreEffective ? releases : stableReleases;
  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageReleases = visible.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const rangeStart = visible.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(safePage * PAGE_SIZE, visible.length);

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      {/* 标题 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">更新 MisMiss</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            当前版本 <span className="font-mono text-primary-600 dark:text-primary-400">v{info?.current_version}</span>
            {latest && !upToDate && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-[10px] font-semibold">
                MisMiss 有新版本！
              </span>
            )}
            {upToDate && latest && <span className="ml-2 text-xs text-gray-400">已是最新版本</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" icon={<RefreshCw />} onClick={checkUpdate} loading={checking}>检查更新</Button>
          {info?.has_backup && (
            <Button variant="ghost" icon={<RotateCcw />}
              onClick={() => setConfirmRollback(true)}>
              回滚 v{info.backup_version}
            </Button>
          )}
        </div>
      </div>

      {/* 最新版本卡片 */}
      {releases.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-base font-bold font-mono text-gray-900 dark:text-white">v{releases[0].tag}</h2>
            <Button variant="ghost" size="sm" icon={<ScrollText />}
              onClick={() => setShowChangelog(!showChangelog)}>
              {showChangelog ? '收起日志' : '更新日志'}
            </Button>
          </div>
          <div className="p-5">
            <p className="text-xs text-gray-400 font-mono mb-2">
              [{releases[0].tag}] - {releases[0].published_at?.slice(0, 10) || '?'}
            </p>
            {showChangelog ? (
              <div className="prose prose-sm dark:prose-invert max-w-none text-sm text-gray-600 dark:text-gray-400">
                <MarkdownRenderer content={releases[0].body || '（无更新日志）'} />
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-3 whitespace-pre-line">
                {releases[0].body || '（无更新日志）'}
              </p>
            )}
            {!upToDate && (
              <div className="flex justify-end mt-4">
                <Button variant="primary" icon={<Download />}
                  onClick={() => setConfirmUpdate(releases[0])}>
                  更新到 v{releases[0].tag}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 版本列表 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">版本列表</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">显示预发布版本</span>
            <button
              onClick={() => { setShowPre(!showPre); setPage(1); }}
              disabled={stableReleases.length === 0}
              title={stableReleases.length === 0 ? '暂无正式版本' : undefined}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-40 disabled:cursor-not-allowed
                ${showPreEffective ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'}`}>
              <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform
                ${showPreEffective ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
            </button>
          </div>
        </div>
        {pageReleases.length === 0 ? (
          <p className="text-center text-gray-400 py-10 text-sm">暂无版本</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-100 dark:border-gray-700/50">
                <th className="px-5 py-2.5 font-medium">标签</th>
                <th className="px-5 py-2.5 font-medium">发布时间</th>
                <th className="px-5 py-2.5 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageReleases.map((r) => (
                <tr key={r.tag}
                  className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-900/50 transition-colors">
                  <td className="px-5 py-3">
                    <span className="font-mono font-medium text-gray-800 dark:text-gray-200">v{r.tag}</span>
                    {r.prerelease && (
                      <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 font-semibold">
                        预发布
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-gray-500 dark:text-gray-400">{formatDateTime(r.published_at)}</td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="outline" size="sm" onClick={() => setChangelogTarget(r)}>查看日志</Button>
                      <Button variant="outline" size="sm" onClick={() => setConfirmUpdate(r)}>切换</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {visible.length > 0 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-gray-700/50">
            <span className="text-xs text-gray-400">
              每页 {PAGE_SIZE} 条 · {rangeStart}-{rangeEnd} / 共 {visible.length} 条
            </span>
            <div className="flex gap-1">
              <button disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}
                className="p-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)}
                className="p-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 更新源设置 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
          <Globe className="w-4 h-4" /> 更新源设置
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">GitHub 仓库</label>
            <input value={repo} onChange={e => setRepo(e.target.value)}
              placeholder="Dresteam/MisMiss"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">镜像站（可选，加速 API 与下载）</label>
            <select
              value={mirrorCustom ? 'custom' : (MIRROR_PRESETS.some(m => m.url === mirror) ? mirror : '')}
              onChange={e => {
                const v = e.target.value;
                if (v === 'custom') {
                  setMirrorCustom(true); // 切换到自定义模式，输入框继续编辑原值
                } else {
                  setMirrorCustom(false);
                  setMirror(v);
                }
              }}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500">
              <option value="">直连 GitHub（不使用镜像）</option>
              {MIRROR_PRESETS.map(m => (
                <option key={m.url} value={m.url}>{m.name}（{m.url}）</option>
              ))}
              <option value="custom">自定义地址...</option>
            </select>
            {mirrorCustom && (
              <input value={mirror} onChange={e => setMirror(e.target.value)}
                placeholder="如 https://gh-proxy.com/"
                className="mt-2 w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
            )}
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs text-gray-500 mb-1">HTTP 代理（可选）</label>
            <input value={proxy} onChange={e => setProxy(e.target.value)}
              placeholder="如 http://127.0.0.1:7890"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
          </div>
        </div>
        <div className="flex justify-end mt-4">
          <Button variant="primary" size="sm" icon={<Shield />} onClick={saveSettings}>保存设置</Button>
        </div>
      </div>

      <ChangelogModal release={changelogTarget} onClose={() => setChangelogTarget(null)} />

      <ConfirmDialog open={!!confirmUpdate}
        title={`切换到 v${confirmUpdate?.tag}?`}
        message="更新将备份当前版本后下载并覆盖程序文件，服务会自动重启。请确保当前没有正在进行的操作。"
        onConfirm={handleApply} onCancel={() => setConfirmUpdate(null)} loading={applying} />
      <ConfirmDialog open={confirmRollback}
        title={`回滚到 v${info?.backup_version}?`}
        message="回滚将恢复备份的程序文件，当前版本将被覆盖。"
        danger onConfirm={handleRollback} onCancel={() => setConfirmRollback(false)} loading={applying} />
    </div>
  );
}

/** 更新日志弹框 —— 展示指定版本的完整更新日志 */
function ChangelogModal({ release, onClose }: { release: ReleaseInfo | null; onClose: () => void }) {
  if (!release) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col animate-slide-in-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 min-w-0">
            <ScrollText className="w-4 h-4 text-gray-500 shrink-0" />
            <h3 className="font-semibold text-gray-900 dark:text-white truncate">v{release.tag} 更新日志</h3>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          <p className="text-xs text-gray-400 font-mono mb-3">
            [{release.tag}] - {release.published_at?.slice(0, 10) || '?'}
          </p>
          {release.body ? (
            <MarkdownRenderer content={release.body} />
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">无更新日志</p>
          )}
        </div>
      </div>
    </div>
  );
}
