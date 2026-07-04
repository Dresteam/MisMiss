import { RefreshCw, X } from 'lucide-react';
import { Button } from './Button';

interface Props {
  open: boolean;
  name: string;
  oldVersion: string;
  newVersion: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export function UpdateDialog({ open, name, oldVersion, newVersion, onConfirm, onCancel, loading }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 animate-slide-in-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">插件更新</h3>
          <button onClick={onCancel} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700">
            <X className="w-5 h-5" />
          </button>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          发现已安装插件 <strong className="text-gray-900 dark:text-white">{name}</strong> 的新版本：
        </p>
        <div className="flex items-center justify-center gap-3 my-4 py-3 px-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <span className="text-lg text-gray-500 line-through">v{oldVersion}</span>
          <RefreshCw className="w-4 h-4 text-gray-400" />
          <span className="text-lg font-bold text-primary-600 dark:text-primary-400">v{newVersion}</span>
        </div>
        <p className="text-xs text-gray-500">
          将先停止当前插件（如果正在运行），然后覆盖安装新版本。
        </p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" icon={<RefreshCw />}
            onClick={onConfirm} loading={loading}>
            确认更新
          </Button>
        </div>
      </div>
    </div>
  );
}
