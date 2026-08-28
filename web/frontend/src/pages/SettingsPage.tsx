import { useEffect, useState } from 'react';
import { Settings, Save, RotateCcw, Loader2, KeyRound, Bot as BotIcon, Copy, Trash2, Plus, Eye, RefreshCw, ShieldCheck, Send } from 'lucide-react';
import { Button } from '../components/Button';
import { HoverTip } from '../components/HoverTip';
import { StatusBadge } from '../components/StatusBadge';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { AccountSetup } from '../components/AccountSetup';
import { useAuth } from '../hooks/useAuth';
import { showToast } from '../hooks/useToast';
import { ApiError } from '../api/client';
import {
  fetchPublicBot, setPublicBot, applyPublicBot, fetchPublicBotCookie,
  refreshPublicBot, verifyPublicBot, deletePublicBot,
  fetchLicenses, generateLicenses, revokeLicense,
} from '../api/client';
import type { PublicBotInfo, LicenseInfo } from '../api/types';

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function SettingsPage() {
  const { token } = useAuth();
  const [showAccount, setShowAccount] = useState(false);
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [editConfig, setEditConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [debugEnabled, setDebugEnabled] = useState(() => localStorage.getItem('debug_enabled') === 'true');
  const [logSaving, setLogSaving] = useState(false);
  const [apiPort, setApiPort] = useState(18080);
  const [portSaving, setPortSaving] = useState(false);

  // 公共 Bot
  const [publicBot, setPublicBotInfo] = useState<PublicBotInfo | null>(null);
  const [publicCookie, setPublicCookie] = useState('');
  const [publicBusy, setPublicBusy] = useState(false);
  const [viewedPublicCookie, setViewedPublicCookie] = useState('');
  const [showPublicCookie, setShowPublicCookie] = useState(false);
  const [deletePublicConfirm, setDeletePublicConfirm] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);

  // 授权码
  const [licenses, setLicenses] = useState<LicenseInfo[]>([]);
  const [licCount, setLicCount] = useState(1);
  const [licDays, setLicDays] = useState(30);
  const [licNote, setLicNote] = useState('');
  const [licBusy, setLicBusy] = useState(false);
  const [licRefreshing, setLicRefreshing] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/config', { headers: authHeaders() });
        const data = await res.json();
        setConfig(data.config);
        setEditConfig(JSON.parse(JSON.stringify(data.config)));
        const api = data.config?.server?.api_port || 18080;
        const web = data.config?.server?.web_port || 15173;
        setApiPort(api);
        localStorage.setItem('api_port', String(api));
      } catch { /* ignore */ }
      setLoading(false);
    })();
    loadPanelData();
  }, []);

  const loadPanelData = async () => {
    try {
      setPublicBotInfo(await fetchPublicBot());
      setLicenses(await fetchLicenses());
    } catch { /* ignore */ }
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ config: editConfig }),
      });
      const data = await res.json();
      if (res.ok) {
        setConfig(JSON.parse(JSON.stringify(editConfig)));
        showToast('success', data.message);
      } else {
        showToast('error', data.detail);
      }
    } catch (e: any) {
      showToast('error', '保存失败', e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleResetConfig = () => {
    if (config) setEditConfig(JSON.parse(JSON.stringify(config)));
  };

  const handleToggleDebug = async (enabled: boolean) => {
    setDebugEnabled(enabled);
    localStorage.setItem('debug_enabled', String(enabled));
    const level = enabled ? 'DEBUG' : 'INFO';
    // 同步更新下方服务器配置中 logging.level 的显示
    setEditConfig((prev) => ({
      ...prev,
      logging: { ...prev.logging, level },
    }));
    setLogSaving(true);
    try {
      await fetch('/api/config/log-level', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ level }),
      });
    } catch { /* silent */ }
    setLogSaving(false);
  };

  const handleSavePorts = async () => {
    setPortSaving(true);
    try {
      const res = await fetch('/api/config/ports', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ api_port: apiPort }),
      });
      const data = await res.json();
      if (res.ok) {
        localStorage.setItem('api_port', String(apiPort));
        showToast('success', data.message);
        // 3秒后跳转到新端口
        setTimeout(() => {
          window.location.href = `http://${window.location.hostname}:${apiPort}`;
        }, 3000);
      } else {
        showToast('error', data.detail);
      }
    } catch {
      // 后端可能已重启，静默等待刷新
    } finally {
      setPortSaving(false);
    }
  };

  const updateField = (section: string, key: string, value: any) => {
    setEditConfig((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">设置</h1>

      {/* Account Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white">
          账户安全
        </div>
        <div className="p-6 flex items-center justify-between">
          <p className="text-sm text-gray-500">修改用户名或密码后需重新登录</p>
          <Button variant="primary" size="sm" onClick={() => setShowAccount(true)}>修改账户</Button>
        </div>
      </div>
      {showAccount && token && (
        <AccountSetup token={token} onDone={() => setShowAccount(false)} />
      )}

      {/* Public Bot Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <BotIcon className="w-4 h-4 text-gray-500" />公共 Bot Cookie
        </div>
        <div className="p-6 space-y-4">
          {/* Bot 卡片(已配置时) */}
          {publicBot?.configured ? (
            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-4">
              <div className="flex items-start gap-4">
                {publicBot.icon_url ? (
                  <img
                    src={`/api/proxy/image?url=${encodeURIComponent(publicBot.icon_url)}`}
                    alt="avatar"
                    className="w-14 h-14 rounded-full object-cover shrink-0 bg-white"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center shrink-0">
                    <BotIcon className="w-7 h-7 text-primary-500" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                      {publicBot.name || '未获取到 Bot 信息'}
                    </h3>
                    <StatusBadge status={publicBot.available ? 'enabled' : 'error'}
                      label={publicBot.available ? '可用' : '不可用'} />
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    用户 ID: {publicBot.user_id || '-'} · Cookie 长度: {publicBot.cookie_length} 字符
                  </p>
                  {publicBot.introduction && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{publicBot.introduction}</p>
                  )}
                  <div className="flex flex-wrap gap-1 mt-2">
                    {publicBot.permissions.map((p) => (
                      <span key={p} className="badge badge-blue">{p}</span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
                <Button size="sm" variant="ghost" icon={<Eye className="w-4 h-4" />}
                  loading={publicBusy} disabled={publicBusy}
                  onClick={async () => {
                    setPublicBusy(true);
                    try {
                      const r = await fetchPublicBotCookie();
                      setViewedPublicCookie(r.cookie);
                      setShowPublicCookie(true);
                    } catch (e: any) {
                      showToast('error', '查看失败', e.message);
                    } finally { setPublicBusy(false); }
                  }}>
                  查看 Cookie
                </Button>
                <Button size="sm" variant="ghost" icon={<RefreshCw className="w-4 h-4" />}
                  loading={publicBusy} disabled={publicBusy}
                  onClick={async () => {
                    setPublicBusy(true);
                    try {
                      const info = await refreshPublicBot();
                      setPublicBotInfo(info);
                      showToast('success', '刷新完成', info.name || '');
                    } catch (e: any) {
                      showToast('error', '刷新失败', e.message);
                    } finally { setPublicBusy(false); }
                  }}>
                  刷新信息
                </Button>
                <Button size="sm" variant="ghost" icon={<ShieldCheck className="w-4 h-4" />}
                  loading={publicBusy} disabled={publicBusy}
                  onClick={async () => {
                    setPublicBusy(true);
                    try {
                      const r = await verifyPublicBot();
                      showToast(r.valid ? 'success' : 'error', r.message, r.name);
                    } catch (e: any) {
                      showToast('error', '验证失败', e.message);
                    } finally { setPublicBusy(false); }
                  }}>
                  验证 Cookie
                </Button>
                <Button size="sm" variant="ghost"
                  icon={<Trash2 className="w-4 h-4 text-red-500" />}
                  disabled={publicBusy}
                  onClick={() => setDeletePublicConfirm(true)}>
                  删除公共 Cookie
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">
              未配置。使用公共 Bot 的账户共享此 Cookie,账户内不可查看。
            </p>
          )}

          {/* 更新 Cookie + 下发 */}
          <div className="space-y-2">
            <textarea value={publicCookie} onChange={(e) => setPublicCookie(e.target.value)} rows={3}
              className="input w-full font-mono text-xs" placeholder="粘贴新的公共 Cookie..." />
            <div className="flex gap-2">
              <Button size="sm" icon={<KeyRound className="w-4 h-4" />}
                loading={publicBusy} disabled={publicBusy || !publicCookie.trim()}
                onClick={async () => {
                  setPublicBusy(true);
                  try {
                    await setPublicBot(publicCookie.trim(), ['SEND_LIVESTREAM_MESSAGE']);
                    showToast('success', '公共 Cookie 已保存(尚未下发)');
                    setPublicCookie('');
                    loadPanelData();
                  } catch (e: any) {
                    showToast('error', '保存失败', e.message);
                  } finally { setPublicBusy(false); }
                }}>
                保存
              </Button>
              <Button size="sm" variant="secondary" icon={<Send className="w-4 h-4" />}
                loading={publicBusy} disabled={publicBusy || !publicBot?.configured}
                onClick={async () => {
                  setPublicBusy(true);
                  try {
                    const r = await applyPublicBot();
                    showToast(r.success ? 'success' : 'error', r.message);
                    loadPanelData();
                  } catch (e: any) {
                    showToast('error', '下发失败', e.message);
                  } finally { setPublicBusy(false); }
                }}>
                下发到全部公共账户
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* License Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-gray-500" />授权码管理
          <Button variant="ghost" size="sm"
            icon={<RefreshCw className={`w-3.5 h-3.5 ${licRefreshing ? 'animate-spin' : ''}`} />}
            disabled={licRefreshing}
            onClick={async () => {
              setLicRefreshing(true);
              try {
                await loadPanelData();
                showToast('success', '列表已刷新');
              } finally {
                setLicRefreshing(false);
              }
            }}>
            刷新
          </Button>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-24">
              <label className="block text-xs text-gray-500 mb-1">数量</label>
              <input type="number" min={1} max={100} value={licCount}
                onChange={(e) => setLicCount(Number(e.target.value) || 1)} className="input text-sm" />
            </div>
            <div className="w-24">
              <label className="block text-xs text-gray-500 mb-1">天数</label>
              <input type="number" min={1} value={licDays}
                onChange={(e) => setLicDays(Number(e.target.value) || 1)} className="input text-sm" />
            </div>
            <div className="flex-1 min-w-40">
              <label className="block text-xs text-gray-500 mb-1">备注(可选)</label>
              <input value={licNote} onChange={(e) => setLicNote(e.target.value)} className="input text-sm" />
            </div>
            <Button size="sm" icon={<Plus className="w-4 h-4" />} loading={licBusy}
              onClick={async () => {
                setLicBusy(true);
                try {
                  const codes = await generateLicenses(licCount, licDays, licNote);
                  showToast('success', `已生成 ${codes.length} 个授权码`);
                  loadPanelData();
                } catch (e: any) {
                  showToast('error', '生成失败', e.message);
                } finally { setLicBusy(false); }
              }}>
              生成
            </Button>
          </div>
          {licenses.length === 0 ? (
            <p className="text-sm text-gray-400">暂无授权码</p>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {licenses.map((l) => (
                <div key={l.code}
                  className="flex items-center gap-2 py-1.5 px-2 rounded-lg bg-gray-50 dark:bg-gray-900/40 text-sm">
                  <code className="font-mono text-xs flex-1">{l.code}</code>
                  <span className="text-xs text-gray-500 shrink-0">{l.days} 天</span>
                  {l.used_at ? (
                    <span className="badge badge-gray shrink-0">已用(账户 {l.used_by_account_id})</span>
                  ) : (
                    <>
                      <span className="badge badge-green shrink-0">未用</span>
                      <Button variant="ghost" size="sm" icon={<Copy className="w-3.5 h-3.5" />}
                        onClick={() => {
                          navigator.clipboard.writeText(l.code).catch(() => {});
                          showToast('success', '已复制');
                        }} />
                      <Button variant="ghost" size="sm" icon={<Trash2 className="w-3.5 h-3.5 text-red-500" />}
                        onClick={() => setRevokeTarget(l.code)} />
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Log Level Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white">
          日志输出
        </div>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">DEBUG 输出</p>
              <p className="text-xs text-gray-400 mt-0.5">启用后日志将包含 DEBUG 级别的详细信息</p>
            </div>
            <div className="flex items-center gap-3">
              {logSaving && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
              <button
                onClick={() => handleToggleDebug(!debugEnabled)}
                disabled={logSaving}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                  ${debugEnabled ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'}`}
              >
                <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform
                  ${debugEnabled ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Port Config Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white">
          端口设置
        </div>
        <div className="p-6">
          <div className="flex items-end gap-4">
            <div className="w-40">
              <label className="block text-xs text-gray-500 mb-1">API 端口</label>
              <input type="number" value={apiPort} onChange={(e) => setApiPort(Number(e.target.value) || 18080)}
                className="input text-sm" />
            </div>
            <Button variant="primary" size="sm" icon={<Save />} onClick={handleSavePorts} loading={portSaving}>
              保存并重启
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            修改后自动重启。生产环境所有流量经由 API 端口，无需单独 Web 端口。
          </p>
        </div>
      </div>

      {/* Server Config Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Settings className="w-4 h-4 text-gray-500" />服务器配置
        </div>
        <div className="p-6 space-y-4">
          {editConfig.server && (
            <ConfigSection title="Server" path="server"
              fields={Object.fromEntries(Object.entries(editConfig.server).filter(([k]) => !['api_port', 'web_port'].includes(k)))}
              onChange={updateField} />
          )}
          {editConfig.bot && (
            <ConfigSection title="Bot" path="bot" fields={editConfig.bot} onChange={updateField} />
          )}
          {editConfig.plugin && (
            <ConfigSection title="Plugin" path="plugin" fields={editConfig.plugin} onChange={updateField} />
          )}
          {editConfig.logging && (
            <ConfigSection title="Logging" path="logging" fields={editConfig.logging} onChange={updateField} />
          )}

          <div className="flex items-center gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
            <Button variant="primary" size="sm" icon={<Save />} onClick={handleSaveConfig} loading={saving}>
              保存配置
            </Button>
            <Button variant="ghost" size="sm" icon={<RotateCcw />} onClick={handleResetConfig}>
              重置
            </Button>
          </div>
        </div>
      </div>

      {/* 公共 Cookie 查看弹框 */}
      {showPublicCookie && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setShowPublicCookie(false)} />
          <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-5">
            <h3 className="font-semibold mb-3">公共 Cookie 信息</h3>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs bg-gray-100 dark:bg-gray-900 p-3 rounded-lg">{viewedPublicCookie}</pre>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="ghost" size="sm" icon={<Copy className="w-3.5 h-3.5" />}
                onClick={() => {
                  navigator.clipboard.writeText(viewedPublicCookie).catch(() => {});
                  showToast('success', '已复制');
                }}>
                复制
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setShowPublicCookie(false)}>关闭</Button>
            </div>
          </div>
        </div>
      )}

      {/* 撤销授权码确认 */}
      <ConfirmDialog
        open={revokeTarget !== null}
        title="撤销授权码"
        message={`确定撤销授权码「${revokeTarget ?? ''}」吗？撤销后该码将无法兑换。`}
        danger
        loading={licBusy}
        onConfirm={async () => {
          if (!revokeTarget) return;
          setLicBusy(true);
          try {
            await revokeLicense(revokeTarget);
            showToast('success', '已撤销');
            setRevokeTarget(null);
            loadPanelData();
          } catch (e: any) {
            showToast('error', '撤销失败', e.message);
          } finally { setLicBusy(false); }
        }}
        onCancel={() => setRevokeTarget(null)}
      />

      {/* 删除公共 Cookie 确认 */}
      <ConfirmDialog
        open={deletePublicConfirm}
        title="删除公共 Cookie"
        message="删除后,使用公共 Bot 的账户在下次重启后将无法连接(已运行的实例不受影响)。确定删除吗？"
        danger
        loading={publicBusy}
        onConfirm={async () => {
          setPublicBusy(true);
          try {
            await deletePublicBot();
            showToast('success', '公共 Cookie 已删除');
            setDeletePublicConfirm(false);
            loadPanelData();
          } catch (e: any) {
            showToast('error', '删除失败', e.message);
          } finally { setPublicBusy(false); }
        }}
        onCancel={() => setDeletePublicConfirm(false)}
      />
    </div>
  );
}

const FIELD_LABELS: Record<string, string> = {
  data_dir: '数据目录',
  state_file: '状态文件',
  timer_interval: '定时消息间隔(秒)',
  pip_mirror: 'pip 镜像源',
  dir: '日志目录',
};

function ConfigSection({
  title, path, fields, onChange,
}: {
  title: string; path: string; fields: Record<string, any>; onChange: (s: string, k: string, v: any) => void;
}) {
  return (
    <div>
      <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">{title}</h3>
      <div className="space-y-3 pl-2 border-l-2 border-gray-100 dark:border-gray-700">
        {Object.entries(fields).map(([key, value]) => (
          <div key={key} className="flex items-center gap-3">
            <label className="relative group w-32 text-xs text-gray-500 dark:text-gray-400 shrink-0 truncate">
              {FIELD_LABELS[key] || key}
              <HoverTip text={key} />
            </label>
            {typeof value === 'boolean' ? (
              <button
                onClick={() => onChange(path, key, !value)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                  ${value ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'}`}
              >
                <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform
                  ${value ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
              </button>
            ) : typeof value === 'number' ? (
              <input type="number" value={value}
                onChange={(e) => onChange(path, key, e.target.value === '' ? '' : Number(e.target.value))}
                className="input text-xs flex-1" />
            ) : (
              <input type="text" value={String(value)}
                onChange={(e) => onChange(path, key, e.target.value)}
                className="input text-xs flex-1" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
