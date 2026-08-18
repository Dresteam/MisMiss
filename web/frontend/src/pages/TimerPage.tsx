import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Clock, Plus, Trash2, ChevronUp, ChevronDown, SkipForward,
  Pencil, Loader2, RefreshCw, X, Globe, Radio, Timer, Send,
} from 'lucide-react';
import { showToast } from '../hooks/useToast';
import { Button } from '../components/Button';
import { HoverTip } from '../components/HoverTip';
import { ConfirmDialog } from '../components/ConfirmDialog';

interface TimerEntry {
  message_id: string;
  live_id: number;
  message: string;
  index: number;
  seconds_until_next: number;
}

interface RoomQueue {
  live_id: number;
  messages: TimerEntry[];
  /** 合并轮转位置（全局 + 独立消息，单指针） */
  position: number;
}

interface TimerData {
  interval: number;
  next_tick_in: number;
  global: TimerEntry[];
  rooms: RoomQueue[];
}

/** 将秒格式化为可读倒计时 */
function formatCountdown(seconds: number): string {
  if (seconds <= 0) return '即将执行';
  if (seconds < 60) return `${seconds}秒`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}分${secs}秒`;
}

/** 定时消息队列管理页面 */
export function TimerPage() {
  const [data, setData] = useState<TimerData>({ interval: 0, next_tick_in: 0, global: [], rooms: [] });
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  // 直播间筛选（0 = 未选中）
  const [roomFilter, setRoomFilter] = useState<number>(0);
  const [tick, setTick] = useState<number>(0);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 添加 / 编辑对话框
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLiveId, setEditLiveId] = useState('');
  const [editMessage, setEditMessage] = useState('');

  // 删除确认
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // 间隔编辑
  const [intervalInput, setIntervalInput] = useState('');
  const [savingInterval, setSavingInterval] = useState(false);

  // soft=true 时静默更新列表数据，不显示整页加载动画（操作后局部刷新用）
  const load = useCallback(async (soft = false) => {
    if (!soft) setLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/timer/list', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const d = await res.json();
      if (d && typeof d === 'object') {
        setData(d as TimerData);
        setIntervalInput(String(d.interval || ''));
        setTick(0);  // 重置本地倒计时递减基准
        // 若当前筛选的直播间已不存在，回退到第一个
        setRoomFilter(prev => {
          if (prev === 0) return (d as TimerData).rooms[0]?.live_id ?? 0;
          return (d as TimerData).rooms.some(r => r.live_id === prev)
            ? prev : (d as TimerData).rooms[0]?.live_id ?? 0;
        });
      }
    } catch { /* ignore */ }
    finally { if (!soft) setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // 每秒刷新一次（本地递减倒计时）
  useEffect(() => {
    tickerRef.current = setInterval(() => setTick(t => t + 1), 1000);
    return () => { if (tickerRef.current) clearInterval(tickerRef.current); };
  }, []);

  // 每 30 秒静默同步一次（校准倒计时，不闪烁整页）
  useEffect(() => {
    const sync = setInterval(() => load(true), 30000);
    return () => clearInterval(sync);
  }, [load]);

  const api = async (path: string, method: string, body?: any) => {
    const token = localStorage.getItem('auth_token');
    const res = await fetch('/api/timer' + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '请求失败');
    }
    return res.json();
  };

  const openAdd = () => {
    setEditingId(null);
    setEditLiveId(roomFilter > 0 ? String(roomFilter) : '');
    setEditMessage('');
    setEditorOpen(true);
  };

  const openEdit = (e: TimerEntry) => {
    setEditingId(e.message_id);
    setEditLiveId(e.live_id === 0 ? '0' : String(e.live_id));
    setEditMessage(e.message);
    setEditorOpen(true);
  };

  const handleSave = async () => {
    try {
      if (editingId) {
        await api(`/${editingId}`, 'PUT', { message: editMessage });
        showToast('success', '定时消息已更新');
      } else {
        await api('/add', 'POST', { live_id: Number(editLiveId) || 0, message: editMessage });
        showToast('success', '定时消息已添加');
      }
      setEditorOpen(false);
      await load(true);
    } catch (e: any) { showToast('error', '操作失败', e.message); }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api(`/${deleteTarget}`, 'DELETE');
      showToast('success', '已删除');
      setDeleteTarget(null);
      await load(true);
    } catch (e: any) { showToast('error', '删除失败', e.message); }
  };

  const handleMove = async (e: TimerEntry, direction: number) => {
    setBusyId(e.message_id);
    try {
      await api(`/${e.message_id}/move`, 'POST', { direction });
      await load(true);
    } catch (err: any) { showToast('error', '移动失败', err.message); }
    finally { setBusyId(null); }
  };

  const handleSkip = async (e: TimerEntry) => {
    setBusyId(e.message_id);
    try {
      // 跳过 = 指针后移一位（全局消息需指定目标直播间）
      const res = await api(`/${e.message_id}/skip`, 'POST', { live_id: roomFilter });
      showToast('success', res.message || '已跳过，指针已后移');
      await load(true);
    } catch (err: any) { showToast('error', '操作失败', err.message); }
    finally { setBusyId(null); }
  };

  const handleSendNow = async (e: TimerEntry) => {
    setBusyId(e.message_id);
    try {
      await api(`/${e.message_id}/send`, 'POST', { live_id: roomFilter });
      showToast('success', '已立即发送');
      await load(true);
    } catch (err: any) { showToast('error', '发送失败', err.message); }
    finally { setBusyId(null); }
  };

  const handleSaveInterval = async () => {
    setSavingInterval(true);
    try {
      const res = await api('/interval', 'PUT', { interval: Number(intervalInput) });
      showToast('success', res.message);
      await load(true);
    } catch (e: any) { showToast('error', '保存失败', e.message); }
    finally { setSavingInterval(false); }
  };

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  // 当前选中的直播间
  const currentRoom = data.rooms.find(r => r.live_id === roomFilter) || null;

  const totalCount = data.global.length + data.rooms.reduce((s, r) => s + r.messages.length, 0);

  // 合并轮转周期：全局 + 选中直播间独立消息，每间隔发送一条
  const cycleSeconds = Math.max(1, data.global.length + (currentRoom?.messages.length ?? 0))
    * Math.max(1, data.interval);

  /** 渲染一条消息卡片。isNext: 是否为即将执行的消息（仅该消息可跳过/立即发送） */
  const renderEntry = (e: TimerEntry, isNext: boolean, cycleSeconds: number,
    entriesCount: number, scope: 'global' | 'room') => {
    // 倒计时采用取模滚动：到达 0 后自动回到完整轮转周期
    // （全局 + 独立消息合并轮转），消息被立即发送/跳过（指针推进）也能持续同步
    const remaining = e.seconds_until_next - tick;
    const cd = ((remaining % cycleSeconds) + cycleSeconds) % cycleSeconds;
    return (
      <div key={e.message_id}
        className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 hover:shadow-sm transition-shadow">
        <span className="text-xs font-bold text-gray-400 w-8 text-center shrink-0">#{e.index + 1}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-gray-800 dark:text-gray-200 truncate">{e.message}</p>
          <p className="text-[10px] text-gray-400 font-mono mt-0.5">
            {scope === 'global' ? '全局 · 所有直播间轮播' : `直播间 ${e.live_id}`} · {e.message_id}
            {isNext && <span className="ml-2 text-primary-500 font-semibold">▶ 即将执行</span>}
          </p>
        </div>
        <span className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold ${
          cd <= 10
            ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
        }`}>
          <Timer className="w-3 h-3 inline mr-0.5 -mt-0.5" />
          {formatCountdown(cd)}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          <button disabled={busyId === e.message_id || e.index === 0}
            onClick={() => handleMove(e, -1)}
            className="relative group p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 transition-colors">
            <ChevronUp className="w-4 h-4" />
            {!(busyId === e.message_id || e.index === 0) && <HoverTip text="上移" />}
          </button>
          <button disabled={busyId === e.message_id || e.index === entriesCount - 1}
            onClick={() => handleMove(e, 1)}
            className="relative group p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 transition-colors">
            <ChevronDown className="w-4 h-4" />
            {!(busyId === e.message_id || e.index === entriesCount - 1) && <HoverTip text="下移" />}
          </button>
          <button disabled={!isNext || busyId === e.message_id}
            onClick={() => handleSendNow(e)}
            className="relative group p-1.5 rounded-lg hover:bg-emerald-100 dark:hover:bg-emerald-900/30 text-emerald-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
            <Send className="w-4 h-4" />
            {!(!isNext || busyId === e.message_id) && <HoverTip text="立即发送" />}
          </button>
          <button disabled={!isNext || busyId === e.message_id}
            onClick={() => handleSkip(e)}
            className="relative group p-1.5 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30 text-amber-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
            <SkipForward className="w-4 h-4" />
            {!(!isNext || busyId === e.message_id) && <HoverTip text="跳过当前待执行消息（指针后移）" />}
          </button>
          <button onClick={() => openEdit(e)}
            className="relative group p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <Pencil className="w-4 h-4" />
            <HoverTip text="编辑" />
          </button>
          <button onClick={() => setDeleteTarget(e.message_id)}
            className="relative group p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-colors">
            <Trash2 className="w-4 h-4" />
            <HoverTip text="删除" />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">定时消息队列</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {totalCount} 条消息 · 先播全局消息，再播直播间消息
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" icon={<RefreshCw />} onClick={() => load()}>刷新</Button>
          <Button variant="primary" icon={<Plus />} onClick={openAdd}>添加消息</Button>
        </div>
      </div>

      {/* 间隔设置 */}
      <div className="flex items-center gap-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
        <Timer className="w-5 h-5 text-primary-500 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-200">发送间隔</p>
          <p className="text-[10px] text-gray-400">修改后实时生效，不重置执行位置指针</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <input type="number" min={1} value={intervalInput}
            onChange={e => setIntervalInput(e.target.value)}
            className="w-24 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
          <span className="text-sm text-gray-500">秒</span>
          <Button variant="primary" size="sm" onClick={handleSaveInterval} loading={savingInterval}>保存</Button>
        </div>
      </div>

      {/* 直播间筛选 */}
      <div className="flex items-center gap-3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
        <Radio className="w-5 h-5 text-emerald-500 shrink-0" />
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200">直播间</span>
        <select value={roomFilter} onChange={e => setRoomFilter(Number(e.target.value))}
          className="flex-1 max-w-xs px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 outline-none">
          {data.rooms.length === 0 ? (
            <option value={0}>暂无直播间</option>
          ) : data.rooms.map(r => (
            <option key={r.live_id} value={r.live_id}>
              直播间 {r.live_id}（{r.messages.length} 条独立消息）
            </option>
          ))}
        </select>
      </div>

      {data.rooms.length === 0 && data.global.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <Clock className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-gray-400">暂无定时消息</p>
          <p className="text-xs text-gray-400 mt-1">添加全局消息（直播间 ID 填 0）或指定直播间 ID</p>
          <div className="mt-4 flex justify-center">
            <Button variant="primary" icon={<Plus />} onClick={openAdd}>添加消息</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* 全局消息（合并显示，先于直播间消息执行） */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-3">
              <Globe className="w-4 h-4 text-primary-500" /> 全局定时消息
              <span className="text-xs text-gray-400 font-normal">
                （{data.global.length} 条{currentRoom && currentRoom.position < data.global.length
                  ? ` · 指针 #${currentRoom.position + 1}` : ''}）
              </span>
            </h2>
            {data.global.length === 0 ? (
              <p className="text-center text-gray-400 py-6 text-sm">暂无全局消息</p>
            ) : data.global.map(e =>
              renderEntry(e,
                currentRoom
                  ? currentRoom.position < data.global.length && e.index === currentRoom.position
                  : false,
                cycleSeconds, data.global.length, 'global')
            )}
          </div>

          {/* 直播间独立消息 */}
          {currentRoom && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-3">
              <Radio className="w-4 h-4 text-emerald-500" /> 直播间 {currentRoom.live_id} 独立消息
              <span className="text-xs text-gray-400 font-normal">
                （{currentRoom.messages.length} 条{currentRoom.position >= data.global.length
                  ? ` · 指针 #${currentRoom.position - data.global.length + 1}` : ''}）
              </span>
            </h2>
            {currentRoom.messages.length === 0 ? (
              <p className="text-center text-gray-400 py-6 text-sm">该直播间暂无独立消息</p>
            ) : currentRoom.messages.map(e =>
              renderEntry(e,
                currentRoom.position >= data.global.length &&
                  currentRoom.position - data.global.length === e.index,
                cycleSeconds, currentRoom.messages.length, 'room')
            )}
          </div>
          )}
        </div>
      )}

      {/* 添加/编辑对话框 */}
      {editorOpen && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={() => setEditorOpen(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 animate-slide-in-up">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
              <h3 className="font-semibold text-gray-900 dark:text-white">
                {editingId ? '编辑定时消息' : '添加定时消息'}
              </h3>
              <button onClick={() => setEditorOpen(false)}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              {!editingId && (
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    直播间 ID（0 = 全局消息）
                  </label>
                  <input type="number" value={editLiveId} onChange={e => setEditLiveId(e.target.value)}
                    placeholder="如 12345，或 0 表示全局"
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500" />
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-500 mb-1">消息内容</label>
                <textarea value={editMessage} onChange={e => setEditMessage(e.target.value)}
                  rows={3} placeholder="定时播报的消息内容..."
                  className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm outline-none focus:ring-2 focus:ring-primary-500 resize-y" />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button variant="ghost" size="sm" onClick={() => setEditorOpen(false)}>取消</Button>
                <Button variant="primary" size="sm" onClick={handleSave} disabled={!editMessage.trim()}>保存</Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog open={!!deleteTarget} title="删除定时消息"
        message="确定删除这条定时消息吗？"
        danger onConfirm={handleDelete} onCancel={() => setDeleteTarget(null)} />
    </div>
  );
}
