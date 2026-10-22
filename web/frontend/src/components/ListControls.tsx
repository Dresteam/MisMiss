/**
 * 列表的搜索 / 筛选 / 分页控件 —— 账户与插件各处共用。
 *
 * 都按触摸端尺寸做（`min-h-8`，即 32px）：这些控件在手机上要用手指点，
 * 之前的 26~28px 高版本按不准。
 */

import { useState } from 'react';
import {
  Search, X, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  SlidersHorizontal, ChevronDown,
} from 'lucide-react';
import { Select } from './Select';

/** 「每页 N 条」的预设值。此前提之外还能选「自定义」手填 */
const PAGE_SIZE_CHOICES = [6, 7, 8, 9, 10];
/** 「自定义」那一项在选项里的哨兵值 —— 页码范围是数字，撞不上 */
const PAGE_SIZE_CUSTOM = '__custom__';
/** 自定义条数的上限：拦一下手滑输成 999 把整页撑爆 */
const PAGE_SIZE_MAX = 200;

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

export function SearchInput({ value, onChange, placeholder, autoFocus = false }: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  /**
   * 挂载即聚焦。**别在触屏上开** —— 软键盘会盖住刚展开的浮层。
   * 调用方自己按指针类型判断，见 `AccountFilter`。
   */
  autoFocus?: boolean;
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
        autoFocus={autoFocus}
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
    // 桌面端用 flex-nowrap 保证四组**排在同一行**：四组加起来的宽度已经很贴近
    // 页面容器（max-w-6xl = 1152px）的上限，再允许换行就会掉到第二行去。
    <div className={`p-1 rounded-lg bg-gray-100 dark:bg-gray-800 gap-1 ${
      block
        ? 'grid grid-cols-4 w-full md:flex md:flex-nowrap md:w-fit'
        : 'flex flex-wrap w-fit'}`}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          className={
            'inline-flex items-center min-h-8 py-1.5 text-xs font-medium rounded-md transition-all ' +
            // block 模式：移动端由网格分配宽度；桌面端四组要挤在一行，内边距收窄一档
            // 留出余量（否则三位的计数就能把某组挤到第二行去）
            (block ? 'px-2 justify-center md:flex-none ' : 'px-3 ') +
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
export function Pagination({ page, pageCount, total, onChange, pageSize, onPageSizeChange }: {
  page: number;
  pageCount: number;
  /** 总条数，用于默认文案 */
  total: number;
  onChange: (next: number) => void;
  /**
   * 每页条数与它的 setter。两个都传才会在左侧渲染「每页 N 条」选择器，
   * 取代默认的「共 N 条」文案。调用方负责在换条数时把页码归 1。
   */
  pageSize?: number;
  onPageSizeChange?: (next: number) => void;
}) {
  // 点了省略号、就地变成输入框的那一格（存 `nums` 里的下标）。省略号最多出现
  // 两个 —— 当前页左右各一个 —— 所以要分开记，一个布尔量不够
  const [jumpAt, setJumpAt] = useState<number | null>(null);
  const [jumpText, setJumpText] = useState('');
  // 选了「自定义」后，下拉框就地换成手填输入框
  const [sizeCustomOpen, setSizeCustomOpen] = useState(false);
  const [sizeCustomText, setSizeCustomText] = useState('');

  if (pageCount <= 1) return null;

  const nums: (number | '…')[] = [];
  for (let i = 1; i <= pageCount; i++) {
    if (i === 1 || i === pageCount || Math.abs(i - page) <= 1) nums.push(i);
    else if (nums[nums.length - 1] !== '…') nums.push('…');
  }

  /** 收起输入框。不改页码 */
  const closeJump = () => {
    setJumpAt(null);
    setJumpText('');
  };

  const submitJump = () => {
    const n = parseInt(jumpText, 10);
    closeJump();
    // 空着或没输入数字 = 取消；超出范围夹到首/末页，别静默丢弃让人以为没反应
    if (Number.isNaN(n)) return;
    onChange(Math.min(pageCount, Math.max(1, n)));
  };

  const submitCustomSize = () => {
    const n = parseInt(sizeCustomText, 10);
    setSizeCustomOpen(false);
    if (Number.isNaN(n) || n < 1) return;   // 空着或 0 = 取消
    onPageSizeChange?.(Math.min(PAGE_SIZE_MAX, n));
  };

  const sizeOptions = [
    ...PAGE_SIZE_CHOICES.map((n) => ({ value: String(n), label: String(n) })),
    // 自定义值不在预设里，补一项让它显示得出来；不补的话 Select 找不到匹配项，
    // 会退回占位文案，看着像没选中
    ...(pageSize !== undefined && !PAGE_SIZE_CHOICES.includes(pageSize)
      ? [{ value: String(pageSize), label: String(pageSize) }]
      : []),
    { value: PAGE_SIZE_CUSTOM, label: '自定义' },
  ];

  const btn = 'inline-flex items-center justify-center min-w-8 h-8 px-2 rounded-lg text-xs ' +
    'border transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
  const navBtn = `${btn} border-gray-200 dark:border-gray-700
    text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700`;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      {pageSize !== undefined && onPageSizeChange ? (
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500 dark:text-gray-400">每页</span>
          {sizeCustomOpen ? (
            <input
              autoFocus
              type="text"
              inputMode="numeric"
              value={sizeCustomText}
              placeholder="条数"
              aria-label="每页条数"
              onChange={(e) => setSizeCustomText(e.target.value.replace(/\D/g, '').slice(0, 3))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitCustomSize();
                else if (e.key === 'Escape') setSizeCustomOpen(false);
              }}
              onBlur={() => setSizeCustomOpen(false)}
              className="w-[5.5rem] min-h-8 px-2 text-center text-xs rounded-lg
                         border border-primary-500 bg-white dark:bg-gray-800
                         text-gray-900 dark:text-white placeholder:text-gray-400
                         focus:outline-none focus:ring-2 focus:ring-primary-500/40"
            />
          ) : (
            // w-[5.5rem] 是为「自定义」三个字留的，单个数字时看着宽一点无妨
            <Select size="sm" className="w-[5.5rem]" ariaLabel="每页条数"
              value={String(pageSize)}
              options={sizeOptions}
              onChange={(v) => {
                if (v === PAGE_SIZE_CUSTOM) { setSizeCustomText(''); setSizeCustomOpen(true); }
                else onPageSizeChange?.(Number(v));
              }} />
          )}
          <span className="text-xs text-gray-500 dark:text-gray-400">条</span>
        </div>
      ) : (
        <span className="text-xs text-gray-500 dark:text-gray-400">共 {total} 条</span>
      )}
      <div className="flex items-center gap-1">
        {/* 首/末页四个导航键全断点都显示：窄屏实测放得下，不必收口
            （容器是 flex-wrap，真放不下时也只是换行，不会裁掉） */}
        <button type="button" className={navBtn}
          disabled={page <= 1} onClick={() => onChange(1)} aria-label="第一页">
          <ChevronsLeft className="w-3.5 h-3.5" />
        </button>
        <button type="button" className={navBtn}
          disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="上一页">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        {nums.map((n, i) => n === '…' ? (
          // 省略号是个「跳页」入口：点开就地变输入框，省得为了去第 12 页
          // 一页页按过去。外观保持原来的轻量（无边框），靠 hover 提示可点
          jumpAt === i ? (
            <input
              key={`gap${i}`}
              autoFocus
              type="text"
              inputMode="numeric"
              value={jumpText}
              placeholder="页码"
              aria-label="跳转到指定页码"
              onChange={(e) => setJumpText(e.target.value.replace(/\D/g, '').slice(0, 4))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitJump();
                else if (e.key === 'Escape') closeJump();
              }}
              // Enter 提交时输入框随即卸载，这里主要兜「点到别处」的情况
              onBlur={closeJump}
              className="w-12 min-h-8 px-1 text-center text-xs rounded-lg
                         border border-primary-500 bg-white dark:bg-gray-800
                         text-gray-900 dark:text-white placeholder:text-gray-400
                         focus:outline-none focus:ring-2 focus:ring-primary-500/40"
            />
          ) : (
            <button
              key={`gap${i}`}
              type="button"
              onClick={() => { setJumpAt(i); setJumpText(''); }}
              title="跳转到指定页码"
              aria-label="跳转到指定页码"
              className="inline-flex items-center justify-center min-w-8 h-8 px-1 rounded-lg
                         text-xs text-gray-400 transition-colors
                         hover:bg-gray-100 hover:text-gray-600
                         dark:hover:bg-gray-700 dark:hover:text-gray-300">
              …
            </button>
          )
        ) : (
          <button key={n} type="button" onClick={() => onChange(n)}
            aria-current={n === page ? 'page' : undefined}
            className={`${btn} ${n === page
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
              : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
            {n}
          </button>
        ))}
        <button type="button" className={navBtn}
          disabled={page >= pageCount} onClick={() => onChange(page + 1)} aria-label="下一页">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
        <button type="button" className={navBtn}
          disabled={page >= pageCount} onClick={() => onChange(pageCount)} aria-label="最后一页">
          <ChevronsRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
