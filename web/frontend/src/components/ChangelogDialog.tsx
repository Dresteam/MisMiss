import { X, ScrollText } from 'lucide-react';
import { MarkdownRenderer } from './MarkdownRenderer';

interface Props {
  open: boolean;
  /** 版本号(不含 v 前缀) */
  version: string;
  /** 弹窗标题;缺省为「v{version} 更新日志」 */
  title?: string;
  /** 标题下的小字元信息(如发布日期) */
  meta?: string;
  /** 更新日志 Markdown 正文 */
  body: string;
  onClose: () => void;
}

/**
 * 更新日志弹框 —— 展示单个版本的完整更新日志。
 *
 * 两处复用:程序更新页的「查看日志」、更新后登录时的自动弹出。
 */
export function ChangelogDialog({ open, version, title, meta, body, onClose }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col animate-slide-in-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 min-w-0">
            <ScrollText className="w-4 h-4 text-gray-500 shrink-0" />
            <h3 className="font-semibold text-gray-900 dark:text-white truncate">
              {title || `v${version} 更新日志`}
            </h3>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {meta && <p className="text-xs text-gray-400 font-mono mb-3">{meta}</p>}
          {body ? (
            <MarkdownRenderer content={body} />
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">无更新日志</p>
          )}
        </div>
        <div className="flex justify-end px-6 py-4 border-t border-gray-200 dark:border-gray-700">
          <button onClick={onClose}
            className="px-4 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium transition-colors">
            我知道了
          </button>
        </div>
      </div>
    </div>
  );
}
