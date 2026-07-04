import { X, BookOpen } from 'lucide-react';
import { MarkdownRenderer } from './MarkdownRenderer';

interface Props {
  open: boolean;
  title: string;
  content: string;
  onClose: () => void;
}

export function ReadmeModal({ open, title, content, onClose }: Props) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in" onClick={onClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col animate-slide-in-up">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 min-w-0">
            <BookOpen className="w-4 h-4 text-gray-500 shrink-0" />
            <h3 className="font-semibold text-gray-900 dark:text-white truncate">{title} · README</h3>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {content ? (
            <MarkdownRenderer content={content} />
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">无 README 文档</p>
          )}
        </div>
      </div>
    </div>
  );
}
