/** API 类型定义 —— 与后端 Pydantic schemas 对应。 */

// ================================================================== //
// 通用
// ================================================================== //

export interface StatusResponse {
  success: boolean;
  message: string;
}

// ================================================================== //
// Bot
// ================================================================== //

export interface BotCreateRequest {
  cookie: string;
  permissions: string[];
}

export interface BotInfo {
  name: string;
  user_id: number;
  introduction: string;
  icon_url: string;
  enabled: boolean;
  available: boolean;
  permissions: string[];
  cookie_length: number;
}

export interface BotCookieResponse {
  cookie: string;
  length: number;
}

// ================================================================== //
// Livestream
// ================================================================== //

export interface LiveAddRequest {
  live_id: number;
}

export interface LiveMessageRequest {
  live_id: number;
  text: string;
  priority: number;
}

export interface LivestreamInfo {
  live_id: number;
  room_name: string;
  room_description: string;
  score: number;
  online_count: number;
  creator_name: string;
  creator_id: number;
  creator_is_online: boolean;
  is_connected: boolean;
  enabled: boolean;
  medal_name: string | null;
  medal_level: number | null;
  cover_url: string;
  creator_avatar: string;
  creator_intro: string;
  is_streaming: boolean;
}

export interface LiveListResponse {
  livestreams: LivestreamInfo[];
  total: number;
}

// ================================================================== //
// Plugin
// ================================================================== //

export interface PluginSummary {
  name: string;
  plugin_id: string;
  author: string;
  version: string;
  display_name: string | null;
  short_desc: string | null;
  desc: string;
  enabled: boolean;
  has_config: boolean;
  has_readme: boolean;
  has_changelog: boolean;
  has_ui: boolean;
}

export interface PluginEventHandler {
  method_name: string;
  event_type: string;
}

export interface PluginDetail {
  name: string;
  plugin_id: string;
  author: string;
  version: string;
  display_name: string | null;
  short_desc: string | null;
  desc: string;
  repo: string | null;
  enabled: boolean;
  has_config: boolean;
  has_readme: boolean;
  has_changelog: boolean;
  handlers: PluginEventHandler[];
  permissions: Record<string, boolean> | null;
  config_schema: Record<string, ConfigFieldSchema> | null;
  config_values: Record<string, unknown> | null;
  ui_schema: Record<string, unknown> | null;
}

export interface ConfigFieldSchema {
  type: string;
  default?: unknown;
  description?: string;
  items?: Record<string, ConfigFieldSchema>;
  options?: { label: string; value: string | number }[];
}

export interface PluginPermissionInfo {
  permissions: Record<string, boolean>;
  effective_flag: number;
  effective_names: string[];
  bot_permissions: string[];
  missing_in_bot: string[];
}

export interface PluginConfigResponse {
  schema: Record<string, ConfigFieldSchema> | null;
  values: Record<string, unknown> | null;
}

export interface FailedPluginInfo {
  dir_name: string;
  error: string;
  traceback?: string;
}

// ================================================================== //
// Dashboard
// ================================================================== //

export interface DashboardData {
  bot: BotInfo | null;
  livestream_count: number;
  livestream_online: number;
  livestream_offline: number;
  plugin_count: number;
  plugin_enabled: number;
  plugin_disabled: number;
  failed_plugin_count: number;
  timer_message_count: number;
}

// ================================================================== //
// Server
// ================================================================== //

export interface ServerStatus {
  running: boolean;
  bot_name: string;
  bot_available: boolean;
  livestream_count: number;
  plugin_count: number;
  enabled_plugin_count: number;
}

// ================================================================== //
// WebSocket
// ================================================================== //

export interface WSLogMessage {
  type: 'log' | 'status' | 'error';
  level: string;
  message: string;
  timestamp: number;
}

// ================================================================== //
// 多账户面板
// ================================================================== //

export interface AccountSummary {
  id: number;
  name: string;
  username: string;
  room_id: number | null;
  bot_mode: 'private' | 'public';
  expires_at: string | null;
  expired: boolean;
  days_left: number | null;
  paused_reason: string | null;
  resume_error: string | null;
  bot_enabled: boolean;
  bot_available: boolean;
  bot_name: string;
  bot_public: boolean;
  room_connected: boolean;
  room_enabled: boolean;
  room_name: string;
  plugin_count: number;
  enabled_plugin_count: number;
  timer_message_count: number;
}

export interface PanelOverview {
  accounts: AccountSummary[];
  total: number;
  expired_count: number;
  running_count: number;
  public_bot_configured: boolean;
  library_plugin_count: number;
  license_unused: number;
}

export interface AccountCreateRequest {
  name: string;
  room_id?: number | null;
  bot_mode: 'private' | 'public';
  cookie?: string;
  permissions?: string[];
  /** 有效时长(天),-1 为永久 */
  duration_days?: number;
  username?: string;
  password?: string;
}

export interface AccountUpdateRequest {
  name?: string;
  room_id?: number | null;
  bot_mode?: 'private' | 'public';
  cookie?: string;
}

export interface RenewRequest {
  days?: number;
  expires_at?: string | null;
}

export interface PublicBotInfo {
  configured: boolean;
  cookie_length: number;
  permissions: string[];
  updated_at: number;
  name: string;
  user_id: number;
  introduction: string;
  icon_url: string;
  available: boolean;
}

export interface PublicBotVerify {
  valid: boolean;
  name: string;
  message: string;
}

export interface LicenseInfo {
  code: string;
  days: number;
  batch: string;
  note: string;
  generated_at: string;
  used_at: string | null;
  used_by_account_id: number | null;
}

export interface LibraryPlugin {
  name: string;
  plugin_id: string;
  author: string;
  version: string;
  display_name: string | null;
  short_desc: string | null;
  desc: string;
  has_config: boolean;
  has_readme: boolean;
  has_changelog: boolean;
  has_ui: boolean;
  used_by_accounts: number[];
  /** 账户库列表附加:是否已安装到本账户 */
  installed?: boolean;
}

export interface TimerData {
  interval: number;
  next_tick_in: number;
  global: TimerMessageItem[];
  rooms: TimerRoomItem[];
  target_live_id?: number | null;
}

export interface TimerMessageItem {
  message_id: string;
  live_id: number;
  message: string;
  index: number;
  seconds_until_next: number;
}

export interface TimerRoomItem {
  live_id: number;
  messages: TimerMessageItem[];
  position: number;
  room_name?: string;
}
