import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import Convert from 'ansi-to-html';
import {
  Terminal, Download, X, ArrowDown, Search, RefreshCw,
} from 'lucide-react';
import { useLogStream, type LogEntry } from '../hooks/useLogStream';
import { Button } from '../components/Button';

const ansi = new Convert({
  fg: '#e2e8f0', bg: '#030712',
  colors: {
    0: '#e2e8f0', 1: '#ef4444', 2: '#22c55e', 3: '#eab308',
    4: '#3b82f6', 5: '#a855f7', 6: '#06b6d4', 7: '#94a3b8',
  },
});

const levelColors: Record<string, string> = {
  DEBUG:   'text-gray-400 dark:text-gray-500',
  INFO:    'text-blue-600 dark:text-blue-400',
  SUCCESS: 'text-emerald-600 dark:text-emerald-400',
  WARNING: 'text-amber-600 dark:text-amber-400',
  ERROR:   'text-red-600 dark:text-red-400',
  CRITICAL:'text-red-700 dark:text-red-400 font-bold',
};

const levels = ['ALL', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL'];

export function LogsPage() {
  const { entries, connected, hasMore, loadMore, refresh } = useLogStream();
  const [filterLevel, setFilterLevel] = useState('ALL');
  const [keyword, setKeyword] = useState('');
  const [atBottom, setAtBottom] = useState(true);
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  // wrap loadMore to deduplicate calls
  const loadingMore = useRef(false);
  const handleLoadMore = useCallback(async () => {
    if (loadingMore.current || !hasMore) return;
    loadingMore.current = true;
    await loadMore();
    loadingMore.current = false;
  }, [hasMore, loadMore]);

  // Filter
  const filtered = useMemo(() => {
    let arr = entries;
    if (filterLevel !== 'ALL') arr = arr.filter((e) => e.level === filterLevel);
    if (keyword) {
      const kw = keyword.toLowerCase();
      arr = arr.filter((e) => e.message.toLowerCase().includes(kw));
    }
    return arr;
  }, [entries, filterLevel, keyword]);

  // Auto-follow
  useEffect(() => {
    if (atBottom && filtered.length > 0) {
      virtuosoRef.current?.scrollToIndex({ index: filtered.length - 1, behavior: 'smooth' });
    }
  }, [filtered.length, atBottom]);

  const handleScrollBottom = () => {
    virtuosoRef.current?.scrollToIndex({ index: filtered.length - 1, behavior: 'smooth' });
    setAtBottom(true);
  };

  // Export
  const handleExport = () => {
    const text = entries
      .map((l) => `[${new Date(l.timestamp * 1000).toISOString()}] [${l.level}] ${l.message}`)
      .join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mis-miss-${new Date().toISOString().slice(0, 19)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">服务器日志</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
            {connected ? '实时' : '离线'} · {filtered.length} 条
            {filtered.length !== entries.length && ` / 共 ${entries.length}`}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {levels.map((lv) => (
            <button key={lv} onClick={() => setFilterLevel(lv)}
              className={`px-2 py-1 text-[11px] font-medium rounded transition-colors
                ${filterLevel === lv
                  ? 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white'
                  : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}`}>
              {lv}
            </button>
          ))}
          <span className="w-px h-5 bg-gray-300 dark:bg-gray-700 mx-1" />
          <Button variant="ghost" size="sm" icon={<RefreshCw />}
            onClick={refresh}>刷新</Button>
          <Button variant="ghost" size="sm" icon={<Download />}
            onClick={handleExport}>导出</Button>
        </div>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-2 mb-2">
        <Search className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 shrink-0" />
        <input type="text" value={keyword} onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索日志关键词..."
          className="flex-1 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
                     rounded-md px-3 py-1.5 text-xs
                     text-gray-900 dark:text-gray-300 placeholder-gray-400 dark:placeholder-gray-600
                     focus:outline-none focus:border-gray-400 dark:focus:border-gray-500 transition-colors" />
        {keyword && (
          <button onClick={() => setKeyword('')}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 dark:text-gray-500">
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Log area */}
      <div className="flex-1 bg-gray-100 dark:bg-gray-950 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden relative">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400 dark:text-gray-600">
            <div className="text-center"><Terminal className="w-8 h-8 mx-auto mb-2 opacity-30" /><p>等待日志输出...</p></div>
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={filtered}
            followOutput="smooth"
            atBottomStateChange={setAtBottom}
            initialTopMostItemIndex={filtered.length - 1}
            startReached={handleLoadMore}
            itemContent={(_index, entry) => (
              <div className="flex gap-2 leading-relaxed hover:bg-black/[0.03] dark:hover:bg-white/[0.03] px-2 text-[11px] font-mono">
                <span className="text-gray-400 dark:text-gray-600 shrink-0 w-16 text-right">
                  {new Date(entry.timestamp * 1000).toLocaleTimeString('zh-CN', { hour12: false })}
                </span>
                <span className={`shrink-0 w-16 ${levelColors[entry.level] || 'text-gray-400'}`}>
                  [{entry.level}]
                </span>
                <span className="text-gray-700 dark:text-gray-300 break-all whitespace-pre-wrap flex-1"
                  dangerouslySetInnerHTML={{ __html: ansi.toHtml(entry.message) }} />
              </div>
            )}
          />
        )}

        {/* Scroll-to-bottom FAB */}
        {!atBottom && filtered.length > 20 && (
          <button onClick={handleScrollBottom}
            className="absolute bottom-4 right-4 w-8 h-8 rounded-full bg-white dark:bg-gray-700
                       border border-gray-200 dark:border-gray-600
                       hover:bg-gray-100 dark:hover:bg-gray-600
                       text-gray-600 dark:text-white shadow-lg flex items-center justify-center
                       transition-all animate-slide-in-up">
            <ArrowDown className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
