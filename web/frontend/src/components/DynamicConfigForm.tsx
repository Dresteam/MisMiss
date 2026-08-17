import { useState } from 'react';
import { Save, RotateCcw, Plus, X } from 'lucide-react';
import type { ConfigFieldSchema } from '../api/types';
import { Button } from './Button';

interface Props {
  schema: Record<string, ConfigFieldSchema>;
  values: Record<string, unknown>;
  onSave: (config: Record<string, unknown>) => Promise<void>;
  loading?: boolean;
}

export function DynamicConfigForm({ schema, values, onSave, loading }: Props) {
  const [formValues, setFormValues] = useState<Record<string, unknown>>(() => {
    // Initialize with current values, falling back to defaults
    const init: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(schema)) {
      init[key] = values[key] !== undefined ? values[key] : field.default;
    }
    return init;
  });
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleChange = (key: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [key]: value }));
    // Clear error on change
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const handleSave = async () => {
    // Basic validation
    const newErrors: Record<string, string> = {};
    for (const [key, field] of Object.entries(schema)) {
      if (field.type === 'int' || field.type === 'integer') {
        if (formValues[key] !== undefined && formValues[key] !== null && formValues[key] !== '') {
          const n = Number(formValues[key]);
          if (isNaN(n)) newErrors[key] = '请输入有效整数';
        }
      }
      if (field.type === 'float' || field.type === 'number') {
        if (formValues[key] !== undefined && formValues[key] !== null && formValues[key] !== '') {
          const n = Number(formValues[key]);
          if (isNaN(n)) newErrors[key] = '请输入有效数字';
        }
      }
    }
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    setSaving(true);
    try {
      // Convert types based on schema
      const processed: Record<string, unknown> = {};
      for (const [key, field] of Object.entries(schema)) {
        let val = formValues[key];
        if (field.type === 'int' || field.type === 'integer') {
          val = val === '' || val === undefined || val === null ? 0 : Number(val);
        } else if (field.type === 'float' || field.type === 'number') {
          val = val === '' || val === undefined || val === null ? 0.0 : Number(val);
        } else if (field.type === 'bool' || field.type === 'boolean') {
          val = Boolean(val);
        } else if (field.type === 'array' || field.type === 'list' || field.type === 'template_list') {
          // Ensure array and filter empty entries
          if (Array.isArray(val)) {
            val = val.filter((s: unknown) => typeof s === 'string' && s.trim() !== '');
          } else if (typeof val === 'string') {
            val = val.split('\n').map((s: string) => s.trim()).filter(Boolean);
          } else {
            val = [];
          }
        }
        processed[key] = val;
      }
      await onSave(processed);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    const defaults: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(schema)) {
      defaults[key] = values[key] !== undefined ? values[key] : field.default;
    }
    setFormValues(defaults);
    setErrors({});
  };

  const renderField = (key: string, field: ConfigFieldSchema) => {
    const value = formValues[key];
    const label = field.description || key;
    const error = errors[key];
    const type = (field.type || 'string').toLowerCase();

    // Boolean → Toggle switch
    if (type === 'bool' || type === 'boolean') {
      const isOn = Boolean(value);
      return (
        <div key={key} className="flex items-center justify-between py-2">
          <div className="flex-1 min-w-0 mr-4">
            <p className="text-sm font-medium text-surface-900 dark:text-surface-100">
              {label}
            </p>
            <p className="text-[10px] text-surface-500 mt-0.5">{key}</p>
          </div>
          <button
            type="button"
            onClick={() => handleChange(key, !isOn)}
            className={`toggle ${isOn ? 'toggle-on' : 'toggle-off'}`}
          >
            <span className="toggle-dot" />
          </button>
        </div>
      );
    }

    // Select / dropdown
    if (type === 'select' && field.options) {
      return (
        <div key={key} className="space-y-1.5">
          <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">
            {label}
          </label>
          <p className="text-[10px] text-surface-400">{key}</p>
          <select
            value={String(value ?? '')}
            onChange={(e) => handleChange(key, e.target.value)}
            className="input"
          >
            <option value="">-- 选择 --</option>
            {field.options.map((opt) => (
              <option key={String(opt.value)} value={String(opt.value)}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      );
    }

    // Integer / Float
    if (type === 'int' || type === 'integer' || type === 'float' || type === 'number') {
      return (
        <div key={key} className="space-y-1.5">
          <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">
            {label}
          </label>
          <p className="text-[10px] text-surface-400">{key}</p>
          <input
            type="number"
            value={value === undefined || value === null ? '' : String(value)}
            onChange={(e) => handleChange(key, e.target.value)}
            step={type === 'float' || type === 'number' ? 'any' : '1'}
            className={`input ${error ? 'input-error' : ''}`}
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
      );
    }

    // Array / List → single-line inputs with add/delete
    if (type === 'array' || type === 'list' || type === 'template_list') {
      const arrValue: string[] = Array.isArray(value) ? (value as string[]) : [];
      return (
        <div key={key} className="space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">
                {label}
              </label>
              <p className="text-[10px] text-surface-400">{key}</p>
            </div>
            <button type="button" onClick={() => handleChange(key, [...arrValue, ''])}
              className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded
                         text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20
                         transition-colors">
              <Plus className="w-3 h-3" />添加
            </button>
          </div>
          <div className="space-y-1.5">
            {arrValue.length === 0 && (
              <p className="text-xs text-surface-400 italic">暂无项目</p>
            )}
            {arrValue.map((item, idx) => (
              <div key={idx} className="flex items-center gap-1.5">
                <span className="text-[10px] text-surface-400 w-5 text-right shrink-0">{idx + 1}</span>
                <input type="text" value={item}
                  onChange={(e) => {
                    const next = [...arrValue];
                    next[idx] = e.target.value;
                    handleChange(key, next);
                  }}
                  className="input text-xs flex-1"
                  placeholder={type === 'template_list' ? '模板内容...' : '值...'} />
                <button type="button"
                  onClick={() => {
                    const next = arrValue.filter((_, i) => i !== idx);
                    handleChange(key, next);
                  }}
                  className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // Object → JSON textarea
    if (type === 'object') {
      const strValue = typeof value === 'object' && value !== null
        ? JSON.stringify(value, null, 2)
        : String(value ?? '{}');
      return (
        <div key={key} className="space-y-1.5">
          <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">
            {label}
          </label>
          <p className="text-[10px] text-surface-400">{key}</p>
          <textarea
            value={strValue}
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value);
                handleChange(key, parsed);
                // Clear error on valid JSON
                if (errors[key]) {
                  setErrors((prev) => {
                    const next = { ...prev };
                    delete next[key];
                    return next;
                  });
                }
              } catch {
                // Still update the raw value so user can continue editing
                handleChange(key, e.target.value);
              }
            }}
            rows={6}
            className={`input font-mono text-xs ${errors[key] ? 'input-error' : ''}`}
          />
          {errors[key] && <p className="text-xs text-red-500">{errors[key]}</p>}
        </div>
      );
    }

    // Text (long string)
    if (type === 'text') {
      return (
        <div key={key} className="space-y-1.5">
          <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">
            {label}
          </label>
          <p className="text-[10px] text-surface-400">{key}</p>
          <textarea
            value={String(value ?? '')}
            onChange={(e) => handleChange(key, e.target.value)}
            rows={3}
            className="input"
          />
        </div>
      );
    }

    // Default: String input
    return (
      <div key={key} className="space-y-1.5">
        <label className="block text-sm font-medium text-surface-700 dark:text-surface-300">
          {label}
        </label>
        <p className="text-[10px] text-surface-400">{key}</p>
        <input
          type="text"
          value={String(value ?? '')}
          onChange={(e) => handleChange(key, e.target.value)}
          className="input"
        />
      </div>
    );
  };

  const fields = Object.entries(schema);

  if (fields.length === 0) {
    return (
      <div className="text-center py-8 text-surface-400 text-sm">
        此插件无配置项
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 配置项滚动区 */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-5 pr-1">
        {fields.map(([key, field]) => renderField(key, field))}
      </div>

      {/* 按钮区 —— 固定底部、不悬浮、不遮挡（占独立空间） */}
      <div className="shrink-0 flex items-center gap-2 pt-3 mt-3
                      border-t border-surface-200 dark:border-surface-700">
        <Button variant="primary" size="sm" icon={<Save />}
          onClick={handleSave}
          loading={saving} disabled={loading}>
          {saving ? '保存中...' : '保存配置'}
        </Button>
        <Button variant="ghost" size="sm" icon={<RotateCcw />}
          onClick={handleReset}>重置</Button>
      </div>
    </div>
  );
}
