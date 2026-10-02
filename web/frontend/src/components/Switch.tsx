import type { MouseEvent } from 'react';
import { Loader2 } from 'lucide-react';

interface Props {
  checked: boolean;
  /**
   * 状态变化回调。第二个参数是原始点击事件 —— 开关嵌在「整行可点」的容器里时
   * 需要它来 `stopPropagation`，否则会连带触发外层动作。
   */
  onChange: (next: boolean, e: MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  /**
   * 保存中。转圈显示在**旋钮内部**，并自动禁用避免连点。
   *
   * 调用方不要把 spinner 放在开关外面 —— 飘在旁边的转圈既不归属这个控件，
   * 也会把标签与开关的间距撑开、保存前后位置跳动。
   */
  loading?: boolean;
  /** 悬浮提示（浏览器原生，有约 1 秒延迟）。适合放较长说明 */
  title?: string;
  /** 无障碍名称（读屏用），通常与旁边的说明文字一致 */
  label?: string;
  /**
   * 悬停**即时**出现的动作提示气泡，如「点击禁用」。
   * 适合开关旁边没有说明文字、需要当场讲清点下去会发生什么的场景；
   * 旁边已有文字说明时不必传（会显得吵）。
   */
  hint?: string;
  className?: string;
}

/**
 * 开关按钮 —— 二元设置的统一控件。
 *
 * 全站开关共用这一份实现（尺寸 h-6×w-11、开启为 primary-600、旋钮内转圈、
 * 焦点环、悬停气泡），避免各处再手抄一遍 class 而慢慢走样。
 * 调用方负责「点一下即保存」的语义：这里只上报新状态，不发请求。
 *
 * 触摸可用性：视觉 44×24，但用 `after:` 伪元素把点击热区向外扩到约 60×44
 * —— 手机上 24px 高的目标按不准。伪元素绝对定位、不占布局，周围排版不受影响。
 */
export function Switch({
  checked, onChange, disabled = false, loading = false,
  title, label, hint, className = '',
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
      onClick={(e) => onChange(!checked, e)}
      className={`relative group inline-flex h-6 w-11 shrink-0 items-center rounded-full
                  transition-colors duration-200
                  focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2
                  dark:focus:ring-offset-gray-800
                  disabled:cursor-not-allowed disabled:opacity-60
                  after:absolute after:-inset-x-2 after:-inset-y-2.5 after:content-['']
                  ${checked ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'}
                  ${className}`}>
      <span className={`inline-flex items-center justify-center h-4 w-4 rounded-full
                        bg-white shadow-sm transition-transform duration-200
                        ${checked ? 'translate-x-6' : 'translate-x-1'}`}>
        {loading && <Loader2 className="h-2.5 w-2.5 animate-spin text-primary-500" />}
      </span>
      {hint && (
        <span role="tooltip"
          className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 z-50
                     whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                     bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                     opacity-0 group-hover:opacity-100 transition-opacity duration-100">
          {hint}
        </span>
      )}
    </button>
  );
}
