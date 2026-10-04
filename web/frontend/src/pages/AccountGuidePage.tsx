import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/Button';
import { useAuth } from '../hooks/useAuth';

/**
 * 漫游步骤：`target` 对应模拟界面里某个元素的 `data-guide` 值。
 *
 * ⚠️ **改了这里的步骤或文案，记得把后端的 `GUIDE_VERSION` 加一**
 * （`src/core/account/manager.py`）。账户记录里存的是「已读版本」，不升版本的话
 * 老用户不会再被跳进来 —— 而改文案的人多半只翻到这一个文件，所以提醒写在这儿。
 */
interface GuideStep {
  target: string;
  title: string;
  body: string;
}

const GUIDE_STEPS: GuideStep[] = [
  { target: 'overview', title: '概览', body: '先看清账户状态：Bot 是否启用、直播间连着没有、插件启用了几个、订阅还剩多少天。' },
  { target: 'live-bind', title: '绑定直播间', body: '直播间标签页里填入直播间 ID 或粘贴链接即可绑定；已绑定的可以在这里换绑。' },
  { target: 'live-connect', title: '连接 / 断开直播间', body: '绑定只是「知道是哪个房间」，还要连接才会真正接收弹幕与礼物。不看了就断开。' },
  { target: 'bot-toggle', title: '启用 / 停用 Bot', body: '停用后这个账户的机器人整体停工（定时消息、插件推送都会停）。临时不想让它发言时用它。' },
  { target: 'cookie', title: '更换 Cookie', body: '私有模式下 Cookie 过期会连不上。用面板给的书签脚本一键取回新 Cookie，不用再找管理员。' },
  { target: 'renew', title: '兑换码续期', body: '订阅快到期时在这里输入授权码续期；永久账户不需要续期。' },
  { target: 'plugins', title: '插件管理', body: '插件标签页里可以启用 / 停用、改配置、设权限。每个插件的配置项由插件自己声明。' },
  { target: 'plugin-page', title: '插件主页', body: '带「插件主页」标记的插件有自己的独立界面（比如点歌、抽签），点卡片即可进入。' },
  { target: 'library', title: '插件库', body: '面板统一维护的插件来源。库里有新版本时插件页会提示，也可以一键更新全部。' },
];

/**
 * 账户端「操作指引」—— 一页**模拟界面** + 蒙版逐步高亮。
 *
 * 之所以用模拟而非真实面板：列出的操作里有「兑换码续期」这类一旦真做就会
 * 消耗掉东西的动作，拿真实界面做演示不安全。这里的卡片与按钮全是摆设，
 * 点了不会发生任何事。
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

  // 量出目标元素在视口里的位置 —— 蒙版的「洞」就开在这里。
  // 用 fixed + 视口坐标定位，所以滚动与窗口尺寸变化都要重量。
  useEffect(() => {
    const measure = () => {
      const el = document.querySelector(`[data-guide="${GUIDE_STEPS[step].target}"]`);
      setRect(el ? el.getBoundingClientRect() : null);
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [step]);

  // 目标元素滚出视口时把提示卡钉在底部，免得跟着飘出屏幕
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'smooth' }); }, [step]);

  const PAD = 6;
  const TIP_W = 352;
  const hole = rect && {
    left: rect.left - PAD,
    top: rect.top - PAD,
    width: rect.width + PAD * 2,
    height: rect.height + PAD * 2,
  };
  const vh = typeof window === 'undefined' ? 0 : window.innerHeight;
  const vw = typeof window === 'undefined' ? 0 : window.innerWidth;
  const tipTop = hole ? hole.top + hole.height + 10 : 0;
  const flipUp = hole ? tipTop + 190 > vh : false;
  const tipLeft = hole
    ? Math.min(Math.max(hole.left, 8), Math.max(8, vw - 8 - TIP_W))
    : 8;

  return (
    <div className="space-y-5 animate-fade-in max-w-3xl">
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

      {/* ---------- 模拟界面：内容全是摆样式用的，不会触发任何操作 ---------- */}
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="card" data-guide="overview">
            <div className="card-header"><h3 className="font-semibold">Bot</h3></div>
            <div className="card-body space-y-1 text-sm">
              <p className="text-gray-600 dark:text-gray-300">示例 Bot · 私有 Cookie</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">已启用</p>
            </div>
          </div>
          <div className="card" data-guide="cookie">
            <div className="card-header"><h3 className="font-semibold">Cookie 状态</h3></div>
            <div className="card-body space-y-1 text-sm">
              <p className="text-gray-600 dark:text-gray-300">私有 Cookie · 有效</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                用书签脚本一键换新，不用找管理员
              </p>
            </div>
          </div>
        </div>

        <div className="card" data-guide="live-bind">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold">直播间</h3>
            <span className="text-xs text-gray-400 dark:text-gray-500">未绑定</span>
          </div>
          <div className="card-body text-sm text-gray-600 dark:text-gray-300">
            填入直播间 ID 或粘贴直播间链接即可绑定，已绑定的可换绑。
          </div>
        </div>

        <div className="card" data-guide="live-connect">
          <div className="card-header"><h3 className="font-semibold">连接控制</h3></div>
          <div className="card-body flex flex-wrap gap-2">
            <Button variant="secondary" size="sm">连接直播间</Button>
            <Button variant="ghost" size="sm">断开</Button>
          </div>
        </div>

        <div className="card" data-guide="bot-toggle">
          <div className="card-header"><h3 className="font-semibold">Bot 启停</h3></div>
          <div className="card-body flex flex-wrap gap-2">
            <Button variant="secondary" size="sm">启用 Bot</Button>
            <Button variant="ghost" size="sm">停用</Button>
          </div>
        </div>

        <div className="card" data-guide="renew">
          <div className="card-header"><h3 className="font-semibold">订阅 / 续期</h3></div>
          <div className="card-body flex flex-wrap gap-2">
            <Button variant="secondary" size="sm">时长管理</Button>
            <Button variant="ghost" size="sm">输入兑换码</Button>
          </div>
        </div>

        <div className="card" data-guide="plugins">
          <div className="card-header"><h3 className="font-semibold">插件</h3></div>
          <div className="card-body text-sm text-gray-600 dark:text-gray-300">
            共 10 个 · 已启用 6 个。启用 / 停用、改配置、设权限都在这里。
          </div>
        </div>

        <div className="card" data-guide="plugin-page">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold">点歌</h3>
            <span className="text-xs text-gray-400 dark:text-gray-500">↗ 插件主页</span>
          </div>
          <div className="card-body text-sm text-gray-600 dark:text-gray-300">
            带「插件主页」标记的插件有自己的独立界面。
          </div>
        </div>

        <div className="card" data-guide="library">
          <div className="card-header flex items-center justify-between">
            <h3 className="font-semibold">插件库</h3>
            <span className="text-xs text-gray-400 dark:text-gray-500">14 个插件</span>
          </div>
          <div className="card-body text-sm text-gray-600 dark:text-gray-300">
            面板统一维护的插件来源，有新版本时会在这里提示更新。
          </div>
        </div>
      </div>

      {/* ---------- 蒙版 + 提示卡 ---------- */}
      {hole && (
        <>
          {/* 用超大 box-shadow 造「四周变暗、中间留洞」：比 clip-path 稳，
              也不会挡住目标元素本身（pointer-events-none） */}
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
    </div>
  );
}
