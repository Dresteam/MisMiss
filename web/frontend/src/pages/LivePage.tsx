import { useEffect, useState, useCallback } from 'react';
import {
  Radio, Plus, Send, Trash2, RefreshCw, TrendingUp,
  Loader2, LogIn, LogOut, RotateCw,
} from 'lucide-react';
import {
  fetchLiveList, addLive, refreshLive, enableLive, disableLive,
  joinLive, quitLive, removeLive, sendLiveMessage,
} from '../api/client';
import type { LivestreamInfo } from '../api/types';
import { showToast } from '../hooks/useToast';
import { StatusBadge } from '../components/StatusBadge';
import { Button } from '../components/Button';
import { MarqueeText } from '../components/MarqueeText';
import { RoomSelect } from '../components/RoomSelect';
import { ConfirmDialog } from '../components/ConfirmDialog';

export function LivePage() {
  const [lives, setLives] = useState<LivestreamInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingMap, setProcessingMap] = useState<Record<number, string | null>>({});
  const [newLiveId, setNewLiveId] = useState('');
  const [adding, setAdding] = useState(false);
  const [msgLiveId, setMsgLiveId] = useState<number | null>(null);
  const [msgText, setMsgText] = useState('');
  const [msgPriority, setMsgPriority] = useState(0);
  const [sending, setSending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string; message: string; variant: 'danger' | 'default'; run: () => Promise<void>;
  } | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchLiveList();
      setLives(data.livestreams);
      if (data.livestreams.length > 0 && !msgLiveId) {
        setMsgLiveId(data.livestreams[0].live_id);
      }
    } catch (e: any) {
      showToast('error', '加载失败', e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [load]);

  // ---- Per-row processing helpers ----

  const setProcessing = (liveId: number, action: string | null) => {
    setProcessingMap((prev) => ({ ...prev, [liveId]: action }));
  };

  // Combined: enable + join
  const handleEnable = async (liveId: number) => {
    if (processingMap[liveId]) return;
    setProcessing(liveId, 'enabling');
    try {
      await enableLive(liveId);
      await joinLive(liveId);
      showToast('success', `直播间 ${liveId} 已启用并连接`);
      await load();
    } catch (e: any) {
      showToast('error', '启用失败', e.message);
    } finally {
      setProcessing(liveId, null);
    }
  };

  // Combined: quit + disable
  const handleDisable = async (liveId: number) => {
    if (processingMap[liveId]) return;
    setProcessing(liveId, 'disabling');
    try {
      await quitLive(liveId);
      await disableLive(liveId);
      showToast('success', `直播间 ${liveId} 已停用并断开`);
      await load();
    } catch (e: any) {
      showToast('error', '停用失败', e.message);
    } finally {
      setProcessing(liveId, null);
    }
  };

  const handleJoin = async (liveId: number) => {
    if (processingMap[liveId]) return;
    setProcessing(liveId, 'joining');
    try {
      await joinLive(liveId);
      showToast('success', '已进入直播间');
      await load();
    } catch (e: any) {
      showToast('error', '进入失败', e.message);
    } finally {
      setProcessing(liveId, null);
    }
  };

  const handleQuit = async (liveId: number) => {
    if (processingMap[liveId]) return;
    setProcessing(liveId, 'quitting');
    try {
      await quitLive(liveId);
      showToast('success', '已退出直播间');
      await load();
    } catch (e: any) {
      showToast('error', '退出失败', e.message);
    } finally {
      setProcessing(liveId, null);
    }
  };

  const handleRefreshLive = async (liveId: number) => {
    if (processingMap[liveId]) return;
    setProcessing(liveId, 'refreshing');
    try {
      await refreshLive(liveId);
      showToast('success', '已刷新');
      await load();
    } catch (e: any) {
      showToast('error', '刷新失败', e.message);
    } finally {
      setProcessing(liveId, null);
    }
  };

  const handleAdd = async () => {
    const id = parseInt(newLiveId);
    if (!id || id <= 0) { showToast('warning', '请输入有效的直播间 ID'); return; }
    setAdding(true);
    try {
      const live = await addLive({ live_id: id });
      setNewLiveId('');
      showToast('success', '直播间已添加', live.room_name || `ID: ${id}`);
      await load();
    } catch (e: any) {
      showToast('error', '添加失败', e.message);
    } finally {
      setAdding(false);
    }
  };

  const handleSendMsg = async () => {
    if (!msgLiveId || !msgText.trim()) { showToast('warning', '请选择直播间并输入消息'); return; }
    setSending(true);
    try {
      const res = await sendLiveMessage({ live_id: msgLiveId, text: msgText.trim(), priority: msgPriority });
      setMsgText('');
      showToast('success', '消息已发送', res.message);
    } catch (e: any) {
      showToast('error', '发送失败', e.message);
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">直播间管理</h1>
        <Button variant="ghost" size="sm"
          icon={<RefreshCw className={refreshing ? 'animate-spin' : ''} />}
          onClick={async () => { setRefreshing(true); await load(); showToast('success', '列表已刷新'); setRefreshing(false); }}
          disabled={refreshing}>刷新</Button>
      </div>

      {/* Add form */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-end gap-2 lg:gap-3">
          <div className="flex-1 min-w-0">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">添加直播间</label>
            <input type="number" value={newLiveId} onChange={(e) => setNewLiveId(e.target.value)}
              placeholder="输入直播间 ID..." className="input text-sm"
              inputMode="numeric"
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()} />
          </div>
          <Button variant="primary" icon={<Plus />} onClick={handleAdd} loading={adding}
            className="shrink-0 px-3 lg:px-4">添加</Button>
        </div>
      </div>

      {/* Livestream Table — desktop only */}
      {lives.length === 0 ? (
        <div className="hidden lg:block text-center py-16 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <Radio className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-gray-400">暂无直播间</p>
          <p className="text-xs text-gray-400 mt-1">在上方输入直播间 ID 添加</p>
        </div>
      ) : (
        <div className="hidden lg:block bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                  <th className="text-left px-4 py-3 font-medium text-gray-500">ID</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">房间名</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">热度</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">状态</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-500">连接</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-500">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                {lives.map((live) => {
                  const isBusy = !!processingMap[live.live_id];
                  const action = processingMap[live.live_id];
                  const isEnabling = action === 'enabling';
                  const isDisabling = action === 'disabling';

                  return (
                    <tr key={live.live_id}
                      className={`hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors ${isBusy ? 'opacity-70' : ''}`}>
                      <td className="px-4 py-3 font-mono text-xs">{live.live_id}</td>
                      <td className="px-4 py-3 max-w-[200px]">
                        <p className="font-medium text-gray-900 dark:text-white">
                          <MarqueeText text={live.room_name || '(未知)'} />
                        </p>
                        <p className="text-[10px] text-gray-400 flex items-center gap-1">
                          <span className={`inline-block w-1.5 h-1.5 rounded-full ${live.creator_is_online ? 'bg-emerald-500' : 'bg-gray-400'}`} />
                          {live.creator_name || '-'}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 text-gray-500">
                          <TrendingUp className="w-3.5 h-3.5" />
                          {live.score.toLocaleString()}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={live.enabled ? 'enabled' : 'disabled'} size="sm" />
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={live.is_connected ? 'online' : 'offline'}
                          pulse={live.is_connected} size="sm" />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          {live.enabled ? (
                            <Button variant="secondary" size="sm"
                              onClick={() => handleDisable(live.live_id)}
                              loading={isDisabling} disabled={isBusy}
                              icon={isDisabling ? undefined : <LogOut />}>
                              {isDisabling ? '停用中' : '停用'}
                            </Button>
                          ) : (
                            <Button variant="success" size="sm"
                              onClick={() => handleEnable(live.live_id)}
                              loading={isEnabling} disabled={isBusy}
                              icon={isEnabling ? undefined : <LogIn />}>
                              {isEnabling ? '启用中' : '启用'}
                            </Button>
                          )}
                          {live.enabled && !live.is_connected && (
                            <Button variant="outline" size="sm"
                              onClick={() => handleJoin(live.live_id)}
                              loading={action === 'joining'} disabled={isBusy}
                              icon={<LogIn />}>进入</Button>
                          )}
                          {!live.enabled && live.is_connected && (
                            <Button variant="outline" size="sm"
                              onClick={() => handleQuit(live.live_id)}
                              loading={action === 'quitting'} disabled={isBusy}
                              icon={<LogOut />}>退出</Button>
                          )}
                          <Button variant="ghost" size="sm"
                            icon={<RotateCw className={action === 'refreshing' ? 'animate-spin' : ''} />}
                            onClick={() => handleRefreshLive(live.live_id)}
                            disabled={isBusy} />
                          <Button variant="ghost" size="sm"
                            onClick={() => setConfirmAction({
                              title: '移除直播间',
                              message: `确定要移除 ${live.room_name || live.live_id} 吗？此操作不可撤销。`,
                              variant: 'danger',
                              run: async () => { await removeLive(live.live_id); await load(); showToast('success', '已移除'); },
                            })}
                            disabled={isBusy}
                            icon={<Trash2 className="text-red-500" />} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Mobile: card view */}
      <div className="lg:hidden">
        {lives.length === 0 ? (
          <div className="text-center py-16 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
            <Radio className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
            <p className="text-gray-500 dark:text-gray-400">暂无直播间</p>
            <p className="text-xs text-gray-400 mt-1">在上方输入直播间 ID 添加</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {lives.map((live) => {
              const isBusy = !!processingMap[live.live_id];
              const action = processingMap[live.live_id];
              return (
                <div key={live.live_id} className={`bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 ${isBusy ? 'opacity-70' : ''}`}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-gray-900 dark:text-white">
                        <MarqueeText text={live.room_name || '(未知)'} />
                      </p>
                      <p className="text-[11px] text-gray-400 flex items-center gap-1 mt-0.5">
                        <span className={`inline-block w-1.5 h-1.5 rounded-full ${live.creator_is_online ? 'bg-emerald-500' : 'bg-gray-400'}`} />
                        {live.creator_name || '-'} · ID {live.live_id}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <StatusBadge status={live.enabled ? 'enabled' : 'disabled'} size="sm" />
                      <StatusBadge status={live.is_connected ? 'online' : 'offline'} pulse={live.is_connected} size="sm" />
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-gray-500 flex items-center gap-1">
                      <TrendingUp className="w-3 h-3" />{live.score.toLocaleString()}
                    </div>
                    <div className="flex items-center gap-1">
                      {live.enabled ? (
                        <Button variant="secondary" size="sm" onClick={() => handleDisable(live.live_id)}
                          loading={action === 'disabling'} disabled={isBusy}>{action === 'disabling' ? '...' : '停用'}</Button>
                      ) : (
                        <Button variant="success" size="sm" onClick={() => handleEnable(live.live_id)}
                          loading={action === 'enabling'} disabled={isBusy}>{action === 'enabling' ? '...' : '启用'}</Button>
                      )}
                      <Button variant="ghost" size="sm" icon={<RotateCw className={action === 'refreshing' ? 'animate-spin' : ''} />}
                        onClick={() => handleRefreshLive(live.live_id)} disabled={isBusy} />
                      <Button variant="ghost" size="sm"
                        onClick={() => setConfirmAction({ title: '移除直播间', message: `确定要移除 ${live.room_name || live.live_id} 吗？`, variant: 'danger',
                          run: async () => { await removeLive(live.live_id); await load(); showToast('success', '已移除'); } })}
                        disabled={isBusy} icon={<Trash2 className="text-red-500" />} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Send Message Bar */}
      {lives.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white">
            发送弹幕
          </div>
          <div className="p-4 lg:p-6">
            <div className="flex flex-col gap-3">
              {/* 直播间 + 优先级：移动端一行两个，桌面端正常 */}
              <div className="flex gap-3">
                <div className="flex-1 min-w-0">
                  <label className="block text-xs text-gray-500 mb-1">目标直播间</label>
                  <RoomSelect
                    lives={lives}
                    selectedId={msgLiveId}
                    onSelect={(id) => setMsgLiveId(id)} />
                </div>
                <div className="w-24 lg:w-20 shrink-0">
                  <label className="block text-xs text-gray-500 mb-1">优先级</label>
                  <input type="number" value={msgPriority}
                    onChange={(e) => setMsgPriority(parseInt(e.target.value) || 0)}
                    className="input text-xs" min={0} />
                </div>
              </div>
              {/* 消息输入 + 发送：移动端输入框全宽、发送按钮在下方 */}
              <div className="flex gap-2">
                <input type="text" value={msgText}
                  onChange={(e) => setMsgText(e.target.value)}
                  placeholder="输入要发送的弹幕..."
                  className="input flex-1 min-w-0 text-sm"
                  onKeyDown={(e) => e.key === 'Enter' && handleSendMsg()} />
                <Button variant="primary" icon={<Send />} onClick={handleSendMsg}
                  loading={sending} disabled={!msgText.trim()}
                  className="shrink-0 px-3 lg:px-4">发送</Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog open={!!confirmAction} title={confirmAction?.title || ''}
        message={confirmAction?.message || ''} variant={confirmAction?.variant || 'default'}
        onConfirm={async () => { if (confirmAction) { await confirmAction.run(); setConfirmAction(null); } }}
        onCancel={() => setConfirmAction(null)} />
    </div>
  );
}
