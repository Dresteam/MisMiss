interface Props {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
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
 */
export function Switch({
  checked, onChange, disabled = false, title, label, className = '',
}: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={title}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full
                  transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                  ${checked ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'}
                  ${className}`}>
      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform
                        ${checked ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
    </button>
  );
}
