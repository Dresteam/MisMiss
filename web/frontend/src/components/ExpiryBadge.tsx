import { useEffect, useState } from 'react';
import { clsx } from 'clsx';

interface Props {
  expiresAt: string | null;
  pausedReason?: string | null;
  size?: 'sm' | 'md';
}

/** 账户到期徽标:永久 / 剩余 X 天 / ≤7 天到期提醒 / 已过期(含暂停原因)。 */
export function ExpiryBadge({ expiresAt, pausedReason, size = 'sm' }: Props) {
  // 每分钟重算剩余天数,徽标随时间自动更新,不依赖父组件轮询
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!expiresAt) return;
    const t = setInterval(() => setTick((x) => x + 1), 60000);
    return () => clearInterval(t);
  }, [expiresAt]);
  const cls = clsx(
    'inline-flex items-center gap-1 rounded-full font-medium',
    size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm',
  );

  if (pausedReason === 'expiry') {
    return <span className={clsx(cls, 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400')}>已过期停用</span>;
  }

  if (!expiresAt) {
    return <span className={clsx(cls, 'bg-surface-100 text-surface-600 dark:bg-surface-700 dark:text-surface-400')}>永久</span>;
  }

  const now = Date.now();
  const expires = new Date(expiresAt).getTime();
  const remainMs = expires - now;
  const days = Math.ceil(remainMs / 86400000);

  if (days <= 0) {
    return <span className={clsx(cls, 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400')}>已过期</span>;
  }
  if (days <= 7) {
    return <span className={clsx(cls, 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400')}>{days} 天后到期</span>;
  }
  return <span className={clsx(cls, 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400')}>剩余 {days} 天</span>;
}
