/** 自定义悬浮提示 —— 替代原生 title，样式与插件卡片按钮一致。
 *
 * 宿主元素需添加 ``relative group`` 类：
 *
 *     <button className="relative group ...">
 *       <HoverTip text="提示文字" />
 *     </button>
 */
export function HoverTip({ text }: { text: string }) {
  return (
    <span
      role="tooltip"
      className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 z-50
                 whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                 opacity-0 group-hover:opacity-100 transition-opacity duration-100"
    >
      {text}
    </span>
  );
}
