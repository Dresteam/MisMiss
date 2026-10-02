/**
 * 列表的搜索 / 筛选 / 分页控件 —— 账户与插件各处共用。
 *
 * 都按触摸端尺寸做（`min-h-8`，即 32px）：这些控件在手机上要用手指点，
 * 之前的 26~28px 高版本按不准。
 */

import { Search, X, ChevronLeft, ChevronRight, SlidersHorizontal, ChevronDown } from 'lucide-react';

// ------------------------------------------------------------------ //
// 窄屏筛选开关
// ------------------------------------------------------------------ //

/**
 * 窄屏下展开/收起筛选区的开关。
 *
 * 提成共享组件是为了让各页在移动端**长得一样** —— 账户总览与日志页此前各写了
 * 一份，一个填充式、一个描边式，断点还分别是 md 与 sm，手机上切换页面时观感割裂。
 * 断点统一为 md（768px）：更宽的屏上筛选区常驻展开，这个按钮不出现。
 */
export function FilterToggle({ open, count, onToggle, className = '' }: {
  open: boolean;
  /** 生效中的筛选项数量；> 0 时显示角标 */
  count: number;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`md:hidden shrink-0 inline-flex items-center gap-1.5 min-h-9 px-3
        rounded-lg bg-gray-100 dark:bg-gray-800 text-xs font-medium
        text-gray-600 dark:text-gray-300
        active:bg-gray-200 dark:active:bg-gray-700 transition-colors ${className}`}
    >
      <SlidersHorizontal className="w-3.5 h-3.5" />
      筛选
      {count > 0 && (
        // 浅底 + 同色深字，而不是饱和底 + 白字：按钮本身是中性灰底，
        // 一块亮蓝压上去太跳、与整体色调不搭。这套浅底角标是全项目通用写法。
        <span className="min-w-4 h-4 px-1 rounded-full
          bg-primary-100 text-primary-700
          dark:bg-primary-900/40 dark:text-primary-300
          text-[10px] leading-4 text-center font-semibold">
          {count}
        </span>
      )}
      <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
    </button>
  );
}

// ------------------------------------------------------------------ //
// 搜索框
// ------------------------------------------------------------------ //

export function SearchInput({ value, onChange, placeholder }: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative flex-1 min-w-0">
      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5
                         text-gray-400 dark:text-gray-500 pointer-events-none" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input w-full min-h-8 pl-8 pr-9 text-sm"
      />
      {value && (
        <button
          type="button"
          aria-label="清空搜索"
          onClick={() => onChange('')}
          className="absolute right-1 top-1/2 -translate-y-1/2 p-2 rounded-lg
                     text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700
                     hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ //
// 筛选胶囊组
// ------------------------------------------------------------------ //

export interface FilterOption<T extends string> {
  id: T;
  label: string;
  /** 可选的计数，显示在标签后面 */
  count?: number;
}

export function FilterChips<T extends string>({ options, value, onChange, block = false }: {
  options: readonly FilterOption<T>[];
  value: T;
  onChange: (next: T) => void;
  /**
   * 移动端独占整行、各选项等分宽度（桌面端仍按内容贴合）。
   *
   * 用于多组筛选竖排的场景：各组选项数量与文案长短不一，默认的 `w-fit`
   * 会让每行右边缘参差不齐，看着很乱。开启后四行等宽，选项在行内等分。
   */
  block?: boolean;
}) {
  return (
    // block 模式用固定 4 列网格而不是等分：各组选项数不同（3 个 vs 4 个），
    // 等分会让每行的胶囊宽度不一致、列对不齐，看着别扭。固定列数后所有行的
    // 胶囊等宽、上下对齐，选项少的那行末尾留一个空格（容器底色，视觉上
    // 读作「这组少一个选项」而不是破版）。
    <div className={`p-1 rounded-lg bg-gray-100 dark:bg-gray-800 gap-1 ${
      block
        ? 'grid grid-cols-4 w-full md:flex md:flex-wrap md:w-fit'
        : 'flex flex-wrap w-fit'}`}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          className={
            'inline-flex items-center min-h-8 px-3 py-1.5 text-xs font-medium rounded-md transition-all ' +
            // block 模式下由网格分配宽度（移动端），桌面端恢复按内容宽度
            (block ? 'justify-center md:flex-none ' : '') +
            (value === o.id
              ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300')
          }>
          {o.label}
          {o.count !== undefined && (
            <span className="ml-1 text-gray-400 dark:text-gray-500">{o.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ //
// 分页
// ------------------------------------------------------------------ //

/**
 * 页码分页。`page` 从 1 开始。
 *
 * 只渲染当前页附近的页码（首尾各留一个），账户上千时页码条也不会撑爆。
 */
export function Pagination({ page, pageCount, total, onChange }: {
  page: number;
  pageCount: number;
  /** 总条数，用于文案 */
  total: number;
  onChange: (next: number) => void;
}) {
  if (pageCount <= 1) return null;

  const nums: (number | '…')[] = [];
  for (let i = 1; i <= pageCount; i++) {
    if (i === 1 || i === pageCount || Math.abs(i - page) <= 1) nums.push(i);
    else if (nums[nums.length - 1] !== '…') nums.push('…');
  }

  const btn = 'inline-flex items-center justify-center min-w-8 h-8 px-2 rounded-lg text-xs ' +
    'border transition-colors disabled:opacity-40 disabled:cursor-not-allowed';

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-xs text-gray-500 dark:text-gray-400">共 {total} 条</span>
      <div className="flex items-center gap-1">
        <button type="button" className={`${btn} border-gray-200 dark:border-gray-700
          text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700`}
          disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="上一页">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        {nums.map((n, i) => n === '…' ? (
          <span key={`gap${i}`} className="px-1 text-xs text-gray-400">…</span>
        ) : (
          <button key={n} type="button" onClick={() => onChange(n)}
            aria-current={n === page ? 'page' : undefined}
            className={`${btn} ${n === page
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
              : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
            {n}
          </button>
        ))}
        <button type="button" className={`${btn} border-gray-200 dark:border-gray-700
          text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700`}
          disabled={page >= pageCount} onClick={() => onChange(page + 1)} aria-label="下一页">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
