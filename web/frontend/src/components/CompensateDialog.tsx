import { useEffect, useMemo, useState } from 'react';
import { CalendarPlus, ChevronDown, ChevronUp, X } from 'lucide-react';
import { Button } from './Button';
import { ConfirmDialog } from './ConfirmDialog';
import { compensateAccounts } from '../api/client';
import type { AccountSummary, CompensateResult } from '../api/types';
import { showToast } from '../hooks/useToast';

interface Props {
  open: boolean;
  accounts: AccountSummary[];
  onClose: () => void;
  /** 补偿完成后通知外部刷新账户列表 */
  onDone: () => void;
}

/** 与内置默认值一致，避免每次都要重新填 */
const DEFAULT_DAYS = 3;

/**
 * 批量补偿时长。
 *
 * 两段式，与其它批量操作一致：先设筛选条件 → 请求 ``dry_run`` 预览 →
 * 二次确认弹窗列出**将要补谁** → 才真正落库。补偿会公开地改变账户到期时间，
 * 误操作代价高，所以宁可多一步。
 */
export function CompensateDialog({ open, accounts, onClose, onDone }: Props) {
  const [days, setDays] = useState(String(DEFAULT_DAYS));
  const [excludeExpired, setExcludeExpired] = useState(false);
  const [excludeActive, setExcludeActive] = useState(false);
  const [overDaysLeft, setOverDaysLeft] = useState('');   // 空 = 不排除
  // 被**取消勾选**的账户 id（默认一个都不排除，即全补）
  const [unpicked, setUnpicked] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<CompensateResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    // 每次打开都回到初始状态，避免上次的选择残留
    setDays(String(DEFAULT_DAYS));
    setExcludeExpired(false);
    setExcludeActive(false);
    setOverDaysLeft('');
    setUnpicked(new Set());
    setPreview(null);
    setListOpen(false);
    setError('');
  }, [open]);

  const limit = overDaysLeft.trim() === '' ? null : Number(overDaysLeft);
  const limitInvalid = limit !== null && (!Number.isInteger(limit) || limit < 0);

  /** 与后端 select_compensation_targets 同规则的前端预演，用于勾选列表 */
  const candidates = useMemo(() => {
    return accounts.filter((a) => {
      if (a.expires_at === null) return false;          // 永久账户不参与
      if (a.expired ? excludeExpired : excludeActive) return false;
      if (limit !== null && !limitInvalid) {
        if (a.days_left === null || a.days_left > limit) return false;
      }
      return true;
    });
  }, [accounts, excludeExpired, excludeActive, limit, limitInvalid]);

  const daysNum = Number(days);
  const daysInvalid = !Number.isInteger(daysNum) || daysNum <= 0;
  const allExcluded = excludeExpired && excludeActive;
  const willCompensate = candidates.filter((a) => !unpicked.has(a.id));
  const canPreview = !daysInvalid && !limitInvalid
    && willCompensate.length > 0;

  const params = (dryRun: boolean) => ({
    days: daysNum,
    exclude_expired: excludeExpired,
    exclude_active: excludeActive,
    exclude_over_days_left: limitInvalid ? null : limit,
    exclude_ids: [...unpicked],
    dry_run: dryRun,
  });

  const runPreview = async () => {
    setBusy(true);
    setError('');
    try {
      setPreview(await compensateAccounts(params(true)));
    } catch (e: any) {
      setError(e.message);
    } finally { setBusy(false); }
  };

  const runApply = async () => {
    setBusy(true);
    try {
      const res = await compensateAccounts(params(false));
      showToast('success', res.message, '');
      setPreview(null);
      onDone();
      onClose();
    } catch (e: any) {
      showToast('error', '补偿失败', e.message);
    } finally { setBusy(false); }
  };

  /** 勾选 = 参与补偿；取消勾选 = 加入排除集合 */
  const togglePick = (id: number) => {
    setUnpicked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  if (!open) return null;

  const rowCls = 'flex items-center justify-between gap-3 py-2';

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
        onClick={onClose} />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full
                      max-w-lg mx-4 animate-slide-in-up max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b
                        border-gray-200 dark:border-gray-700 shrink-0">
          <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <CalendarPlus className="w-4 h-4 text-primary-500" />
            批量补偿时长
          </h3>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4 overflow-y-auto">
          {/* 天数 */}
          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
              每个账户补偿
            </label>
            <div className="flex items-center gap-2">
              <input value={days} onChange={(e) => setDays(e.target.value)}
                inputMode="numeric" className="input w-24" aria-label="补偿天数" />
              <span className="text-sm text-gray-500 dark:text-gray-400">天</span>
              {daysInvalid && <span className="text-xs text-red-500">请输入正整数</span>}
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              从「现在」与「原到期时间」中较晚的那个开始顺延；已过期的账户补完即从今天续上。
            </p>
          </div>

          {/* 排除项：默认全补，这里用来把某些账户剔出去 */}
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5">
              默认补偿全部账户（永久账户除外），以下用于排除。
            </p>
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 divide-y
                            divide-gray-100 dark:divide-gray-700/60 px-3">
              <label className={rowCls + ' cursor-pointer'}>
                <span className="text-sm text-gray-700 dark:text-gray-200">排除已过期</span>
                <input type="checkbox" checked={excludeExpired}
                  onChange={(e) => setExcludeExpired(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 dark:border-gray-600
                             text-primary-600 focus:ring-primary-500" />
              </label>
              <label className={rowCls + ' cursor-pointer'}>
                <span className="text-sm text-gray-700 dark:text-gray-200">排除未过期</span>
                <input type="checkbox" checked={excludeActive}
                  onChange={(e) => setExcludeActive(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 dark:border-gray-600
                             text-primary-600 focus:ring-primary-500" />
              </label>
              <div className={rowCls}>
                <span className="text-sm text-gray-700 dark:text-gray-200">
                  排除剩余天数多于
                  <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">留空则不排除</span>
                </span>
                <div className="flex items-center gap-1.5">
                  <input value={overDaysLeft} onChange={(e) => setOverDaysLeft(e.target.value)}
                    inputMode="numeric" placeholder="不限" aria-label="排除剩余天数多于"
                    className="input w-20 py-1 text-sm" />
                  <span className="text-xs text-gray-400">天</span>
                </div>
              </div>
            </div>
            {limitInvalid && <p className="text-xs text-red-500 mt-1">剩余天数需为非负整数</p>}
          </div>

          {/* 命中预览 + 逐个取消勾选 */}
          <div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-300">
                将补偿 <span className="font-semibold text-gray-900 dark:text-white">
                  {willCompensate.length}</span> 个账户
                {unpicked.size > 0 && <> · 已排除 {unpicked.size} 个</>}
              </span>
              {candidates.length > 0 && (
                <button type="button" onClick={() => setListOpen((v) => !v)}
                  className="flex items-center gap-1 text-xs text-primary-600
                             dark:text-primary-400 hover:underline">
                  {listOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  {listOpen ? '收起' : '逐个查看'}
                </button>
              )}
            </div>
            {candidates.length === 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                {allExcluded
                  ? '「排除已过期」与「排除未过期」同时勾选，没有账户可选了。'
                  : '没有符合当前条件的账户。永久账户无需补偿，不会出现在这里。'}
              </p>
            )}
            {candidates.length > 0 && willCompensate.length === 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                已把全部候选账户取消勾选，没有可补偿的账户。
              </p>
            )}
            {listOpen && candidates.length > 0 && (
              <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border
                              border-gray-200 dark:border-gray-700 divide-y
                              divide-gray-100 dark:divide-gray-700/60">
                <div className="flex items-center justify-between px-3 py-1.5">
                  <button type="button" onClick={() => setUnpicked(new Set())}
                    className="text-[11px] text-primary-600 dark:text-primary-400 hover:underline">全选</button>
                  <button type="button"
                    onClick={() => setUnpicked(new Set(candidates.map((a) => a.id)))}
                    className="text-[11px] text-gray-400 hover:text-red-500 transition-colors">全不选</button>
                </div>
                {candidates.map((a) => (
                  <label key={a.id}
                    className="flex items-center gap-2 px-3 py-1.5 cursor-pointer
                               hover:bg-gray-50 dark:hover:bg-gray-700/40">
                    <input type="checkbox" checked={!unpicked.has(a.id)}
                      onChange={() => togglePick(a.id)}
                      className="h-3.5 w-3.5 rounded border-gray-300 dark:border-gray-600
                                 text-primary-600 focus:ring-primary-500" />
                    <span className="flex-1 truncate text-sm text-gray-700 dark:text-gray-200">
                      {a.name}
                    </span>
                    <span className={`text-[11px] shrink-0 ${a.expired
                      ? 'text-red-500' : 'text-gray-400 dark:text-gray-500'}`}>
                      {a.expired ? '已过期' : `剩 ${a.days_left} 天`}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              默认全部勾选；取消勾选即把该账户排除。
            </p>
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t
                        border-gray-200 dark:border-gray-700 shrink-0">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>取消</Button>
          <Button variant="primary" size="sm" icon={<CalendarPlus className="w-4 h-4" />}
            onClick={runPreview} disabled={!canPreview} loading={busy}>
            预览并补偿
          </Button>
        </div>
      </div>

      {/* 第二段：预览明细确认 */}
      <ConfirmDialog
        open={!!preview}
        title="确认批量补偿"
        message={preview?.message ?? ''}
        variant="warning"
        confirmLabel="确认补偿"
        loading={busy}
        onConfirm={runApply}
        onCancel={() => setPreview(null)}
      >
        {preview && preview.groups.length > 0 && (
          <div className="mt-3 max-h-52 overflow-y-auto rounded-lg border
                          border-gray-200 dark:border-gray-700 divide-y
                          divide-gray-100 dark:divide-gray-700/60">
            {preview.groups.map((g) => (
              <div key={g.label} className="px-3 py-2">
                <p className="text-xs font-medium text-gray-700 dark:text-gray-200">
                  {g.label}（{g.items.length}）
                </p>
                <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 break-all">
                  {g.items.join('、')}
                </p>
              </div>
            ))}
          </div>
        )}
        {preview && preview.skipped.length > 0 && (
          <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500 break-all">
            跳过：{preview.skipped.join('、')}
          </p>
        )}
      </ConfirmDialog>
    </div>
  );
}
