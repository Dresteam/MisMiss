import { useCallback, useEffect, useState } from 'react';
import { X, ScrollText, RefreshCw, Loader2 } from 'lucide-react';
import { fetchPluginLogs } from '../api/client';
import type { LogEntry } from '../api/types';

interface Props {
  open: boolean;
  /** 弹窗标题，缺省「插件日志」 */
  title?: string;
  /** 顶部说明，可用于指出是哪个插件失败 */
  hint?: string;
  onClose: () => void;
}

/** 日志等级配色，与 LogsPage 保持一致 */
const levelColors: Record<string, string> = {
  DEBUG: 'text-gray-400',
  INFO: 'text-blue-500',
  WARNING: 'text-amber-500',
  ERROR: 'text-red-500',
  CRITICAL: 'text-red-600 font-bold',
};

/**
 * 插件日志弹窗 —— 只展示插件相关的日志。
 *
 * 「插件相关」由服务端按日志来源文件判定：插件自身代码（插件库源码或账户副本）
 * 与框架的插件生命周期代码（core/plugin/），不含 Bot / 服务器等业务日志。
 */
export function PluginLogDialog({ open, title, hint, onClose }: Props) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await fetchPluginLogs(500));
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // 每次打开都重新拉取，避免展示陈旧内容
  useEffect(() => {
    if (open) load();
  }, [open, load]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[80vh] flex flex-col animate-slide-in-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 min-w-0">
            <ScrollText className="w-4 h-4 text-gray-500 shrink-0" />
            <h3 className="font-semibold text-gray-900 dark:text-white truncate">
              {title || '插件日志'}
            </h3>
            <span className="text-xs text-gray-400 shrink-0">({entries.length})</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={load} disabled={loading} title="刷新"
              className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50">
              {loading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <RefreshCw className="w-4 h-4" />}
            </button>
            <button onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {hint && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mb-3">{hint}</p>
          )}
          {loading && entries.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">加载中…</p>
          ) : entries.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">暂无插件日志</p>
          ) : (
            <div className="space-y-1 font-mono text-xs">
              {entries.map((e) => (
                <div key={e.seq_id} className="flex gap-3 py-0.5 hover:bg-gray-50 dark:hover:bg-gray-700/40">
                  <span className="text-gray-400 shrink-0">
                    {new Date(e.timestamp * 1000).toLocaleTimeString()}
                  </span>
                  <span className={`w-16 shrink-0 ${levelColors[e.level] || 'text-gray-500'}`}>
                    {e.level}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400 shrink-0 max-w-[10rem] truncate"
                    title={e.source || ''}>
                    {e.source || '—'}
                  </span>
                  <span className="text-gray-700 dark:text-gray-200 break-all whitespace-pre-wrap">
                    {e.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end px-6 py-4 border-t border-gray-200 dark:border-gray-700">
          <button onClick={onClose}
            className="px-4 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors">
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
