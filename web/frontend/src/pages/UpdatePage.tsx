import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Download, RefreshCw, RotateCcw, Loader2, Globe, Shield, Container,
  ScrollText, Megaphone, ArrowRightLeft,
  CheckCircle2, XCircle, AlertTriangle, X,
} from 'lucide-react';
import { showToast } from '../hooks/useToast';
import { Button } from '../components/Button';
import { Pagination } from '../components/ListControls';
import { MarqueeText } from '../components/MarqueeText';
import { Select } from '../components/Select';
import { Switch } from '../components/Switch';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ChangelogDialog } from '../components/ChangelogDialog';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

interface ReleaseInfo {
  tag: string;
  name: string;
  published_at: string;
  body: string;
  prerelease: boolean;
  assets: { name: string; url: string }[];
}

/** GET /api/update/status —— 更新进度（后端后台执行，前端轮询） */
interface UpdateStatus {
  busy: boolean;
  /** idle=没有记录 / running=进行中 / done / failed / interrupted */
  state: 'idle' | 'running' | 'done' | 'failed' | 'interrupted';
  kind?: 'apply' | 'rollback';
  step?: string;
  step_label?: string;
  message?: string;
  version?: string;
  started_at?: number;
  finished_at?: number | null;
}

interface UpdateInfo {
  current_version: string;
  repo: string;
  mirror: string;
  proxy: string;
  /** 更新时是否向各账户直播间发送提示消息 */
  notify_enabled: boolean;
  /** 更新前（重启前）发送的消息 */
  notify_before: string;
  /** 更新后（新版本启动完成）发送的消息 */
  notify_after: string;
  /** 单条提示消息的字符上限 */
  notify_max_len: number;
  has_backup: boolean;
  backup_version: string;
  is_docker: boolean;
  /** Docker 部署且已挂载 docker.sock + 部署目录（在线更新可用） */
  docker_ready: boolean;
}

/** 常用 GitHub 镜像站（URL 前缀代理，同时加速 API 与下载） */
const MIRROR_PRESETS = [
  { name: 'gh-proxy.com', url: 'https://gh-proxy.com/' },
  { name: 'ghproxy.net', url: 'https://ghproxy.net/' },
  { name: 'mirror.ghproxy.com', url: 'https://mirror.ghproxy.com/' },
  { name: 'ghfast.top', url: 'https://ghfast.top/' },
  { name: 'hub.gitmirror.com', url: 'https://hub.gitmirror.com/' },
];

/** 版本列表每页条数的默认值（可在页脚里改，见 ``pageSize``） */
const PAGE_SIZE = 6;

/** 将 ISO 时间格式化为 ``2026/8/13 01:03:15`` 样式 */
function formatDateTime(iso: string): string {
  if (!iso) return '-';
  const [date, time] = iso.replace('T', ' ').slice(0, 19).split(' ');
  const [, month, day] = date.split('-');
  return `${date.slice(0, 4)}/${Number(month)}/${Number(day)} ${time}`;
}

/** 窄屏版本 ``8/13 01:03`` —— 去掉年份与秒。
 *
 * 完整的 18 字符串在 375px 屏上要占掉半行，会把操作列挤到折行（见下方版本列表）。
 * 复用 `formatDateTime` 的输出再裁，免得同一套解析写两遍。 */
function formatShortDateTime(iso: string): string {
  const full = formatDateTime(iso);
  if (full === '-') return full;
  const [date, time] = full.split(' ');
  return `${date.slice(5)} ${time.slice(0, 5)}`;
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
  // 与 applying 分开：applying 只控按钮禁用，polling 表示「本次请求已受理，开始跟进度」。
  // 必须在 POST 成功之后才置位 —— 否则轮询会先读到上一轮的终态并误报。
  const [polling, setPolling] = useState(false);
  const [progress, setProgress] = useState<UpdateStatus | null>(null);
  const [confirmUpdate, setConfirmUpdate] = useState<ReleaseInfo | null>(null);
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [showChangelog, setShowChangelog] = useState(false);
  const [showPre, setShowPre] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [changelogTarget, setChangelogTarget] = useState<ReleaseInfo | null>(null);

  // 设置
  const [repo, setRepo] = useState('');
  const [mirror, setMirror] = useState('');
  const [mirrorCustom, setMirrorCustom] = useState(false); // 是否处于「自定义地址」模式
  const [proxy, setProxy] = useState('');

  // 更新提示消息
  const [notifyEnabled, setNotifyEnabled] = useState(false);
  const [notifyBefore, setNotifyBefore] = useState('');
  const [notifyAfter, setNotifyAfter] = useState('');
  const [notifySaving, setNotifySaving] = useState(false);
  const notifyMaxLen = info?.notify_max_len || 80;

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
      setNotifyEnabled(Boolean(data.notify_enabled));
      setNotifyBefore(data.notify_before ?? '');
      setNotifyAfter(data.notify_after ?? '');
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

  // 更新进度轮询。apply/rollback 在后端已改为后台执行（秒回 202），
  // 真实进度只能靠轮询 —— 否则下载+导入镜像动辄数分钟，长请求会被代理掐断。
  useEffect(() => {
    if (!polling) return;
    let stopped = false;
    const tick = async () => {
      try {
        const st: UpdateStatus = await api('/status');
        if (stopped) return;
        setProgress(st);
        if (st.state === 'running') return;
        // 终态：停止轮询并汇报
        setPolling(false);
        setApplying(false);
        if (st.state === 'done') {
          showToast('success', st.message || '更新已完成');
          checkUpdate();
        } else if (st.state === 'interrupted') {
          showToast('error', '更新中断', st.message || '更新未完成即中断');
        } else {
          showToast('error', '更新失败', st.message || '未知原因');
        }
      } catch {
        /* 下一轮再试 —— 容器重建期间请求会短暂失败，属正常 */
      }
    };
    tick();
    const timer = setInterval(tick, 2000);
    return () => { stopped = true; clearInterval(timer); };
  }, [polling, checkUpdate]);

  // 进入页面时若后端仍有更新在跑（如刷新过页面），接上轮询。
  //
  // ⚠️ **只接 running**：终态（done / failed / interrupted）是**上一次**更新的
  // 结果，当时已经报过了。无条件 setProgress 会让那个结果每次打开本页都重新
  // 弹出来 —— 而它又没有关闭入口，于是永远挂在页面上。
  useEffect(() => {
    let stopped = false;
    api('/status')
      .then((st: UpdateStatus) => {
        if (stopped || st.state !== 'running') return;
        setProgress(st);
        setPolling(true);
        setApplying(true);
      })
      .catch(() => { /* 拿不到就不显示进度 */ });
    return () => { stopped = true; };
  }, []);

  const saveSettings = async (label = '更新配置') => {
    try {
      // 两张设置卡片共用同一份状态与同一个接口，任一「保存」都会落盘全部字段
      await api('/settings', 'POST', {
        repo, mirror, proxy,
        notify_enabled: notifyEnabled,
        notify_before: notifyBefore,
        notify_after: notifyAfter,
      });
      showToast('success', `${label}已保存`);
      loadInfo();
    } catch (e: any) { showToast('error', '保存失败', e.message); }
  };

  /**
   * 开关点一下即时生效：只提交 notify_enabled 这一个字段。
   * 后端的 /settings 是「只更新请求体里出现过的键」，所以不会把用户还没点保存的
   * 其它输入（仓库/镜像/代理/两条文案）顺带写进去。
   * 成功与否都不调 loadInfo() —— 那会把用户正在编辑的输入框重置回已保存值。
   */
  const toggleNotify = async () => {
    const next = !notifyEnabled;
    setNotifyEnabled(next); // 先动 UI，点下去立刻有反馈
    setNotifySaving(true);
    try {
      await api('/settings', 'POST', { notify_enabled: next });
      showToast('success', next ? '更新提示已开启' : '更新提示已关闭');
    } catch (e: any) {
      setNotifyEnabled(!next); // 失败回滚开关
      showToast('error', '切换失败', e.message);
    } finally { setNotifySaving(false); }
  };

  const handleApply = async () => {
    if (!confirmUpdate) return;
    setApplying(true);
    try {
      // Docker 部署：后端自动选择 docker 部署包资产；
      // 原生部署：优先源码归档（mismiss-<tag>.zip/.tar.gz），排除 docker 部署包资产
      const tag = confirmUpdate.tag;
      const preferred = [`mismiss-${tag}.zip`, `mismiss-${tag}.tar.gz`];
      const assetName = info?.is_docker ? '' : (
        confirmUpdate.assets.find(a => preferred.includes(a.name))?.name
        || confirmUpdate.assets.find(a =>
          (a.name.endsWith('.zip') || a.name.endsWith('.tar.gz')) && !a.name.includes('-docker'))?.name
        || ''
      );
      await api('/apply', 'POST', { version: confirmUpdate.tag, asset_name: assetName });
      // 这里**不报成功** —— 请求只表示「已受理」，真实结果由轮询给出
      setConfirmUpdate(null);
      setProgress({ busy: true, state: 'running', step_label: '准备中', message: '正在开始更新…' });
      setPolling(true);
    } catch (e: any) {
      showToast('error', '更新失败', e.message);
      setApplying(false);
    }
  };

  const handleRollback = async () => {
    setApplying(true);
    setProgress(null);
    try {
      await api('/rollback', 'POST');
      setConfirmRollback(false);
      setProgress({ busy: true, state: 'running', step_label: '准备中', message: '正在开始回滚…' });
      setPolling(true);
    } catch (e: any) {
      showToast('error', '回滚失败', e.message);
      setApplying(false);
    }
  };

  // ------------------------------------------------------------------ #
  // 版本列表：预发布过滤 + 分页
  // ------------------------------------------------------------------ #

  const stableReleases = useMemo(() => releases.filter(r => !r.prerelease), [releases]);
  // 全部都是预发布时强制显示，避免空列表
  const showPreEffective = showPre || stableReleases.length === 0;
  const visible = showPreEffective ? releases : stableReleases;
  const totalPages = Math.max(1, Math.ceil(visible.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageReleases = visible.slice((safePage - 1) * pageSize, safePage * pageSize);

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
            <Button variant="ghost" icon={<RotateCcw />} disabled={info?.is_docker && !info?.docker_ready}
              title={info?.is_docker && !info?.docker_ready ? '未挂载 docker.sock，请通过部署包更新' : undefined}
              onClick={() => setConfirmRollback(true)}>
              回滚 v{info.backup_version}
            </Button>
          )}
        </div>
      </div>

      {/* 更新进度：后端后台执行，这里轮询显示 */}
      {progress && progress.state !== 'idle' && (
        <div className={`flex items-start gap-3 px-4 py-3 rounded-lg border text-sm ${
          progress.state === 'running'
            ? 'bg-sky-100 dark:bg-sky-900/30 border-sky-200 dark:border-sky-800 text-sky-800 dark:text-sky-400'
            : progress.state === 'done'
              ? 'bg-emerald-100 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-400'
              : 'bg-red-100 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-800 dark:text-red-400'
        }`}>
          {progress.state === 'running' && <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin" />}
          {progress.state === 'done' && <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />}
          {progress.state === 'failed' && <XCircle className="w-4 h-4 mt-0.5 shrink-0" />}
          {progress.state === 'interrupted' && <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />}
          <div className="min-w-0 flex-1">
            <div className="font-medium">
              {progress.kind === 'rollback' ? '回滚' : '更新'}
              {progress.state === 'running' && ` · ${progress.step_label || '进行中'}`}
              {progress.state === 'done' && ' 已完成'}
              {progress.state === 'failed' && ' 失败'}
              {progress.state === 'interrupted' && ' 被中断'}
              {progress.version && `（v${progress.version}）`}
            </div>
            {progress.message && (
              <div className="mt-0.5 break-words opacity-90">{progress.message}</div>
            )}
            {progress.state === 'running' && (
              <div className="mt-0.5 opacity-75 text-xs">
                更新在服务端后台执行，可以离开本页；重新进入会自动接上进度。
              </div>
            )}
          </div>
          {/* 只有终态给关：「进行中」关掉会被下一轮轮询（2 秒）立刻重新点亮，
              看着像坏了；而且那时的进度本身还带着信息。
              终态关掉后不会再回来 —— 进页面时只接 running 状态。 */}
          {progress.state !== 'running' && (
            <button onClick={() => setProgress(null)} aria-label="关闭提示"
              className="shrink-0 -mr-1 p-1 rounded-lg hover:bg-black/5
                         dark:hover:bg-white/10 transition-colors">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      )}

      {/* Docker 部署提示：在线更新可用 / 未挂载 socket */}
      {info?.is_docker && info?.docker_ready && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-sky-100 dark:bg-sky-900/30 border border-sky-200 dark:border-sky-800 text-sky-800 dark:text-sky-400 text-sm">
          <Container className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            当前为 Docker 部署。点击更新将自动下载部署包、导入镜像并重建容器
            （约 10~30 秒，期间页面短暂断开）；更新前会备份当前版本，支持一键回滚。
          </span>
        </div>
      )}
      {info?.is_docker && !info?.docker_ready && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-amber-100 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-400 text-sm">
          <Container className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            当前为 Docker 部署，但未检测到 docker.sock / 部署目录挂载，在线更新不可用。
            请检查 docker-compose.yml 中 mismiss 服务的两处挂载，或通过部署包手动更新：
            上传服务器后执行 <code className="font-mono">bash deploy.sh</code>。
          </span>
        </div>
      )}

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
            {!upToDate && !(info?.is_docker && !info?.docker_ready) && (
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
            <Switch
              checked={showPreEffective}
              onChange={() => { setShowPre(!showPre); setPage(1); }}
              disabled={stableReleases.length === 0}
              label="显示预发布版本"
              title={stableReleases.length === 0 ? '暂无正式版本' : undefined}
            />
          </div>
        </div>
        {pageReleases.length === 0 ? (
          <p className="text-center text-gray-400 py-10 text-sm">暂无版本</p>
        ) : (
          /* table-fixed 是「标签能横向滚动」的前提：自动布局下浏览器会按
             min-content 排布，`whitespace-nowrap` 的标签会把这列撑到全宽、
             整张表溢出屏幕，轮不到标签自己滚。定宽后内容超出就在格子里滚。
             右侧两列的宽度按各自最宽的内容给（窄屏是缩写日期 + 纯图标按钮）。 */
          <table className="w-full table-fixed text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-100 dark:border-gray-700/50">
                <th className="px-2 py-2.5 font-medium md:px-5">标签</th>
                <th className="w-[5.5rem] px-2 py-2.5 font-medium md:w-48 md:px-5">发布时间</th>
                <th className="w-[6.5rem] px-2 py-2.5 font-medium text-right md:w-48 md:px-5">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageReleases.map((r) => (
                <tr key={r.tag}
                  className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-900/50 transition-colors">
                  <td className="px-2 py-3 md:px-5">
                    {/* 这层只干两件事：贴住标签、给角标当定位基准。
                        `w-max` 让宽度等于标签本身（短标签不再顶满整列，角标才不会
                        飘到离标签很远的地方）；`max-w-full` 在标签超长时收回列宽，
                        于是里面的 MarqueeText 照旧测得出溢出、照旧滚动。
                        它不能写成 flex-1/自适应宽 —— 那样宽度就等于整列，角标会贴在
                        列尾而不是标签上（本行高度也只有一行，怎么放都别扭）。 */}
                    <div className="relative w-max max-w-full">
                      {/* 标签溢出就自动滚动，不折行、不撑宽本行 */}
                      <MarqueeText text={`v${r.tag}`}
                        className="font-mono font-medium text-gray-800 dark:text-gray-200" />
                      {/* 角标：绝对定位，**不占任何布局宽度** —— 标签列总共 135px，
                          而 `v1.5.2-beta.1` 自己就要 109px，文字徽标怎么也放不下。
                          `left-full` 贴在标签右缘、`top-1/2 -translate-y-1/2` 与文字
                          垂直居中；`-ml-px` 吃掉 1px 缝隙，免得看着断开。
                          超出的部分落在两列内边距里（标签列右 8px + 日期列左 8px），
                          不会碰到日期文字 */}
                      {r.prerelease && (
                        <span className="absolute left-full top-1/2 -translate-y-1/2 -ml-px
                                         whitespace-nowrap rounded-full
                                         bg-purple-100 dark:bg-purple-900/30
                                         text-purple-600 dark:text-purple-400
                                         text-[9px] leading-none px-1 py-0.5 font-semibold">
                          预发布
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-3 whitespace-nowrap text-gray-500 dark:text-gray-400 md:px-5">
                    {/* 两份长度都在 DOM 里，由 CSS 决定显示哪份 —— 与日志页的级别按钮同一套
                        做法，比 matchMedia 简单且无首帧闪烁 */}
                    <span className="md:hidden">{formatShortDateTime(r.published_at)}</span>
                    <span className="hidden md:inline">{formatDateTime(r.published_at)}</span>
                  </td>
                  <td className="px-2 py-3 text-right md:px-5">
                    <div className="flex items-center justify-end gap-1">
                      {/* 窄屏只留图标：两个文字按钮要 136px，在 375px 屏上放不下，
                          只能折行。换成图标后整列只要 80px，让出的宽度归标签。
                          用的是 Button 抬头注释里那套 `hidden md:inline` 写法 ——
                          图标走 `md:hidden` 而不是 `icon` prop，好让**宽屏与改动前
                          完全一致**（走 icon prop 会给宽屏也多加一个图标）。
                          图标按钮按全站惯例配 `tooltip` + `aria-label`（同 `LogsPage`
                          的日志工具条、《账户总览》的卡片操作）。
                          ⚠️ `HoverTip` 只认 `group-hover`，触屏上不会出现 —— 手机上
                          这两个按钮依旧没有可见文字，提示是给桌面看的。 */}
                      <Button variant="outline" size="sm"
                        tooltip="查看日志" tooltipClassName="md:hidden"
                        aria-label="查看日志"
                        onClick={() => setChangelogTarget(r)}>
                        <ScrollText className="md:hidden w-3.5 h-3.5 shrink-0" />
                        <span className="hidden md:inline">查看日志</span>
                      </Button>
                      {/* `tooltip` 与 `title` 各管一段：Button 在 disabled 时不渲染
                          HoverTip（见其 `!isDisabled`），所以「为什么不能点」仍走原生
                          `title`，启用时置 undefined 免得两个提示叠在一起 —— 顶部那个
                          「回滚」按钮本来就是这么写的 */}
                      <Button variant="outline" size="sm"
                        tooltip="切换到此版本" tooltipClassName="md:hidden"
                        aria-label="切换到此版本"
                        title={info?.is_docker && !info?.docker_ready
                          ? '未挂载 docker.sock，请通过部署包更新'
                          : undefined}
                        disabled={info?.is_docker && !info?.docker_ready}
                        onClick={() => setConfirmUpdate(r)}>
                        {/* 换掉原来的 `Download`：那图标读起来就是「下载」，与旁边
                            真正的下载动作分不开。`ArrowRightLeft` 才对应「切换」 */}
                        <ArrowRightLeft className="md:hidden w-3.5 h-3.5 shrink-0" />
                        <span className="hidden md:inline">切换</span>
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {visible.length > 0 && (
          <div className="px-5 py-3 border-t border-gray-100 dark:border-gray-700/50">
            {/* 复用账户总览那套分页：`<< < 1 2 3 … > >>`，窄屏自动去掉首/末页。
                版本列表不再报「每页 6 条 · 1-6 / 共 13 条」——那条说明一半是恒定的、
                另一半（末页页码）本来就看得到；改成能直接调每页条数更实用。
                改条数要回到第 1 页：否则原页码可能越界，虽会被 `safePage` 夹住，
                但用户看到的是「刚跳到第 4 页，一改条数又弹回第 1 页」，不如直接回顶 */}
            <Pagination page={safePage} pageCount={totalPages} total={visible.length}
              onChange={setPage}
              pageSize={pageSize}
              onPageSizeChange={(n) => { setPageSize(n); setPage(1); }} />
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
            <Select
              value={mirrorCustom ? 'custom' : (MIRROR_PRESETS.some(m => m.url === mirror) ? mirror : '')}
              onChange={v => {
                if (v === 'custom') {
                  setMirrorCustom(true); // 切换到自定义模式，输入框继续编辑原值
                } else {
                  setMirrorCustom(false);
                  setMirror(v);
                }
              }}
              placeholder="直连 GitHub（不使用镜像）"
              ariaLabel="镜像站"
              className="w-full"
              options={[
                { value: '', label: '直连 GitHub（不使用镜像）' },
                ...MIRROR_PRESETS.map(m => ({ value: m.url, label: `${m.name}（${m.url}）` })),
                { value: 'custom', label: '自定义地址...' },
              ]}
            />
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
          <Button variant="primary" size="sm" icon={<Shield />} onClick={() => saveSettings()}>保存设置</Button>
        </div>
      </div>

      {/* 更新提示消息 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Megaphone className="w-4 h-4" /> 更新提示消息
          </h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">启用更新提示</span>
            {/* 保存中用 loading（转圈在旋钮里），与账户页的「安装后自动启用」一致；
                原先用 disabled，只变淡、看不出在保存 */}
            <Switch
              checked={notifyEnabled}
              onChange={toggleNotify}
              loading={notifySaving}
              label="启用更新提示"
              title="点击即时生效，无需再点保存"
            />
          </div>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          开关<span className="font-medium text-gray-600 dark:text-gray-300">点击即生效</span>，
          无需再点保存。开启后，程序更新时会用各账户的机器人在其绑定的直播间各发一条消息；
          <span className="text-gray-400 dark:text-gray-500">
            直播间未启用或未开播的账户自动跳过。
          </span>
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">更新前提示（重启前发送）</label>
            <input value={notifyBefore} maxLength={notifyMaxLen}
              disabled={!notifyEnabled}
              onChange={e => setNotifyBefore(e.target.value)}
              placeholder="如：机器人即将更新，稍后自动恢复"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">更新后提示（新版本启动后发送）</label>
            <input value={notifyAfter} maxLength={notifyMaxLen}
              disabled={!notifyEnabled}
              onChange={e => setNotifyAfter(e.target.value)}
              placeholder="如：机器人已更新完成，已恢复正常"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50" />
          </div>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
          单条最多 {notifyMaxLen} 个字符。留空则跳过对应阶段的消息。
        </p>
        <div className="flex justify-end mt-4">
          <Button variant="primary" size="sm" icon={<Megaphone />}
            onClick={() => saveSettings('提示文案')}>保存提示文案</Button>
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
  return (
    <ChangelogDialog
      open={!!release}
      version={release?.tag ?? ''}
      meta={release ? `[${release.tag}] - ${release.published_at?.slice(0, 10) || '?'}` : undefined}
      body={release?.body ?? ''}
      onClose={onClose}
    />
  );
}
