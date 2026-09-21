import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, LayoutPanelTop, Users } from 'lucide-react';

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

/** 浮层宽度，用于把它夹在视口内 */
const PANEL_W = 232;

/** 日志页的账户筛选器：多选浮层。
 *
 * 不用原生 ``<select multiple>`` —— 原生多选在各平台要按住 Ctrl 才加选，
 * 且展开列表由系统绘制、不跟随应用主题。这里改为自绘的勾选浮层。
 */
export function AccountFilter({ accounts, selected, onChange }: Props) {
  const [open, setOpen] = useState(false);
  // 相对触发按钮的横向偏移：按视口夹住，避免浮层越出左边或右边
  const [offsetX, setOffsetX] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // 点击外部 / Esc 关闭
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const toggleOpen = () => {
    if (!open) {
      const r = triggerRef.current?.getBoundingClientRect();
      if (r) {
        const left = Math.min(
          Math.max(8, r.right - PANEL_W),
          Math.max(8, window.innerWidth - PANEL_W - 8),
        );
        setOffsetX(left - r.left);
      }
    }
    setOpen((v) => !v);
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

  const rowCls = 'w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left '
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
        <div role="listbox" aria-multiselectable="true"
          style={{ left: offsetX, width: PANEL_W }}
          className="absolute top-full mt-1 z-30 max-h-72 overflow-y-auto p-1
                     rounded-lg border border-gray-200 dark:border-gray-700
                     bg-white dark:bg-gray-800 shadow-lg animate-fade-in">
          <div className="flex items-center justify-between px-2 py-1.5 mb-0.5
                          border-b border-gray-100 dark:border-gray-700">
            <span className="text-[11px] text-gray-400 dark:text-gray-500">按账户筛选</span>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => onChange(accounts.map((a) => a.name))}
                className="text-[11px] text-primary-600 dark:text-primary-400 hover:underline">全选</button>
              <button type="button" onClick={() => onChange([])}
                className="text-[11px] text-gray-400 hover:text-red-500 transition-colors">清空</button>
            </div>
          </div>
          {item(PANEL, '面板级', <LayoutPanelTop className="w-3.5 h-3.5 shrink-0 text-gray-400 dark:text-gray-500" />)}
          {accounts.length === 0 && (
            <p className="px-2 py-3 text-[11px] text-center text-gray-400 dark:text-gray-500">暂无账户</p>
          )}
          {accounts.map((a) => item(a.name, a.name))}
        </div>
      )}
    </div>
  );
}
