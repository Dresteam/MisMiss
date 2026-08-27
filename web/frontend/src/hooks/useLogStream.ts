import { useEffect, useRef, useState, useCallback } from 'react';

export interface LogEntry {
  seq_id: number;
  timestamp: number;
  level: string;
  message: string;
}

interface UseLogStreamReturn {
  entries: LogEntry[];
  connected: boolean;
  loading: boolean;
  latestSeq: number;
  total: number;
  hasMore: boolean;
  loadMore: () => Promise<boolean>;
  refresh: () => void;
}

/** 单次加载条数（初始加载 / 向上翻页 / 筛选补拉均使用该值） */
const PAGE_SIZE = 100;

/** 日志流：HTTP 按需加载历史 + WebSocket 批量实时推送 + 源头级别过滤。
 *
 * - ``levels`` 变化时**不清空重拉**：先对已加载日志做本地过滤，
 *   不足 ``PAGE_SIZE`` 条时再向后端补拉更早的筛选项
 * - 加载更早历史期间冻结实时插入，完成后一次性批量合并（避免列表抖动）
 */
export function useLogStream(levels: string[] = []): UseLogStreamReturn {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [latestSeq, setLatestSeq] = useState(0);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const lastSeqRef = useRef(0);
  const entriesRef = useRef<LogEntry[]>([]);
  const loadingMore = useRef(false);
  const frozenRef = useRef(false);          // 加载历史期间冻结实时插入
  const pendingLiveRef = useRef<LogEntry[]>([]); // 冻结期间暂存的实时日志
  const isFirstRunRef = useRef(true);

  const levelsKey = [...levels].sort().join(',');
  const levelsRef = useRef(levelsKey);
  levelsRef.current = levelsKey;

  // ---- HTTP: 历史拉取（含源头级别过滤）----
  const fetchHistory = useCallback(async (since: number, lvKey: string) => {
    const token = localStorage.getItem('auth_token');
    const lv = lvKey ? `&levels=${encodeURIComponent(lvKey)}` : '';
    const res = await fetch(
      `/api/logs/history?since=${since}&limit=${PAGE_SIZE}${lv}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    const data = await res.json();
    return {
      entries: (data.entries || []) as LogEntry[],
      has_more: data.has_more ?? false,
      total: data.total ?? 0,
    };
  }, []);

  const loadHistory = useCallback(async (since: number, lvKey: string) => {
    setLoading(true);
    try {
      const data = await fetchHistory(since, lvKey);
      const merged = [...data.entries].sort((a, b) => a.seq_id - b.seq_id);
      entriesRef.current = merged;
      setEntries(merged);
      setHasMore(data.has_more);
      setTotal(data.total);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [fetchHistory]);

  /** 冻结实时插入，一次性合并暂存日志（loadMore / 筛选补拉结束时调用）。 */
  const flushPending = useCallback(() => {
    if (!pendingLiveRef.current.length) return;
    const existing = new Set(entriesRef.current.map((e) => e.seq_id));
    const newItems = pendingLiveRef.current.filter((e) => !existing.has(e.seq_id));
    pendingLiveRef.current = [];
    if (!newItems.length) return;
    // 新条目已在服务端缓冲中且匹配当前筛选 → total 同步 +N
    setTotal((prev) => prev + newItems.length);
    setEntries((prev) => {
      const merged = [...prev, ...newItems].sort((a, b) => a.seq_id - b.seq_id);
      entriesRef.current = merged;
      return merged;
    });
  }, []);

  const loadMore = useCallback(async () => {
    if (loadingMore.current) return false;
    loadingMore.current = true;
    frozenRef.current = true; // 冻结实时插入，加载完成后一次性合并
    try {
      const oldest = entriesRef.current.length > 0 ? entriesRef.current[0].seq_id : 0;
      if (oldest <= 0) return false;
      const data = await fetchHistory(oldest, levelsRef.current);
      if (!data.entries.length) return false;
      setEntries((prev) => {
        const existing = new Set(prev.map((e) => e.seq_id));
        const fresh = data.entries.filter((e) => !existing.has(e.seq_id));
        // 历史 + 冻结期间暂存的实时日志一次性合并
        const merged = [...fresh, ...prev, ...pendingLiveRef.current]
          .sort((a, b) => a.seq_id - b.seq_id);
        pendingLiveRef.current = [];
        entriesRef.current = merged;
        return merged;
      });
      setHasMore(data.has_more);
      setTotal(data.total);
      return data.has_more;
    } catch {
      return false;
    } finally {
      frozenRef.current = false;
      loadingMore.current = false;
    }
  }, [fetchHistory]);

  const refresh = useCallback(() => {
    // 重置并立即按当前筛选重拉
    entriesRef.current = [];
    pendingLiveRef.current = [];
    lastSeqRef.current = 0;
    setEntries([]);
    setLatestSeq(0);
    setTotal(0);
    setHasMore(false);
    setRefreshKey((k) => k + 1); // 触发 WS 重连
    loadHistory(0, levelsRef.current);
  }, [loadHistory]);

  // ---- 挂载时初始加载 ----
  useEffect(() => {
    loadHistory(0, levelsRef.current);
  }, [loadHistory]);

  // ---- 级别筛选变化：本地过滤 + 最新窗口合并 + 不足时向更早历史补拉 ----
  const applyLevelFilter = useCallback(async (lvKey: string) => {
    frozenRef.current = true;
    try {
      const levelSet = new Set(lvKey ? lvKey.split(',') : []);
      // 1. 先对已加载日志做本地过滤（空筛选 = 全部保留）
      const local = levelSet.size === 0
        ? entriesRef.current
        : entriesRef.current.filter((e) => levelSet.has(e.level));

      // 2. 拉取最新 PAGE_SIZE 条筛选结果并合并：
      //    保证加选级别 / 取消筛选后，最近日志立即正确出现
      const latest = await fetchHistory(0, lvKey);
      const existingLatest = new Set(local.map((e) => e.seq_id));
      const freshLatest = latest.entries.filter((e) => !existingLatest.has(e.seq_id));
      let current = [...local, ...freshLatest].sort((a, b) => a.seq_id - b.seq_id);

      // 3. 向更早历史补拉筛选项，直到全部加载（每请求 PAGE_SIZE 条），
      //    保证「已加载 = 共 N 条」，数量一致。
      //    注意：游标必须从「最新窗口的边界」开始连续翻页——本地已加载
      //    条目可能被前一次筛选挖出空洞，缺失条目可能位于已加载范围中间，
      //    不能从已合并列表的最旧条目开始跳页。
      let cursor = latest.entries.length ? latest.entries[0].seq_id : 0;
      let more = latest.has_more;
      let filteredTotal = latest.total;
      while (more) {
        const data = await fetchHistory(cursor, lvKey);
        if (!data.entries.length) { more = false; filteredTotal = data.total; break; }
        // 游标严格递减（本批最旧 seq），必然终止
        cursor = data.entries[0].seq_id;
        const existing = new Set(current.map((e) => e.seq_id));
        const fresh = data.entries.filter((e) => !existing.has(e.seq_id));
        if (fresh.length) {
          current = [...fresh, ...current].sort((a, b) => a.seq_id - b.seq_id);
        }
        more = data.has_more;
        filteredTotal = data.total;
      }
      entriesRef.current = current;
      setEntries(current);
      setHasMore(more);
      setTotal(filteredTotal);
    } catch { /* ignore */ }
    finally {
      frozenRef.current = false;
      flushPending(); // 合并筛选期间暂存的实时日志
    }
  }, [fetchHistory, flushPending]);

  useEffect(() => {
    if (isFirstRunRef.current) { isFirstRunRef.current = false; return; }
    applyLevelFilter(levelsKey);
  }, [levelsKey, applyLevelFilter]);

  // ---- WebSocket（levels / refreshKey 变化时重连）----
  useEffect(() => {
    let stopped = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let reconnectDelay = 1000;

    function connect() {
      if (stopped) return;
      const lastSeq = lastSeqRef.current;
      // 始终使用同源连接：经过反向代理时自动适配 HTTPS/WSS
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = window.location.host; // 含端口（非标准端口时）
      const lv = levelsKey ? `&levels=${encodeURIComponent(levelsKey)}` : '';
      const wsUrl = `${wsProtocol}//${wsHost}/api/ws?last_seq=${lastSeq}${lv}`;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!stopped) {
            setConnected(true);
            reconnectDelay = 1000; // reset on success
          }
        };

        ws.onmessage = (event) => {
          if (stopped) return;
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'logs' && Array.isArray(msg.entries)) {
              const fresh = msg.entries as LogEntry[];
              if (!fresh.length) return;
              const last = fresh[fresh.length - 1];
              lastSeqRef.current = Math.max(lastSeqRef.current, last.seq_id);
              setLatestSeq((prev) => Math.max(prev, last.seq_id));
              if (frozenRef.current) {
                // 冻结中：暂存，等待批量合并
                pendingLiveRef.current.push(...fresh);
                return;
              }
              const existing = new Set(entriesRef.current.map((e) => e.seq_id));
              const newItems = fresh.filter((e) => !existing.has(e.seq_id));
              if (newItems.length) {
                // 新条目已在服务端缓冲中且匹配当前筛选 → total 同步 +N
                setTotal((prev) => prev + newItems.length);
                setEntries((prev) => {
                  const merged = [...prev.slice(-1999), ...newItems];
                  entriesRef.current = merged;
                  return merged;
                });
              }
            } else if (msg.type === 'log' && msg.seq_id) {
              // 兼容单条推送（旧版后端）
              lastSeqRef.current = msg.seq_id;
              setLatestSeq((prev) => Math.max(prev, msg.seq_id));
              if (frozenRef.current) {
                pendingLiveRef.current.push(msg as LogEntry);
                return;
              }
              const exists = entriesRef.current.some((e) => e.seq_id === msg.seq_id);
              if (!exists) {
                setTotal((prev) => prev + 1);
                setEntries((prev) => {
                  const merged = [...prev.slice(-1999), msg as LogEntry];
                  entriesRef.current = merged;
                  return merged;
                });
              }
            }
          } catch { /* ignore */ }
        };

        ws.onclose = () => {
          if (!stopped) {
            setConnected(false);
            wsRef.current = null;
            reconnectTimer = setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30000); // 1s → 2s → 4s → ... → 30s max
          }
        };

        ws.onerror = () => {
          ws.close();
          wsRef.current = null;
        };
      } catch {
        if (!stopped) {
          reconnectTimer = setTimeout(connect, reconnectDelay);
        }
      }
    }

    connect();

    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [refreshKey, levelsKey]);

  return { entries, connected, loading, latestSeq, total, hasMore, loadMore, refresh };
}
