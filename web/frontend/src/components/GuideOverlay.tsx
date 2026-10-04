import {
  createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState,
  type CSSProperties,
} from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button } from './Button';
import { resetPluginDemo } from '../pages/AccountDetailPage';

/**
 * 指引是否正在浮着。页面据此决定要不要进「演示态」—— 目前只有直播间页用：
 * 账户没绑直播间时渲染一个虚拟房间，让「连接 / 断开」那一步有东西可讲、可点。
 *
 * 用 context 而不是让页面查 DOM，是因为页面得跟着它重新渲染。
 * 页面里凡是**只在指引期间出现假数据**的地方，都要挂在它后面。
 */
export const GuideActiveContext = createContext(false);
export const useGuideActive = () => useContext(GuideActiveContext);

/**
 * 账户端「操作指引」—— 一个挂在 App 顶层的全局蒙版，**不渲染任何自己的界面**。
 *
 * 页面就是真实页面：本组件只做三件事 ——
 *   1. 按 `data-guide` 找到真实元素，在它周围画一圈高亮；
 *   2. 用蒙版盖住**整屏**（高亮的那一块除外），让真实按钮点不到；
 *   3. 显示提示卡，切页由用户点左侧导航完成。
 *
 * **任何时刻最多只有一个按钮是可点的**：
 *   - 讲解步（锚点在内容区）—— 整屏都挡，被高亮的按钮**同样点不动**
 *     （兑换码点一下就真花掉，绝不能在指引里被误触）；
 *   - 切页步（锚点是左侧导航项）—— 只放行被高亮的那一项，导航里其余各项
 *     连同内容一起挡掉。用户不会点错页，也不会中途溜到别的页去。
 *
 * 这样主页改了样式、加了字段、调了布局，指引自动跟着变 —— 因为看到的
 * 就是主页本身。**不要再退回「另抄一份模拟界面」的老路**：抄的那份一定会漂移，
 * 之前六轮改造都栽在这里。
 *
 * 与真实页面之间只有一个约定，纯属性、不改逻辑：
 *   `data-guide="<id>"` —— 高亮锚点，取值见下面 GUIDE_PAGES 的 `target`。
 * 锚点缺失（元素没渲染）不报错，那一步退化成「只有文字、没有高亮」。
 *
 * ⚠️ **改了步骤或文案，记得把后端的 `GUIDE_VERSION` 加一**
 * （`src/core/account/manager.py`）。账户记录里存的是「已读版本」，不升版本
 * 老用户不会再被跳进来 —— 改文案的人多半只翻到这一个文件，提醒写在这儿。
 */

/** 视口矩形。用四边而不是 width/height —— 挖洞要反复求交并，四边最好算 */
interface Rect { left: number; top: number; right: number; bottom: number }

interface GuideStep {
  /** 高亮锚点，对应真实元素上的 `data-guide` */
  target: string;
  /** 锚点不存在或不可见时的备选锚点（见「切页」那一步用到的 nav-menu） */
  fallback?: string;
  /**
   * 允许点这个锚点吗。**只有「切页」步为真** —— 那是导航项，点了才能往下走；
   * 内容区的锚点一律挡住，除非它自己声明了 `data-guide-clickable`。
   */
  clickable?: boolean;
  /**
   * 「这一步要用户做的事做完了」的判据：这个锚点一出现就算做完。
   *
   * 用于「得先动手、才允许往下走」的步骤 —— 做没做完之前不显示「下一步」，
   * 免得用户没切就直接跳过去，讲了个寂寞。不填 = 纯讲解步，随时可下一步。
   */
  doneWhen?: string;
  title: string;
  body: string;
}

interface GuidePage {
  /** 真实路由，必须与 App.tsx 的路由表一致 */
  path: string;
  /** 左侧导航里的名字 */
  label: string;
  /**
   * 「切到这一页」要点的那个元素的 `data-guide`。多数页是左侧导航项，
   * 但插件主页没有导航项 —— 它是点插件卡片上的链接进去的，那里就填 `pg-page`。
   */
  navTarget: string;
  /**
   * 切到这一页的提示语。默认是「点左侧导航的「X」切过去」——
   * 插件主页不是从导航进的，那种要自己写一句（见下面 switchStep）。
   */
  switchBody?: string;
  steps: GuideStep[];
}

/**
 * 插件主页的路由前缀 —— 它是动态路由 `/account/plugin/:name/page`，只能按前缀认。
 * ⚠️ 末尾那个斜杠不能省：少了它 `/account/plugins`（插件页）也会被这条前缀吃掉
 */
const PLUGIN_PAGE_PREFIX = '/account/plugin/';

const GUIDE_PAGES: GuidePage[] = [
  {
    path: '/account/home',
    label: '概览',
    navTarget: 'nav-home',
    steps: [
      { target: 'ov-bot', title: '概览 · 账户状态',
        body: '这是「概览」页。四张卡分别是 Bot、直播间、插件、定时消息 —— 账户什么状态，一眼看这里。' },
      { target: 'ov-bot-toggle', title: '启用 / 停用 Bot',
        body: '停用后整个账户的机器人停工 —— 定时消息与插件推送都会停。指引期间这里点不动，放心看。' },
      { target: 'ov-redeem', title: '兑换码续期',
        body: '订阅快到期时点这里输入授权码；永久账户不需要续期。' },
    ],
  },
  {
    path: '/account/live',
    label: '直播间',
    navTarget: 'nav-live',
    steps: [
      { target: 'lv-bind', title: '绑定直播间',
        body: '填入直播间 ID，或者直接把直播间链接粘进来。已经绑过的，这里就是换绑入口。' },
      { target: 'lv-control', title: '连接 / 断开直播间',
        body: '绑定只是「知道是哪个房间」，启用之后才真正连上去收弹幕与礼物；停用即断开。' },
    ],
  },
  {
    path: '/account/bot',
    label: 'Bot',
    navTarget: 'nav-bot',
    steps: [
      // doneWhen：切到自定义之后，下面那张 Cookie 表单卡才会渲染出来 ——
      // 它出现就说明切好了，这时才放「下一步」
      { target: 'bt-mode', doneWhen: 'bt-cookie', title: '更换 Cookie · 先切到自定义',
        body: '先点高亮的「自定义 Cookie」，让来源停在它上面。公共 Cookie 由面板统一配置，账户里看不到也换不了。' },
      { target: 'bt-cookie', title: '粘贴新 Cookie',
        body: '切过来之后，这张卡就是粘贴新 Cookie 的地方，过期了换一条保存即可。（公共 Cookie 模式下没有这张卡，也不用你管。）' },
    ],
  },
  {
    path: '/account/library',
    label: '插件库',
    navTarget: 'nav-library',
    steps: [
      { target: 'lb-list', title: '插件库',
        body: '面板统一维护的插件来源。装插件从这一页开始 —— 先装，装完才谈得上配置。' },
      // doneWhen：装完之后那个角标会从「未安装」变成「已安装」，它一出现就自动翻页
      { target: 'lb-install', doneWhen: 'lb-installed', title: '先装一个插件',
        body: '点高亮的「安装」，把「点歌」装进你的账户 —— 安装 = 把源码副本拷进账户，之后它独立运行。指引期间这里点不会真的装。' },
    ],
  },
  {
    // ⚠️「插件库」排在「插件」**前面**：指引讲的是「先装、再去插件页用它」，
    // 顺序反了就变成先看一个空列表。代价是这一步要往导航**上方**切，
    // 与左侧导航的排列顺序相反 —— 是有意为之，别按导航顺序「顺手」改回来
    path: '/account/plugins',
    label: '插件',
    navTarget: 'nav-plugins',
    steps: [
      { target: 'pg-list', title: '插件管理',
        body: '刚装的「点歌」已经在这儿了 —— 安装与启用是两回事，装完还要在这一页启用才会跑。' },
      { target: 'pg-info', title: '插件详情',
        body: '点「详情」看它的基本信息：版本、作者、注册了哪些事件、要哪些权限。' },
      { target: 'pg-config', title: '插件配置',
        body: '点「配置」改它的参数 —— 配置项由插件自己声明，不是面板写死的。' },
      // 这里不再单独放一步讲「插件主页」：下面自动补的「切到插件主页」那一步
      // 指的就是同一张卡片，连着两步圈同一个地方没意义
    ],
  },
  {
    path: PLUGIN_PAGE_PREFIX,
    label: '插件主页',
    navTarget: 'pg-page',
    switchBody: '点高亮的插件名 —— 带「插件主页」标记的插件，点名字就能进它自己的界面。',
    steps: [
      { target: 'pv-title', title: '插件主页',
        body: '这就是插件主页 —— 内容完全由插件自己决定，面板只负责给它一块地方。到这里就讲完了，点「完成」结束。' },
    ],
  },
];

/**
 * 每页讲完自动补一步「切到下一页」：把左侧导航里那一项圈出来，**由用户自己点**。
 * 指引要教的正是「怎么切」，代劳跳转就白教了 —— 所以这一步没有「下一步」按钮，
 * 卡片只负责说清点哪里。
 *
 * 这是唯一 `clickable` 的一类步骤：蒙版给这一项留洞，导航里其余各项仍然挡着。
 */
function switchStep(next: GuidePage): GuideStep {
  return {
    target: next.navTarget,
    // 只有导航项需要兜底：手机端导航项要拉开抽屉才存在，退而圈住左上角的菜单按钮。
    // 插件主页那类锚点（插件卡片上的链接）本来就一直在，兜底反而会指错地方
    fallback: next.navTarget.startsWith('nav-') ? 'nav-menu' : undefined,
    clickable: true,
    title: `切到「${next.label}」`,
    body: next.switchBody ?? `点左侧导航的「${next.label}」切过去 —— 手机上先点左上角的菜单。`,
  };
}

const CARD_W = 340;   // 提示卡宽度
const CARD_H = 200;   // 提示卡估高，只用来判断往下放还是往上翻
// 变暗层用一个超大的 box-shadow 在中间留洞（见下方渲染处）。得远大于任何屏幕：
// 洞贴在最右边时，阴影还得往左铺满整屏
const DIM_SPREAD = 9999;
// 蒙版比视口再外扩一圈。手机浏览器地址栏收放时 window.innerHeight 与
// position:fixed 的包含块会差几十像素，不留余量的话边上会剩一条没盖住的缝 ——
// 缝里正好能点到内容。外扩出去的几块都在屏幕外，看不见也点不到
const OVERSCAN = 120;

/** 从 area 里挖掉 cut，返回剩下的矩形（最多 4 块）；不相交则原样返回。 */
function cutArea(area: Rect, cut: Rect): Rect[] {
  if (cut.right <= area.left || cut.left >= area.right
      || cut.bottom <= area.top || cut.top >= area.bottom) return [area];
  const out: Rect[] = [];
  if (cut.top > area.top) out.push({ ...area, bottom: cut.top });
  if (cut.bottom < area.bottom) out.push({ ...area, top: cut.bottom });
  // 左右两块只取 cut 的纵向区间，否则会和上面两块重叠 —— 重叠处蒙版会叠得更黑
  const top = Math.max(area.top, cut.top);
  const bottom = Math.min(area.bottom, cut.bottom);
  if (cut.left > area.left) out.push({ left: area.left, top, right: cut.left, bottom });
  if (cut.right < area.right) out.push({ left: cut.right, top, right: area.right, bottom });
  return out;
}

/** DOMRect 转普通对象 —— 别写成 `{...r}`，DOMRect 的属性在原型上，展开是空的 */
const toRect = (r: DOMRect): Rect =>
  ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });

/** 夹进视口。目标比屏幕高（或滚出去一半）时，高亮框贴着屏幕边，不会画到屏幕外 */
const clampRect = (r: Rect, vw: number, vh: number): Rect => ({
  left: Math.max(r.left, 0), top: Math.max(r.top, 0),
  right: Math.min(r.right, vw), bottom: Math.min(r.bottom, vh),
});

/**
 * 取第一个**真实可见**的锚点元素。
 *
 * 同一个 `data-guide` 常常有多份：左侧导航在桌面侧栏和手机抽屉里各渲染一次，
 * 但同一时刻只有一份是活的（另一份 display:none，尺寸为 0）。`querySelector`
 * 只认 DOM 顺序、会挑中隐藏的那份，所以这里按尺寸筛。
 */
function findAnchor(name: string): HTMLElement | null {
  for (const n of Array.from(document.querySelectorAll(`[data-guide="${name}"]`))) {
    const r = n.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return n as HTMLElement;
  }
  return null;
}

/** 本步要圈的元素：主锚点不可见时退到 fallback（手机端导航项要开抽屉才存在 → 退到菜单按钮） */
const anchorOf = (s: GuideStep): HTMLElement | null =>
  findAnchor(s.target) ?? (s.fallback ? findAnchor(s.fallback) : null);

interface Props {
  /** 点「跳过」或「完成」时调用 —— 只有这两处算读过，从侧栏溜走不算 */
  onDone: () => void;
}

export function GuideOverlay({ onDone }: Props) {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // 先精确匹配；匹配不上再试前缀 —— 插件主页是动态路由，只能按前缀认
  const pageIndex = GUIDE_PAGES.findIndex(
    (p) => p.path === pathname || pathname.startsWith(p.path),
  );
  const page = pageIndex >= 0 ? GUIDE_PAGES[pageIndex] : null;

  const [stepIndex, setStepIndex] = useState(0);
  // 切页就回到这一页的第一步 —— 用户可能来回切，每页都从头讲
  useEffect(() => { setStepIndex(0); }, [pathname]);
  // 本页要讲的步骤 = 声明的内容步骤 + 末尾自动补的「切到下一页」那步
  const steps = useMemo(() => {
    if (!page) return [] as GuideStep[];
    const next = GUIDE_PAGES[pageIndex + 1];
    return next ? [...page.steps, switchStep(next)] : page.steps;
  }, [page, pageIndex]);
  // 重置 stepIndex 的 effect 要等这一帧渲染完才跑，所以切页那一帧读到的还是
  // 上一页的序号，可能越界 —— 夹一下再取，页面上的「第 n 步」也用它，免得对不上
  const cur = Math.min(stepIndex, Math.max(0, steps.length - 1));
  const step = steps[cur] ?? null;
  // 本页最后一步：中间页收在「切页」那步（不给「下一步」，就等用户去点导航），
  // 最后一页才收在内容步、给「完成」
  const atLastStep = steps.length > 0 && cur === steps.length - 1;
  const isSwitchStep = atLastStep && pageIndex < GUIDE_PAGES.length - 1;
  const isDoneStep = atLastStep && pageIndex === GUIDE_PAGES.length - 1;

  // ---- 量真实 DOM ----
  // 目标元素可能还在加载、可能因为滚动/折叠动画在动、手机抽屉开合也会改变
  // 可点区域，所以不能只在挂载时量一次。每帧量一遍比 MutationObserver 省心：
  // 它同时覆盖了「晚到」和「动了」两种情况，且比较过 key，没变就不重渲染。
  const [rects, setRects] = useState<{
    target: Rect | null; clickable: boolean; done: boolean; drawerOpen: boolean;
    vw: number; vh: number;
  }>({ target: null, clickable: false, done: false, drawerOpen: false, vw: 0, vh: 0 });
  const lastKey = useRef('');

  const measure = useCallback(() => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const el = step ? anchorOf(step) : null;
    const target = el ? toRect(el.getBoundingClientRect()) : null;
    // 允许点的高亮框只有两类：
    //   1. 切页步的导航项（`step.clickable`）—— 那一步本来就要用户去点它；
    //   2. 元素自己声明 `data-guide-clickable` —— 目前只有虚拟直播间，那是假数据，
    //      点了不产生任何真实影响。真实房间卡**没有**这个声明，所以照样挡住：
    //      那里按一下「停用」就真的断开了。
    const clickable = el != null
      && (step?.clickable === true || el.hasAttribute('data-guide-clickable'));
    // 这一步的动作做完了没。没有 doneWhen 的步骤一律算做完（它们只是讲解），
    // 所以下面「下一步」的显隐只对声明了 doneWhen 的步骤有影响
    const done = !step?.doneWhen || findAnchor(step.doneWhen) != null;
    // 演示抽屉开着没。抽屉是 z-40/50，在蒙版（z-84 起）之下 —— 不让位的话它会
    // 开在蒙版底下：用户看不见也点不到，看着像卡死。见下面渲染处的让位
    const drawerOpen = document.querySelector('[data-guide-drawer]') != null;

    const key = JSON.stringify([target, clickable, done, drawerOpen, vw, vh]);
    if (key === lastKey.current) return;
    lastKey.current = key;
    setRects({ target, clickable, done, drawerOpen, vw, vh });
  }, [step]);

  // layoutEffect：首帧就要把蒙版量出来。晚一帧的话，那一帧内容区是**没有遮挡**的，
  // 正好在点击路径上（用户可能正按着鼠标）—— 用 layoutEffect 就没有这个空窗
  useLayoutEffect(() => {
    measure();
    // 每帧量一次，而不是定时采样：换一步时页面会平滑滚过去，元素位置是连续变的，
    // 按固定间隔采样会让高亮框一跳一跳地追。measure 里比较过 key，没变就不重渲染，
    // 所以静止时几乎没有开销。
    // resize / scroll / click 都不必单独监听 —— 每帧都量了，任何变化最迟一帧就到
    let raf = window.requestAnimationFrame(function tick() {
      measure();
      raf = window.requestAnimationFrame(tick);
    });
    return () => window.cancelAnimationFrame(raf);
  }, [measure]);

  // 用户把这一步该做的事做完了，就**自动翻到下一步**，不用再点一次按钮。
  //
  // 只认「看着它从没做完变成做完」这个真实的切换过程：进来时就已经满足
  // doneWhen 的（账户本来就在自定义 Cookie 模式）不自动翻 —— 那会把这一步的
  // 讲解整段跳过去，用户根本没机会读。那种情况下改成露出「下一步」按钮手动走。
  const pendingDone = useRef<{ step: GuideStep | null; sawPending: boolean }>({
    step: null, sawPending: false,
  });
  useEffect(() => {
    if (!step?.doneWhen) return;
    const w = pendingDone.current;
    if (w.step !== step) { w.step = step; w.sawPending = false; }
    if (!rects.done) { w.sawPending = true; return; }
    if (!w.sawPending) return;
    w.sawPending = false;   // 先清掉，免得同一页里反复翻
    setStepIndex((s) => s + 1);
  }, [rects.done, step]);

  // 换一步就把它滚进视野（仅当它本来不在视野里，免得每步都把页面拽一下）
  useEffect(() => {
    if (!step) return;
    const el = anchorOf(step);
    if (!el) return;
    // 切页步的锚点是导航项（侧栏项 / 汉堡按钮），本来就在眼前，滚它只会把内容区带跑
    if (step.clickable) return;
    const r = el.getBoundingClientRect();
    if (r.top >= 0 && r.bottom <= window.innerHeight) return;
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [step]);

  // 刚进来时若不在指引覆盖的页面上（比如从「重看指引」进、人停在修改密码页），
  // 送去第一页。**只在挂载时跳这一次**，之后切页一律由用户点导航完成。
  const jumped = useRef(false);
  useEffect(() => {
    if (jumped.current) return;
    jumped.current = true;
    // 从哪一页点开都先回「概览」：用户点「重看」就是想完整再走一遍，
    // 从半截开讲反而摸不着头脑。**只跳这一次**，之后切页一律由用户点导航完成
    if (pathname !== GUIDE_PAGES[0].path) navigate(GUIDE_PAGES[0].path, { replace: true });
    // pathname 在依赖里只是为了拿到最新值，真正的「只跳一次」由上面的 ref 保证 ——
    // 少了这个 ref，用户每切一次页都会被拽回第一页
  }, [navigate, pathname]);

  // 高亮框和可点的洞都用**目标的原始矩形**，一点都不外扩。
  //
  // 外扩是个陷阱，而且踩过两次：插件卡片上那几个图标按钮之间只隔 2~4px，
  // 外扩 6px 就盖到相邻按钮上了 —— 用户点「详情」歪一点进「配置」，点「配置」
  // 歪一点进「详情」或「重载」，全是真操作。同理，卡片标题那条拉伸链接也是被
  // 外扩出来的那一圈盖到才误触的。
  //
  // 不外扩的代价只是圆角处那几像素落回卡片背景（那儿没绑任何行为，等于没反应），
  // 比点错按钮划算得多。环形自带 2px 的 ring，视觉上并不会贴着按钮边，所以
  // 不留边距也不难看。
  const hole = useMemo(() => {
    if (!rects.target || rects.vw === 0) return null;
    const c = clampRect(rects.target, rects.vw, rects.vh);
    return c.right - c.left > 0 && c.bottom - c.top > 0 ? c : null;
  }, [rects]);

  // 拦截层：**只给可点的那一个留洞**（切页步的导航项，或自己声明了
  // `data-guide-clickable` 的虚拟房间），其余整屏都挡。讲解步没有可点的锚点，
  // 于是整屏全挡：用户看得见被高亮的兑换码 / Bot 启停，但点不动 —— 那些点一下
  // 就真作用到账户上。
  //
  // 这一层是全透明的，所以**不能加过渡**：换一步时必须立刻生效，否则那 200ms
  // 的动画里会点到不该点的东西。
  //（变暗层不在这里算 —— 它是单个带超大 box-shadow 的元素，见下面渲染处。
  //  分块挖洞的话块数会随步骤变，换步时整片暗区会跳，看着就是一帧闪。）
  const blockers = useMemo(() => {
    if (rects.vw === 0) return [] as Rect[];
    const screen: Rect = {
      left: -OVERSCAN, top: -OVERSCAN,
      right: rects.vw + OVERSCAN, bottom: rects.vh + OVERSCAN,
    };
    return rects.clickable && hole ? cutArea(screen, hole) : [screen];
  }, [rects, hole]);

  // ---- 提示卡位置 ----
  const { vw, vh } = rects;
  const cardStyle: CSSProperties = (() => {
    const size: CSSProperties = { width: CARD_W, maxWidth: 'calc(100vw - 1rem)' };
    // 量不到目标就钉在右下角，别飘出屏幕 —— 宽度仍要定死，否则长文案会把卡片撑得很宽
    if (!hole) return { ...size, right: 16, bottom: 16 };
    const below = hole.bottom + 10;
    const flipUp = below + CARD_H > vh;
    return {
      ...size,
      left: Math.min(Math.max(hole.left, 8), Math.max(8, vw - 8 - CARD_W)),
      ...(flipUp ? { bottom: Math.max(8, vh - hole.top + 10) } : { top: below }),
    };
  })();

  /**
   * 结束指引 —— 「完成」和「跳过」走同一条路：清演示数据 + 回概览。
   *
   * 「跳过」本来只是中途退出、不必挪人，但不挪有个坑：用户可能正停在插件主页，
   * 而那一页的正文只在指引期间成立（见 PluginPageView 的 demo 分支），留着就是
   * 一张「演示期间不加载真实插件界面」的说明页。两条路一致反而更省心。
   *
   * resetPluginDemo 清的是「哪些演示插件被装过」——那份状态在模块级，不主动清
   * 就会留到下一次看指引。
   */
  const finish = () => {
    resetPluginDemo();
    navigate(GUIDE_PAGES[0].path, { replace: true });
    onDone();
  };

  // 抽屉开着 → 整层让位，连提示卡一起收掉：卡片在 z-95，比抽屉面板（z-50）高，
  // 留着会把抽屉压住、挡掉它的按钮。抽屉自带全屏遮罩，内容区照样是挡着的，
  // 所以这里让位不会漏出可点的东西。用户关掉抽屉，蒙版自动回来，还停在这一步
  if (rects.drawerOpen) return null;

  return (
    <>
      {/* 变暗层：**单个**元素 + 超大 box-shadow，在中间留洞。
          用一个元素而不是把整屏切成若干块，就是为了能加 transition ——
          换一步时暗区平滑地滑过去，而不是「啪」地闪一下。
          它和高亮框的时长、缓动一致，两者同一次 commit 里改，所以是同步滑的 */}
      {hole ? (
        <div className="fixed z-[84] pointer-events-none rounded-lg
                        transition-all duration-200 ease-out"
          style={{
            left: hole.left, top: hole.top,
            width: hole.right - hole.left, height: hole.bottom - hole.top,
            boxShadow: `0 0 0 ${DIM_SPREAD}px rgba(0, 0, 0, 0.55)`,
          }} />
      ) : rects.vw > 0 && (
        /* 量不到锚点（元素没渲染出来）：整屏压暗，不留洞 */
        <div className="fixed z-[84] pointer-events-none"
          style={{
            left: -OVERSCAN, top: -OVERSCAN,
            width: rects.vw + OVERSCAN * 2, height: rects.vh + OVERSCAN * 2,
            backgroundColor: 'rgba(0, 0, 0, 0.55)',
          }} />
      )}

      {/* 拦截层：全透明。讲解步这里是**整屏一整块**，连被高亮的那块也在内 ——
          变暗层为了做聚光灯必须留洞，而洞就是漏洞；只有切页步才跟着留洞，
          因为那一步本来就是让用户去点导航项 */}
      {blockers.map((t, i) => (
        <div key={`blk-${i}`} className="fixed z-[85]"
          style={{ left: t.left, top: t.top, width: t.right - t.left, height: t.bottom - t.top }} />
      ))}

      {/* 高亮框：纯视觉，pointer-events-none。被框住的按钮**同样点不动** ——
          兑换码这类点一下就真花掉的东西，绝不能在指引里被误触 */}
      {hole && (
        <div className="fixed z-[88] rounded-lg ring-2 ring-primary-400 pointer-events-none
                        transition-all duration-200 ease-out"
          style={{
            left: hole.left, top: hole.top,
            width: hole.right - hole.left, height: hole.bottom - hole.top,
          }} />
      )}

      {/* 提示卡 */}
      <div className="fixed z-[95] rounded-xl shadow-2xl bg-white dark:bg-gray-800
                      border border-gray-200 dark:border-gray-700 p-4"
        style={cardStyle}>
        {page && step ? (
          <>
            <p className="text-[11px] font-medium text-primary-600 dark:text-primary-400">
              {/* 分母用 steps 而不是 page.steps —— 末尾那步「切页」也是要走的，
                  用 page.steps 会在切页步显示成「第 4/3 步」 */}
              {page.label} · 第 {cur + 1}/{steps.length} 步
            </p>
            <p className="font-semibold text-sm text-gray-900 dark:text-white mt-1">{step.title}</p>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{step.body}</p>
          </>
        ) : (
          <>
            {/* 用户可能自己溜去定时消息 / 修改密码这些不在指引里的页面 ——
                不拦着，只告诉他怎么回去 */}
            <p className="font-semibold text-sm text-gray-900 dark:text-white">这一页不在指引里</p>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
              点左侧导航的「{GUIDE_PAGES[0].label}」就能接着看 —— 以后自己用面板也是这样切页。
            </p>
          </>
        )}

        <div className="flex items-center justify-between mt-3 gap-2">
          <button onClick={finish}
            className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200
                       transition-colors shrink-0">
            跳过指引
          </button>

          {page && step ? (
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" disabled={cur === 0}
                onClick={() => setStepIndex((s) => Math.max(0, s - 1))}>
                上一步
              </Button>
              {/* 「切页」那一步不给「下一步」：这一步该做的就是去点左侧导航，
                  再塞个按钮只会把「怎么切」讲糊；代劳跳转更是白教。
                  声明了 doneWhen 的步骤平时也不给 —— 用户一做完就自动翻页了。
                  这里露出来的其实是**兜底**：进来时就已经满足 doneWhen 的情况
                  （账户本来就在自定义 Cookie 模式）没什么可切，得留条手动前进的路 */}
              {!isSwitchStep && !isDoneStep && rects.done && (
                <Button variant="primary" size="sm"
                  onClick={() => setStepIndex((s) => s + 1)}>
                  下一步
                </Button>
              )}
              {isDoneStep && (
                <Button variant="primary" size="sm" onClick={finish}>完成</Button>
              )}
            </div>
          ) : (
            <Button variant="primary" size="sm" onClick={finish}>完成</Button>
          )}
        </div>
      </div>
    </>
  );
}
