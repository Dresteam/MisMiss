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
  latestSeq: number;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  refresh: () => void;
}

const PAGE_SIZE = 50;

export function useLogStream(): UseLogStreamReturn {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [latestSeq, setLatestSeq] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const lastSeqRef = useRef(0);
  const fetchedSeqRef = useRef(0);
  const oldestSeqRef = useRef(0);

  // ---- HTTP: load history ----
  const loadHistory = useCallback(async (since: number) => {
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(`/api/logs/history?since=${since}&limit=${PAGE_SIZE}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await res.json();
      if (data.entries?.length) {
        setEntries((prev) => {
          const existing = new Set(prev.map((e) => e.seq_id));
          const fresh = data.entries.filter((e: LogEntry) => !existing.has(e.seq_id));
          return [...fresh, ...prev].sort((a, b) => a.seq_id - b.seq_id);
        });
        fetchedSeqRef.current = Math.max(fetchedSeqRef.current, since);
      }
      setLatestSeq(data.latest_seq || 0);
      oldestSeqRef.current = data.oldest_seq || 0;
      setHasMore(data.has_more || false);
    } catch { /* ignore */ }
  }, []);

  const loadMore = useCallback(async () => {
    if (!hasMore) return;
    const oldest = entries.length > 0 ? entries[0].seq_id - 1 : 0;
    await loadHistory(oldest);
  }, [hasMore, entries, loadHistory]);

  const refresh = useCallback(() => {
    setEntries([]);
    setLatestSeq(0);
    setHasMore(false);
    lastSeqRef.current = 0;
    fetchedSeqRef.current = 0;
    setRefreshKey((k) => k + 1);
  }, []);

  // ---- Initial load (re-triggers on refreshKey change) ----
  useEffect(() => {
    loadHistory(0);
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- WebSocket (reconnects on refreshKey change) ----
  useEffect(() => {
    let stopped = false;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      if (stopped) return;
      const lastSeq = lastSeqRef.current;
      const apiPort = localStorage.getItem('api_port') || '8080';
      const wsUrl = `ws://${window.location.hostname}:${apiPort}/api/ws?last_seq=${lastSeq}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!stopped) setConnected(true);
      };

      ws.onmessage = (event) => {
        if (stopped) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'log' && msg.seq_id) {
            lastSeqRef.current = msg.seq_id;
            setLatestSeq((prev) => Math.max(prev, msg.seq_id));
            setEntries((prev) => {
              if (prev.some((e) => e.seq_id === msg.seq_id)) return prev;
              return [...prev.slice(-1999), msg as LogEntry];
            });
          }
        } catch { /* ignore */ }
      };

      ws.onclose = () => {
        if (!stopped) {
          setConnected(false);
          wsRef.current = null;
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws.close();
        wsRef.current = null;
      };
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
  }, [refreshKey]);

  return { entries, connected, latestSeq, hasMore, loadMore, refresh };
}
