import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

/** 面板筛选条件的本地持久化前缀 —— 与业务数据无关，只存 UI 偏好。 */
const PREFIX = 'mismiss.filters.';

/**
 * 与 ``useState`` 用法一致的持久化状态，值写入 ``sessionStorage``。
 *
 * 为什么用 sessionStorage 而不是 URL：
 * - 筛选条件是页面临时偏好，不需要出现在地址栏里被分享/收藏；
 * - 同一个标签页内前进/后退、点侧栏切走再回来都能恢复；
 * - 每个标签页独立，不会出现两个窗口互相覆盖筛选条件。
 *
 * 值必须能 JSON 序列化（字符串/数组/对象/布尔/数字）。存储不可用（隐私模式、
 * 配额满）时静默退化为普通 state，不影响页面功能。
 */
export function usePersistedState<T>(
  key: string,
  initial: T,
): [T, Dispatch<SetStateAction<T>>] {
  const storageKey = PREFIX + key;
  const [value, setValue] = useState<T>(() => {
    if (typeof window === 'undefined') return initial;
    try {
      const raw = window.sessionStorage.getItem(storageKey);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      /* 隐私模式或配额满：保持内存态即可 */
    }
  }, [storageKey, value]);

  return [value, setValue];
}
