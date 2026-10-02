import { useCallback, useLayoutEffect, useRef, useState } from 'react';

/**
 * 自定义悬浮提示 —— 全站唯一的提示气泡实现（替代原生 title）。
 *
 * 宿主元素需添加 ``relative group`` 类：
 *
 *     <button className="relative group ...">
 *       <HoverTip text="提示文字" />
 *     </button>
 *
 * **贴边自动夹回**：气泡默认居中于宿主，宿主靠近视口左右边缘时，居中会让
 * 气泡越出屏幕 —— 而 body 上有 ``overflow-x: hidden``，越出的部分直接看不见
 * （表现为「提示左端显示不全」）。CSS 无法按视口位置改对齐，所以这里在挂载时
 * 量一次实际宽度，把水平偏移夹回视口内。
 *
 * 只在挂载与窗口尺寸变化时量：气泡虽然 opacity-0，但始终参与布局，
 * 几何是稳定的，不需要每次悬停都读一遍。
 */
/**
 * 宿主离视口顶部多近时，提示改为**显示在下方**。
 *
 * 本应用移动端有一条 `sticky top-0 z-20 h-12` 的顶栏（左上角是菜单按钮），
 * 而提示是 z-50 —— 层级更高，所以顶部那排按钮的气泡会盖在顶栏上、挡住菜单。
 * 48px 顶栏 + 余量，取 64。
 */
const FLIP_BELOW_TOP = 64;

export function HoverTip({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shift, setShift] = useState(0);
  const [below, setBelow] = useState(false);

  const clamp = useCallback(() => {
    const el = ref.current;
    const host = el?.parentElement; // 宿主按钮，即气泡定位的基准
    if (!el || !host) return;

    // ⚠️ 不能量气泡自己的 getBoundingClientRect —— 它返回的是**已应用 transform
    // 之后**的盒子。那样再量一次会算出「已经修正过」的位置、把偏移撤销掉，
    // 气泡就在居中与夹取之间来回横跳。
    // 改为量宿主（不受 transform 影响）+ 气泡自身宽度（offsetWidth 同样不受影响），
    // 反推它在未变换时的左边缘。
    const width = el.offsetWidth;
    const height = el.offsetHeight;
    if (!width || !height) return; // 尚未布局
    const pad = 8; // 与视口留一点缝，贴着边不好看
    const GAP = 8; // 气泡与宿主之间的间距（对应 mb-2 / mt-2）
    const hostRect = host.getBoundingClientRect();

    // 横向：夹回视口内
    const left = hostRect.left + hostRect.width / 2 - width / 2;
    let dx = 0;
    if (left < pad) dx = pad - left;
    else if (left + width > window.innerWidth - pad) dx = window.innerWidth - pad - (left + width);
    setShift(dx);

    // 纵向：宿主离顶太近（或上方根本放不下）就翻到下方，避免盖住顶栏与菜单按钮
    setBelow(hostRect.top - GAP < height + FLIP_BELOW_TOP);
  }, []);

  useLayoutEffect(() => {
    clamp();
    // 挂载时若宿主尚未完成布局（字体未就绪、父容器宽度未定）宽度会量到 0 而被跳过，
    // 所以悬停（即将显示）前再算一次；resize 同样要重算。
    //
    // 重算之所以安全，是因为上一版把「量气泡自己」改成了「量宿主 + 气泡宽度」——
    // 结果与当前偏移无关，重复调用是幂等的，不会在居中与夹取之间来回跳。
    const host = ref.current?.parentElement;
    host?.addEventListener('mouseenter', clamp);
    window.addEventListener('resize', clamp);
    return () => {
      host?.removeEventListener('mouseenter', clamp);
      window.removeEventListener('resize', clamp);
    };
  }, [clamp, text]);

  return (
    <span
      ref={ref}
      role="tooltip"
      // 用内联 transform 覆盖 Tailwind 的 -translate-x-1/2，把夹取量叠上去
      style={{ transform: `translateX(calc(-50% + ${shift}px))` }}
      // 默认贴在宿主正上方；宿主贴近顶部时改为下方（见 FLIP_BELOW_TOP）。
      // 用 bottom-full/top-full 而非写死的 -top-9：偏移随气泡高度自适应，
      // 文字换行变高也不会压到宿主上。
      //
      // w-max + max-w —— 短提示按内容宽度一行放下；长提示被 max-w 卡住后**换行**。
      // 单靠 whitespace-nowrap 时，比屏幕还宽的提示无论怎么夹取都会有一端越界
      // （夹住左边右端就出去），窄机型上尤其明显。
      className={`pointer-events-none absolute left-1/2 z-50
                 ${below ? 'top-full mt-2' : 'bottom-full mb-2'}
                 w-max max-w-[calc(100vw-1rem)] text-center
                 px-2 py-1 rounded-md text-[11px] font-medium
                 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                 opacity-0 group-hover:opacity-100 transition-opacity duration-100`}
    >
      {text}
    </span>
  );
}
