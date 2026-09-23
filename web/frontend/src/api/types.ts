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

/** 一条服务器日志。 */
export interface LogEntry {
  seq_id: number;
  timestamp: number;
  level: string;
  message: string;
  /** 来源类名（如 NicknamePlugin / PluginManager）；旧数据可能为空 */
  source?: string;
  /** 所属账户名；空串表示面板级日志（非账户上下文） */
  account?: string;
}

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
  /** 最近一次初始化失败的原因；成功后清空 */
  last_error?: string | null;
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
  /** 配置分组名（如「常用」/「高级」）。schema 里只要有一个字段带 group，配置页就按组渲染 */
  group?: string;
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
  /** 全局消息的字符上限 */
  broadcast_max_len: number;
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
  /** 定时消息总数（普通 + 插件） */
  timer_message_count: number;
  /** 面板添加的普通定时消息数 */
  normal_timer_message_count: number;
  /** 插件注册的定时消息数 */
  plugin_timer_message_count: number;
  /** 操作结果提示（如「永久账户无需续期」），仅写操作返回 */
  notice?: string | null;
  /** 账户级偏好：从插件库安装插件后是否自动启用（默认关闭） */
  auto_enable_on_install: boolean;
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
  /** 设为永不过期 */
  permanent?: boolean;
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
  /** 是否为默认插件：新建账户时自动安装并启用 */
  is_default: boolean;
  used_by_accounts: number[];
  /** 账户库列表附加:是否已安装到本账户 */
  installed?: boolean;
  /** 最近一次初始化失败的原因；成功后清空 */
  last_error?: string | null;
}

/** 批量操作的影响明细（确认弹窗展示用） */
export interface BulkGroup {
  /** 分组名：推送按插件分组、补齐默认按账户分组 */
  label: string;
  /** 组内条目：推送为账户名、补齐默认为插件名 */
  items: string[];
}

/** 批量补偿时长：目标账户默认全选，下列字段全部用于**排除** */
export interface CompensateParams {
  /** 补偿天数（正整数） */
  days: number;
  /** 排除已过期的账户 */
  exclude_expired: boolean;
  /** 排除未过期的账户 */
  exclude_active: boolean;
  /** 排除剩余天数多于该值的账户；null 表示不排除 */
  exclude_over_days_left?: number | null;
  /** 排除这些账户 id（手动取消勾选） */
  exclude_ids?: number[];
  /** true = 只预览不动手 */
  dry_run?: boolean;
}

/** 批量补偿结果 */
export interface CompensateResult {
  success?: boolean;
  /** 实际（或将要）补偿的账户名 */
  compensated: string[];
  skipped: string[];
  failed: string[];
  /** 供二次确认弹窗展示的明细分组 */
  groups: BulkGroup[];
  /** 一句话摘要 */
  message: string;
  days: number;
  dry_run: boolean;
}

/** 批量推送结果（插件库 → 各账户副本） */
export interface PluginPushResult {
  /** 更新（dry_run 时为「将更新」）的条目，形如 `插件名@账户名` */
  updated: string[];
  /** 因副本不旧于库版本而跳过的条目 */
  skipped: string[];
  /** 更新失败的条目（dry_run 时恒为空） */
  failed: string[];
  /** 按插件分组的明细 */
  groups: BulkGroup[];
  message: string;
  dry_run?: boolean;
}

/** 账户端一键更新结果（StatusResponse 的超集） */
export interface AccountUpdateAllResult {
  success: boolean;
  message: string;
  /** 按插件分组的明细，条目为版本跨度（如 `v1.0.4 → v1.0.5`） */
  groups: BulkGroup[];
  updated: string[];
  skipped: string[];
  failed: string[];
  dry_run?: boolean;
}

/** 默认插件补齐结果 */
export interface ApplyDefaultsResult {
  applied: Record<string, string[]>;
  failed: string[];
  /** 按账户分组的明细 */
  groups: BulkGroup[];
  message: string;
  dry_run?: boolean;
}

export interface TimerData {
  interval: number;
  next_tick_in: number;
  /** 账户单队列展示用：账户直播间的合并轮转列表（插件消息置顶） */
  global: TimerMessageItem[];
  /** 插件注册的定时消息（`global` 中同样包含，此处为按插件分组的视图） */
  plugin?: TimerMessageItem[];
  rooms: TimerRoomItem[];
  target_live_id?: number | null;
}

export interface TimerMessageItem {
  message_id: string;
  live_id: number;
  message: string;
  index: number;
  seconds_until_next: number;
  /** 注册来源：插件托管的消息不可编辑/删除/移动 */
  source?: 'plugin' | 'normal';
  /** `source === 'plugin'` 时，注册该消息的插件名 */
  plugin_name?: string | null;
}

export interface TimerRoomItem {
  live_id: number;
  messages: TimerMessageItem[];
  position: number;
  room_name?: string;
}
