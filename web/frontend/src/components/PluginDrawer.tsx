import { useEffect, useState } from 'react';
import {
  X, Puzzle, Zap, Shield, Settings, FileText, BookOpen, History, Loader2,
} from 'lucide-react';
import { MarkdownRenderer } from './MarkdownRenderer';
import {
  fetchPluginDetail,
  fetchPluginPermissions,
  fetchPluginConfig,
  updatePluginPermission,
  updatePluginConfig,
  fetchPluginReadme,
  fetchPluginChangelog,
} from '../api/client';
import type { PluginDetail, PluginPermissionInfo, PluginConfigResponse } from '../api/types';
import { showToast } from '../hooks/useToast';
import { StatusBadge } from './StatusBadge';
import { DynamicConfigForm } from './DynamicConfigForm';

interface Props {
  pluginName: string;
  open: boolean;
  onClose: () => void;
  onUpdate: () => void;
}

type TabId = 'info' | 'handlers' | 'permissions' | 'config' | 'readme' | 'changelog';

interface Tab {
  id: TabId;
  label: string;
  icon: typeof Puzzle;
}

const PERM_DESC: Record<string, string> = {
  SEND_LIVESTREAM_MESSAGE: '发送直播间消息',
  SEND_PRIVATE_MESSAGE: '发送私信',
  SEND_BACKPACK_GIFT: '赠送背包礼物',
  SEND_GIFT: '赠送直售礼物',
  EXPOSE_COOKIE: '查看完整 Cookie',
};

const tabs: Tab[] = [
  { id: 'info', label: '基本信息', icon: Puzzle },
  { id: 'handlers', label: '监听器', icon: Zap },
  { id: 'permissions', label: '权限管理', icon: Shield },
  { id: 'config', label: '配置', icon: Settings },
  { id: 'readme', label: '文档', icon: BookOpen },
  { id: 'changelog', label: '更新日志', icon: History },
];

export function PluginDrawer({ pluginName, open, onClose, onUpdate }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>('info');
  const [detail, setDetail] = useState<PluginDetail | null>(null);
  const [permissions, setPermissions] = useState<PluginPermissionInfo | null>(null);
  const [config, setConfig] = useState<PluginConfigResponse | null>(null);
  const [readme, setReadme] = useState('');
  const [changelog, setChangelog] = useState('');
  const [loading, setLoading] = useState(true);
  const [permLoading, setPermLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !pluginName) return;
    loadAll();
  }, [open, pluginName]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [d, p, c] = await Promise.all([
        fetchPluginDetail(pluginName),
        fetchPluginPermissions(pluginName).catch(() => null),
        fetchPluginConfig(pluginName).catch(() => null),
      ]);
      setDetail(d);
      setPermissions(p);
      setConfig(c);

      // Load readme/changelog if available
      if (d.has_readme) {
        fetchPluginReadme(pluginName)
          .then((r) => setReadme(r.content))
          .catch(() => {});
      }
      if (d.has_changelog) {
        fetchPluginChangelog(pluginName)
          .then((r) => setChangelog(r.content))
          .catch(() => {});
      }
    } catch (e: any) {
      showToast('error', '加载插件详情失败', e.message);
    } finally {
      setLoading(false);
    }
  };

  const handlePermToggle = async (key: string, value: boolean) => {
    if (permLoading) return;
    if (value && permissions && !permissions.bot_permissions.includes(key)) {
      showToast('warning', `Bot 未授予此项权限，无法启用`);
      return;
    }
    setPermLoading(key);
    const prev = permissions;
    if (permissions) {
      setPermissions({ ...permissions, permissions: { ...permissions.permissions, [key]: value } });
    }
    try {
      await updatePluginPermission(pluginName, key, value);
      showToast('success', `权限 ${key} 已${value ? '允许' : '禁止'}`);
    } catch (e: any) {
      setPermissions(prev);
      showToast('error', '权限更新失败', e.message);
    } finally {
      setPermLoading(null);
    }
  };

  const handleConfigSave = async (values: Record<string, unknown>) => {
    await updatePluginConfig(pluginName, values);
    showToast('success', '配置已保存');
    const c = await fetchPluginConfig(pluginName);
    setConfig(c);
  };

  if (!open) return null;

  const displayName = detail?.display_name || detail?.name || pluginName;

  return (
    <>
      {/* Overlay */}
      <div className="drawer-overlay" onClick={onClose} />

      {/* Drawer panel */}
      <div className="drawer-panel" style={{ display: 'flex', flexDirection: 'column', height: '100dvh' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4
                        bg-white dark:bg-surface-800 border-b border-surface-200 dark:border-surface-700"
             style={{ flexShrink: 0 }}>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-surface-900 dark:text-white truncate">
              {displayName}
            </h2>
            <p className="text-xs text-surface-500 truncate">
              {detail?.plugin_id} · v{detail?.version}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {detail && (
              <StatusBadge status={detail.enabled ? 'enabled' : 'disabled'} size="sm" />
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-surface-200 dark:border-surface-700 px-2 overflow-x-auto"
             style={{ flexShrink: 0 }}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors whitespace-nowrap
                  ${activeTab === tab.id ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-surface-500 hover:text-surface-700 dark:hover:text-surface-300'}`}>
                <Icon className="w-3.5 h-3.5" />{tab.label}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="overflow-y-auto p-6" style={{ flex: 1, minHeight: 0 }}>
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="w-6 h-6 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : detail ? (
            <>
              {/* Info Tab */}
              {activeTab === 'info' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <InfoItem label="名称" value={detail.name} />
                    <InfoItem label="版本" value={detail.version} />
                    <InfoItem label="作者" value={detail.author} />
                    <InfoItem label="Plugin ID" value={detail.plugin_id} mono />
                    {detail.repo && <InfoItem label="仓库" value={detail.repo} span={2} />}
                  </div>
                  {detail.desc && (
                    <div>
                      <p className="text-xs font-medium text-surface-500 mb-1">描述</p>
                      <p className="text-sm text-surface-700 dark:text-surface-300">{detail.desc}</p>
                    </div>
                  )}
                  {detail.short_desc && detail.short_desc !== detail.desc && (
                    <div>
                      <p className="text-xs font-medium text-surface-500 mb-1">简介</p>
                      <p className="text-sm text-surface-700 dark:text-surface-300">{detail.short_desc}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Handlers Tab */}
              {activeTab === 'handlers' && (
                <div className="space-y-2">
                  {detail.handlers.length === 0 ? (
                    <p className="text-sm text-surface-400 text-center py-8">无事件处理器</p>
                  ) : (
                    detail.handlers.map((h, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2.5 rounded-lg bg-surface-50 dark:bg-surface-900"
                      >
                        <span className="text-sm font-mono text-surface-700 dark:text-surface-300">
                          {h.method_name}
                        </span>
                        <span className="badge-blue text-[10px]">{h.event_type}</span>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Permissions Tab */}
              {activeTab === 'permissions' && (
                <div className="space-y-3">
                  {permissions ? (
                    <>
                      <div className="text-xs text-surface-500 mb-2">
                        生效权限 Flag: {permissions.effective_flag} · Bot 权限: {permissions.bot_permissions.join(', ') || '(无)'}
                      </div>
                      {permissions.missing_in_bot.length > 0 && (
                        <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-xs text-amber-700 dark:text-amber-300">
                          ⚠ Bot 缺失权限: {permissions.missing_in_bot.join(', ')}
                        </div>
                      )}
                      <div className="space-y-1.5">
                        {Object.entries(permissions.permissions).map(([key, val]) => {
                          const inBot = permissions.bot_permissions.includes(key);
                          return (
                            <div
                              key={key}
                              className="flex items-center justify-between p-2.5 rounded-lg bg-surface-50 dark:bg-surface-900"
                            >
                              <div className="min-w-0 mr-3">
                                <p className="text-sm font-medium text-surface-900 dark:text-surface-100">
                                  {key}
                                </p>
                                <p className="text-[10px] text-surface-500">
                                  {PERM_DESC[key] || key}
                                </p>
                              </div>
                              <button
                                onClick={() => handlePermToggle(key, !val)}
                                disabled={!!permLoading}
                                className={`toggle ${val && inBot ? 'toggle-on' : 'toggle-off'} ${permLoading === key ? 'opacity-60' : ''}`}
                              >
                                {permLoading === key && (
                                  <Loader2 className="absolute inset-0 m-auto h-3 w-3 animate-spin text-white" />
                                )}
                                <span className="toggle-dot" />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-surface-400 text-center py-8">无权限配置</p>
                  )}
                </div>
              )}

              {/* Config Tab */}
              {activeTab === 'config' && (
                <div>
                  {config?.schema && Object.keys(config.schema).length > 0 ? (
                    <DynamicConfigForm
                      schema={config.schema}
                      values={config.values || {}}
                      onSave={handleConfigSave}
                    />
                  ) : (
                    <p className="text-sm text-surface-400 text-center py-8">
                      此插件无配置项（无 _conf_schema.json）
                    </p>
                  )}
                </div>
              )}

              {/* README Tab */}
              {activeTab === 'readme' && (
                <div>
                  {readme ? (
                    <MarkdownRenderer content={readme} />
                  ) : (
                    <p className="text-sm text-surface-400 text-center py-8">无 README</p>
                  )}
                </div>
              )}

              {/* CHANGELOG Tab */}
              {activeTab === 'changelog' && (
                <div>
                  {changelog ? (
                    <MarkdownRenderer content={changelog} />
                  ) : (
                    <p className="text-sm text-surface-400 text-center py-8">无 CHANGELOG</p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-surface-400 text-center py-8">加载失败</p>
          )}
        </div>

      </div>
    </>
  );
}

/** Simple info display item */
function InfoItem({
  label,
  value,
  mono,
  span,
}: {
  label: string;
  value: string;
  mono?: boolean;
  span?: number;
}) {
  return (
    <div className={span === 2 ? 'col-span-2' : ''}>
      <p className="text-[10px] text-surface-500 uppercase tracking-wide">{label}</p>
      <p className={`text-sm mt-0.5 text-surface-900 dark:text-surface-100 truncate ${mono ? 'font-mono text-xs' : ''}`}>
        {value || '-'}
      </p>
    </div>
  );
}
