import { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { Button } from './Button';

interface Props {
  open: boolean;
  pluginName: string;
  /** 三个选项都默认不勾选，且每次打开都会重置回不勾选 */
  onConfirm: (
    deleteConfig: boolean,
    deleteData: boolean,
    deletePersistent: boolean,
  ) => Promise<void>;
  onCancel: () => void;
  loading?: boolean;
}

/**
 * 卸载确认对话框。
 *
 * 外壳在关闭时直接不渲染，内层因此会在每次打开时**重新挂载**——勾选状态自然归零。
 * 这些选项都是不可撤销的，不该沿用上一次的选择；把重置做在组件内部（而不是要求
 * 调用方条件渲染），任何调用方都不会踩到「状态残留」的坑。
 */
export function UninstallDialog(props: Props) {
  if (!props.open) return null;
  return <UninstallDialogBody {...props} />;
}

function UninstallDialogBody({ pluginName, onConfirm, onCancel, loading }: Props) {
  const [deleteConfig, setDeleteConfig] = useState(false);
  const [deleteData, setDeleteData] = useState(false);
  const [deletePersistent, setDeletePersistent] = useState(false);

  const anyChecked = deleteConfig || deleteData || deletePersistent;

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
            <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              插件源码副本会被删除。以下数据默认保留，勾选后一并清除且不可撤销。
            </p>
            {anyChecked && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400 font-medium">
                此操作不可撤销！
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 space-y-3 px-14">
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={deleteConfig}
              onChange={(e) => setDeleteConfig(e.target.checked)}
              className="mt-0.5 rounded text-primary-600 focus:ring-primary-500" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">删除配置文件</p>
              <p className="text-[11px] text-gray-500">
                移除本账户 <span className="font-mono">config/</span>、
                <span className="font-mono">permissions/</span> 下的配置与权限文件
              </p>
            </div>
          </label>
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={deleteData}
              onChange={(e) => setDeleteData(e.target.checked)}
              className="mt-0.5 rounded text-primary-600 focus:ring-primary-500" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">删除插件数据</p>
              <p className="text-[11px] text-gray-500">
                移除插件通过 <span className="font-mono">self.data</span> 创建的
                <span className="font-mono"> .json </span>数据（如签到记录、点播单、幸运值统计）
              </p>
            </div>
          </label>
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={deletePersistent}
              onChange={(e) => setDeletePersistent(e.target.checked)}
              className="mt-0.5 rounded text-primary-600 focus:ring-primary-500" />
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">删除持久化数据</p>
              <p className="text-[11px] text-gray-500">
                移除插件数据目录中<strong className="font-semibold">其他</strong>文件——插件自带或自行
                创建的非<span className="font-mono"> .json </span>文件（如缓存、数据库、日志）
              </p>
            </div>
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="destructive"
            onClick={() => onConfirm(deleteConfig, deleteData, deletePersistent)}
            loading={loading}>确认卸载</Button>
        </div>
      </div>
    </div>
  );
}
