import { Loader2 } from 'lucide-react';

interface Props {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  /**
   * 保存中。转圈显示在**旋钮内部**，并自动禁用避免连点。
   *
   * 调用方不要把 spinner 放在开关外面 —— 飘在旁边的转圈既不归属这个控件，
   * 也会把标签与开关的间距撑开、保存前后位置跳动。
   */
  loading?: boolean;
  /** 悬浮提示；开关本身没有文字，建议传 */
  title?: string;
  /** 无障碍名称（读屏用），通常与旁边的说明文字一致 */
  label?: string;
  className?: string;
}

/**
 * 开关按钮 —— 二元设置的统一控件。
 *
 * 全站的开关都用同一套尺寸与配色（h-5 w-9，开启为 primary-600），
 * 避免各处再手抄一遍 class。调用方负责「点一下即保存」的语义：
 * 这里只上报新状态，不发请求。
 *
 * 触摸可用性：视觉仍是 36×20，但用 `after:` 伪元素把点击热区向外扩到
 * 52×44 —— 手机上 20px 高的目标按不准。伪元素是绝对定位，不占布局，
 * 所以周围排版一个像素都不会动。
 */
export function Switch({
  checked, onChange, disabled = false, loading = false, title, label, className = '',
}: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-busy={loading}
      aria-label={label}
      title={title}
      disabled={disabled || loading}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full
                  transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                  after:absolute after:-inset-x-2 after:-inset-y-3 after:content-['']
                  ${checked ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'}
                  ${className}`}>
      <span className={`inline-flex items-center justify-center h-3.5 w-3.5 rounded-full
                        bg-white shadow-sm transition-transform
                        ${checked ? 'translate-x-[18px]' : 'translate-x-[3px]'}`}>
        {loading && <Loader2 className="h-2.5 w-2.5 animate-spin text-primary-600" />}
      </span>
    </button>
  );
}
