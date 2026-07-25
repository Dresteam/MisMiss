import { useEffect, useState, useCallback } from 'react';
import { Loader2, RefreshCw, X } from 'lucide-react';
import { Button } from './Button';
import type { ConfigFieldSchema } from '../api/types';

interface UISchema {
  type: 'table' | 'list' | 'stats' | 'cards' | 'playlist';
  api?: string;
  columns?: { key: string; label: string; type?: string }[];
  actions?: {
    label: string;
    method: string;
    url: string;
    /** 若设置，点击时弹出输入框收集数据，作为 JSON body 发送 */
    prompt_field?: { key: string; label: string; placeholder?: string };
    /** 若设置，仅当行数据的 status 匹配时才显示此按钮 */
    show_when?: string;
  }[];
  fields?: { key: string; label: string; format?: string }[];
  /** playlist 类型专用 */
  status_actions?: { label: string; status: string; icon?: string; show_when?: string }[];
  batch_actions?: { label: string; method: string; url: string; status?: string }[];
  add_action?: { label: string; method: string; url: string; prompt_field: { key: string; label: string; placeholder?: string } };
}

interface Props {
  schema: UISchema;
  pluginName: string;
}

export function PluginUI({ schema, pluginName }: Props) {
  const [data, setData] = useState<any[] | Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  // Prompt dialog state
  const [promptAction, setPromptAction] = useState<UISchema['actions'][number] | null>(null);
  const [promptValue, setPromptValue] = useState('');
  const [promptRow, setPromptRow] = useState<any>(null);
  // Batch selection (playlist type)
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    if (!schema.api) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch(schema.api, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const result = await res.json();
      setData(result);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [schema.api]);

  useEffect(() => { load(); }, [load]);

  /** 关闭 prompt 弹窗 */
  const closePrompt = () => {
    setPromptAction(null);
    setPromptValue('');
    setPromptRow(null);
  };

  /** 提交带 body 的 action */
  const submitPrompt = async () => {
    if (!promptAction || !promptAction.prompt_field) return;
    setActionLoading(promptAction.label);
    try {
      let url = promptAction.url;
      if (promptRow) url = url.replace('{id}', promptRow.id || '');
      const token = localStorage.getItem('auth_token');
      const body: Record<string, string> = {};
      body[promptAction.prompt_field.key] = promptValue;
      await fetch(url, {
        method: promptAction.method,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      closePrompt();
      await load();
    } catch { /* ignore */ }
    finally { setActionLoading(null); }
  };

  const handleAction = async (action: UISchema['actions'][number], row?: any) => {
    if (!action) return;
    // 若 action 定义 prompt_field，弹出输入框
    if (action.prompt_field) {
      setPromptAction(action);
      setPromptValue('');
      setPromptRow(row || null);
      return;
    }
    // 无 body 的简单 action
    setActionLoading(action.label);
    try {
      let url = action.url;
      if (row) url = url.replace('{id}', row.id || '');
      const token = localStorage.getItem('auth_token');
      await fetch(url, {
        method: action.method,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      await load();
    } catch { /* ignore */ }
    finally { setActionLoading(null); }
  };

  if (loading) {
    return <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>;
  }

  if (!schema.type) return <p className="text-sm text-gray-400 py-4">UI Schema 缺少 type 字段</p>;

  if (!data) return <p className="text-sm text-gray-400 py-4">暂无数据</p>;

  // Unwrap common response wrappers
  let listData: any[] | null = null;
  if (Array.isArray(data)) {
    listData = data;
  } else if (data && typeof data === 'object' && Array.isArray((data as any).items)) {
    listData = (data as any).items;
  } else if (data && typeof data === 'object' && Array.isArray((data as any).data)) {
    listData = (data as any).data;
  }

  // Shared action-button renderer
  const renderActions = (row?: any) => {
    if (!schema.actions) return null;
    return (
      <div className="flex items-center gap-1">
        {schema.actions.map((action) => (
          <Button key={action.label} variant="ghost" size="sm"
            loading={actionLoading === action.label}
            onClick={() => handleAction(action, row)}>
            {action.label}
          </Button>
        ))}
      </div>
    );
  };

  // ---- Table ----
  if (schema.type === 'table' && schema.columns) {
    const rows = listData || [];
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          <span className="text-xs text-gray-400">{rows.length} 条</span>
          {/* 全局操作（不带 row 上下文） */}
          {renderActions()}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                {schema.columns.map((col) => (
                  <th key={col.key} className="text-left px-3 py-2 text-xs font-medium text-gray-500">{col.label}</th>
                ))}
                {schema.actions && <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">操作</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {rows.length === 0 ? (
                <tr><td colSpan={(schema.columns?.length || 1) + (schema.actions ? 1 : 0)} className="px-3 py-4 text-center text-gray-400">暂无数据</td></tr>
              ) : rows.map((row: any, i: number) => (
                <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  {schema.columns!.map((col) => (
                    <td key={col.key} className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      {col.type === 'badge'
                        ? <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${String(row[col.key] || '').includes('完成') ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'}`}>{row[col.key]}</span>
                        : String(row[col.key] ?? '-')}
                    </td>
                  ))}
                  {schema.actions && (
                    <td className="px-3 py-2 text-right">
                      {renderActions(row)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {renderPromptDialog()}
      </div>
    );
  }

  // ---- Stats ----
  if (schema.type === 'stats' && data && !Array.isArray(data) && schema.fields) {
    const stats = data as Record<string, any>;
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {schema.fields.map((field) => (
            <div key={field.key} className="p-4 rounded-lg bg-gray-50 dark:bg-gray-900">
              <p className="text-[10px] text-gray-500 uppercase">{field.label}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white mt-1">
                {field.format === 'duration'
                  ? `${Math.floor(Number(stats[field.key] || 0) / 60)}分${Number(stats[field.key] || 0) % 60}秒`
                  : String(stats[field.key] ?? '-')}
              </p>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ---- List ----
  if (schema.type === 'list' && schema.columns) {
    const items = listData || [];
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          {renderActions()}
        </div>
        <div className="space-y-1.5">
          {items.map((item: any, i: number) => (
            <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 dark:bg-gray-900">
              <div>
                {schema.columns!.map((col) => (
                  <span key={col.key} className="text-sm text-gray-700 dark:text-gray-300 mr-3">{String(item[col.key] ?? '-')}</span>
                ))}
              </div>
              {renderActions(item)}
            </div>
          ))}
        </div>
        {renderPromptDialog()}
      </div>
    );
  }

  // ---- Cards ----
  if (schema.type === 'cards' && schema.columns) {
    const cards = listData || [];
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          {renderActions()}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {cards.map((item: any, i: number) => (
            <div key={i} className="p-4 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700">
              {schema.columns!.map((col) => (
                <div key={col.key} className="flex justify-between py-0.5">
                  <span className="text-xs text-gray-500">{col.label}</span>
                  <span className="text-sm text-gray-900 dark:text-white">{String(item[col.key] ?? '-')}</span>
                </div>
              ))}
              {renderActions(item)}
            </div>
          ))}
        </div>
        {renderPromptDialog()}
      </div>
    );
  }

  /** Prompt dialog for actions with prompt_field */
  function renderPromptDialog() {
    if (!promptAction || !promptAction.prompt_field) return null;
    const pf = promptAction.prompt_field;
    return (
      <div className="fixed inset-0 z-[70] flex items-center justify-center">
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={closePrompt} />
        <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white">{promptAction.label}</h3>
            <button onClick={closePrompt}
              className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="p-5 space-y-3">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {pf.label}
            </label>
            <input
              type="text"
              value={promptValue}
              onChange={(e) => setPromptValue(e.target.value)}
              placeholder={pf.placeholder || ''}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              onKeyDown={(e) => { if (e.key === 'Enter') submitPrompt(); }}
              autoFocus
            />
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" size="sm" onClick={closePrompt}>取消</Button>
              <Button variant="primary" size="sm" onClick={submitPrompt}
                loading={actionLoading === promptAction.label}
                disabled={!promptValue.trim()}>
                确定
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ---- Playlist (点播单) ----
  if (schema.type === 'playlist') {
    const [roomId, setRoomId] = useState<number>(0);
    const [rooms, setRooms] = useState<any[]>([]);
    const [roomsLoaded, setRoomsLoaded] = useState(false);

    // 加载房间列表
    const loadRooms = useCallback(async () => {
      try {
        const token = localStorage.getItem('auth_token');
        const res = await fetch('/api/plugin/' + pluginName + '/ui/rooms', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const data = await res.json();
        if (Array.isArray(data)) {
          setRooms(data);
          if (data.length > 0 && roomId === 0) setRoomId(data[0].room_id);
        }
      } catch { /* ignore */ }
      setRoomsLoaded(true);
    }, [pluginName]);

    useEffect(() => { loadRooms(); }, [loadRooms]);

    const qs = (extra: Record<string, string> = {}) => {
      const p = new URLSearchParams({ room_id: String(roomId), ...extra });
      return '?' + p.toString();
    };

    // Wrap load() to include room_id
    const loadWithRoom = useCallback(async () => {
      if (!roomId) return;
      setLoading(true);
      try {
        const token = localStorage.getItem('auth_token');
        const url = '/api/plugin/' + pluginName + '/ui/playlist' + qs();
        const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
        const result = await res.json();
        setData(result);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    }, [roomId, pluginName]);

    useEffect(() => { if (roomId) loadWithRoom(); }, [loadWithRoom]);

    // re-parse data
    let plData: any[] = [];
    if (Array.isArray(data)) plData = data;
    else if (data && typeof data === 'object' && Array.isArray((data as any).items)) plData = (data as any).items;

    const items = plData;
    const stats: Record<string, number> = {};
    items.forEach((i: any) => { const s = i.status || 'pending'; stats[s] = (stats[s] || 0) + 1; });

    const toggleSel = (i: number) => {
      const next = new Set(selected);
      next.has(i) ? next.delete(i) : next.add(i);
      setSelected(next);
    };
    const clearSel = () => setSelected(new Set());
    const batchApi = async (st: string) => {
      const indices = [...selected].sort((a, b) => b - a);
      for (const i of indices) {
        await fetch('/api/plugin/' + pluginName + '/ui/status' + qs(), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ index: i, status: st }),
        });
      }
      clearSel(); await loadWithRoom();
    };
    const batchDelete = async () => {
      if (!confirm('确定删除选中的 ' + selected.size + ' 项？')) return;
      const indices = [...selected].sort((a, b) => b - a);
      for (const i of indices) {
        await fetch('/api/plugin/' + pluginName + '/ui/delete' + qs(), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ index: i }),
        });
      }
      clearSel(); await loadWithRoom();
    };

    const statusIcons: Record<string, string> = { pending: '⏳', playing: '🎵', working: '🔧', done: '✅' };
    const statusLabels: Record<string, string> = { pending: '待播', playing: '播放中', working: '操作中', done: '已完成' };

    // submitPrompt override that includes room_id
    const submitPromptWithRoom = async () => {
      if (!promptAction || !promptAction.prompt_field) return;
      setActionLoading(promptAction.label);
      try {
        const token = localStorage.getItem('auth_token');
        const body: Record<string, string> = {};
        body[promptAction.prompt_field.key] = promptValue;
        await fetch(promptAction.url + qs(), {
          method: promptAction.method,
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify(body),
        });
        closePrompt();
        await loadWithRoom();
      } catch { /* ignore */ }
      finally { setActionLoading(null); }
    };

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Room selector */}
          {rooms.length > 1 && (
            <select value={roomId} onChange={e => setRoomId(Number(e.target.value))}
              className="px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
              {rooms.map((r: any) => (
                <option key={r.room_id} value={r.room_id}>{r.room_name} ({r.count}条)</option>
              ))}
            </select>
          )}
          {rooms.length === 1 && (
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{rooms[0].room_name}</span>
          )}
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={loadWithRoom}>刷新</Button>
          <span className="text-xs text-gray-400">{items.length} 条</span>
          {schema.add_action && (
            <Button variant="primary" size="sm" onClick={() => {
              setPromptAction(schema.add_action!);
              setPromptValue('');
              setPromptRow(null);
            }}>{schema.add_action.label}</Button>
          )}
        </div>

        {/* Stats bar */}
        <div className="flex gap-2 flex-wrap">
          {Object.entries(statusLabels).map(([k, v]) =>
            stats[k] ? <span key={k} className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{statusIcons[k]} {v} {stats[k]}</span> : null
          )}
        </div>

        {/* Batch toolbar */}
        {selected.size > 0 && (
          <div className="flex items-center gap-2 flex-wrap p-2 rounded-lg bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800">
            <span className="text-xs font-medium text-primary-700 dark:text-primary-300">已选 {selected.size} 项</span>
            <Button variant="ghost" size="sm" onClick={() => batchApi('playing')}>🎵</Button>
            <Button variant="ghost" size="sm" onClick={() => batchApi('working')}>🔧</Button>
            <Button variant="ghost" size="sm" onClick={() => batchApi('done')}>✅</Button>
            <Button variant="ghost" size="sm" onClick={() => batchApi('pending')}>🔄</Button>
            <Button variant="ghost" size="sm" className="text-red-500!" onClick={batchDelete}>🗑️ 删除</Button>
            <Button variant="ghost" size="sm" onClick={clearSel}>取消</Button>
          </div>
        )}

        {/* Item list */}
        <div className="space-y-1">
          {!roomsLoaded ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
          ) : items.length === 0 ? (
            <p className="text-center text-gray-400 py-8">📭 点播单为空</p>
          ) : items.map((item: any, i: number) => {
            const st = item.status || 'pending';
            const rowCls = st === 'playing' ? 'border-emerald-400/50 bg-emerald-50/30 dark:bg-emerald-900/10' :
                           st === 'working' ? 'border-blue-400/50 bg-blue-50/30 dark:bg-blue-900/10' :
                           st === 'done' ? 'opacity-50' : '';
            return (
              <div key={i} className={`flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 ${rowCls}`}>
                <input type="checkbox" checked={selected.has(i)} onChange={() => toggleSel(i)}
                  className="w-4 h-4 rounded accent-primary-500 cursor-pointer" />
                <span className="text-xs font-bold text-gray-400 w-7 text-center">#{item.index || i + 1}</span>
                <span className="flex-1 text-sm font-medium text-gray-800 dark:text-gray-200">{item.song_name}</span>
                <span className="text-xs text-gray-400">@{item.user_name}</span>
                <span className="cursor-pointer text-sm px-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                  title="点击切换状态"
                  onClick={async () => {
                    const order = ['pending', 'playing', 'working', 'done'];
                    const nxt = order[(order.indexOf(st) + 1) % 4];
                    await fetch('/api/plugin/' + pluginName + '/ui/status' + qs(), {
                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ index: i, status: nxt }),
                    });
                    await loadWithRoom();
                  }}>{statusIcons[st]}</span>
                <div className="flex gap-0.5">
                  {['playing', 'working', 'done', 'pending'].map(s => (
                    <button key={s} title={statusLabels[s]}
                      className="px-1.5 py-0.5 text-xs rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      onClick={async () => {
                        await fetch('/api/plugin/' + pluginName + '/ui/status' + qs(), {
                          method: 'POST', headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ index: i, status: s }),
                        });
                        await loadWithRoom();
                      }}>{statusIcons[s]}</button>
                  ))}
                  <button title="删除"
                    className="px-1.5 py-0.5 text-xs rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-colors"
                    onClick={async () => {
                      if (!confirm('确定删除 #' + (item.index || i + 1) + '「' + item.song_name + '」？')) return;
                      await fetch('/api/plugin/' + pluginName + '/ui/delete' + qs(), {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ index: i }),
                      });
                      setSelected(prev => { const n = new Set(prev); n.delete(i); return n; });
                      await loadWithRoom();
                    }}>✕</button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Override prompt dialog for room_id support */}
        {promptAction && promptAction.prompt_field && (
          (() => { const pf = promptAction.prompt_field!; return (
            <div className="fixed inset-0 z-[70] flex items-center justify-center">
              <div className="fixed inset-0 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={closePrompt} />
              <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
                <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold text-gray-900 dark:text-white">{promptAction.label}</h3>
                  <button onClick={closePrompt} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"><X className="w-4 h-4" /></button>
                </div>
                <div className="p-5 space-y-3">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{pf.label}</label>
                  <input type="text" value={promptValue} onChange={(e) => setPromptValue(e.target.value)}
                    placeholder={pf.placeholder || ''}
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
                    onKeyDown={(e) => { if (e.key === 'Enter') submitPromptWithRoom(); }} autoFocus />
                  <div className="flex justify-end gap-2 pt-1">
                    <Button variant="ghost" size="sm" onClick={closePrompt}>取消</Button>
                    <Button variant="primary" size="sm" onClick={submitPromptWithRoom}
                      loading={actionLoading === promptAction.label} disabled={!promptValue.trim()}>确定</Button>
                  </div>
                </div>
              </div>
            </div>
          )})()
        )}
      </div>
    );
  }

  return <p className="text-sm text-gray-400 py-4">不支持的 UI Schema 类型: {schema.type}</p>;
}
