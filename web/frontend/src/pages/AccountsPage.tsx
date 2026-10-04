import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Plus, Trash2, Bot as BotIcon,
  Radio, Puzzle, Clock, AlertTriangle, Loader2, Lock, Hourglass, CalendarPlus, ExternalLink, CalendarCog,
  CirclePlay, CircleStop, Plug, Unplug, ListOrdered, X,
} from 'lucide-react';
import {
  fetchPanelOverview, createAccount, deleteAccount, renewAccount, redeemAccount,
  resetAccountCredentials, expireAccount, renumberAccounts,
  enableAccountBot, disableAccountBot, enableAccountLive, disableAccountLive,
} from '../api/client';
import type { AccountSummary, AccountCreateRequest, PanelOverview, RenewRequest } from '../api/types';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { ExpiryBadge } from '../components/ExpiryBadge';
import { CreateAccountDialog, RenewDialog, CredentialsDialog } from '../components/AccountDialogs';
import { CompensateDialog } from '../components/CompensateDialog';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { SearchInput, FilterChips, FilterToggle, Pagination } from '../components/ListControls';
import { showToast } from '../hooks/useToast';
import { livePageUrl } from '../utils/live';

/** 账户列表每页条数 —— 3 列 × 4 行 */
const ACCOUNTS_PER_PAGE = 12;

/**
 * 「即将过期」的判定阈值（天）。7 天足够提前续期，又不至于把大半个列表都算进来。
 * 与「正常」「已过期」互斥：已过期的不再算即将过期。
 */
const EXPIRING_SOON_DAYS = 7;

/** 卡片上的运行时快捷开关:Bot 启停 / 直播间连断 */
type RuntimeKind = 'bot' | 'live';

/**
 * 把一个运行时开关的「当前状态」翻译成确认框文案与要执行的动作。
 *
 * 同一个开关的两个方向共用这一份定义 —— 文案、按钮字、危险色、成功提示
 * 都从 `on` 推导，避免按钮、确认框、toast 三处各写一遍而写岔。
 */
function runtimeIntent(acc: AccountSummary, kind: RuntimeKind) {
  if (kind === 'bot') {
    const on = acc.bot_enabled;
    return {
      /** 当前是否处于「开」的状态;为真表示这次动作是停止/断开 */
      on,
      title: on ? '停止 Bot' : '启动 Bot',
      message: on
        ? `将停用账户「${acc.name}」的 Bot:断开与平台的连接,其定时消息与插件推送随即停止。`
        : `将启用账户「${acc.name}」的 Bot:连接平台并开始轮转发送该账户的定时消息。`,
      confirmLabel: on ? '停止' : '启动',
      done: on ? 'Bot 已停止' : 'Bot 已启动',
      run: () => (on ? disableAccountBot(acc.id) : enableAccountBot(acc.id)),
    };
  }
  const on = acc.room_enabled;
  return {
    on,
    title: on ? '断开直播间' : '连接直播间',
    message: on
      ? `将断开账户「${acc.name}」的直播间:停止接收弹幕与礼物事件,且重启后不会自动连回。`
      : `将连接账户「${acc.name}」的直播间:Bot 进入房间,开始接收弹幕与礼物事件。`,
    confirmLabel: on ? '断开' : '连接',
    done: on ? '直播间已断开' : '直播间已连接',
    run: () => (on ? disableAccountLive(acc.id) : enableAccountLive(acc.id)),
  };
}

export function AccountsPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<PanelOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [renewTarget, setRenewTarget] = useState<AccountSummary | null>(null);
  const [renewMode, setRenewMode] = useState<'days' | 'set' | 'code' | 'permanent' | 'expire'>('days');
  const [renewing, setRenewing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AccountSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [credTarget, setCredTarget] = useState<AccountSummary | null>(null);
  const [credBusy, setCredBusy] = useState(false);
  const [compensateOpen, setCompensateOpen] = useState(false);
  // 编号重排：先拿 dry-run 映射给用户确认，再真正执行
  const [renumberPlan, setRenumberPlan] = useState<
    { mapping: Record<string, number>; changed: number; total: number } | null
  >(null);
  const [renumberBusy, setRenumberBusy] = useState(false);
  /** 待确认的运行时开关 —— 点快捷按钮只弹确认框，确认后才真正执行 */
  const [runtimeTarget, setRuntimeTarget] = useState<{ acc: AccountSummary; kind: RuntimeKind } | null>(null);
  const [runtimeBusy, setRuntimeBusy] = useState(false);

  // ---- 列表筛选与分页（全在浏览器里做，后端不动） ----
  const [keyword, setKeyword] = useState('');
  // 四组筛选一律「全部 + 三个互斥状态」= 4 项，正好排满 4 列网格、不留空格
  const [statusFilter, setStatusFilter] = useState<'all' | 'normal' | 'expiring' | 'expired'>('all');
  const [modeFilter, setModeFilter] = useState<'all' | 'public' | 'private' | 'broken'>('all');
  const [liveFilter, setLiveFilter] = useState<'all' | 'live' | 'offline' | 'unbound'>('all');
  // Bot 状态：「已启用」用卡片徽标的判定（enabled && available），这样筛选结果与
  // 徽标永远一致；「未就绪」= 已启用但不可用（平台风控期间账户起不来的样子），
  // 与用户主动「已停用」是两回事，混在一起会误导排查。
  const [botFilter, setBotFilter] = useState<'all' | 'ready' | 'off' | 'notready'>('all');
  const [page, setPage] = useState(1);
  // 移动端默认折叠筛选胶囊：四组共 13 个，展开会占满整屏；桌面端不受影响
  const [filtersOpen, setFiltersOpen] = useState(false);
  /** 当前生效的筛选项数量（不含关键字搜索）—— 移动端折叠时用它提示"有筛选在生效" */
  const activeFilterCount =
    (statusFilter !== 'all' ? 1 : 0) +
    (modeFilter !== 'all' ? 1 : 0) +
    (liveFilter !== 'all' ? 1 : 0) +
    (botFilter !== 'all' ? 1 : 0);

  const load = useCallback(async () => {
    try {
      const data = await fetchPanelOverview();
      setOverview(data);
    } catch (e: any) {
      // 401 由 client 统一处理;其他错误静默,保留旧数据
      if (e.status !== 401) showToast('error', '加载失败', e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const handleCreate = async (data: AccountCreateRequest) => {
    setCreating(true);
    try {
      const acc = await createAccount(data);
      showToast('success', `账户「${acc.name}」已创建`, '');
      setCreateOpen(false);
      load();
    } catch (e: any) {
      showToast('error', '创建失败', e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleRenew = async (id: number, data: RenewRequest) => {
    setRenewing(true);
    try {
      await renewAccount(id, data);
      showToast('success', '续期成功', '');
      setRenewTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '续期失败', e.message);
    } finally {
      setRenewing(false);
    }
  };

  const handleRedeem = async (id: number, code: string) => {
    setRenewing(true);
    try {
      await redeemAccount(id, code);
      showToast('success', '兑换成功', '');
      setRenewTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '兑换失败', e.message);
    } finally {
      setRenewing(false);
    }
  };

  const handleExpire = async (id: number) => {
    setRenewing(true);
    try {
      await expireAccount(id);
      showToast('success', '已设为过期停用', '');
      setRenewTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '设置失败', e.message);
    } finally {
      setRenewing(false);
    }
  };

  /**
   * 执行已确认的运行时开关。
   *
   * 走的是「启用 / 停用」而不是「进入 / 退出」：停用会断开连接并落盘，
   * Bot 重启后不会自动连回来 —— 与账户详情页的语义保持一致。
   */
  const runRuntimeIntent = async () => {
    if (!runtimeTarget) return;
    const it = runtimeIntent(runtimeTarget.acc, runtimeTarget.kind);
    setRuntimeBusy(true);
    try {
      await it.run();
      showToast('success', it.done, '');
      setRuntimeTarget(null);
      load();
    } catch (e: any) {
      // 失败时保留确认框:目标状态没变，用户可重试或取消
      showToast('error', '操作失败', e.message);
    } finally {
      setRuntimeBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteAccount(deleteTarget.id, false);
      showToast('success', `账户「${deleteTarget.name}」已删除`, '');
      setDeleteTarget(null);
      load();
    } catch (e: any) {
      showToast('error', '删除失败', e.message);
    } finally {
      setDeleting(false);
    }
  };

  const accounts = overview?.accounts ?? [];
  const runtimeIt = runtimeTarget ? runtimeIntent(runtimeTarget.acc, runtimeTarget.kind) : null;
  /** 公有模式但面板没配公共 Cookie —— 该模式下 Bot 根本起不来，属于配置异常 */
  const publicCookieMissing = !(overview?.public_bot_configured ?? true);
  const isBrokenMode = (a: AccountSummary) => a.bot_public && publicCookieMissing;
  const isExpiring = (a: AccountSummary) =>
    !a.expired && a.days_left != null && a.days_left <= EXPIRING_SOON_DAYS;

  // ⚠️ 状态这组不是三分：**「即将过期」是「正常」的子集** —— 快到期但还没过期的
  // 账户本来就是正常账户，硬把它从「正常」里摘出去是错的。
  // 所以正常 + 即将过期 + 已过期 ≠ 总数，这是有意为之，不是计数 bug。
  const expiredCount = accounts.filter((a) => a.expired).length;
  const expiringCount = accounts.filter(isExpiring).length;
  const normalCount = accounts.length - expiredCount;
  const publicCount = accounts.filter((a) => a.bot_public).length;
  const brokenModeCount = accounts.filter(isBrokenMode).length;
  const privateCount = accounts.length - publicCount;
  const liveCount = accounts.filter((a) => a.room_streaming).length;
  const unboundCount = accounts.filter((a) => a.room_id == null).length;
  const offlineCount = accounts.length - liveCount - unboundCount;
  const botReadyCount = accounts.filter((a) => a.bot_enabled && a.bot_available).length;
  const botNotReadyCount = accounts.filter((a) => a.bot_enabled && !a.bot_available).length;
  const botOffCount = accounts.filter((a) => !a.bot_enabled).length;

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return accounts.filter((a) => {
      // 判定口径与卡片上的徽标一致，不会出现「筛出来却在卡片上看着是另一回事」
      // 的矛盾。注意状态这组的「正常」**包含**「即将过期」—— 后者只是个提醒性的
      // 细分，不是与「正常」并列的第三态。
      if (statusFilter === 'normal' && a.expired) return false;
      if (statusFilter === 'expiring' && !isExpiring(a)) return false;
      if (statusFilter === 'expired' && !a.expired) return false;
      if (modeFilter === 'public' && !a.bot_public) return false;
      if (modeFilter === 'private' && a.bot_public) return false;
      if (modeFilter === 'broken' && !isBrokenMode(a)) return false;
      // 开播：未绑定的账户压根没有直播间，与「已绑定但没开播」是两回事
      if (liveFilter === 'live' && !a.room_streaming) return false;
      if (liveFilter === 'offline' && !(a.room_id != null && !a.room_streaming)) return false;
      if (liveFilter === 'unbound' && a.room_id != null) return false;
      if (botFilter === 'ready' && !(a.bot_enabled && a.bot_available)) return false;
      if (botFilter === 'notready' && !(a.bot_enabled && !a.bot_available)) return false;
      if (botFilter === 'off' && a.bot_enabled) return false;
      if (!kw) return true;
      // 命中范围：直播间名称 / 登录用户名 / 主播名 / 直播间简介 / 主播简介，
      // 外加账户名、Bot 名、房间 ID 与**账户编号** —— 管理端多半只记得住其中某一片段。
      // 编号写成 `#12` 而非 `12`：前者同时能命中「#12」与「12」两种输入，
      // 后者只沾得上不带井号的写法
      return [
        a.name, a.username,
        a.room_name, a.room_description, a.creator_name, a.creator_intro,
        a.bot_name, a.room_id == null ? '' : String(a.room_id),
        `#${a.id}`,
      ].some((s) => (s || '').toLowerCase().includes(kw));
    });
  }, [accounts, keyword, statusFilter, modeFilter, liveFilter, botFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / ACCOUNTS_PER_PAGE));
  // 筛选后页码可能越界（比如在第 5 页时把条件收窄到只剩 1 页），夹回有效范围
  const safePage = Math.min(page, pageCount);
  const paged = filtered.slice((safePage - 1) * ACCOUNTS_PER_PAGE, safePage * ACCOUNTS_PER_PAGE);

  // 改筛选条件就回到第一页，否则会停在一个空的页码上
  useEffect(() => { setPage(1); }, [keyword, statusFilter, modeFilter, liveFilter, botFilter]);

  /**
   * 默认用户名 `user_{账户总数 + 1}`。
   *
   * 用**总数**而不是账户 id：id 是单调递增的计数器，删过账户就会跳号，
   * 于是 3 个账户可能默认出 user_7，看着莫名其妙。
   * 顺带跳过已占用的名字 —— 删掉中间某个账户后，总数+1 可能正好撞上现存的用户名，
   * 那样一打开弹窗就是个注定失败的默认值。
   */
  const defaultUsername = useMemo(() => {
    const taken = new Set(accounts.map((a) => a.username).filter(Boolean));
    let n = accounts.length + 1;
    while (taken.has(`user_${n}`)) n += 1;
    return `user_${n}`;
  }, [accounts]);

  /**
   * 编号是否存在空号（如 #25 的下一个直接是 #27）。
   * 只有真的有空号才显示「重排编号」入口 —— 编号本就连续时那个按钮纯属噪音。
   */
  const hasIdGaps = useMemo(() => {
    const ids = accounts.map((a) => a.id).sort((x, y) => x - y);
    return ids.some((id, i) => id !== i + 1);
  }, [accounts]);

  /** 拉一次 dry-run 映射并弹出确认框 */
  const startRenumber = async () => {
    try {
      const plan = await renumberAccounts(true);
      if (!plan.changed) {
        showToast('success', '账户编号已经是连续的，无需重排');
        return;
      }
      setRenumberPlan(plan);
    } catch (e: any) {
      showToast('error', '获取重排方案失败', e.message);
    }
  };

  const confirmRenumber = async () => {
    setRenumberBusy(true);
    try {
      const res = await renumberAccounts(false);
      showToast('success', `已重排 ${res.changed} 个账户的编号`);
      setRenumberPlan(null);
      await load();
    } catch (e: any) {
      showToast('error', '重排失败', e.message);
    } finally {
      setRenumberBusy(false);
    }
  };

  if (loading && !overview) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-7xl">
      {/* 上面用 max-w-7xl 而非 6xl：四组筛选要在桌面端排进同一行，合计宽度已接近
          1152px，六档只剩二十几像素余量 —— 字体度量稍有出入就会翻到第二行。
          放到七档留出约 150px，请求才真正被保证（卡片会相应略宽一点） */}

      {/* 头部(移动端可换行) */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold">账户总览</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            每个账户对应一个直播间与一个 Bot
            {overview && ` · ${overview.total} 个账户 · ${overview.expired_count} 个已过期`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" icon={<CalendarPlus className="w-4 h-4" />}
            onClick={() => setCompensateOpen(true)}>
            批量补偿
          </Button>
          {/* 只在真的有空号时才出现 */}
          {hasIdGaps && (
            <Button variant="secondary" icon={<ListOrdered className="w-4 h-4" />}
              onClick={startRenumber}
              title="账户编号存在断号（如 #25 之后是 #27），可压紧为连续编号">
              重排编号
            </Button>
          )}
          <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
            创建账户
          </Button>
        </div>
      </div>

      {/* 公共 Bot 提示 */}
      {overview && !overview.public_bot_configured && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          面板公共 Cookie 尚未配置 —— 使用公共 Bot 的账户将无法工作,请前往
          <button className="underline font-medium" onClick={() => navigate('/settings')}>设置</button>
          配置。
        </div>
      )}

      {/* 筛选 —— 不设显示门槛：之前按「账户少于 6 个就藏起来」做过，
          结果小规模用户根本看不到这个功能，等于没做 */}
      {accounts.length > 0 && (
        <div className="space-y-2">
          <SearchInput value={keyword} onChange={setKeyword}
            placeholder="搜索账户名 / 用户名 / 直播间 / 房间 ID / 编号 #12…" />

          {/* 移动端：折叠开关。四组筛选在窄屏上展开会占满整屏，
              折叠后用一个按钮 + 生效数量提示，桌面端（md 起）始终展开、看不到这个按钮 */}
          <div className="flex items-center gap-2 md:hidden">
            <FilterToggle
              open={filtersOpen}
              count={activeFilterCount}
              onToggle={() => setFiltersOpen((v) => !v)}
            />
            {activeFilterCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  setStatusFilter('all'); setModeFilter('all');
                  setLiveFilter('all'); setBotFilter('all');
                }}
                className="inline-flex items-center gap-1 min-h-9 px-2 text-xs text-gray-500 dark:text-gray-400
                  active:text-gray-700 dark:active:text-gray-200"
              >
                <X className="w-3.5 h-3.5" />
                清除
              </button>
            )}
          </div>

          {/* 展开时移动端竖排（每组独占一行；组内过宽由 FilterChips 自己的 flex-wrap
              换行，不会横向溢出），桌面端维持原本的换行排布 */}
          <div
            className={`${filtersOpen ? 'flex' : 'hidden'} md:flex
              flex-col md:flex-row md:flex-wrap items-stretch md:items-center gap-2
              md:gap-2`}
          >
            <FilterChips
              options={[
                { id: 'all', label: '全部', count: accounts.length },
                { id: 'normal', label: '正常', count: normalCount },
                { id: 'expiring', label: '即将过期', count: expiringCount },
                { id: 'expired', label: '已过期', count: expiredCount },
              ] as const}
              value={statusFilter} onChange={setStatusFilter} block />
            <FilterChips
              options={[
                { id: 'all', label: '全部 Bot' },
                { id: 'public', label: '公有', count: publicCount },
                { id: 'private', label: '私有', count: privateCount },
                { id: 'broken', label: '异常', count: brokenModeCount },
              ] as const}
              value={modeFilter} onChange={setModeFilter} block />
            <FilterChips
              options={[
                { id: 'all', label: '全部开播' },
                { id: 'live', label: '已开播', count: liveCount },
                { id: 'offline', label: '未开播', count: offlineCount },
                { id: 'unbound', label: '未绑定', count: unboundCount },
              ] as const}
              value={liveFilter} onChange={setLiveFilter} block />
            <FilterChips
              options={[
                { id: 'all', label: '全部状态' },
                { id: 'ready', label: '已启用', count: botReadyCount },
                { id: 'off', label: '已停用', count: botOffCount },
                { id: 'notready', label: '未就绪', count: botNotReadyCount },
              ] as const}
              value={botFilter} onChange={setBotFilter} block />
          </div>
        </div>
      )}

      {/* 账户卡片 */}
      {accounts.length === 0 ? (
        <div className="card">
          <div className="card-body flex flex-col items-center justify-center py-16 text-center">
            <p className="text-gray-500 dark:text-gray-400">暂无账户</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
              点击右上角「创建账户」开始
            </p>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card">
          <div className="card-body flex flex-col items-center justify-center py-16 text-center">
            <p className="text-gray-500 dark:text-gray-400">没有符合条件的账户</p>
            <button type="button"
              className="text-sm text-primary-600 dark:text-primary-400 hover:underline mt-2"
              onClick={() => { setKeyword(''); setStatusFilter('all'); setModeFilter('all'); }}>
              清除筛选条件
            </button>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {paged.map((acc) => (
            <div key={acc.id}
              className="card hover:shadow-lg transition-shadow relative group/card">
              {/* 账户编号放右上角：与标题分开，既不挤占标题宽度，也方便和搜索里
                  输入的「#12」对上。pointer-events-none —— 卡片整卡可点，
                  这个纯标签不该在角落里挡掉一块点击热区 */}
              <span className="absolute top-3 right-4 pointer-events-none select-none
                               font-mono text-xs text-gray-400 dark:text-gray-500">
                #{acc.id}
              </span>
              <div className="card-header">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    {/* 拉伸链接：标题是真实 <a>，其 ::after 覆盖整张卡片，
                        从而「整卡可点」且保留键盘可达 / 中键新标签页打开 */}
                    <h3 className="font-semibold truncate">
                      <Link
                        to={`/account/${acc.id}`}
                        className="rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-800 after:absolute after:inset-0"
                      >
                        {acc.name}
                      </Link>
                    </h3>
                    <span className={
                      'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ' +
                      (acc.bot_public
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                        : 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300')
                    }>
                      {acc.bot_public ? '公共 Bot' : '私有 Bot'}
                    </span>
                  </div>
                  {acc.username && (
                    <p className="text-xs text-gray-400 truncate" title={`登录用户名: ${acc.username}`}>
                      @{acc.username}
                    </p>
                  )}
                </div>
                <ExpiryBadge expiresAt={acc.expires_at} pausedReason={acc.paused_reason} />
              </div>
              <div className="card-body space-y-3">
                {/* 状态行 */}
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                    <BotIcon className="w-4 h-4" />
                    {acc.bot_name || (acc.bot_available ? '已连接' : '未配置')}
                  </div>
                  <div className="flex justify-end">
                    <StatusBadge status={acc.bot_enabled && acc.bot_available ? 'enabled' : 'disabled'} label="Bot" />
                  </div>
                  <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300 min-w-0">
                    <Radio className="w-4 h-4 shrink-0" />
                    <span className="min-w-0 break-words sm:truncate">{acc.room_name || (acc.room_id ? `房间 ${acc.room_id}` : '未绑定房间')}</span>
                    {/* 外链要 relative z-10：卡片标题用 after:inset-0 铺了整卡点击层，
                        不抬高层级的话这个链接会被那层盖住，点了会进账户页 */}
                    {acc.room_id != null && (
                      <a href={livePageUrl(acc.room_id)} target="_blank" rel="noopener noreferrer"
                        title={`在猫耳打开直播间 ${acc.room_id}`}
                        aria-label="打开直播间"
                        className="relative z-10 shrink-0 p-2.5 -m-2 rounded text-gray-400 hover:text-primary-600
                                   dark:text-gray-500 dark:hover:text-primary-400 transition-colors">
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                  <div className="flex justify-end items-center gap-1.5">
                    {/* 开播状态与「已连接」是两件事：连着但没开播是常态 */}
                    {acc.room_id != null && (
                      <StatusBadge
                        status={acc.room_streaming ? 'online' : 'offline'}
                        label={acc.room_streaming ? '开播中' : '未开播'} />
                    )}
                    <StatusBadge status={acc.room_connected ? 'online' : 'offline'} label={acc.room_connected ? '已连接' : '未连接'} />
                  </div>
                </div>
                {/* 统计 */}
                <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                  <span className="flex items-center gap-1"><Puzzle className="w-3.5 h-3.5" />插件 {acc.enabled_plugin_count}/{acc.plugin_count}</span>
                  <span className="flex items-center gap-1" title="面板添加的普通定时消息数">
                    <Clock className="w-3.5 h-3.5" />普通 {acc.normal_timer_message_count}
                  </span>
                  <span className="flex items-center gap-1" title="插件注册的定时消息数">
                    <Hourglass className="w-3.5 h-3.5" />插件定时 {acc.plugin_timer_message_count}
                  </span>
                </div>
                {acc.resume_error && (
                  <p className="text-xs text-red-600 dark:text-red-400 truncate" title={acc.resume_error}>
                    {acc.resume_error}
                  </p>
                )}
                {/* 操作 —— 允许换行:窄屏下按钮行落到第二行,不会挤扁「进入管理」 */}
                <div className="flex flex-wrap items-center gap-y-1 pt-1 border-t border-gray-100 dark:border-gray-700">
                  {/* 纯视觉锚点，不接收点击——整卡点击由标题的拉伸链接承担 */}
                  <span
                    aria-hidden="true"
                    className="text-sm font-medium text-gray-400 dark:text-gray-500 transition-colors group-hover/card:text-primary-600 dark:group-hover/card:text-primary-400"
                  >
                    进入管理 →
                  </span>
                  {/* z-10 把图标行抬到拉伸链接的覆盖层之上，避免点操作按钮时连带跳转 */}
                  <div className="relative z-10 ml-auto flex flex-wrap justify-end gap-1">
                    {/* 运行时快捷开关 —— 图标表示「点下去会发生什么」，与按钮状态一致。
                        两种情况都会改变线上行为，故一律先弹确认框再执行 */}
                    <Button variant="ghost" size="sm"
                      icon={acc.bot_enabled
                        ? <CircleStop className="w-4 h-4" />
                        : <CirclePlay className="w-4 h-4" />}
                      tooltip={acc.bot_enabled ? '停止 Bot' : '启动 Bot'}
                      onClick={() => setRuntimeTarget({ acc, kind: 'bot' })} />
                    {acc.room_id != null && (
                      <Button variant="ghost" size="sm"
                        icon={acc.room_enabled
                          ? <Unplug className="w-4 h-4" />
                          : <Plug className="w-4 h-4" />}
                        tooltip={acc.room_enabled ? '断开直播间' : '连接直播间'}
                        onClick={() => setRuntimeTarget({ acc, kind: 'live' })} />
                    )}
                    {/* 剩余天数 / 续期 / 兑换授权码 / 设为永久 / 设为停用 全在同一个对话框里，
                        卡片上只留这一个入口 —— 几项可在弹窗顶部切换，不必每项一个按钮 */}
                    <Button variant="ghost" size="sm" icon={<CalendarCog className="w-4 h-4" />}
                      tooltip="时长管理"
                      onClick={() => { setRenewMode('set'); setRenewTarget(acc); }} />
                    <Button variant="ghost" size="sm" icon={<Lock className="w-4 h-4" />}
                      tooltip="重置登录凭据" onClick={() => setCredTarget(acc)} />
                    <Button variant="ghost" size="sm" icon={<Trash2 className="w-4 h-4 text-red-500" />}
                      tooltip="删除账户" onClick={() => setDeleteTarget(acc)} />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {filtered.length > 0 && (
        <Pagination page={safePage} pageCount={pageCount} total={filtered.length}
          onChange={setPage} />
      )}

      <CreateAccountDialog
        open={createOpen}
        loading={creating}
        onConfirm={handleCreate}
        onCancel={() => setCreateOpen(false)}
        defaultUsername={defaultUsername}
      />
      <CompensateDialog
        open={compensateOpen}
        accounts={overview?.accounts ?? []}
        onClose={() => setCompensateOpen(false)}
        onDone={load}
      />
      <RenewDialog
        open={renewTarget !== null}
        accountId={renewTarget?.id ?? 0}
        accountName={renewTarget?.name ?? ''}
        mode={renewMode}
        loading={renewing}
        onRenew={handleRenew}
        onExpire={handleExpire}
        onRedeem={handleRedeem}
        onCancel={() => setRenewTarget(null)}
      />
      <CredentialsDialog
        open={credTarget !== null}
        accountName={credTarget?.name ?? ''}
        currentUsername={credTarget?.username ?? ''}
        loading={credBusy}
        onConfirm={async (username, password) => {
          if (!credTarget) return;
          setCredBusy(true);
          try {
            await resetAccountCredentials(credTarget.id, username, password);
            showToast('success', `账户「${credTarget.name}」登录凭据已重置`, '');
            setCredTarget(null);
            load();
          } catch (e: any) {
            showToast('error', '重置失败', e.message);
          } finally { setCredBusy(false); }
        }}
        onCancel={() => setCredTarget(null)}
      />

      {/* Bot 启停 / 直播间连断的二次确认 —— 停用方向标红，因为会中断正在运行的服务 */}
      <ConfirmDialog
        open={runtimeIt !== null}
        title={runtimeIt?.title ?? ''}
        message={runtimeIt?.message ?? ''}
        confirmLabel={runtimeIt?.confirmLabel ?? '确定'}
        variant={runtimeIt?.on ? 'danger' : 'default'}
        loading={runtimeBusy}
        onConfirm={runRuntimeIntent}
        onCancel={() => setRuntimeTarget(null)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除账户"
        message={`确定要删除账户「${deleteTarget?.name ?? ''}」吗？运行时数据目录将保留(可恢复)。`}
        danger
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={renumberPlan !== null}
        title="重排账户编号"
        message={`将把 ${renumberPlan?.changed ?? 0} 个账户的编号压紧，去掉中间的空号。`
          + '账户名称、直播间、Cookie、插件配置都不会变，但登录凭据会随编号更新；'
          + '重排过程会重启全部账户，期间面板短暂不可用。'}
        confirmLabel="确认重排"
        variant="warning"
        loading={renumberBusy}
        onConfirm={confirmRenumber}
        onCancel={() => setRenumberPlan(null)}
      >
        <div className="mt-3 max-h-56 overflow-auto rounded border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-800">
          {Object.entries(renumberPlan?.mapping ?? {}).map(([oldId, newId]) => {
            const acc = accounts.find((a) => a.id === Number(oldId));
            return (
              <div key={oldId} className="flex items-center gap-2 px-3 py-1.5 text-xs">
                <span className="font-mono text-gray-400">#{oldId}</span>
                <span className="text-gray-400">→</span>
                <span className="font-mono font-semibold text-primary-600 dark:text-primary-400">
                  #{newId}
                </span>
                {acc?.name && <span className="truncate text-gray-500">{acc.name}</span>}
              </div>
            );
          })}
        </div>
      </ConfirmDialog>
    </div>
  );
}
