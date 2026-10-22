import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, LayoutPanelTop, Users } from 'lucide-react';
import { SearchInput } from './ListControls';

interface AccountOption {
  id: number;
  name: string;
}

interface Props {
  accounts: AccountOption[];
  /** 已选账户名；空数组 = 不过滤（全部）；含空串元素 = 只看面板级日志 */
  selected: string[];
  onChange: (next: string[]) => void;
}

/** 面板级日志的哨兵值：与后端 account 参数的空串约定一致 */
const PANEL = '';

/** 「面板级」那一项的显示名。既是渲染文案，也是搜索时要匹配的目标 */
const PANEL_LABEL = '面板级';

/** 浮层宽度，用于把它夹在视口内 */
const PANEL_W = 232;

/** 日志页的账户筛选器：多选浮层。
 *
 * 不用原生 ``<select multiple>`` —— 原生多选在各平台要按住 Ctrl 才加选，
 * 且展开列表由系统绘制、不跟随应用主题。这里改为自绘的勾选浮层。
 *
 * 顶部带搜索框：账户一多，纯翻列表太长（见 ``ListControls`` 的 ``SearchInput``）。
 */
export function AccountFilter({ accounts, selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  // 搜索词。只在浮层打开期间有意义，关闭即清空（见 close）
  const [query, setQuery] = useState('');
  // 相对触发按钮的横向偏移：按视口夹住，避免浮层越出左边或右边
  const [offsetX, setOffsetX] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  /**
   * 打开即聚焦搜索框 —— 但**只在有真实指针时**。
   *
   * 触屏上聚焦会立刻弹出软键盘，把刚展开的列表盖掉一大半，用户还得先收键盘。
   * 按指针类型判断而不是 UA：带鼠标的窄窗口也该享受这个便利。
   *
   * 这是全仓唯一一处 `matchMedia` —— 别的地方能用 CSS 断点就别用 JS（见
   * `LogsPage` 里那段），但 `autoFocus` 没有 CSS 等价物，只能在这里判。
   */
  const autoFocusSearch = useMemo(
    () => window.matchMedia('(hover: hover) and (pointer: fine)').matches,
    [],
  );

  /** 关闭浮层并清空搜索词 —— 下次打开重新是全量列表，不留上次的残留筛选 */
  const close = () => {
    setOpen(false);
    setQuery('');
  };

  // 点击外部 / Esc 关闭
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const toggleOpen = () => {
    if (open) {
      close();
      return;
    }
    const r = triggerRef.current?.getBoundingClientRect();
    if (r) {
      const left = Math.min(
        Math.max(8, r.right - PANEL_W),
        Math.max(8, window.innerWidth - PANEL_W - 8),
      );
      setOffsetX(left - r.left);
    }
    setOpen(true);
  };

  const toggle = (value: string) => {
    onChange(
      selected.includes(value)
        ? selected.filter((v) => v !== value)
        : [...selected, value],
    );
  };

  const label = selected.length === 0
    ? '全部账户'
    : selected.length === 1
      ? (selected[0] === PANEL ? '面板级' : selected[0])
      : `已选 ${selected.length} 项`;

  // min-h-8 是全局触摸尺寸（见 `ListControls` 抬头）：不含它这行只有 28px，
  // 手机上会点不中 —— 账户列表比别处长，误触的代价是选错账户、要翻回去取消
  const rowCls = 'w-full min-h-8 flex items-center gap-2 px-2 py-1.5 rounded-md text-left '
    + 'text-xs text-gray-700 dark:text-gray-200 '
    + 'hover:bg-gray-100 dark:hover:bg-gray-700/60 transition-colors';

  const item = (value: string, text: string, icon?: React.ReactNode) => {
    const on = selected.includes(value);
    return (
      <button key={value || '__panel__'} type="button" role="option"
        aria-selected={on} onClick={() => toggle(value)} className={rowCls}>
        <span className={`shrink-0 w-3.5 h-3.5 rounded border flex items-center justify-center transition-colors
          ${on ? 'bg-primary-600 border-primary-600' : 'border-gray-300 dark:border-gray-500'}`}>
          {on && <Check className="w-2.5 h-2.5 text-white" strokeWidth={3} />}
        </span>
        {icon}
        <span className="truncate">{text}</span>
      </button>
    );
  };

  // ---- 搜索过滤 ----
  const q = query.trim().toLowerCase();
  // 账户编号同账户总览的搜索框：拼成 `#12` 再匹配，带不带井号的输入都能命中
  const shown = q
    ? accounts.filter((a) => `${a.name} #${a.id}`.toLowerCase().includes(q))
    : accounts;
  // 「面板级」也一并过筛。它是固定项，但搜到只剩它自己时，列表看着像搜索没生效
  const showPanel = !q || PANEL_LABEL.includes(q);
  // 空状态两种成因，别合并：一个是真没账户（此时列表里还有「面板级」），
  // 一个是搜索把账户全筛掉了
  let emptyText: string | null = null;
  if (accounts.length === 0) emptyText = '暂无账户';
  else if (!showPanel && shown.length === 0) emptyText = '无匹配账户';

  return (
    <div className="relative flex" ref={rootRef}>
      <button ref={triggerRef} type="button" onClick={toggleOpen}
        aria-expanded={open} aria-haspopup="listbox"
        title="按账户筛选日志，可同时选中多个"
        className="h-8 max-w-[12rem] flex items-center gap-1.5 pl-2.5 pr-2 rounded-lg
                   border border-gray-300 dark:border-gray-600
                   bg-transparent text-xs text-gray-700 dark:text-gray-300
                   hover:bg-gray-50 dark:hover:bg-gray-800
                   focus:outline-none focus:ring-2 focus:ring-primary-500
                   transition-colors">
        <Users className="w-3.5 h-3.5 shrink-0 text-gray-400 dark:text-gray-500" />
        <span className="truncate">{label}</span>
        <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-gray-400 dark:text-gray-500 transition-transform
          ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        // 外层只管定位与边框，滚动交给下面那份列表 —— 否则搜索框会跟着列表一起滚走
        <div style={{ left: offsetX, width: PANEL_W }}
          className="absolute top-full mt-1 z-30 flex flex-col max-h-72 p-1
                     rounded-lg border border-gray-200 dark:border-gray-700
                     bg-white dark:bg-gray-800 shadow-lg animate-fade-in">
          <div className="shrink-0 px-2 pt-1.5 pb-2 mb-0.5
                          border-b border-gray-100 dark:border-gray-700">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] text-gray-400 dark:text-gray-500">按账户筛选</span>
              {/* 这两个键原来只有 11px 文字、没有内边距，手机上几乎点不中。
                  给足高度与横向留白，`-mr-1.5` 让「清空」的点击区贴到浮层边缘 */}
              <div className="flex items-center -mr-1.5">
                {/* 「全选」始终指全部账户，不随搜索收窄 —— 按钮行为取决于看不见的
                    搜索词会很难解释。要只看筛出来的几个，直接勾更省事。 */}
                <button type="button" onClick={() => onChange(accounts.map((a) => a.name))}
                  className="min-h-8 px-1.5 text-[11px] text-primary-600 dark:text-primary-400
                             hover:underline">全选</button>
                <button type="button" onClick={() => onChange([])}
                  className="min-h-8 px-1.5 text-[11px] text-gray-400
                             hover:text-red-500 transition-colors">清空</button>
              </div>
            </div>
            <SearchInput value={query} onChange={setQuery}
              placeholder="搜索账户…" autoFocus={autoFocusSearch} />
          </div>

          {/* min-h-0 不能省：flex 子项默认 min-height:auto，不加就撑破外层、
              轮不到自己滚动 */}
          <div role="listbox" aria-multiselectable="true" className="overflow-y-auto flex-1 min-h-0">
            {showPanel && item(PANEL, PANEL_LABEL,
              <LayoutPanelTop className="w-3.5 h-3.5 shrink-0 text-gray-400 dark:text-gray-500" />)}
            {shown.map((a) => item(a.name, a.name))}
            {emptyText && (
              <p className="px-2 py-3 text-[11px] text-center text-gray-400 dark:text-gray-500">
                {emptyText}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
