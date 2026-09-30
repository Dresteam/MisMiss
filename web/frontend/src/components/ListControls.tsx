/**
 * 列表的搜索 / 筛选 / 分页控件 —— 账户与插件各处共用。
 *
 * 都按触摸端尺寸做（`min-h-8`，即 32px）：这些控件在手机上要用手指点，
 * 之前的 26~28px 高版本按不准。
 */

import { Search, X, ChevronLeft, ChevronRight } from 'lucide-react';

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

export function FilterChips<T extends string>({ options, value, onChange }: {
  options: readonly FilterOption<T>[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1 p-1 rounded-lg bg-gray-100 dark:bg-gray-800 w-fit">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          className={
            'inline-flex items-center min-h-8 px-3 py-1.5 text-xs font-medium rounded-md transition-all ' +
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
