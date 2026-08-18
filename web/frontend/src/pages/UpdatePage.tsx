import { useEffect, useState, useCallback } from 'react';
import {
  Download, RefreshCw, History, RotateCcw, Loader2, Globe, Shield,
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
  const [showHistory, setShowHistory] = useState(false);
  const [selectedRelease, setSelectedRelease] = useState<ReleaseInfo | null>(null);

  // 设置
  const [repo, setRepo] = useState('');
  const [mirror, setMirror] = useState('');
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

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">程序更新</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            当前版本 <span className="font-mono text-primary-600 dark:text-primary-400">v{info?.current_version}</span>
            {latest && !upToDate && (
              <span className="ml-2 px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-[10px] font-semibold">
                新版本 v{latest} 可用
              </span>
            )}
            {upToDate && <span className="ml-2 text-xs text-gray-400">已是最新版本</span>}
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

      {/* 更新设置 */}
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
            <label className="block text-xs text-gray-500 mb-1">镜像站 API 地址（可选）</label>
            <input value={mirror} onChange={e => setMirror(e.target.value)}
              placeholder="如 https://ghproxy.com/https://api.github.com"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
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

      {/* 最新版本卡片 */}
      {releases.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <Download className="w-4 h-4" /> 最新版本 v{releases[0].tag}
            </h2>
            <Button variant="ghost" size="sm" icon={<History />}
              onClick={() => setShowHistory(!showHistory)}>
              {showHistory ? '收起历史' : '历史版本'}
            </Button>
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none text-sm text-gray-600 dark:text-gray-400">
            <MarkdownRenderer content={releases[0].body || '（无更新日志）'} />
          </div>
          {!upToDate && (
            <div className="flex justify-end mt-4">
              <Button variant="primary" icon={<Download />}
                onClick={() => setConfirmUpdate(releases[0])}>
                更新到 v{releases[0].tag}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* 历史版本 */}
      {showHistory && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">历史版本</h2>
          <div className="space-y-2">
            {releases.slice(1).map((r) => (
              <div key={r.tag}
                className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700">
                <div className="min-w-0 flex-1 cursor-pointer" onClick={() => setSelectedRelease(selectedRelease?.tag === r.tag ? null : r)}>
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    v{r.tag} <span className="text-xs text-gray-400 font-normal">{r.name}</span>
                  </p>
                  <p className="text-[10px] text-gray-400">{r.published_at?.slice(0, 10)}</p>
                </div>
                <Button variant="ghost" size="sm"
                  onClick={() => setConfirmUpdate(r)}>更新到此版本</Button>
              </div>
            ))}
          </div>
          {selectedRelease && (
            <div className="mt-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-900">
              <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                v{selectedRelease.tag} 更新日志
              </p>
              <div className="text-sm text-gray-600 dark:text-gray-400">
                <MarkdownRenderer content={selectedRelease.body || '（无更新日志）'} />
              </div>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog open={!!confirmUpdate}
        title={`更新到 v${confirmUpdate?.tag}?`}
        message="更新将备份当前版本后下载并覆盖程序文件，服务会自动重启。请确保当前没有正在进行的操作。"
        onConfirm={handleApply} onCancel={() => setConfirmUpdate(null)} loading={applying} />
      <ConfirmDialog open={confirmRollback}
        title={`回滚到 v${info?.backup_version}?`}
        message="回滚将恢复备份的程序文件，当前版本将被覆盖。"
        danger onConfirm={handleRollback} onCancel={() => setConfirmRollback(false)} loading={applying} />
    </div>
  );
}
