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
  creator_name: string;
  creator_id: number;
  creator_is_online: boolean;
  is_connected: boolean;
  enabled: boolean;
  medal_name: string | null;
  medal_level: number | null;
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
