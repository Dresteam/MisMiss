import { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';

type ButtonVariant = 'primary' | 'secondary' | 'destructive' | 'success' | 'ghost' | 'outline';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
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
          'inline-flex items-center justify-center font-medium rounded-lg',
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
      </button>
    );
  },
);

Button.displayName = 'Button';
