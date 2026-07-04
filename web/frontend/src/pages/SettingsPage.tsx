import { useEffect, useState } from 'react';
import { Settings, Save, RotateCcw, Loader2 } from 'lucide-react';
import { Button } from '../components/Button';
import { showToast } from '../hooks/useToast';

export function SettingsPage() {
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [editConfig, setEditConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [debugEnabled, setDebugEnabled] = useState(() => localStorage.getItem('debug_enabled') === 'true');
  const [logSaving, setLogSaving] = useState(false);
  const [apiPort, setApiPort] = useState(8000);
  const [webPort, setWebPort] = useState(5173);
  const [portSaving, setPortSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/config');
        const data = await res.json();
        setConfig(data.config);
        setEditConfig(JSON.parse(JSON.stringify(data.config)));
        setApiPort(data.config?.server?.api_port || 8000);
        setWebPort(data.config?.server?.web_port || 5173);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
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
    setLogSaving(true);
    try {
      await fetch('/api/config/log-level', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: enabled ? 'DEBUG' : 'INFO' }),
      });
    } catch { /* silent */ }
    setLogSaving(false);
  };

  const handleSavePorts = async () => {
    setPortSaving(true);
    try {
      const res = await fetch('/api/config/ports', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_port: apiPort, web_port: webPort }),
      });
      const data = await res.json();
      if (res.ok) {
        showToast('success', data.message);
        // 后端重启中，前端30秒后自动刷新
        setTimeout(() => window.location.reload(), 3000);
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
              <input type="number" value={apiPort} onChange={(e) => setApiPort(Number(e.target.value) || 8000)}
                className="input text-sm" />
            </div>
            <div className="w-40">
              <label className="block text-xs text-gray-500 mb-1">Web 端口</label>
              <input type="number" value={webPort} onChange={(e) => setWebPort(Number(e.target.value) || 5173)}
                className="input text-sm" />
            </div>
            <Button variant="primary" size="sm" icon={<Save />} onClick={handleSavePorts} loading={portSaving}>
              保存并重启
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            修改后端端口后自动重启。Web 端口需手动重启前端。
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
            <ConfigSection title="Server" path="server" fields={editConfig.server} onChange={updateField} />
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
            <label className="w-32 text-xs text-gray-500 dark:text-gray-400 shrink-0 truncate" title={key}>
              {FIELD_LABELS[key] || key}
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
