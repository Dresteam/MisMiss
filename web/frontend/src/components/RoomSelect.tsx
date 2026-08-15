import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { MarqueeText } from './MarqueeText';
import type { LivestreamInfo } from '../api/types';

interface Props {
  lives: LivestreamInfo[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

/** 自定义直播间下拉选择器 —— 选中项文字支持滚动显示。 */
export function RoomSelect({ lives, selectedId, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const selected = lives.find(l => l.live_id === selectedId);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      {/* 触发按钮 —— 显示选中项，文字溢出时滚动 */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="input text-xs w-full flex items-center justify-between gap-2 text-left"
      >
        <span className="flex-1 min-w-0 overflow-hidden">
          <MarqueeText text={selected ? `[${selected.live_id}] ${selected.room_name}` : '未选择直播间'} />
        </span>
        <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* 下拉列表 */}
      {open && (
        <div className="absolute z-30 mt-1 w-full max-h-56 overflow-y-auto rounded-lg
                        bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700
                        shadow-lg animate-fade-in">
          {lives.map((l) => (
            <button
              key={l.live_id}
              type="button"
              onClick={() => { onSelect(l.live_id); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50
                ${l.live_id === selectedId ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400' : 'text-gray-700 dark:text-gray-300'}`}
            >
              [{l.live_id}] {l.room_name}
            </button>
          ))}
          {lives.length === 0 && (
            <p className="px-3 py-2 text-xs text-gray-400">暂无直播间</p>
          )}
        </div>
      )}
    </div>
  );
}
