import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
}

interface Props {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  /** value 为空串时显示的占位文案 */
  placeholder?: string;
  disabled?: boolean;
  /** md 对齐 .input（表单里用），sm 用于紧凑工具条 */
  size?: 'md' | 'sm';
  /** 控制宽度等外层布局（宽度类传这里，不要试图覆盖内边距） */
  className?: string;
  /** 无障碍名称：没有可见 label 时应当传 */
  ariaLabel?: string;
  title?: string;
}

/**
 * 下拉选择 —— 自绘，不用原生 ``<select>``。
 *
 * 原生控件的展开列表由系统绘制，配色跟着操作系统而不是应用主题走，
 * 深色界面里经常突兀地弹出一块亮色；各平台箭头样式也不一致。
 *
 * 这里保留原生选择的可用性：role=combobox/listbox/option、aria-expanded 与
 * aria-activedescendant，支持 ↑↓ 移动、Enter/Space 选中、Esc 关闭、点击外部
 * 关闭。焦点始终留在触发按钮上，因此不需要自己管焦点陷阱。
 */
export function Select({
  value, options, onChange, placeholder = '请选择',
  disabled = false, size = 'md', className = '', ariaLabel, title,
}: Props) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // 浮层相对触发按钮的偏移与方向：按视口夹住，底部空间不足时向上弹
  const [pos, setPos] = useState({ left: 0, width: 0, up: false });
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  const close = () => { setOpen(false); setActive(-1); };

  const openPanel = () => {
    const r = triggerRef.current?.getBoundingClientRect();
    if (r) {
      const width = Math.min(
        Math.max(r.width, 160),
        Math.max(160, window.innerWidth - 16),
      );
      const left = Math.min(
        Math.max(8, r.left),
        Math.max(8, window.innerWidth - width - 8),
      );
      // 下方不足 220px 且上方更宽裕时向上弹
      const spaceBelow = window.innerHeight - r.bottom;
      const up = spaceBelow < 220 && r.top > spaceBelow;
      setPos({ left: left - r.left, width, up });
    }
    setActive(selectedIndex);
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  // 选中项或浮层高度变化时把它滚进可视区
  useLayoutEffect(() => {
    if (!open || active < 0) return;
    document.getElementById(`${listId}-${active}`)
      ?.scrollIntoView({ block: 'nearest' });
  }, [open, active, listId]);

  const commit = (idx: number) => {
    const opt = options[idx];
    if (!opt) return;
    if (opt.value !== value) onChange(opt.value);
    close();
    triggerRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      // Enter/Space 以及上下键都能打开，与原生 select 一致
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        openPanel();
      }
      return;
    }
    switch (e.key) {
      case 'Escape':
        e.preventDefault(); close(); break;
      case 'ArrowDown':
        e.preventDefault();
        setActive((i) => Math.min(i + 1, options.length - 1)); break;
      case 'ArrowUp':
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0)); break;
      case 'Home':
        e.preventDefault(); setActive(0); break;
      case 'End':
        e.preventDefault(); setActive(options.length - 1); break;
      case 'Enter':
      case ' ':
        e.preventDefault(); commit(active); break;
      case 'Tab':
        close(); break;   // 让焦点正常移走
    }
  };

  const sizeCls = size === 'sm'
    ? 'h-8 px-2 text-sm'
    : 'px-3 py-2 text-sm';

  return (
    <div className={`relative ${className}`} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        title={title}
        disabled={disabled}
        onClick={() => (open ? close() : openPanel())}
        onKeyDown={onKeyDown}
        className={`w-full flex items-center gap-2 rounded-lg text-left
                    border border-gray-300 dark:border-gray-600
                    bg-white dark:bg-gray-800
                    text-gray-900 dark:text-gray-100
                    transition-colors
                    hover:border-gray-400 dark:hover:border-gray-500
                    focus:outline-none focus:ring-2 focus:ring-primary-500
                    disabled:opacity-50 disabled:cursor-not-allowed
                    ${sizeCls}`}
      >
        <span className={`flex-1 truncate ${selected ? '' : 'text-gray-400 dark:text-gray-500'}`}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown
          className={`w-4 h-4 shrink-0 text-gray-400 dark:text-gray-500 transition-transform
                      ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          style={{ left: pos.left, width: pos.width }}
          className={`absolute z-30 max-h-60 overflow-y-auto p-1
                      rounded-lg border border-gray-200 dark:border-gray-700
                      bg-white dark:bg-gray-800 shadow-lg animate-fade-in
                      ${pos.up ? 'bottom-full mb-1' : 'top-full mt-1'}`}
        >
          {options.length === 0 && (
            <p className="px-2 py-3 text-xs text-center text-gray-400 dark:text-gray-500">
              无可选项
            </p>
          )}
          {options.map((opt, i) => {
            const isSelected = opt.value === value;
            const isActive = i === active;
            return (
              <button
                key={opt.value || `__empty_${i}`}
                id={`${listId}-${i}`}
                type="button"
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActive(i)}
                onClick={() => commit(i)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left
                            text-sm transition-colors
                  ${isActive
                    ? 'bg-gray-100 dark:bg-gray-700/60'
                    : ''}
                  ${isSelected
                    ? 'text-primary-700 dark:text-primary-300 font-medium'
                    : 'text-gray-700 dark:text-gray-200'}`}
              >
                <span className="flex-1 truncate">{opt.label}</span>
                {isSelected && <Check className="w-3.5 h-3.5 shrink-0 text-primary-600 dark:text-primary-400" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
