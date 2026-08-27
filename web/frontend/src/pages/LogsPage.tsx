import { useState, useMemo, useCallback, useRef, useEffect, useLayoutEffect } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import Convert from 'ansi-to-html';
import {
  Terminal, Download, X, ArrowDown, Search, RefreshCw, Package, Loader2,
} from 'lucide-react';
import { useLogStream, type LogEntry } from '../hooks/useLogStream';
import { Button } from '../components/Button';
import { showToast } from '../hooks/useToast';

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

const levels = ['DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL'];

export function LogsPage() {
  const [filterLevels, setFilterLevels] = useState<Set<string>>(new Set());
  // 级别筛选下推到后端（源头过滤），级别变化时 hook 自动重连重拉
  const { entries, connected, loading, total, hasMore, loadMore, refresh } =
    useLogStream([...filterLevels]);
  const [keyword, setKeyword] = useState('');
  const [atBottom, setAtBottom] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set()); // 展开的日志行
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  // Pip install modal
  const [pipOpen, setPipOpen] = useState(false);
  const [pipPkg, setPipPkg] = useState('');
  const [pipInstalling, setPipInstalling] = useState(false);

  // wrap loadMore to deduplicate calls
  const loadingMore = useRef(false);
  // 锚定滚动位置：加载更早日志时 firstItemIndex 递减，视图不跳动
  const [firstItemIndex, setFirstItemIndex] = useState(0);
  const prevFilteredLength = useRef(0);
  const loadingAnchor = useRef(false); // 标记正在 loadMore，避免 WS 新日志误触锚定

  // Filter
  const toggleLevel = (lv: string) => {
    setFilterLevels((prev) => {
      const next = new Set(prev);
      next.has(lv) ? next.delete(lv) : next.add(lv);
      return next;
    });
  };

  // 级别过滤已由后端完成，这里仅做关键词本地过滤
  const filtered = useMemo(() => {
    if (!keyword) return entries;
    const kw = keyword.toLowerCase();
    return entries.filter((e) => e.message.toLowerCase().includes(kw));
  }, [entries, keyword]);

  const toggleExpand = (seq: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(seq) ? next.delete(seq) : next.add(seq);
      return next;
    });
  };

  // filtered 增长时锚定视图（仅 loadMore 前置插入时）。
  // 使用 useLayoutEffect：绘制前同步调整锚点，避免「先下跳再回位」的中间帧
  useLayoutEffect(() => {
    const prev = prevFilteredLength.current;
    const curr = filtered.length;
    if (curr > prev && loadingAnchor.current) {
      setFirstItemIndex((idx) => idx - (curr - prev));
      loadingAnchor.current = false;
    }
    prevFilteredLength.current = curr;
  }, [filtered.length]);

  const handleLoadMore = useCallback(async () => {
    if (loadingMore.current || !hasMore) return;
    loadingMore.current = true;
    loadingAnchor.current = true; // 标记本次增长来自 loadMore
    await loadMore();
    loadingMore.current = false;
  }, [hasMore, loadMore]);

  // Auto-follow
  useEffect(() => {
    if (atBottom && filtered.length > 0) {
      virtuosoRef.current?.scrollToIndex({ index: filtered.length - 1, behavior: 'smooth' });
    }
  }, [filtered.length, atBottom]);

  // 级别筛选变化时回到最新日志位置（列表按新筛选重建）
  useEffect(() => {
    if (filtered.length > 0) {
      virtuosoRef.current?.scrollToIndex({ index: filtered.length - 1, behavior: 'auto' });
      setAtBottom(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterLevels]);

  const handleScrollBottom = () => {
    virtuosoRef.current?.scrollToIndex({ index: filtered.length - 1, behavior: 'smooth' });
    setAtBottom(true);
  };

  // Export
  const handlePipInstall = async () => {
    if (!pipPkg.trim()) return;
    setPipInstalling(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/config/pip-install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ package: pipPkg.trim() }),
      });
      const data = await res.json();
      if (res.ok) { showToast('success', data.message); setPipPkg(''); setPipOpen(false); }
      else showToast('error', data.detail);
    } catch { showToast('error', '安装失败'); }
    finally { setPipInstalling(false); }
  };

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
    <div className="flex flex-col h-[calc(100vh-8rem)] lg:h-[calc(100vh-6rem)] animate-fade-in">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="min-w-0">
          <h1 className="text-xl lg:text-2xl font-bold text-gray-900 dark:text-white">服务器日志</h1>
          <p className="text-xs lg:text-sm text-gray-500 dark:text-gray-400 mt-1">
            <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
            {connected ? '实时' : '离线'} · 已加载 {entries.length} / 共 {total} 条
            {filtered.length !== entries.length && `（筛选后 ${filtered.length} 条）`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {levels.map((lv) => {
            const active = filterLevels.has(lv);
            return (
              <button key={lv} onClick={() => toggleLevel(lv)}
                className={`px-2 py-1 text-[11px] font-medium rounded transition-colors
                  ${active
                    ? 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white'
                    : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'}`}>
                {lv}
              </button>
            );
          })}
          {filterLevels.size > 0 && (
            <button onClick={() => setFilterLevels(new Set())}
              className="px-2 py-1 text-[11px] text-gray-400 hover:text-red-500 transition-colors">清除</button>
          )}
          <span className="w-px h-5 bg-gray-300 dark:bg-gray-700 mx-1" />
          <Button variant="ghost" size="sm" icon={<RefreshCw />}
            onClick={refresh}>刷新</Button>
          <Button variant="ghost" size="sm" icon={<Package />}
            onClick={() => setPipOpen(true)}>安装包</Button>
          <Button variant="ghost" size="sm" icon={<Download />}
            onClick={handleExport}>导出</Button>
        </div>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
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
            <div className="text-center">
              {loading ? (
                <><Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-40" /><p>加载中...</p></>
              ) : (
                <><Terminal className="w-8 h-8 mx-auto mb-2 opacity-30" /><p>等待日志输出...</p></>
              )}
            </div>
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={filtered}
            firstItemIndex={firstItemIndex}
            followOutput="smooth"
            atBottomStateChange={setAtBottom}
            initialTopMostItemIndex={filtered.length - 1}
            startReached={handleLoadMore}
            itemContent={(_index, entry) => {
              const isExpanded = expanded.has(entry.seq_id);
              return (
                <div className={`flex gap-2 leading-5 ${isExpanded ? 'min-h-5 h-auto' : 'h-5'}
                                hover:bg-black/[0.03] dark:hover:bg-white/[0.03] px-2 text-[11px] font-mono`}>
                  <span className="text-gray-400 dark:text-gray-600 shrink-0 w-16 text-right">
                    {new Date(entry.timestamp * 1000).toLocaleTimeString('zh-CN', { hour12: false })}
                  </span>
                  <span className={`shrink-0 w-16 ${levelColors[entry.level] || 'text-gray-400'}`}>
                    [{entry.level}]
                  </span>
                  {/* 固定行高：默认单行截断，点击展开全文 */}
                  <span
                    onClick={() => toggleExpand(entry.seq_id)}
                    title={isExpanded ? '点击收起' : '点击展开'}
                    className={`flex-1 min-w-0 cursor-pointer text-gray-700 dark:text-gray-300
                      ${isExpanded ? 'h-auto break-all whitespace-pre-wrap' : 'truncate [&_span]:whitespace-nowrap'}`}
                    dangerouslySetInnerHTML={{ __html: ansi.toHtml(entry.message) }}
                  />
                </div>
              );
            }}
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
      {/* Pip install modal */}
      {pipOpen && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={() => setPipOpen(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 animate-slide-in-up">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">安装 pip 包</h3>
            <p className="text-xs text-gray-500 mb-4">输入包名，将使用 pip 安装到当前 Python 环境</p>
            <div className="flex gap-2">
              <input type="text" value={pipPkg} onChange={e => setPipPkg(e.target.value)}
                className="input flex-1" placeholder="例如: pypinyin"
                onKeyDown={e => e.key === 'Enter' && handlePipInstall()} />
              <Button variant="primary" onClick={handlePipInstall} loading={pipInstalling}>安装</Button>
            </div>
            <div className="flex justify-end mt-3">
              <Button variant="ghost" size="sm" onClick={() => setPipOpen(false)}>取消</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
