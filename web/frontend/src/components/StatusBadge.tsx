import { clsx } from 'clsx';

interface Props {
  status: 'online' | 'offline' | 'enabled' | 'disabled' | 'error' | 'warning';
  label?: string;
  pulse?: boolean;
  size?: 'sm' | 'md';
}

const styles: Record<Props['status'], { dot: string; text: string; bg: string }> = {
  online: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-400',
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
  },
  offline: {
    dot: 'bg-surface-400',
    text: 'text-surface-600 dark:text-surface-400',
    bg: 'bg-surface-100 dark:bg-surface-700',
  },
  enabled: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-400',
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
  },
  disabled: {
    dot: 'bg-surface-400',
    text: 'text-surface-600 dark:text-surface-400',
    bg: 'bg-surface-100 dark:bg-surface-700',
  },
  error: {
    dot: 'bg-red-500',
    text: 'text-red-700 dark:text-red-400',
    bg: 'bg-red-100 dark:bg-red-900/40',
  },
  warning: {
    dot: 'bg-amber-500',
    text: 'text-amber-700 dark:text-amber-400',
    bg: 'bg-amber-100 dark:bg-amber-900/40',
  },
};

const labels: Record<Props['status'], string> = {
  online: '在线',
  offline: '离线',
  enabled: '已启用',
  disabled: '已禁用',
  error: '错误',
  warning: '警告',
};

export function StatusBadge({ status, label, pulse, size = 'md' }: Props) {
  const s = styles[status];
  const sizeCls = size === 'sm' ? 'text-[10px] px-1.5 py-0' : 'text-xs px-2.5 py-0.5';

  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full font-medium', sizeCls, s.bg, s.text)}>
      <span
        className={clsx(
          'inline-block rounded-full',
          size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2',
          s.dot,
          pulse && 'animate-pulse-dot',
        )}
      />
      {label || labels[status]}
    </span>
  );
}
