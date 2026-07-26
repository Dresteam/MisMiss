import {useCallback, useEffect, useState} from 'react';
import {ExternalLink, Loader2, RefreshCw, Trash2, X} from 'lucide-react';
import {Button} from './Button';
import {ConfirmDialog} from './ConfirmDialog';

// =====================================================================
// Schema 定义 —— 所有预设类型及其字段
// =====================================================================

/** 列/字段的渲染类型 */
type CellType = 'badge' | 'link' | 'switch' | 'text' | 'number' | 'date' | 'image';

/** 表格/列表/卡片的列定义 */
interface ColumnDef {
  key: string;
  label: string;
  /** 渲染类型，默认纯文本 */
  type?: CellType;
  /** badge: 状态→颜色的映射 */
  badge_colors?: Record<string, string>;
  /** link: 链接模板，支持 {key} 占位符，默认用本列值 */
  href_template?: string;
  /** image: 图片宽度（px） */
  image_width?: number;
  /** date: 日期格式化（'relative' | 'datetime'），默认 datetime */
  date_format?: string;
  /** switch: 切换的 API 端点（POST），接收 {key: value} */
  switch_url?: string;
  /** number: 小数位数 */
  decimals?: number;
}

/** 操作的字段收集方式 */
interface ActionPrompt {
  key: string;
  label: string;
  placeholder?: string;
  /** 输入类型：text | number | select */
  input_type?: string;
  /** select 的选项 */
  options?: { label: string; value: string }[];
}
interface UISchema {
  // ── 通用 ──
  type: 'table' | 'list' | 'stats' | 'cards' | 'playlist' | 'form' | 'composite';
  api?: string;
  /** 页面标题（composite 模式下每个 section 可单独设置） */
  title?: string;
  columns?: ColumnDef[];
  actions?: {
    label: string;
    method: string;
    url: string;
    prompt_field?: ActionPrompt;
    show_when?: string;
    /** 从行数据构建 body，如 {"status": "{{row.status}}"} */
    body_template?: Record<string, string>;
  }[];
  fields?: (ColumnDef & { format?: string; subtitle?: string })[];
  /** playlist 专用 */
  status_actions?: { label: string; status: string; icon?: string; show_when?: string }[];
  batch_actions?: { label: string; method: string; url: string; status?: string }[];
  add_action?: { label: string; method: string; url: string; prompt_field: ActionPrompt };

  // ── form 类型专用 ──
  /** 表单提交配置 */
  submit?: { label: string; method: string; url: string };
  // ── composite 类型专用 ──
  /** 子页面列表，每个子页面独立加载数据并渲染 */
  sections?: UISchema[];

  /** form 字段列表 */
  form_fields?: {
    key: string;
    label: string;
    type: 'text' | 'number' | 'select' | 'textarea' | 'switch' | 'password' | 'date';
    placeholder?: string;
    default?: string | number | boolean;
    required?: boolean;
    options?: { label: string; value: string }[];  // select 选项
    rows?: number;  // textarea 行数
  }[];
}

// =====================================================================
// 共享单元格渲染器 —— 所有列表类型共用
// =====================================================================

function renderCell(col: ColumnDef, value: any, row: any, onToggle?: (col: ColumnDef, row: any, newVal: boolean) => void) {
  const val = value ?? '';
  switch (col.type) {
    // ── badge ──
    case 'badge': {
      const str = String(val);
      const colors = col.badge_colors || {};
      const auto = str.includes('完成') || str.includes('done') || str.includes('✅')
        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
        : str.includes('播放') || str.includes('playing') || str.includes('🎵')
        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400';
      const cls = colors[str] || auto;
      return <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${cls}`}>{str}</span>;
    }
    // ── link ──
    case 'link': {
      const href = col.href_template
        ? col.href_template.replace(/\{(\w+)}/g, (_match: string, key: string) => String(row[key] ?? ''))
        : String(val);
      return (
        <a href={href} target="_blank" rel="noopener noreferrer"
          className="text-primary-500 hover:text-primary-600 dark:text-primary-400 dark:hover:text-primary-300 underline text-xs inline-flex items-center gap-0.5">
          {String(val)} <ExternalLink className="w-3 h-3" />
        </a>
      );
    }
    // ── switch (toggle) ──
    case 'switch': {
      const checked = Boolean(val);
      return (
        <button
          role="switch" aria-checked={checked}
          onClick={(e) => { e.stopPropagation(); onToggle?.(col, row, !checked); }}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 ${
            checked ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'
          }`}
        >
          <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
            checked ? 'translate-x-[18px]' : 'translate-x-[3px]'
          }`} />
        </button>
      );
    }
    // ── number ──
    case 'number': {
      const num = Number(val);
      return <span className="text-xs tabular-nums">{isNaN(num) ? '-' : num.toFixed(col.decimals ?? (Number.isInteger(num) ? 0 : 2))}</span>;
    }
    // ── date ──
    case 'date': {
      const d = new Date(val);
      if (isNaN(d.getTime())) return <span className="text-xs text-gray-400">-</span>;
      if (col.date_format === 'relative') {
        const diff = Date.now() - d.getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return <span className="text-xs">刚刚</span>;
        if (mins < 60) return <span className="text-xs">{mins}分钟前</span>;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return <span className="text-xs">{hours}小时前</span>;
        const days = Math.floor(hours / 24);
        return <span className="text-xs">{days}天前</span>;
      }
      return <span className="text-xs">{d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>;
    }
    // ── image ──
    case 'image': {
      const w = col.image_width || 48;
      return <img src={String(val)} alt="" className="rounded object-cover" style={{ width: w, height: w }} />;
    }
    // ── text (inline input) ──
    case 'text':
      return <span className="text-xs break-all">{String(val)}</span>;
    // ── 默认：纯文本 ──
    default:
      return <span className="text-xs">{String(val)}</span>;
  }
}

// =====================================================================
// Props
// =====================================================================

interface Props {
  schema: UISchema;
  pluginName: string;
}

// =====================================================================
// PluginUI 主组件
// =====================================================================

export function PluginUI({ schema, pluginName }: Props) {
  const [data, setData] = useState<any[] | Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [promptAction, setPromptAction] = useState<NonNullable<UISchema['actions']>[number] | null>(null);
  const [promptValue, setPromptValue] = useState('');
  const [promptRow, setPromptRow] = useState<any>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [roomId, setRoomId] = useState<number>(0);
  const [rooms, setRooms] = useState<any[]>([]);
  const [roomsLoaded, setRoomsLoaded] = useState(false);
  // Form state
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formInited, setFormInited] = useState(false);
  // Confirm dialog state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmTitle, setConfirmTitle] = useState('');
  const [confirmMsg, setConfirmMsg] = useState('');
  const [confirmDanger, setConfirmDanger] = useState(false);
  const [confirmCallback, setConfirmCallback] = useState<(() => void) | null>(null);

  // ────────────────────────────────────────────────────────────────
  // 数据加载
  // ────────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    if (!schema.api) return;
    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      let url = schema.api;
      if (schema.type === 'playlist' && roomId) url += '?room_id=' + roomId;
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      const result = await res.json();
      setData(result);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [schema.api, schema.type, roomId]);

  const loadRooms = useCallback(async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const res = await fetch('/api/plugin/' + pluginName + '/ui/rooms', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const d = await res.json();
      if (Array.isArray(d)) { setRooms(d); if (d.length > 0) setRoomId(prev => prev || d[0].room_id); }
    } catch { /* ignore */ }
    setRoomsLoaded(true);
  }, [pluginName]);

  useEffect(() => {
    if (schema.type === 'composite' || schema.type === 'form') { setLoading(false); return; }
    if (schema.type === 'playlist') { loadRooms(); return; }
    load();
    /* eslint-disable-next-line */
  }, []);
  useEffect(() => { if (schema.type === 'playlist' && roomId) load(); }, [roomId, load]);
  // Form defaults — init once when form fields change
  useEffect(() => {
    if (schema.type !== 'form' || !schema.form_fields || formInited) return;
    const defaults: Record<string, any> = {};
    schema.form_fields.forEach(f => { defaults[f.key] = f.default ?? (f.type === 'switch' ? false : ''); });
    setFormValues(defaults);
    setFormInited(true);
  }, [schema.type, schema.form_fields, formInited]);

  // ────────────────────────────────────────────────────────────────
  // 操作处理
  // ────────────────────────────────────────────────────────────────

  const closePrompt = () => { setPromptAction(null); setPromptValue(''); setPromptRow(null); };

  const doFetch = async (url: string, method: string, body?: any) => {
    const token = localStorage.getItem('auth_token');
    return fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  };

  const submitPrompt = async () => {
    if (!promptAction || !promptAction.prompt_field) return;
    setActionLoading(promptAction.label);
    try {
      let url = promptAction.url;
      if (promptRow) url = url.replace('{id}', promptRow.id || '');
      const body: Record<string, any> = {};
      body[promptAction.prompt_field.key] = promptAction.prompt_field.input_type === 'number'
        ? Number(promptValue) : promptValue;
      await doFetch(url, promptAction.method, body);
      closePrompt();
      await load();
    } catch { /* ignore */ }
    finally { setActionLoading(null); }
  };

  const handleAction = async (action: NonNullable<UISchema['actions']>[number], row?: any) => {
    if (!action) return;
    if (action.prompt_field) { setPromptAction(action); setPromptValue(''); setPromptRow(row || null); return; }
    setActionLoading(action.label);
    try {
      let url = action.url;
      if (row) url = url.replace('{id}', row.id || '');
      let body: Record<string, string> | undefined;
      if (action.body_template) {
        body = {};
        for (const [k, v] of Object.entries(action.body_template)) {
          body[k] = v.replace(/\{\{row\.(\w+)}}/g, (_match: string, field: string) => String(row[field] ?? ''));
        }
      }
      await doFetch(url, action.method, body);
      await load();
    } catch { /* ignore */ }
    finally { setActionLoading(null); }
  };

  // Switch toggle callback
  const handleSwitchToggle = async (col: ColumnDef, row: any, newVal: boolean) => {
    if (!col.switch_url) return;
    try {
      await doFetch(col.switch_url, 'POST', { [col.key]: newVal, id: row.id });
      await load();
    } catch { /* ignore */ }
  };

  // ────────────────────────────────────────────────────────────────
  // 共享渲染
  // ────────────────────────────────────────────────────────────────

  const renderActions = (row?: any) => {
    if (!schema.actions) return null;
    return (
      <div className="flex items-center gap-1">
        {schema.actions
          .filter(a => !a.show_when || String(row?.[a.show_when]) === a.show_when)
          .map((action) => (
            <Button key={action.label} variant="ghost" size="sm"
              loading={actionLoading === action.label}
              onClick={() => handleAction(action, row)}>
              {action.label}
            </Button>
          ))}
      </div>
    );
  };

  const renderPromptDialog = () => {
    if (!promptAction || !promptAction.prompt_field) return null;
    const pf = promptAction.prompt_field;
    const isSelect = pf.input_type === 'select' && pf.options;
    return (
      <div className="fixed inset-0 z-[70] flex items-center justify-center">
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={closePrompt} />
        <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white">{promptAction.label}</h3>
            <button onClick={closePrompt} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"><X className="w-4 h-4" /></button>
          </div>
          <div className="p-5 space-y-3">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{pf.label}</label>
            {isSelect ? (
              <select value={promptValue} onChange={e => setPromptValue(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm outline-none focus:ring-2 focus:ring-primary-500">
                <option value="">-- 请选择 --</option>
                {pf.options!.map((o: {label: string; value: string}) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (
              <input type={pf.input_type || 'text'} value={promptValue}
                onChange={(e) => setPromptValue(e.target.value)}
                placeholder={pf.placeholder || ''}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
                onKeyDown={(e) => { if (e.key === 'Enter') submitPrompt(); }} autoFocus />
            )}
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" size="sm" onClick={closePrompt}>取消</Button>
              <Button variant="primary" size="sm" onClick={submitPrompt}
                loading={actionLoading === promptAction.label} disabled={!promptValue.trim()}>确定</Button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Unwrap data
  const unwrap = (d: any): any[] | null => {
    if (Array.isArray(d)) return d;
    if (d && typeof d === 'object') {
      if (Array.isArray(d.items)) return d.items;
      if (Array.isArray(d.data)) return d.data;
    }
    return null;
  };

  // ────────────────────────────────────────────────────────────────
  // 加载状态
  // ────────────────────────────────────────────────────────────────

  if (loading) {
    return <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>;
  }
  if (!schema.type) return <p className="text-sm text-gray-400 py-4">UI Schema 缺少 type 字段</p>;
  // Composite & form types don't require api/data at top level
  if (!data && schema.type !== 'form' && schema.type !== 'composite') {
    return <p className="text-sm text-gray-400 py-4">暂无数据</p>;
  }

  const listData = data ? unwrap(data) : null;
  const qs = (extra: Record<string, string> = {}) => '?' + new URLSearchParams({ room_id: String(roomId), ...extra }).toString();

  // ==================================================================
  // Table
  // ==================================================================
  if (schema.type === 'table' && schema.columns) {
    const rows = listData || [];
    return (
      <div className="space-y-3">{renderPromptDialog()}
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          <span className="text-xs text-gray-400">{rows.length} 条</span>
          {renderActions()}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                {schema.columns.map((col) => (
                  <th key={col.key} className="text-left px-3 py-2 text-xs font-medium text-gray-500">{col.label}</th>
                ))}
                {schema.actions && <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">操作</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {rows.length === 0 ? (
                <tr><td colSpan={(schema.columns.length || 1) + (schema.actions ? 1 : 0)} className="px-3 py-4 text-center text-gray-400">暂无数据</td></tr>
              ) : rows.map((row: any, i: number) => (
                <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  {schema.columns!.map((col) => (
                    <td key={col.key} className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      {renderCell(col, row[col.key], row, handleSwitchToggle)}
                    </td>
                  ))}
                  {schema.actions && <td className="px-3 py-2 text-right">{renderActions(row)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ==================================================================
  // List
  // ==================================================================
  if (schema.type === 'list' && schema.columns) {
    const items = listData || [];
    return (
      <div className="space-y-2">{renderPromptDialog()}
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          {renderActions()}
        </div>
        <div className="space-y-1.5">
          {items.map((item: any, i: number) => (
            <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 dark:bg-gray-900">
              <div className="flex items-center gap-3 flex-wrap">
                {schema.columns!.map((col) => renderCell(col, item[col.key], item, handleSwitchToggle))}
              </div>
              {renderActions(item)}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ==================================================================
  // Cards
  // ==================================================================
  if (schema.type === 'cards' && schema.columns) {
    const cards = listData || [];
    return (
      <div className="space-y-3">{renderPromptDialog()}
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          {renderActions()}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {cards.map((item: any, i: number) => (
            <div key={i} className="p-4 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700">
              {schema.columns!.map((col) => (
                <div key={col.key} className="flex justify-between py-0.5">
                  <span className="text-xs text-gray-500">{col.label}</span>
                  {renderCell(col, item[col.key], item, handleSwitchToggle)}
                </div>
              ))}
              <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">{renderActions(item)}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ==================================================================
  // Stats
  // ==================================================================
  if (schema.type === 'stats' && data && !Array.isArray(data) && schema.fields) {
    const stats = data as Record<string, any>;
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {schema.fields.map((field) => (
            <div key={field.key} className="p-4 rounded-lg bg-gray-50 dark:bg-gray-900">
              <p className="text-[10px] text-gray-500 uppercase">{field.label}</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white mt-1">
                {field.format === 'duration'
                  ? `${Math.floor(Number(stats[field.key] || 0) / 60)}分${Number(stats[field.key] || 0) % 60}秒`
                  : field.type && field.type !== 'text'
                  ? renderCell(field, stats[field.key], stats, handleSwitchToggle)
                  : String(stats[field.key] ?? '-')}
              </p>
              {field.subtitle && <p className="text-[10px] text-gray-400 mt-0.5">{field.subtitle}</p>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ==================================================================
  // Playlist
  // ==================================================================
  if (schema.type === 'playlist') {
    const items = listData || [];
    const statsMap: Record<string, number> = {};
    items.forEach((i: any) => { const s = i.status || 'pending'; statsMap[s] = (statsMap[s] || 0) + 1; });

    const toggleSel = (i: number) => { const n = new Set(selected); n.has(i) ? n.delete(i) : n.add(i); setSelected(n); };
    const clearSel = () => setSelected(new Set());
    const batchApi = async (st: string) => {
      for (const i of [...selected].sort((a, b) => b - a))
        await doFetch('/api/plugin/' + pluginName + '/ui/status' + qs(), 'POST', { index: i, status: st });
      clearSel(); await load();
    };
    const showConfirm = (title: string, msg: string, cb: () => void, danger = false) => {
      setConfirmTitle(title); setConfirmMsg(msg); setConfirmDanger(danger);
      setConfirmCallback(() => cb); setConfirmOpen(true);
    };
    const batchDelete = () => {
      showConfirm('批量删除', '确定删除选中的 ' + selected.size + ' 项？', async () => {
        for (const i of [...selected].sort((a, b) => b - a))
          await doFetch('/api/plugin/' + pluginName + '/ui/delete' + qs(), 'POST', { index: i });
        clearSel(); await load();
      }, true);
    };
    const clearAll = () => {
      showConfirm('清空点播单', '确定清空当前直播间的全部点播项吗？此操作不可恢复。', async () => {
        await doFetch('/api/plugin/' + pluginName + '/ui/clear' + qs(), 'POST');
        clearSel(); await load();
      }, true);
    };

    const statusIcons: Record<string, string> = { pending: '⏳', playing: '🎵', working: '🔧', done: '✅' };
    const statusLabels: Record<string, string> = { pending: '待播', playing: '播放中', working: '操作中', done: '已完成' };

    const plSubmitPrompt = async () => {
      if (!promptAction || !promptAction.prompt_field) return;
      setActionLoading(promptAction.label);
      try {
        const token = localStorage.getItem('auth_token');
        const body: Record<string, any> = {};
        body[promptAction.prompt_field.key] = promptValue;
        await fetch(promptAction.url + qs(), {
          method: promptAction.method,
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify(body),
        });
        closePrompt(); await load();
      } catch { /* ignore */ }
      finally { setActionLoading(null); }
    };

    return (
      <div className="space-y-3">
        {/* Toolbar */}
        <div className="flex items-center gap-2 flex-wrap">
          {rooms.length > 1 && (
            <select value={roomId} onChange={e => setRoomId(Number(e.target.value))}
              className="px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
              {rooms.map((r: any) => <option key={r.room_id} value={r.room_id}>{r.room_name} ({r.count}条)</option>)}
            </select>
          )}
          {rooms.length === 1 && <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{rooms[0].room_name}</span>}
          <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={load}>刷新</Button>
          <span className="text-xs text-gray-400">{items.length} 条</span>
          {schema.add_action && (
            <Button variant="primary" size="sm" onClick={() => {
              setPromptAction(schema.add_action!); setPromptValue(''); setPromptRow(null);
            }}>{schema.add_action.label}</Button>
          )}
          {items.length > 0 && (
            <Button variant="ghost" size="sm" icon={<Trash2 />} className="text-red-500!"
              onClick={clearAll}>清空</Button>
          )}
        </div>

        {/* Stats */}
        <div className="flex gap-2 flex-wrap">
          {Object.entries(statusLabels).map(([k, v]) =>
            statsMap[k] ? <span key={k} className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{statusIcons[k]} {v} {statsMap[k]}</span> : null
          )}
        </div>

        {/* Items + batch bar (scrollable container) */}
        <div className="relative max-h-[60vh] overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="space-y-1 p-1 min-h-[120px]">
            {!roomsLoaded ? (
              <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
            ) : rooms.length === 0 ? (
              <p className="text-center text-gray-400 py-8">📭 暂无直播间数据<br /><small className="text-xs">在直播间发送弹幕后将自动出现</small></p>
            ) : items.length === 0 ? (
              <p className="text-center text-gray-400 py-8">📭 点播单为空</p>
            ) : items.map((item: any, i: number) => {
            const st = item.status || 'pending';
            let rowCls = '';
            if (st === 'playing') rowCls = 'border-emerald-400/50 bg-emerald-50/30 dark:bg-emerald-900/10';
            else if (st === 'working') rowCls = 'border-blue-400/50 bg-blue-50/30 dark:bg-blue-900/10';
            else if (st === 'done') rowCls = 'opacity-50';
            let statusCls = 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400';
            if (st === 'playing') statusCls = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400';
            else if (st === 'working') statusCls = 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400';
            else if (st === 'done') statusCls = 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400';
            return (
              <div key={i} className={'flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 ' + rowCls}>
                <input type="checkbox" checked={selected.has(i)} onChange={() => toggleSel(i)}
                  className="w-4 h-4 rounded accent-primary-500 cursor-pointer" />
                <span className="text-xs font-bold text-gray-400 w-7 text-center">#{item.index || i + 1}</span>
                {schema.columns?.map(col => {
                  const spanCls = col.key === 'song_name' ? 'flex-1 text-sm font-medium text-gray-800 dark:text-gray-200' : 'text-xs text-gray-400';
                  return <span key={col.key} className={spanCls}>
                    {col.key === 'status'
                      ? <span className={'text-[10px] font-semibold px-2 py-0.5 rounded-full ' + statusCls}>{statusLabels[st]}</span>
                      : col.type ? renderCell(col, item[col.key], item, handleSwitchToggle)
                      : String(item[col.key] ?? '-')}
                  </span>
                })}
                <div className="flex gap-0.5">
                  {['playing', 'working', 'done', 'pending'].map(s => {
                    const btnCls = 'px-1.5 py-0.5 text-xs rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors' + (s === st ? ' opacity-30 cursor-default' : '');
                    return <button key={s} title={statusLabels[s]} disabled={s === st} className={btnCls}
                      onClick={async () => { if (s === st) return; await doFetch('/api/plugin/' + pluginName + '/ui/status' + qs(), 'POST', { index: i, status: s }); await load(); }}>
                      {statusIcons[s]}</button>
                  })}

                  <button title="删除"
                    className="px-1.5 py-0.5 text-xs rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-colors"
                    onClick={async () => {
                      if (!confirm('确定删除 #' + (item.index || i + 1) + '「' + item.song_name + '」？')) return;
                      await doFetch('/api/plugin/' + pluginName + '/ui/delete' + qs(), 'POST', { index: i });
                      setSelected(prev => { const n = new Set(prev); n.delete(i); return n; }); await load();
                    }}>✕</button>
                </div>
              </div>
            );
          })}
          </div>

          {/* 底部 padding 为批量工具栏预留空间，避免遮挡最后一行 */}
          {selected.size > 0 && <div className="pb-10" />}

          {/* Batch toolbar — 绝对定位在滚动容器底部，不挤压列表项 */}
          <div className={'absolute bottom-0 left-0 right-0 flex items-center gap-2 flex-wrap p-2 border-t border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-800/95 backdrop-blur-sm rounded-b-lg transition-all ' + (selected.size > 0 ? 'opacity-100' : 'opacity-0 pointer-events-none')}>
            <span className="text-xs font-medium text-primary-700 dark:text-primary-300">已选 {selected.size} 项</span>
            <Button variant="ghost" size="sm" onClick={() => batchApi('playing')}>🎵</Button>
            <Button variant="ghost" size="sm" onClick={() => batchApi('working')}>🔧</Button>
            <Button variant="ghost" size="sm" onClick={() => batchApi('done')}>✅</Button>
            <Button variant="ghost" size="sm" onClick={() => batchApi('pending')}>🔄</Button>
            <Button variant="ghost" size="sm" className="text-red-500!" onClick={batchDelete}>🗑️ 删除</Button>
            <Button variant="ghost" size="sm" onClick={clearSel}>取消</Button>
          </div>
        </div>

        {/* Prompt dialog */}
        {promptAction && promptAction.prompt_field && (
          (() => { const pf = promptAction.prompt_field!; return (
            <div className="fixed inset-0 z-[70] flex items-center justify-center">
              <div className="fixed inset-0 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={closePrompt} />
              <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
                <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold text-gray-900 dark:text-white">{promptAction.label}</h3>
                  <button onClick={closePrompt} className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"><X className="w-4 h-4" /></button>
                </div>
                <div className="p-5 space-y-3">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">{pf.label}</label>
                  <input type={pf.input_type || 'text'} value={promptValue} onChange={e => setPromptValue(e.target.value)}
                    placeholder={pf.placeholder || ''}
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
                    onKeyDown={e => { if (e.key === 'Enter') plSubmitPrompt(); }} autoFocus />
                  <div className="flex justify-end gap-2 pt-1">
                    <Button variant="ghost" size="sm" onClick={closePrompt}>取消</Button>
                    <Button variant="primary" size="sm" onClick={plSubmitPrompt} loading={actionLoading === promptAction.label} disabled={!promptValue.trim()}>确定</Button>
                  </div>
                </div>
              </div>
            </div>
          )})()
        )}

        {/* Confirm dialog */}
        {confirmCallback && (
          <ConfirmDialog open={confirmOpen} title={confirmTitle} message={confirmMsg}
            danger={confirmDanger}
            onConfirm={() => { confirmCallback?.(); setConfirmOpen(false); setConfirmCallback(null); }}
            onCancel={() => { setConfirmOpen(false); setConfirmCallback(null); }} />
        )}
      </div>
    );
  }

  // ==================================================================
  // Form
  // ==================================================================
  if (schema.type === 'form' && schema.form_fields) {
    const updateField = (key: string, value: any) => setFormValues(prev => ({ ...prev, [key]: value }));

    const handleSubmit = async () => {
      if (!schema.submit) return;
      setFormSubmitting(true);
      try {
        await doFetch(schema.submit.url, schema.submit.method, formValues);
        // Reset to defaults on success
        const defaults: Record<string, any> = {};
        schema.form_fields!.forEach(f => { defaults[f.key] = f.default ?? (f.type === 'switch' ? false : ''); });
        setFormValues(defaults);
      } catch { /* ignore */ }
      finally { setFormSubmitting(false); }
    };

    const inputCls = "w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white text-sm outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-50";

    return (
      <div className="space-y-4 max-w-lg">
        {schema.form_fields.map(f => (
          <div key={f.key}>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              {f.label}
              {f.required && <span className="text-red-500 ml-0.5">*</span>}
            </label>

            {/* text / password */}
            {(f.type === 'text' || f.type === 'password') && (
              <input type={f.type} value={formValues[f.key] ?? ''} onChange={e => updateField(f.key, e.target.value)}
                placeholder={f.placeholder || ''} required={f.required}
                className={inputCls} />
            )}

            {/* number */}
            {f.type === 'number' && (
              <input type="number" value={formValues[f.key] ?? ''} onChange={e => updateField(f.key, Number(e.target.value))}
                placeholder={f.placeholder || ''} required={f.required}
                className={inputCls} />
            )}

            {/* date */}
            {f.type === 'date' && (
              <input type="date" value={formValues[f.key] ?? ''} onChange={e => updateField(f.key, e.target.value)}
                required={f.required} className={inputCls} />
            )}

            {/* textarea */}
            {f.type === 'textarea' && (
              <textarea value={formValues[f.key] ?? ''} onChange={e => updateField(f.key, e.target.value)}
                placeholder={f.placeholder || ''} rows={f.rows || 3} required={f.required}
                className={inputCls + ' resize-y'} />
            )}

            {/* select */}
            {f.type === 'select' && f.options && (
              <select value={formValues[f.key] ?? ''} onChange={e => updateField(f.key, e.target.value)}
                required={f.required} className={inputCls}>
                <option value="">-- 请选择 --</option>
                {f.options.map((o: {label: string; value: string}) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            )}

            {/* switch */}
            {f.type === 'switch' && (
              <button role="switch" aria-checked={!!formValues[f.key]}
                onClick={() => updateField(f.key, !formValues[f.key])}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 ${
                  formValues[f.key] ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'
                }`}>
                <span className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  formValues[f.key] ? 'translate-x-6' : 'translate-x-1'
                }`} />
              </button>
            )}
          </div>
        ))}

        {schema.submit && (
          <div className="flex justify-end pt-2">
            <Button variant="primary" size="sm" onClick={handleSubmit} loading={formSubmitting}>
              {schema.submit.label}
            </Button>
          </div>
        )}
      </div>
    );
  }

  // ==================================================================
  // Composite —— 多类型复合页面
  // ==================================================================
  if (schema.type === 'composite' && schema.sections) {
    return (
      <div className="space-y-6">
        {schema.sections.map((sec, idx) => (
          <div key={idx}>
            {sec.title && (
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 pb-2 border-b border-gray-200 dark:border-gray-700">
                {sec.title}
              </h3>
            )}
            <PluginUI schema={sec} pluginName={pluginName} />
          </div>
        ))}
      </div>
    );
  }

  // ==================================================================
  // Fallback
  // ==================================================================
  return <p className="text-sm text-gray-400 py-4">不支持的 UI Schema 类型: {schema.type}</p>;
}
