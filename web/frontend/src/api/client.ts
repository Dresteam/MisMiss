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
  const token = localStorage.getItem('auth_token');
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.reload();
      throw new ApiError(401, '登录已过期');
    }
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

export async function deleteBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/bot/', { method: 'DELETE' });
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

// ================================================================== //
// 面板(账户 / 公共 Bot / 授权码)
// ================================================================== //

import type {
  AccountCreateRequest,
  AccountSummary,
  AccountUpdateRequest,
  LicenseInfo,
  PanelOverview,
  PublicBotInfo,
  PublicBotVerify,
  RenewRequest,
  LibraryPlugin,
  TimerData,
} from './types';

export async function fetchPanelOverview(): Promise<PanelOverview> {
  return request<PanelOverview>('/panel/overview');
}

export async function fetchAccounts(): Promise<AccountSummary[]> {
  return request<AccountSummary[]>('/panel/accounts');
}

export async function fetchAccountSummary(id: number): Promise<AccountSummary> {
  // 账户级端点:面板管理员与账户持有者均可访问
  return request<AccountSummary>(`/accounts/${id}/info`);
}

export async function createAccount(data: AccountCreateRequest): Promise<AccountSummary> {
  return request<AccountSummary>('/panel/accounts', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateAccount(
  id: number,
  data: AccountUpdateRequest,
): Promise<AccountSummary> {
  return request<AccountSummary>(`/panel/accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteAccount(id: number, purgeData = false): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/panel/accounts/${id}?purge_data=${purgeData}`,
    { method: 'DELETE' },
  );
}

export async function resetAccountCredentials(
  id: number,
  username: string,
  password: string,
): Promise<AccountSummary> {
  return request<AccountSummary>(`/panel/accounts/${id}/credentials`, {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export async function renewAccount(id: number, data: RenewRequest): Promise<AccountSummary> {
  return request<AccountSummary>(`/panel/accounts/${id}/renew`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function redeemAccount(id: number, code: string): Promise<AccountSummary> {
  return request<AccountSummary>(`/panel/accounts/${id}/redeem`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

/** 账户自助兑换授权码(账户级端点,过期账户也可调用)。 */
export async function redeemAccountCode(id: number, code: string): Promise<AccountSummary> {
  return request<AccountSummary>(`/accounts/${id}/redeem`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

export async function fetchPublicBot(): Promise<PublicBotInfo> {
  return request<PublicBotInfo>('/panel/public-bot');
}

export async function setPublicBot(
  cookie: string,
  permissions: string[],
): Promise<StatusResponse> {
  return request<StatusResponse>('/panel/public-bot', {
    method: 'PUT',
    body: JSON.stringify({ cookie, permissions }),
  });
}

export async function applyPublicBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/panel/public-bot/apply', { method: 'POST' });
}

export async function fetchPublicBotCookie(): Promise<BotCookieResponse> {
  return request<BotCookieResponse>('/panel/public-bot/cookie');
}

export async function refreshPublicBot(): Promise<PublicBotInfo> {
  return request<PublicBotInfo>('/panel/public-bot/refresh', { method: 'POST' });
}

export async function verifyPublicBot(): Promise<PublicBotVerify> {
  return request<PublicBotVerify>('/panel/public-bot/verify', { method: 'POST' });
}

export async function deletePublicBot(): Promise<StatusResponse> {
  return request<StatusResponse>('/panel/public-bot', { method: 'DELETE' });
}

export async function fetchLicenses(): Promise<LicenseInfo[]> {
  return request<LicenseInfo[]>('/panel/licenses');
}

export async function generateLicenses(
  count: number,
  days: number,
  note = '',
): Promise<LicenseInfo[]> {
  return request<LicenseInfo[]>('/panel/licenses/generate', {
    method: 'POST',
    body: JSON.stringify({ count, days, note }),
  });
}

export async function revokeLicense(code: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/panel/licenses/${encodeURIComponent(code)}`, {
    method: 'DELETE',
  });
}

// ================================================================== //
// 账户级 Bot
// ================================================================== //

export async function fetchAccountBot(id: number): Promise<BotInfo> {
  return request<BotInfo>(`/accounts/${id}/bot/info`);
}

export async function createAccountBot(
  id: number,
  data: BotCreateRequest,
): Promise<BotInfo> {
  return request<BotInfo>(`/accounts/${id}/bot/create`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function setAccountBotMode(
  id: number,
  mode: 'public' | 'private',
  cookie = '',
  permissions: string[] = [],
): Promise<BotInfo> {
  return request<BotInfo>(`/accounts/${id}/bot/mode`, {
    method: 'POST',
    body: JSON.stringify({ mode, cookie, permissions }),
  });
}

export async function refreshAccountBot(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/bot/refresh`, { method: 'POST' });
}

export async function verifyAccountBot(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/bot/verify`, { method: 'POST' });
}

export async function getAccountBotCookie(id: number): Promise<BotCookieResponse> {
  return request<BotCookieResponse>(`/accounts/${id}/bot/cookie`);
}

export async function enableAccountBot(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/bot/enable`, { method: 'POST' });
}

export async function disableAccountBot(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/bot/disable`, { method: 'POST' });
}

export async function deleteAccountBot(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/bot/`, { method: 'DELETE' });
}

// ================================================================== //
// 账户级直播间
// ================================================================== //

export async function fetchAccountLive(id: number): Promise<LivestreamInfo | null> {
  return request<LivestreamInfo | null>(`/accounts/${id}/live/`);
}

export async function addAccountLive(id: number, liveId: number): Promise<LivestreamInfo> {
  return request<LivestreamInfo>(`/accounts/${id}/live/add`, {
    method: 'POST',
    body: JSON.stringify({ live_id: liveId }),
  });
}

export async function removeAccountLive(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/live/`, { method: 'DELETE' });
}

export async function refreshAccountLive(id: number): Promise<LivestreamInfo> {
  return request<LivestreamInfo>(`/accounts/${id}/live/refresh`, { method: 'POST' });
}

export async function enableAccountLive(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/live/enable`, { method: 'POST' });
}

export async function disableAccountLive(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/live/disable`, { method: 'POST' });
}

export async function joinAccountLive(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/live/join`, { method: 'POST' });
}

export async function quitAccountLive(id: number): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/live/quit`, { method: 'POST' });
}

export async function sendAccountLiveMessage(
  id: number,
  text: string,
  priority: number,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/live/message`, {
    method: 'POST',
    body: JSON.stringify({ text, priority }),
  });
}

// ================================================================== //
// 账户级定时消息
// ================================================================== //

export async function fetchAccountTimers(id: number): Promise<TimerData> {
  return request<TimerData>(`/accounts/${id}/timer/list`);
}

export async function setAccountTimerInterval(
  id: number,
  interval: number,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/interval`, {
    method: 'PUT',
    body: JSON.stringify({ interval }),
  });
}

export async function addAccountTimer(
  id: number,
  message: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/add`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export async function updateAccountTimer(
  id: number,
  messageId: string,
  message: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/${messageId}`, {
    method: 'PUT',
    body: JSON.stringify({ message }),
  });
}

export async function deleteAccountTimer(
  id: number,
  messageId: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/${messageId}`, {
    method: 'DELETE',
  });
}

export async function moveAccountTimer(
  id: number,
  messageId: string,
  direction: number,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/${messageId}/move`, {
    method: 'POST',
    body: JSON.stringify({ direction }),
  });
}

export async function skipAccountTimer(
  id: number,
  messageId: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/${messageId}/skip`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export async function sendAccountTimerNow(
  id: number,
  messageId: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/timer/${messageId}/send`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

// ================================================================== //
// 账户级插件
// ================================================================== //

export async function fetchAccountPlugins(id: number): Promise<PluginSummary[]> {
  return request<PluginSummary[]>(`/accounts/${id}/plugins/`);
}

export async function fetchAccountLibrary(id: number): Promise<LibraryPlugin[]> {
  return request<LibraryPlugin[]>(`/accounts/${id}/plugins/library`);
}

export async function installAccountPlugin(id: number, name: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/accounts/${id}/plugins/install`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function uninstallAccountPluginFromAccount(
  id: number,
  name: string,
  deleteConfig = false,
  deleteData = false,
): Promise<StatusResponse> {
  const params = new URLSearchParams({
    delete_config: String(deleteConfig),
    delete_data: String(deleteData),
  });
  return request<StatusResponse>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}?${params}`,
    { method: 'DELETE' },
  );
}

export async function fetchAccountPluginChangelog(
  id: number,
  name: string,
): Promise<{ content: string }> {
  return request(`/accounts/${id}/plugins/${encodeURIComponent(name)}/changelog`);
}

export async function fetchAccountPluginDetail(
  id: number,
  name: string,
): Promise<PluginDetail> {
  return request<PluginDetail>(`/accounts/${id}/plugins/${encodeURIComponent(name)}`);
}

export async function enableAccountPlugin(
  id: number,
  name: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/enable`,
    { method: 'POST' },
  );
}

export async function disableAccountPlugin(
  id: number,
  name: string,
): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/disable`,
    { method: 'POST' },
  );
}

export async function reloadAccountPlugin(
  id: number,
  name: string,
): Promise<PluginSummary> {
  return request<PluginSummary>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/reload`,
    { method: 'POST' },
  );
}

export async function fetchAccountPluginPermissions(
  id: number,
  name: string,
): Promise<PluginPermissionInfo> {
  return request<PluginPermissionInfo>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/permissions`,
  );
}

export async function updateAccountPluginPermission(
  id: number,
  name: string,
  key: string,
  value: boolean,
): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/permissions`,
    {
      method: 'PUT',
      body: JSON.stringify({ key, value }),
    },
  );
}

export async function fetchAccountPluginConfig(
  id: number,
  name: string,
): Promise<PluginConfigResponse> {
  return request<PluginConfigResponse>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/config`,
  );
}

export async function updateAccountPluginConfig(
  id: number,
  name: string,
  config: Record<string, unknown>,
): Promise<StatusResponse> {
  return request<StatusResponse>(
    `/accounts/${id}/plugins/${encodeURIComponent(name)}/config`,
    {
      method: 'PUT',
      body: JSON.stringify({ config }),
    },
  );
}

export async function fetchAccountPluginReadme(
  id: number,
  name: string,
): Promise<{ content: string }> {
  return request(`/accounts/${id}/plugins/${encodeURIComponent(name)}/readme`);
}

// ================================================================== //
// 插件库(面板级)
// ================================================================== //

export async function fetchLibraryPlugins(): Promise<LibraryPlugin[]> {
  return request<LibraryPlugin[]>('/plugin/list');
}

export { ApiError };
