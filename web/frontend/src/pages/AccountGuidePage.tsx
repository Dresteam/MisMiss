import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot as BotIcon, Radio, Puzzle, Clock, Loader2 } from 'lucide-react';
import { Button } from '../components/Button';
import { StatusBadge } from '../components/StatusBadge';
import { useAuth } from '../hooks/useAuth';

/** 模拟界面的分页 —— 与账户端真实标签页一一对应 */
type MockPage = 'overview' | 'live' | 'bot' | 'plugins' | 'library';

const MOCK_TABS: { key: MockPage; label: string }[] = [
  { key: 'overview', label: '概览' },
  { key: 'live', label: '直播间' },
  { key: 'bot', label: 'Bot' },
  { key: 'plugins', label: '插件' },
  { key: 'library', label: '插件库' },
];

/**
 * 漫游步骤。`page` 是这一步所在的模拟分页，`target` 对应元素的 `data-guide`。
 *
 * ⚠️ **改了步骤或文案，记得把后端的 `GUIDE_VERSION` 加一**
 * （`src/core/account/manager.py`）。账户记录里存的是「已读版本」，不升版本
 * 老用户不会再被跳进来 —— 改文案的人多半只翻到这一个文件，提醒写在这儿。
 */
const GUIDE_STEPS: { page: MockPage; target: string; title: string; body: string }[] = [
  { page: 'overview', target: 'ov-bot', title: '概览 · 账户状态', body: '进来先看这四张卡：Bot 是否启用、直播间连着没有、插件启用了几个、订阅还剩多少天。' },
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
 * 账户端「操作指引」—— 一页**模拟界面**（带分页）+ 蒙版逐步高亮。
 *
 * 之所以用模拟而非真实面板：列出的操作里有「兑换码续期」这类一旦真做就会
 * 消耗掉东西的动作，拿真实界面做演示不安全。这里的卡片与按钮全是摆设，
 * 点了不会发生任何事；漫游推进到下一步时，模拟界面会**自动切到对应的分页**。
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

  const cur = GUIDE_STEPS[step];
  const isLast = step === GUIDE_STEPS.length - 1;

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

  // 切到本步所在的模拟分页后再量目标 —— 用 layoutEffect 保证量的是渲染后的 DOM，
  // 否则跨页的那一步会量到上一页残留（或量到空）。
  useLayoutEffect(() => {
    const el = document.querySelector(`[data-guide="${cur.target}"]`);
    setRect(el ? el.getBoundingClientRect() : null);
  }, [step, cur.target]);

  // 位置随滚动 / 窗口尺寸变化，遮罩要跟着走
  useEffect(() => {
    const measure = () => {
      const el = document.querySelector(`[data-guide="${cur.target}"]`);
      setRect(el ? el.getBoundingClientRect() : null);
    };
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [cur.target]);

  // 换步后把页面滚回顶部，避免目标元素在视口外
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
            下面是一个<strong className="font-medium">模拟界面</strong>
            ，只作演示，期间不会真的执行任何操作。
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
            第 {step + 1} / {GUIDE_STEPS.length} 步
          </span>
          <Button variant="secondary" size="sm" onClick={finish}>跳过</Button>
        </div>
      </div>

      {/* ---------- 模拟界面：与账户端同款分页结构，内容全是摆设 ---------- */}
      <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-600">
        <div className="px-3 py-1.5 text-[11px] text-gray-400 dark:text-gray-500
                        border-b border-dashed border-gray-300 dark:border-gray-600">
          模拟界面 · 下方内容不会真实生效
        </div>

        {/* 分页条：跟随当前步骤自动切换 */}
        <div className="flex border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
          {MOCK_TABS.map((t) => (
            <span
              key={t.key}
              className={
                'flex-1 shrink-0 px-3 py-2.5 text-center text-sm font-medium border-b-2 -mb-px whitespace-nowrap ' +
                (t.key === cur.page
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-400 dark:text-gray-500')
              }
            >
              {t.label}
            </span>
          ))}
        </div>

        <div className="p-4 space-y-4 min-h-[16rem]">
          {cur.page === 'overview' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="card" data-guide="ov-bot">
                <div className="card-body">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <BotIcon className="w-4 h-4" /> Bot 状态
                    </span>
                    <StatusBadge status="enabled" label="已启用" />
                  </div>
                  <p className="mt-2 font-semibold text-lg truncate">示例 Bot</p>
                  <div className="mt-3" data-guide="ov-bot-toggle">
                    <Button size="sm" variant="secondary">停用 Bot</Button>
                  </div>
                </div>
              </div>
              <div className="card">
                <div className="card-body">
                  <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <Radio className="w-4 h-4" /> 直播间
                  </span>
                  <p className="mt-2 font-semibold text-lg truncate">示例直播间</p>
                  <p className="text-xs text-gray-400 mt-1">已绑定 · 已连接</p>
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
                    <Clock className="w-4 h-4" /> 订阅
                  </span>
                  <p className="mt-2 font-semibold text-lg">剩余 30 天</p>
                  <div className="mt-3">
                    <Button size="sm" variant="secondary">兑换授权码</Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {cur.page === 'live' && (
            <>
              <div className="card" data-guide="lv-bind">
                <div className="card-header"><h3 className="font-semibold">绑定直播间</h3></div>
                <div className="card-body space-y-3">
                  <div className="h-9 rounded-lg border border-gray-300 dark:border-gray-600
                                  px-3 flex items-center text-sm text-gray-400 dark:text-gray-500">
                    直播间 ID 或链接
                  </div>
                  <Button size="sm" variant="secondary">绑定</Button>
                </div>
              </div>
              <div className="card" data-guide="lv-control">
                <div className="card-header"><h3 className="font-semibold">连接控制</h3></div>
                <div className="card-body flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary">连接直播间</Button>
                  <Button size="sm" variant="ghost">断开</Button>
                </div>
              </div>
            </>
          )}

          {cur.page === 'bot' && (
            <div className="card" data-guide="bt-cookie">
              <div className="card-header"><h3 className="font-semibold">Cookie</h3></div>
              <div className="card-body space-y-2 text-sm">
                <p className="text-gray-600 dark:text-gray-300">私有 Cookie · 有效</p>
                <p className="text-xs text-gray-400">用面板给的书签脚本一键取回新 Cookie</p>
                <div className="pt-1"><Button size="sm" variant="secondary">更换 Cookie</Button></div>
              </div>
            </div>
          )}

          {cur.page === 'plugins' && (
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

          {cur.page === 'library' && (
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

      {/* ---------- 蒙版 + 提示卡 ---------- */}
      {hole && (
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
      )}

      {/* 空闲提示：目标还没量出来时（首帧）告诉用户下面可以点 */}
      {!hole && (
        <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" /> 正在载入演示…
        </p>
      )}
    </div>
  );
}
