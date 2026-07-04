import { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { Button } from './Button';

interface Props {
  open: boolean;
  pluginName: string;
  onConfirm: (deleteConfig: boolean, deleteData: boolean) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

export function UninstallDialog({ open, pluginName, onConfirm, onCancel, loading }: Props) {
  const [deleteConfig, setDeleteConfig] = useState(false);
  const [deleteData, setDeleteData] = useState(false);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onCancel} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 animate-slide-in-up">
        <div className="flex items-start gap-4">
          <div className="shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              卸载 "{pluginName}"
            </h3>
            {(deleteConfig || deleteData) && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400 font-medium">
                此操作不可撤销！
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 space-y-3 px-14">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={deleteConfig}
              onChange={(e) => setDeleteConfig(e.target.checked)}
              className="rounded text-primary-600 focus:ring-primary-500" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">删除配置文件</p>
              <p className="text-[11px] text-gray-500">移除 data/config/ 下的配置 JSON 文件</p>
            </div>
          </label>
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={deleteData}
              onChange={(e) => setDeleteData(e.target.checked)}
              className="rounded text-primary-600 focus:ring-primary-500" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">删除持久化数据</p>
              <p className="text-[11px] text-gray-500">移除 data/plugins/ 下的插件数据目录</p>
            </div>
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="destructive"
            onClick={() => onConfirm(deleteConfig, deleteData)}
            loading={loading}>确认卸载</Button>
        </div>
      </div>
    </div>
  );
}
