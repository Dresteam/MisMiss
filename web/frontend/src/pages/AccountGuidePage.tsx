import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot as BotIcon, Radio, Puzzle, Clock, LayoutDashboard, KeyRound, Loader2,
} from 'lucide-react';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../hooks/useAuth';

/** 模拟界面的分页 —— 与账户端左侧导航一一对应 */
type DemoPage = 'overview' | 'live' | 'bot' | 'timer' | 'plugins' | 'library';

const DEMO_NAV: { key: DemoPage; label: string; icon: React.ReactNode }[] = [
  { key: 'overview', label: '概览', icon: <LayoutDashboard className="w-4 h-4" /> },
  { key: 'live', label: '直播间', icon: <Radio className="w-4 h-4" /> },
  { key: 'bot', label: 'Bot', icon: <BotIcon className="w-4 h-4" /> },
  { key: 'timer', label: '定时消息', icon: <Clock className="w-4 h-4" /> },
  { key: 'plugins', label: '插件', icon: <Puzzle className="w-4 h-4" /> },
  { key: 'library', label: '插件库', icon: <Puzzle className="w-4 h-4" /> },
];

/**
 * 漫游步骤：`page` 是这一步所在的模拟分页，`target` 对应元素的 `data-guide`。
 *
 * ⚠️ **改了步骤或文案，记得把后端的 `GUIDE_VERSION` 加一**
 * （`src/core/account/manager.py`）。账户记录里存的是「已读版本」，不升版本
 * 老用户不会再被跳进来 —— 改文案的人多半只翻到这一个文件，提醒写在这儿。
 */
const GUIDE_STEPS: { page: DemoPage; target: string; title: string; body: string }[] = [
  { page: 'overview', target: 'ov-bot', title: '概览 · 账户状态', body: '进来先看这几张卡：Bot 是否启用、直播间连着没有、插件启用了几个、订阅还剩多少天。' },
  { page: 'overview', target: 'ov-bot-toggle', title: '启用 / 停用 Bot', body: '停用后这个账户的机器人整体停工 —— 定时消息与插件推送都会停。临时不想让它发言时用它。' },
  { page: 'overview', target: 'ov-redeem', title: '兑换码续期', body: '订阅快到期时点这里输入授权码；永久账户不需要续期。' },
  { page: 'live', target: 'lv-bind', title: '绑定直播间', body: '填入直播间 ID 或粘贴直播间链接即可绑定；已绑定的可以在这里换绑。' },
  { page: 'live', target: 'lv-control', title: '连接 / 断开直播间', body: '绑定只是「知道是哪个房间」，还要连接才会真正接收弹幕与礼物。不看了就断开。' },
  { page: 'bot', target: 'bt-cookie', title: '更换 Cookie', body: '私有模式下 Cookie 过期会连不上。用面板给的书签脚本一键取回新 Cookie，不用再找管理员。' },
  { page: 'plugins', target: 'pg-list', title: '插件管理', body: '启用 / 停用、改配置、设权限都在这里。每个插件的配置项由插件自己声明。' },
  { page: 'plugins', target: 'pg-page', title: '插件主页', body: '带「插件主页」标记的插件有自己的独立界面（比如点歌、抽签），点卡片即可进入。' },
  { page: 'library', target: 'lb-list', title: '插件库', body: '面板统一维护的插件来源。库里有新版本时插件页会提示，也可以一键更新全部。' },
];

/**
 * 账户端「操作指引」—— 模拟界面 + 左侧导航切换 + 蒙版逐步高亮。
 *
 * **全套都是本页的局部状态**：左侧导航、各页内容、按钮点击，都只改本组件的
 * state，不发任何请求、碰不到真实账户。每次进入都从初始状态开始（组件重新
 * 挂载即重置），所以过程中怎么点都没关系 —— 尤其是「兑换码续期」这类一旦
 * 真做就会消耗掉东西的动作，拿真实界面演示是不安全的。
 *
 * 首次登录由 App 导到这里（见 useAuth 的 showGuide）；**只有点「跳过」或
 * 「完成」才算读过**，从侧栏溜走不算，下次进来仍会跳。
 */
export function AccountGuidePage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const acked = useRef(false);

  // ---- 演示用的局部状态：全部随组件挂载重建，退出即丢弃 ----
  const [botOn, setBotOn] = useState(true);
  const [bound, setBound] = useState(false);
  const [connected, setConnected] = useState(false);

  const cur = GUIDE_STEPS[step];
  const isLast = step === GUIDE_STEPS.length - 1;
  const demoPage = cur.page;

  const ack = useCallback(() => {
    if (acked.current || !auth.token) return;
    acked.current = true;
    // 上报失败不重试：下次再跳一次也无伤大雅，比在这里维护重试队列划算
    fetch('/api/auth/ack-guide', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + auth.token },
    }).catch(() => { /* ignore */ });
    auth.clearShowGuide();
  }, [auth]);

  const finish = useCallback(() => {
    ack();
    navigate('/account/home');
  }, [ack, navigate]);

  const measure = useCallback(() => {
    const el = document.querySelector(`[data-guide="${cur.target}"]`);
    setRect(el ? el.getBoundingClientRect() : null);
  }, [cur.target]);

  // 切到本步所在分页后再量 —— layoutEffect 保证量的是渲染后的 DOM，
  // 否则跨页那一步会量到上一页的残留坐标（或量到空，蒙版直接不出现）
  useLayoutEffect(() => { measure(); }, [measure, step]);

  useEffect(() => {
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [measure]);

  useEffect(() => { window.scrollTo({ top: 0 }); }, [step]);

  const PAD = 6;
  const TIP_W = 340;
  const vh = typeof window === 'undefined' ? 0 : window.innerHeight;
  const vw = typeof window === 'undefined' ? 0 : window.innerWidth;
  const hole = rect && {
    left: rect.left - PAD, top: rect.top - PAD,
    width: rect.width + PAD * 2, height: rect.height + PAD * 2,
  };
  const tipTop = hole ? hole.top + hole.height + 10 : 0;
  const flipUp = hole ? tipTop + 190 > vh : false;
  const tipLeft = hole ? Math.min(Math.max(hole.left, 8), Math.max(8, vw - 8 - TIP_W)) : 8;

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">操作指引</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            下面是<strong className="font-medium">模拟界面</strong>，怎么点都不会
            影响你的账户；每次进来都会重置。
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            第 {step + 1} / {GUIDE_STEPS.length} 步
          </span>
          <Button variant="secondary" size="sm" onClick={finish}>跳过</Button>
        </div>
      </div>

      {/* ---------- 模拟外壳：左侧导航 + 右侧内容，与账户端同款布局 ---------- */}
      <div className="rounded-xl border-2 border-dashed border-amber-300 dark:border-amber-700/60
                      overflow-hidden bg-white dark:bg-gray-800">
        <div className="px-3 py-1.5 text-[11px] text-amber-700 dark:text-amber-500
                        bg-amber-50 dark:bg-amber-900/20
                        border-b border-dashed border-amber-300 dark:border-amber-700/60">
          模拟界面 · 这里的操作只改本页状态，不会影响你的账户，退出即重置
        </div>

        <div className="flex min-h-[22rem]">
          {/* 左栏导航 —— 点它切的是模拟分页，不是真路由 */}
          <nav className="w-32 sm:w-40 shrink-0 border-r border-gray-200 dark:border-gray-700
                          p-2 space-y-0.5 bg-gray-50 dark:bg-gray-900/40">
            {DEMO_NAV.map((n) => (
              <span key={n.key}
                className={
                  'flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm ' +
                  (n.key === demoPage
                    ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
                    : 'text-gray-500 dark:text-gray-400')
                }>
                {n.icon}
                <span className="truncate">{n.label}</span>
              </span>
            ))}
          </nav>

          {/* 右栏内容 */}
          <div className="flex-1 min-w-0 p-4 space-y-4">
            {demoPage === 'overview' && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="card" data-guide="ov-bot">
                  <div className="card-body">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                        <BotIcon className="w-4 h-4" /> Bot 状态
                      </span>
                      <StatusBadge status={botOn ? 'enabled' : 'disabled'}
                        label={botOn ? '已启用' : '已停用'} />
                    </div>
                    <p className="mt-2 font-semibold text-lg truncate">示例 Bot</p>
                    <div className="mt-3" data-guide="ov-bot-toggle">
                      {/* 只改本地状态，不发请求 */}
                      <Button size="sm" variant="secondary" onClick={() => setBotOn((v) => !v)}>
                        {botOn ? '停用 Bot' : '启用 Bot'}
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="card">
                  <div className="card-body">
                    <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <Radio className="w-4 h-4" /> 直播间
                    </span>
                    <p className="mt-2 font-semibold text-lg truncate">
                      {bound ? '示例直播间' : '未绑定'}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {bound ? (connected ? '已连接' : '已绑定 · 未连接') : '尚未绑定直播间'}
                    </p>
                  </div>
                </div>

                <div className="card">
                  <div className="card-body">
                    <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <Puzzle className="w-4 h-4" /> 插件
                    </span>
                    <p className="mt-2 font-semibold text-lg">6 启用</p>
                    <p className="text-xs text-gray-400 mt-1">共 10 个插件</p>
                  </div>
                </div>

                <div className="card" data-guide="ov-redeem">
                  <div className="card-body">
                    <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <KeyRound className="w-4 h-4" /> 订阅
                    </span>
                    <p className="mt-2 font-semibold text-lg">剩余 30 天</p>
                    <div className="mt-3">
                      <Button size="sm" variant="secondary">兑换授权码</Button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {demoPage === 'live' && (
              <>
                <div className="card" data-guide="lv-bind">
                  <div className="card-header"><h3 className="font-semibold">绑定直播间</h3></div>
                  <div className="card-body space-y-3">
                    <div className="h-9 rounded-lg border border-gray-300 dark:border-gray-600
                                    px-3 flex items-center text-sm text-gray-400 dark:text-gray-500">
                      直播间 ID 或链接
                    </div>
                    <Button size="sm" variant="secondary" onClick={() => setBound(true)}>
                      绑定
                    </Button>
                  </div>
                </div>
                <div className="card" data-guide="lv-control">
                  <div className="card-header"><h3 className="font-semibold">连接控制</h3></div>
                  <div className="card-body flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" disabled={!bound}
                      onClick={() => setConnected(true)}>
                      连接直播间
                    </Button>
                    <Button size="sm" variant="ghost" disabled={!connected}
                      onClick={() => setConnected(false)}>
                      断开
                    </Button>
                  </div>
                </div>
              </>
            )}

            {demoPage === 'bot' && (
              <div className="card" data-guide="bt-cookie">
                <div className="card-header"><h3 className="font-semibold">Cookie</h3></div>
                <div className="card-body space-y-2 text-sm">
                  <p className="text-gray-600 dark:text-gray-300">私有 Cookie · 有效</p>
                  <p className="text-xs text-gray-400">用面板给的书签脚本一键取回新 Cookie</p>
                  <div className="pt-1">
                    <Button size="sm" variant="secondary">更换 Cookie</Button>
                  </div>
                </div>
              </div>
            )}

            {demoPage === 'timer' && (
              <div className="card">
                <div className="card-header"><h3 className="font-semibold">定时消息</h3></div>
                <div className="card-body text-sm text-gray-600 dark:text-gray-300">
                  按间隔轮播的消息，可调整间隔、上下移动顺序、复制或删除。
                </div>
              </div>
            )}

            {demoPage === 'plugins' && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="card" data-guide="pg-list">
                  <div className="card-header flex items-center justify-between">
                    <h3 className="font-semibold">欢迎插件</h3>
                    <StatusBadge status="enabled" label="已启用" />
                  </div>
                  <div className="card-body text-xs text-gray-500 dark:text-gray-400">
                    新观众进入时发送欢迎语
                  </div>
                </div>
                <div className="card" data-guide="pg-page">
                  <div className="card-header flex items-center justify-between">
                    <h3 className="font-semibold">点歌</h3>
                    <span className="text-xs text-gray-400 dark:text-gray-500">↗ 插件主页</span>
                  </div>
                  <div className="card-body text-xs text-gray-500 dark:text-gray-400">
                    观众发「点歌 歌名」即可点播
                  </div>
                </div>
              </div>
            )}

            {demoPage === 'library' && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="card" data-guide="lb-list">
                  <div className="card-header flex items-center justify-between">
                    <h3 className="font-semibold">礼物答谢</h3>
                    <span className="text-xs text-gray-400 dark:text-gray-500">v1.3.6</span>
                  </div>
                  <div className="card-body text-xs text-gray-500 dark:text-gray-400">
                    收到礼物时自动致谢
                  </div>
                </div>
                <div className="card">
                  <div className="card-header flex items-center justify-between">
                    <h3 className="font-semibold">签到</h3>
                    <span className="text-xs text-gray-400 dark:text-gray-500">v1.0.2</span>
                  </div>
                  <div className="card-body text-xs text-gray-500 dark:text-gray-400">
                    观众每日签到
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ---------- 蒙版 + 提示卡 ---------- */}
      {hole ? (
        <>
          {/* 用超大 box-shadow 造「四周变暗、中间留洞」：比 clip-path 稳 */}
          <div
            className="fixed z-[90] rounded-lg ring-2 ring-primary-400 pointer-events-none
                       transition-all duration-200"
            style={{
              left: hole.left, top: hole.top, width: hole.width, height: hole.height,
              boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.55)',
            }}
          />
          <div
            className="fixed z-[95] rounded-xl shadow-2xl bg-white dark:bg-gray-800
                       border border-gray-200 dark:border-gray-700 p-4"
            style={{
              width: TIP_W, maxWidth: 'calc(100vw - 1rem)', left: tipLeft,
              ...(flipUp ? { bottom: vh - hole.top + 10 } : { top: tipTop }),
            }}
          >
            <p className="font-semibold text-sm text-gray-900 dark:text-white">{cur.title}</p>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{cur.body}</p>
            <div className="flex items-center justify-between mt-3 gap-2">
              <button
                onClick={finish}
                className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200
                           transition-colors shrink-0"
              >
                跳过指引
              </button>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" disabled={step === 0}
                  onClick={() => setStep((s) => s - 1)}>
                  上一步
                </Button>
                <Button variant="primary" size="sm"
                  onClick={() => (isLast ? finish() : setStep((s) => s + 1))}>
                  {isLast ? '完成' : '下一步'}
                </Button>
              </div>
            </div>
          </div>
        </>
      ) : (
        <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" /> 正在载入演示…
        </p>
      )}
    </div>
  );
}
