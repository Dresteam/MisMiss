import { useEffect, useRef, useState } from 'react';
import { X, Loader2, CheckCircle, XCircle } from 'lucide-react';

interface Props {
  open: boolean;
  file: File | null;
  onDone: () => void;
}

export function InstallModal({ open, file, onDone }: Props) {
  const [logs, setLogs] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(false);
  const startedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const appendLog = (msg: string) => {
    setLogs(prev => [...prev, msg]);
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });
  };

  useEffect(() => {
    if (!open || !file || startedRef.current) return;
    startedRef.current = true;
    setLogs([]); setDone(false); setError(false);

    (async () => {
      const token = localStorage.getItem('auth_token');
      const form = new FormData();
      form.append('file', file);

      try {
        const res = await fetch('/api/plugin/install/stream', {
          method: 'POST', body: form,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });

        if (res.status === 409) {
          appendLog('⚠️ 另一个插件安装正在进行中，请稍候...');
          setDone(true); setError(true); return;
        }
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          appendLog('❌ 请求失败: ' + (err.detail || res.statusText));
          setDone(true); setError(true); return;
        }

        const reader = res.body?.getReader();
        if (!reader) { appendLog('❌ 无法读取响应流'); setDone(true); setError(true); return; }

        const decoder = new TextDecoder(); let buffer = '';
        while (true) {
          const { value, done: streamDone } = await reader.read();
          if (streamDone) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                appendLog(data.message);
                if (data.done) { setDone(true); if (data.message.startsWith('错误')) setError(true); }
              } catch { /* ignore */ }
            }
          }
        }
        if (!done) setDone(true);
      } catch (e: any) {
        appendLog('❌ 网络错误: ' + (e.message || ''));
        setDone(true); setError(true);
      }
    })();
  }, [open, file]);

  // 重置
  useEffect(() => { if (!open) startedRef.current = false; }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={done ? onDone : undefined} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 animate-slide-in-up flex flex-col" style={{ maxHeight: '80vh' }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <div className="flex items-center gap-2">
            {!done ? <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />
              : error ? <XCircle className="w-5 h-5 text-red-500" />
                : <CheckCircle className="w-5 h-5 text-emerald-500" />}
            <h3 className="font-semibold text-gray-900 dark:text-white">
              {!done ? '正在安装插件...' : error ? '安装失败' : '安装完成'}
            </h3>
          </div>
          {done && (
            <button onClick={onDone} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-900 font-mono text-xs leading-relaxed space-y-0.5 min-h-[200px] rounded-b-xl">
          {logs.map((line, i) => (
            <p key={i} className={line.startsWith('错误') || line.startsWith('❌') ? 'text-red-600 dark:text-red-400' : 'text-gray-700 dark:text-gray-300'}>
              {line}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}
