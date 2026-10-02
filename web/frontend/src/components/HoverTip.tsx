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
export function HoverTip({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shift, setShift] = useState(0);

  const clamp = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (!rect.width) return; // 尚未布局
    const pad = 8; // 与视口留一点缝，贴着边不好看
    let dx = 0;
    if (rect.left < pad) dx = pad - rect.left;
    else if (rect.right > window.innerWidth - pad) dx = window.innerWidth - pad - rect.right;
    setShift(dx);
  }, []);

  useLayoutEffect(() => {
    clamp();
    window.addEventListener('resize', clamp);
    return () => window.removeEventListener('resize', clamp);
  }, [clamp, text]);

  return (
    <span
      ref={ref}
      role="tooltip"
      // 用内联 transform 覆盖 Tailwind 的 -translate-x-1/2，把夹取量叠上去
      style={{ transform: `translateX(calc(-50% + ${shift}px))` }}
      className="pointer-events-none absolute -top-9 left-1/2 z-50
                 whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                 opacity-0 group-hover:opacity-100 transition-opacity duration-100"
    >
      {text}
    </span>
  );
}
