import { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';

export type ButtonVariant = 'primary' | 'secondary' | 'destructive' | 'danger' | 'warning' | 'success' | 'ghost' | 'outline';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
  /** 自定义悬浮提示文字，显示在按钮上方，主题自适应 */
  tooltip?: string;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800 ' +
    'focus:ring-primary-500',
  secondary:
    'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 ' +
    'hover:bg-gray-300 dark:hover:bg-gray-600 focus:ring-gray-400',
  destructive:
    'bg-red-600 text-white hover:bg-red-700 active:bg-red-800 ' +
    'focus:ring-red-500',
  danger:
    'bg-red-600 text-white hover:bg-red-700 active:bg-red-800 ' +
    'focus:ring-red-500',
  warning:
    'bg-amber-500 text-white hover:bg-amber-600 active:bg-amber-700 ' +
    'focus:ring-amber-500',
  success:
    'bg-emerald-600 text-white hover:bg-emerald-700 active:bg-emerald-800 ' +
    'focus:ring-emerald-500',
  ghost:
    'bg-transparent text-gray-600 dark:text-gray-400 ' +
    'hover:bg-gray-100 dark:hover:bg-gray-800 focus:ring-gray-400',
  outline:
    'bg-transparent text-gray-700 dark:text-gray-300 ' +
    'border border-gray-300 dark:border-gray-600 ' +
    'hover:bg-gray-50 dark:hover:bg-gray-800 focus:ring-gray-400',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-9 px-4 text-sm gap-2',
  lg: 'h-10 px-6 text-base gap-2',
};

const iconSizes: Record<ButtonSize, string> = {
  sm: 'h-3.5 w-3.5 [&_svg]:h-full [&_svg]:w-full',
  md: 'h-4 w-4 [&_svg]:h-full [&_svg]:w-full',
  lg: 'h-4 w-4 [&_svg]:h-full [&_svg]:w-full',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      loading = false,
      icon,
      children,
      className = '',
      disabled,
      tooltip,
      ...props
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={[
          'relative group inline-flex items-center justify-center font-medium rounded-lg',
          'transition-all duration-200',
          'focus:outline-none focus:ring-2 focus:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          variantStyles[variant],
          sizeStyles[size],
          className,
        ].join(' ')}
        {...props}
      >
        {loading ? (
          <Loader2 className={`${iconSizes[size]} animate-spin shrink-0`} />
        ) : icon ? (
          <span className={`${iconSizes[size]} shrink-0`}>{icon}</span>
        ) : null}
        {children && <span>{children}</span>}
        {tooltip && !isDisabled && (
          <span
            role="tooltip"
            className="pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 z-50
                       whitespace-nowrap px-2 py-1 rounded-md text-[11px] font-medium
                       bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg
                       opacity-0 group-hover:opacity-100 transition-opacity duration-100"
          >
            {tooltip}
          </span>
        )}
      </button>
    );
  },
);

Button.displayName = 'Button';
