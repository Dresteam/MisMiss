/** API 客户端 —— 封装所有后端 REST 调用。 */

import type {
  StatusResponse,
  BotInfo,
  BotCreateRequest,
  BotCookieResponse,
  LiveListResponse,
  LivestreamInfo,
  LiveAddRequest,
  LiveMessageRequest,
  PluginSummary,
  PluginDetail,
  PluginEventHandler,
  PluginPermissionInfo,
  PluginConfigResponse,
  FailedPluginInfo,
  DashboardData,
  ServerStatus,
} from './types';

// ================================================================== //
// 基础请求
// ================================================================== //

const BASE = '/api';

class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }

  return res.json();
}

// ================================================================== //
// Dashboard
// ================================================================== //

export async function fetchDashboard(): Promise<DashboardData> {
  return request<DashboardData>('/dashboard');
}

// ================================================================== //
// Bot
// ================================================================== //

export async function fetchBotInfo(): Promise<BotInfo> {
  return request<BotInfo>('/bot/info');
}

export async function createBot(data: BotCreateRequest): Promise<BotInfo> {
  return request<BotInfo>('/bot/create', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function refreshBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/bot/refresh', { method: 'POST' });
}

export async function verifyBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/bot/verify', { method: 'POST' });
}

export async function getBotCookie(): Promise<BotCookieResponse> {
  return request<BotCookieResponse>('/bot/cookie');
}

export async function getBotCookieRaw(): Promise<BotCookieResponse> {
  return request<BotCookieResponse>('/config/cookie');
}

export async function enableBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/bot/enable', { method: 'POST' });
}

export async function disableBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/bot/disable', { method: 'POST' });
}

// ================================================================== //
// Livestream
// ================================================================== //

export async function fetchLiveList(): Promise<LiveListResponse> {
  return request<LiveListResponse>('/live/list');
}

export async function fetchLiveInfo(liveId: number): Promise<LivestreamInfo> {
  return request<LivestreamInfo>(`/live/${liveId}`);
}

export async function refreshLive(liveId: number): Promise<LivestreamInfo> {
  return request<LivestreamInfo>(`/live/${liveId}/refresh`, { method: 'POST' });
}

export async function addLive(data: LiveAddRequest): Promise<LivestreamInfo> {
  return request<LivestreamInfo>('/live/add', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function enableLive(liveId: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/live/${liveId}/enable`, { method: 'POST' });
}

export async function disableLive(liveId: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/live/${liveId}/disable`, { method: 'POST' });
}

export async function joinLive(liveId: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/live/${liveId}/join`, { method: 'POST' });
}

export async function quitLive(liveId: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/live/${liveId}/quit`, { method: 'POST' });
}

export async function removeLive(liveId: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/live/${liveId}`, { method: 'DELETE' });
}

export async function sendLiveMessage(data: LiveMessageRequest): Promise<StatusResponse> {
  return request<StatusResponse>('/live/message', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ================================================================== //
// Plugin
// ================================================================== //

export async function fetchPluginList(): Promise<PluginSummary[]> {
  return request<PluginSummary[]>('/plugin/list');
}

export async function fetchPluginDetail(name: string): Promise<PluginDetail> {
  return request<PluginDetail>(`/plugin/${encodeURIComponent(name)}`);
}

export async function fetchPluginHandlers(name: string): Promise<PluginEventHandler[]> {
  return request<PluginEventHandler[]>(`/plugin/${encodeURIComponent(name)}/handlers`);
}

export async function enablePlugin(name: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/plugin/${encodeURIComponent(name)}/enable`, {
    method: 'POST',
  });
}

export async function disablePlugin(name: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/plugin/${encodeURIComponent(name)}/disable`, {
    method: 'POST',
  });
}

export async function reloadPlugin(name: string): Promise<PluginSummary> {
  return request<PluginSummary>(`/plugin/${encodeURIComponent(name)}/reload`, {
    method: 'POST',
  });
}

export async function uninstallPlugin(
  name: string,
  deleteConfig = true,
  deleteData = false,
): Promise<StatusResponse> {
  const params = new URLSearchParams({
    delete_config: String(deleteConfig),
    delete_data: String(deleteData),
  });
  return request<StatusResponse>(
    `/plugin/${encodeURIComponent(name)}?${params}`,
    { method: 'DELETE' },
  );
}

export async function fetchPluginPermissions(name: string): Promise<PluginPermissionInfo> {
  return request<PluginPermissionInfo>(
    `/plugin/${encodeURIComponent(name)}/permissions`,
  );
}

export async function updatePluginPermission(
  name: string,
  key: string,
  value: boolean,
): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/plugin/${encodeURIComponent(name)}/permissions`,
    {
      method: 'PUT',
      body: JSON.stringify({ key, value }),
    },
  );
}

export async function fetchPluginConfig(name: string): Promise<PluginConfigResponse> {
  return request<PluginConfigResponse>(
    `/plugin/${encodeURIComponent(name)}/config`,
  );
}

export async function updatePluginConfig(
  name: string,
  config: Record<string, unknown>,
): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/plugin/${encodeURIComponent(name)}/config`,
    {
      method: 'PUT',
      body: JSON.stringify({ config }),
    },
  );
}

export async function fetchPluginReadme(name: string): Promise<{ content: string }> {
  return request(`/plugin/${encodeURIComponent(name)}/readme`);
}

export async function fetchPluginChangelog(name: string): Promise<{ content: string }> {
  return request(`/plugin/${encodeURIComponent(name)}/changelog`);
}

export async function fetchFailedPlugins(): Promise<FailedPluginInfo[]> {
  return request<FailedPluginInfo[]>('/plugin/failed/list');
}

export async function retryFailedPlugin(dirName: string): Promise<PluginSummary> {
  return request<PluginSummary>(`/plugin/failed/${encodeURIComponent(dirName)}/retry`, {
    method: 'POST',
  });
}

export async function refreshPlugins(): Promise<StatusResponse> {
  return request<StatusResponse>('/plugin/refresh', { method: 'POST' });
}

// ================================================================== //
// Server
// ================================================================== //

export async function fetchServerStatus(): Promise<ServerStatus> {
  return request<ServerStatus>('/server/status');
}

export async function reloadServer(): Promise<StatusResponse> {
  return request<StatusResponse>('/server/reload', { method: 'POST' });
}

export async function shutdownServer(): Promise<StatusResponse> {
  return request<StatusResponse>('/server/shutdown', { method: 'POST' });
}

export { ApiError };
