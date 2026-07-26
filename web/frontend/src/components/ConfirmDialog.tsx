import { X } from 'lucide-react';
import { Button, type ButtonVariant } from './Button';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'primary' | 'danger' | 'warning' | 'default';
  danger?: boolean;           // deprecated, kept for backward compat
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 通用确认对话框组件。
 *
 * 插件可在任意位置直接引用：
 * ```tsx
 * import { ConfirmDialog } from '../components/ConfirmDialog';
 * <ConfirmDialog open={show} title="确认删除" message="此操作不可恢复"
 *   danger onConfirm={handleDelete} onCancel={() => setShow(false)} />
 * ```
 */
export function ConfirmDialog({
  open, title, message, confirmLabel = '确定', cancelLabel = '取消',
  variant = 'default', danger = false, loading = false, onConfirm, onCancel,
}: ConfirmDialogProps) {
  const btnVariant = (
    danger ? 'danger' :
    variant && variant !== 'default' ? variant :
    'primary'
  ) as ButtonVariant;
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-sm mx-4 animate-slide-in-up">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white">{title}</h3>
          <button onClick={onCancel}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-600 dark:text-gray-400">{message}</p>
        </div>
        <div className="flex justify-end gap-2 px-5 pb-4">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>{cancelLabel}</Button>
          <Button variant={btnVariant} size="sm" onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
